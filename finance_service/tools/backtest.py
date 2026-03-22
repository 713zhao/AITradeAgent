#!/usr/bin/env python3
"""
Backtest Runner - Validates trading strategies against historical data.

Usage:
    python -m finance_service.tools.backtest \
        --symbols AAPL NVDA MSFT \
        --start-date 2024-01-01 \
        --end-date 2024-12-31 \
        --output results.json
"""

import argparse
import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import pandas as pd
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from finance_service.core.yaml_config import YAMLConfigEngine
from finance_service.agents.data_agent import DataAgent
from finance_service.agents.analysis_agent import AnalysisAgent
from finance_service.agents.strategy_agent import RuleStrategy, RuleType, Rule
from finance_service.portfolio.trade_repository import TradeRepository
from finance_service.portfolio.models import TradeStatus
from finance_service.storage import get_backtest_db
from finance_service.core.event_bus import EventBus

logger = logging.getLogger(__name__)


class BacktestRunner:
    """Runs backtests for trading strategies"""
    
    def __init__(
        self,
        config_engine: YAMLConfigEngine,
        initial_capital: float = 100000.0,
        commission: float = 0.001,  # 0.1% per trade
        slippage: float = 0.001,    # 0.1% slippage
        strategy_name: Optional[str] = None,
    ):
        self.config_engine = config_engine
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.strategy_name = strategy_name
        
        self.data_agent = DataAgent(config_engine)
        # Build extended periods dict to include SMA10 and SMA30 for crossover
        periods = {
            'rsi': 14,
            'macd_fast': 12,
            'macd_slow': 26,
            'macd_signal': 9,
            'sma': [10, 20, 30, 50, 200],
            'ema': [12, 26],
            'atr': 14,
            'bb_period': 20,
            'bb_std': 2.0,
            'stoch_k': 14,
            'stoch_d': 3,
        }
        self.analysis_agent = AnalysisAgent(periods)
        
        event_bus = EventBus()
        self.data_agent.event_bus = event_bus
        self.analysis_agent.event_bus = event_bus
        
        # Load multiple strategies from config
        self.strategies: Dict[str, Dict] = {}
        strategies_cfg = config_engine.get("finance", "strategies", default={})
        if isinstance(strategies_cfg, dict):
            for name, strat_cfg in strategies_cfg.items():
                if not isinstance(strat_cfg, dict):
                    continue
                entry_rules = strat_cfg.get('entry_rules', [])
                exit_rules = strat_cfg.get('exit_rules', [])
                all_rules = entry_rules + exit_rules
                rule_strategy = RuleStrategy(all_rules)
                self.strategies[name] = {
                    'rule_strategy': rule_strategy,
                    'allocation': float(strat_cfg.get('allocation', 1.0)),
                    'risk_budget_pct': float(strat_cfg.get('risk_budget_pct', 1.0)),
                    'confidence_threshold': float(strat_cfg.get('confidence_threshold', 0.5))
                }
                logger.info(f"Backtest: loaded strategy '{name}' allocation={strat_cfg.get('allocation')} risk_budget={strat_cfg.get('risk_budget_pct')}%")
        
        if not self.strategies:
            # Fallback to default
            default_rules = [
                Rule(name="rsi_oversold", type=RuleType.ENTRY, indicator="rsi", condition="less_than", value=35, enabled=True),
                Rule(name="macd_bullish", type=RuleType.ENTRY, indicator="macd", condition="greater_than", value=0, enabled=True),
                Rule(name="rsi_high", type=RuleType.EXIT, indicator="rsi", condition="greater_than", value=60, enabled=True)
            ]
            self.strategies['default'] = {
                'rule_strategy': RuleStrategy([r.__dict__ for r in default_rules]),
                'allocation': 1.0,
                'risk_budget_pct': 1.0,
                'confidence_threshold': 0.5
            }
        
        # If specific strategy requested, filter to only that one
        if self.strategy_name:
            if self.strategy_name in self.strategies:
                self.strategies = {self.strategy_name: self.strategies[self.strategy_name]}
                logger.info(f"Using only strategy: {self.strategy_name}")
            else:
                available = ", ".join(self.strategies.keys())
                raise ValueError(f"Strategy '{self.strategy_name}' not found. Available: {available}")
        
        self.selected_strategy_name = self.strategy_name if self.strategy_name else (next(iter(self.strategies.keys())) if self.strategies else "default")
        
        self.repository = TradeRepository(use_db=False)
        self.current_cash = initial_capital
        self.equity_curve: List[Dict[str, Any]] = []
        self.trade_log: List[Dict[str, Any]] = []
        self.next_trade_id = 1
        
        logger.info(f"BacktestRunner: ${initial_capital:,.2f} capital, commission={commission*100:.2f}%, slippage={slippage*100:.2f}%")
    
    def _execute_buy(self, symbol: str, quantity: float, price: float, confidence: float, rules: List[str]) -> bool:
        task_id = f"BT_{self.next_trade_id}"; self.next_trade_id += 1
        try:
            trade = self.repository.create_trade(
                task_id=task_id, symbol=symbol, side="BUY", quantity=quantity, price=price,
                decision={"confidence": confidence, "rules": rules}, confidence=confidence, reason="Backtest entry"
            )
            pos = self.repository.get_position(symbol)
            if pos:
                new_qty = pos.quantity + quantity
                new_cost = (pos.avg_cost * pos.quantity + price * quantity) / new_qty
                self.repository.update_position(symbol, quantity=new_qty, avg_cost=new_cost, add_trade=trade.trade_id)
            else:
                self.repository.create_position(symbol, quantity=quantity, avg_cost=price, trades=[trade.trade_id])
            self.repository.update_trade_status(trade.trade_id, TradeStatus.FILLED, filled_quantity=quantity, executed_by="backtest")
            return True
        except Exception as e:
            logger.error(f"Buy failed: {e}"); return False
    
    def _execute_sell(self, symbol: str, quantity: float, price: float, rules: List[str]) -> bool:
        task_id = f"BT_{self.next_trade_id}"; self.next_trade_id += 1
        try:
            trade = self.repository.create_trade(
                task_id=task_id, symbol=symbol, side="SELL", quantity=quantity, price=price,
                decision={"rules": rules}, confidence=0.7, reason="Backtest exit"
            )
            pos = self.repository.get_position(symbol)
            if pos:
                new_qty = pos.quantity - quantity
                if new_qty <= 0:
                    self.repository.close_position(symbol)
                else:
                    self.repository.update_position(symbol, quantity=new_qty, add_trade=trade.trade_id)
            else:
                self.repository.create_position(symbol, quantity=-quantity, avg_cost=price, trades=[trade.trade_id])
            self.repository.update_trade_status(trade.trade_id, TradeStatus.FILLED, filled_quantity=quantity, executed_by="backtest")
            return True
        except Exception as e:
            logger.error(f"Sell failed: {e}"); return False
    
    def _compute_news_sentiment_proxy(self, df: pd.DataFrame, lookback_days: int = 5, threshold: float = 0.03) -> pd.Series:
        """
        Compute a simulated news sentiment proxy based on past returns (momentum).
        Positive past returns → positive sentiment; negative → negative.
        Returns a pandas Series aligned to df.index with values in [-1, 1].
        """
        if 'close' not in df.columns:
            logger.warning("No 'close' column for sentiment proxy; returning empty Series")
            return pd.Series(index=df.index, data=0.0)
        close = df['close']
        # Compute past return over lookback_days (non-lookahead)
        past_ret = close / close.shift(lookback_days) - 1.0
        # Map to sentiment
        def map_sentiment(ret):
            if pd.isna(ret):
                return None
            if ret > threshold:
                return 1.0
            elif ret < -threshold:
                return -1.0
            else:
                # Linear scale between -threshold and +threshold to [-1,1]
                return float(ret / threshold)
        sentiment = past_ret.apply(map_sentiment)
        return sentiment
    
    async def fetch_historical_data(self, symbol: str, start_date: datetime, end_date: datetime, interval: str = "1d", extra_days: int = 0) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        logger.info(f"Fetching {symbol} from {start_date.date()} to {end_date.date()}")
        # Fetch extended history for indicator warm-up (need at least 200 days prior to start_date)
        warmup_days = 500
        extended_start = start_date - timedelta(days=warmup_days)
        extended_end = end_date + timedelta(days=extra_days)
        report = await self.data_agent.run(
            symbol=symbol,
            start_date=extended_start.strftime("%Y-%m-%d"),
            end_date=extended_end.strftime("%Y-%m-%d"),
            interval=interval,
            use_cache=False
        )
        if report.status != "success" or "dataframe" not in report.payload:
            raise ValueError(f"Failed to fetch {symbol}: {report.message}")
        df_dict = report.payload["dataframe"]
        fundamentals = report.payload.get("fundamentals", {})
        df = pd.DataFrame.from_dict(df_dict)
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        if len(df) < 200:
            raise ValueError(f"Insufficient history for {symbol}: only {len(df)} bars (need >=200 for indicators)")
        logger.info(f"Fetched {len(df)} bars for {symbol} (with warmup)")
        return df, fundamentals
    
    async def run_backtest(self, symbols: List[str], start_date: datetime, end_date: datetime, progress_callback=None) -> Dict[str, Any]:
        logger.info(f"Starting backtest: {len(symbols)} symbols, {start_date.date()} to {end_date.date()}")
        
        # Fetch data
        all_data: Dict[str, pd.DataFrame] = {}
        fundamentals_store: Dict[str, Dict[str, Any]] = {}
        for i, sym in enumerate(symbols):
            if progress_callback: progress_callback(f"Fetching {sym} ({i+1}/{len(symbols)})")
            try:
                # Fetch extra days for forward-looking sentiment proxy (enough to cover 5 trading days)
                df, fundamentals = await self.fetch_historical_data(sym, start_date, end_date, extra_days=14)
                if len(df) >= 200:
                    all_data[sym] = df
                    fundamentals_store[sym] = fundamentals
                else:
                    logger.warning(f"Insufficient data for {sym}: only {len(df)} bars")
            except Exception as e:
                logger.error(f"Failed to fetch {sym}: {e}")
        
        if not all_data:
            raise ValueError("No data available for backtest")
        
        # Determine simulation trading dates from first symbol, restricted to [start_date, end_date]
        first_df = all_data[list(all_data.keys())[0]]
        trading_dates = first_df.index[(first_df.index >= pd.Timestamp(start_date)) & (first_df.index <= pd.Timestamp(end_date))]
        logger.info(f"Backtest simulation: {len(trading_dates)} trading days")
        
        # Reset simulation state
        self.repository = TradeRepository(use_db=False)
        self.current_cash = self.initial_capital
        self.equity_curve = []
        self.trade_log = []
        self.next_trade_id = 1
        
        # Precompute simulated news sentiment (proxy using past returns)
        sentiment_store = {}
        for sym, df in all_data.items():
            sentiment_store[sym] = self._compute_news_sentiment_proxy(df, lookback_days=5, threshold=0.03)
            logger.debug(f"Computed news sentiment proxy for {sym}")
        
        for i, date in enumerate(trading_dates):
            if progress_callback and i % 20 == 0:
                progress_callback(f"Day {i+1}/{len(trading_dates)} - {date.date()}")
            
            # Update position prices for equity calculation
            prices = {}
            for sym in self.repository.positions:
                if sym in all_data and date in all_data[sym].index:
                    prices[sym] = all_data[sym].loc[date, "close"]
            self.repository.update_position_prices(prices)
            
            # Entry scan: evaluate all strategies for each symbol without position
            for sym in symbols:
                if sym in self.repository.positions or sym not in all_data:
                    continue
                df = all_data[sym]
                if date not in df.index: continue
                idx = df.index.get_loc(date)
                if idx < 200: continue
                
                lookback = df.iloc[idx-199:idx+1].copy()
                try:
                    fundamentals = fundamentals_store.get(sym, {}).copy()
                    # Inject simulated news sentiment for this date
                    sent_series = sentiment_store.get(sym)
                    if sent_series is not None and date in sent_series.index:
                        sent_val = sent_series.loc[date]
                        if pd.notna(sent_val):
                            fundamentals['news_sentiment'] = float(sent_val)
                    indicators = self.analysis_agent._calculate_all(lookback, sym, fundamentals)
                    indicators.current_price = lookback.iloc[-1]["close"]
                    indicators.symbol = sym
                except Exception as e:
                    logger.debug(f"Indicator calc failed for {sym} on {date}: {e}"); continue
                
                # Evaluate all strategies; pick highest confidence that meets threshold
                best_strategy = None
                best_confidence = 0.0
                best_rules = []
                for strat_name, strat_cfg in self.strategies.items():
                    should_buy, confidence, entry_rules = strat_cfg['rule_strategy'].evaluate_entry(indicators)
                    threshold = strat_cfg['confidence_threshold']
                    if should_buy and confidence >= threshold and confidence > best_confidence:
                        best_strategy = strat_name
                        best_confidence = confidence
                        best_rules = entry_rules
                
                if best_strategy is None:
                    continue
                
                # Position sizing: risk amount = current_equity * strategy_allocation * risk_budget_pct
                total_equity = self.current_cash + sum(pos.quantity * indicators.current_price for pos in self.repository.positions.values() if pos.symbol in all_data and date in all_data[pos.symbol].index)
                strat = self.strategies[best_strategy]
                allocation = strat['allocation']
                risk_budget_pct = strat['risk_budget_pct']
                risk_amount = total_equity * allocation * (risk_budget_pct / 100.0)
                
                # ATR-based stop distance
                atr = indicators.indicators.get("atr").value if "atr" in indicators.indicators else indicators.current_price * 0.02
                risk_per_share = atr * 2
                if risk_per_share <= 0: continue
                
                quantity = max(1, int(risk_amount / risk_per_share))
                # Also limit by available cash (max 20% of cash for any trade)
                max_cash_qty = int(self.current_cash * 0.20 / indicators.current_price)
                quantity = min(quantity, max_cash_qty)
                if quantity <= 0: continue
                
                exec_price = indicators.current_price * (1 + self.slippage)
                total_cost = quantity * exec_price * (1 + self.commission)
                if total_cost > self.current_cash:
                    quantity = int(self.current_cash / (exec_price * (1 + self.commission)))
                    if quantity <= 0: continue
                    total_cost = quantity * exec_price * (1 + self.commission)
                
                if self._execute_buy(sym, quantity, exec_price, best_confidence, best_rules):
                    self.current_cash -= total_cost
                    self.trade_log.append({
                        "date": date.isoformat(),
                        "symbol": sym,
                        "action": "BUY",
                        "quantity": quantity,
                        "price": exec_price,
                        "confidence": best_confidence,
                        "strategy": best_strategy,
                        "rules_triggered": best_rules
                    })
            
            # Exit scan: any strategy exit signal OR stop-loss triggers sells the position
            for sym, pos in list(self.repository.positions.items()):
                if sym not in all_data: continue
                df = all_data[sym]
                if date not in df.index: continue
                idx = df.index.get_loc(date)
                if idx < 200: continue
                
                lookback = df.iloc[idx-199:idx+1].copy()
                try:
                    fundamentals = fundamentals_store.get(sym, {}).copy()
                    # Inject simulated news sentiment for this date
                    sent_series = sentiment_store.get(sym)
                    if sent_series is not None and date in sent_series.index:
                        sent_val = sent_series.loc[date]
                        if pd.notna(sent_val):
                            fundamentals['news_sentiment'] = float(sent_val)
                    indicators = self.analysis_agent._calculate_all(lookback, sym, fundamentals)
                    indicators.current_price = lookback.iloc[-1]["close"]
                    indicators.symbol = sym
                except Exception as e:
                    logger.debug(f"Indicator calc failed for exit {sym}: {e}"); continue
                
                current_price = indicators.current_price
                # Check stop-loss (2x ATR below entry) if ATR available
                should_sell = False
                exit_rules_triggered = []
                exit_strategy = None
                
                atr_ind = indicators.indicators.get("atr")
                if atr_ind:
                    atr_value = atr_ind.value
                    stop_price = pos.avg_cost - (atr_value * 2)
                    if current_price <= stop_price:
                        should_sell = True
                        exit_strategy = "stop_loss"
                        exit_rules_triggered = [f"stop_loss@2xATR (stop={stop_price:.2f}, price={current_price:.2f})"]
                    # Check take-profit (3x ATR above entry) - only if not already selling
                    if not should_sell:
                        take_profit_price = pos.avg_cost + (atr_value * 3)
                        if current_price >= take_profit_price:
                            should_sell = True
                            exit_strategy = "take_profit"
                            exit_rules_triggered = [f"take_profit@3xATR (tp={take_profit_price:.2f}, price={current_price:.2f})"]
                
                # Check strategy exit rules if not already selling
                if not should_sell:
                    for strat_name, strat_cfg in self.strategies.items():
                        sell_flag, rules = strat_cfg['rule_strategy'].evaluate_exit(indicators)
                        if sell_flag:
                            should_sell = True
                            exit_strategy = strat_name
                            exit_rules_triggered.extend([f"{strat_name}:{r}" for r in rules])
                
                if should_sell:
                    quantity = pos.quantity
                    exec_price = current_price * (1 - self.slippage)
                    proceeds = quantity * exec_price * (1 - self.commission)
                    if self._execute_sell(sym, quantity, exec_price, exit_rules_triggered):
                        self.current_cash += proceeds
                        self.trade_log.append({
                            "date": date.isoformat(),
                            "symbol": sym,
                            "action": "SELL",
                            "quantity": quantity,
                            "price": exec_price,
                            "strategy": exit_strategy,
                            "rules_triggered": exit_rules_triggered
                        })
            
            # Record equity
            pos_value = 0.0
            for sym, pos in self.repository.positions.items():
                if sym in all_data and date in all_data[sym].index:
                    pos_value += pos.quantity * all_data[sym].loc[date, "close"]
            total_eq = self.current_cash + pos_value
            self.equity_curve.append({
                "date": date.isoformat(),
                "cash": self.current_cash,
                "positions_value": pos_value,
                "total_value": total_eq,
                "positions_count": len(self.repository.positions)
            })
        
        # Final metrics
        metrics = self._calculate_metrics()
        await self._save_results_to_db(metrics, start_date, end_date, symbols)
        
        return {"metrics": metrics, "equity_curve": self.equity_curve, "trade_log": self.trade_log}
    
    def _calculate_metrics(self) -> Dict[str, Any]:
        if len(self.equity_curve) < 2:
            return {}
        df = pd.DataFrame(self.equity_curve)
        df["date"] = pd.to_datetime(df["date"]); df = df.set_index("date")
        series = df["total_value"]
        
        total_ret = (series.iloc[-1] - series.iloc[0]) / series.iloc[0]
        years = (series.index[-1] - series.index[0]).days / 365.25
        cagr = (1 + total_ret) ** (1/years) - 1 if years > 0 else 0.0
        
        daily_ret = series.pct_change().dropna()
        sharpe = (daily_ret.mean() / daily_ret.std() * (252**0.5)) if daily_ret.std() > 0 else 0.0
        downside = daily_ret[daily_ret < 0]
        sortino = (daily_ret.mean() / downside.std() * (252**0.5)) if downside.std() > 0 else 0.0
        
        rolling_max = series.expanding().max()
        drawdown = (series - rolling_max) / rolling_max
        max_dd = drawdown.min()
        
        total_trades = len([t for t in self.trade_log if t["action"] == "SELL"])
        
        return {
            "total_return_pct": float(total_ret * 100),
            "cagr_pct": float(cagr * 100),
            "sharpe_ratio": float(sharpe),
            "sortino_ratio": float(sortino),
            "max_drawdown_pct": float(max_dd * 100),
            "total_trades": int(total_trades),
            "initial_capital": float(self.initial_capital),
            "final_value": float(series.iloc[-1])
        }
    
    async def _save_results_to_db(self, metrics: Dict[str, Any], start: datetime, end: datetime, symbols: List[str]):
        db = get_backtest_db()
        cursor = db.connection.cursor()
        run_name = f"{self.selected_strategy_name} {start.date()} to {end.date()}"
        cursor.execute('''
            INSERT INTO backtest_runs (
                run_name, start_date, end_date, initial_capital, final_equity,
                total_return_pct, cagr_pct, max_drawdown_pct, sharpe_ratio,
                sortino_ratio, win_rate_pct, profit_factor, total_trades,
                winning_trades, losing_trades, avg_win, avg_loss, config_json, results_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            run_name,
            start, end,
            metrics.get("initial_capital", self.initial_capital),
            metrics.get("final_value", 0.0),
            metrics.get("total_return_pct"),
            metrics.get("cagr_pct"),
            metrics.get("max_drawdown_pct"),
            metrics.get("sharpe_ratio"),
            metrics.get("sortino_ratio"),
            0.0,  # win_rate_pct - placeholder
            0.0,  # profit_factor - placeholder
            metrics.get("total_trades", 0),
            0, 0, 0.0, 0.0,  # avg win/loss placeholders
            json.dumps({"symbols": symbols, "strategy": self.selected_strategy_name, "commission": self.commission, "slippage": self.slippage}),
            json.dumps({"metrics": metrics, "trade_count": len(self.trade_log)})
        ))
        db.connection.commit()
        logger.info(f"Saved backtest results to DB (ID: {cursor.lastrowid})")


async def main():
    parser = argparse.ArgumentParser(description="Run backtest for trading strategy")
    parser.add_argument("--symbols", nargs="+", required=True)
    parser.add_argument("--start-date", type=str, required=True, help="YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, required=True, help="YYYY-MM-DD")
    parser.add_argument("--capital", type=float, default=100000.0)
    parser.add_argument("--output", type=str)
    parser.add_argument("--config-dir", type=str, default="config")
    parser.add_argument("--strategy", type=str, help="Strategy name from config under finance/strategies. If not set, uses first defined.")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    
    start = datetime.strptime(args.start_date, "%Y-%m-%d")
    end = datetime.strptime(args.end_date, "%Y-%m-%d")
    
    config = YAMLConfigEngine(args.config_dir)
    if not config.validate():
        logger.error("Config validation failed"); sys.exit(1)
    
    runner = BacktestRunner(config, initial_capital=args.capital, strategy_name=args.strategy)
    
    try:
        results = await runner.run_backtest(args.symbols, start, end, progress_callback=lambda msg: logger.info(f"Progress: {msg}"))
        m = results["metrics"]
        logger.info("BACKTEST COMPLETE")
        logger.info(f"Total Return: {m['total_return_pct']:.2f}%")
        logger.info(f"CAGR: {m['cagr_pct']:.2f}%")
        logger.info(f"Sharpe: {m['sharpe_ratio']:.2f}")
        logger.info(f"Max Drawdown: {m['max_drawdown_pct']:.2f}%")
        logger.info(f"Trades: {m['total_trades']}")
        logger.info(f"Final Value: ${m['final_value']:,.2f}")
        
        if args.output:
            with open(args.output, "w") as f:
                json.dump(results, f, indent=2, default=str)
            logger.info(f"Results saved to {args.output}")
        
        if m.get("cagr_pct", 0) >= 20.0 and m.get("max_drawdown_pct", -100) <= 30.0:
            logger.info("✅ Strategy meets 20% CAGR / <30% drawdown target!")
            sys.exit(0)
        else:
            logger.warning("⚠️ Strategy does NOT meet target criteria")
            sys.exit(1)
    
    except Exception as e:
        logger.error(f"Backtest failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
