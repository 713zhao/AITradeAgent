import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
import asyncio

from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.event_bus import Event, Events, get_event_bus
from finance_service.core.config import Config

# Import models and repository from the portfolio module
from finance_service.portfolio.models import Position, Trade, Portfolio, TradeStatus
from finance_service.portfolio.trade_repository import TradeRepository
from finance_service.portfolio.equity_calculator import EquityCalculator

logger = logging.getLogger(__name__)

class PortfolioAgent(Agent):
    """Portfolio Agent - Manages portfolio operations, tracks positions, and calculates equity."""

    @property
    def agent_id(self) -> str:
        return "portfolio_agent"

    @property
    def goal(self) -> str:
        return "Maintain an accurate record of portfolio holdings, execute trades, and provide real-time portfolio metrics."

    def __init__(self, config: Dict[str, Any], data_agent=None):
        self.config = config
        self.event_bus = get_event_bus()
        self.initial_cash = config.get("initial_cash", 100000.0)
        self.repository = TradeRepository() # This will need to be async-adapted later
        self.equity_calculator = EquityCalculator()
        self.data_agent = data_agent  # Optional DataAgent for fetching live quotes
        self.updated_at = datetime.utcnow()
        self._price_update_lock = asyncio.Lock()  # Prevent concurrent price updates
        self._last_price_update = datetime(1970, 1, 1)  # Never updated initially
        self._price_update_interval = 300  # seconds (5 minutes); match scheduler frequency
        logger.info("PortfolioAgent initialized.")

    async def run(self, **kwargs) -> AgentReport:
        """Main entry point for the Portfolio Agent. Responds to events and performs portfolio actions."""
        event_type = kwargs.get("event_type")
        payload = kwargs.get("payload", {})

        if event_type == Events.TRADE_EXECUTED:
            # Accept either direct execution_result or wrapped in trade_info
            trade_info = payload.get("trade_info") or payload
            if trade_info:
                return await self.handle_trade_executed(trade_info)
            else:
                return AgentReport(agent_id=self.agent_id, status="error", message="Missing trade_info in TRADE_EXECUTED event")
        elif event_type == Events.GET_PORTFOLIO_STATE:
            chat_id = payload.get("chat_id") # For direct response via TelegramAgent
            return await self.get_detailed_portfolio_state(chat_id)
        elif event_type == Events.ANALYSIS_COMPLETE:
            return await self.handle_analysis_complete(payload)
        # Add other event types the PortfolioAgent might react to
        else:
            return AgentReport(agent_id=self.agent_id, status="success", message="PortfolioAgent is running.")

    async def handle_trade_executed(self, trade_info: Dict[str, Any]) -> AgentReport:
        """Handles TRADE_EXECUTED event to update portfolio positions and trades."""
        logger.info(f"[PORTFOLIO DEBUG] handle_trade_executed called with trade_info: {trade_info}")
        # Unwrap AgentReport wrapper: {agent_id, status, payload: {execution_result: {...}}}
        if "agent_id" in trade_info and "payload" in trade_info:
            trade_info = trade_info["payload"].get("execution_result", trade_info["payload"])
        # Unwrap bare execution_result nesting: {execution_result: {...}}
        elif "execution_result" in trade_info:
            trade_info = trade_info["execution_result"]
        # Accept both 'action'/'side' and 'price'/'filled_price' for compatibility
        symbol = trade_info.get("symbol")
        side = trade_info.get("side") or trade_info.get("action")
        quantity = trade_info.get("quantity")
        price = trade_info.get("price") or trade_info.get("filled_price")
        trade_id = trade_info.get("trade_id") or f"exec_{int(datetime.utcnow().timestamp()*1000)}"

        logger.info(f"[PORTFOLIO DEBUG] Parsed: symbol={symbol}, side={side}, quantity={quantity}, price={price}, trade_id={trade_id}")

        if not all([symbol, side, quantity, price]):
            msg = f"Missing required trade fields: {trade_info}"
            logger.error(msg)
            return AgentReport(agent_id=self.agent_id, status="error", message=msg)

        try:
            side = side.upper()
            if side == "BUY":
                # --- FIX 1: Cash sufficiency check ---
                trade_value = quantity * price
                # Get current available cash from repository (track running cash balance)
                # Since repository doesn't track cash separately, we compute from portfolio formula
                # available_cash = initial_cash - spent_on_long_positions
                current_portfolio = self.repository.calculate_portfolio(self.initial_cash)
                available_cash = current_portfolio.current_cash
                if trade_value > available_cash:
                    msg = f"Insufficient cash for BUY: need ${trade_value:,.2f}, available ${available_cash:,.2f}"
                    logger.error(msg)
                    return AgentReport(agent_id=self.agent_id, status="error", message=msg)

                logger.info(f"[PORTFOLIO DEBUG] Creating BUY trade for {symbol}")
                trade = self.repository.create_trade(
                    task_id=trade_id,
                    symbol=symbol, side="BUY", quantity=quantity, price=price,
                    decision={}, confidence=1.0, reason="Executed Trade"
                )
                logger.info(f"[PORTFOLIO DEBUG] Trade created with trade_id={trade.trade_id}")
                position = self.repository.get_position(symbol)
                logger.info(f"[PORTFOLIO DEBUG] Existing position before update: {position}")
                if position:
                    new_qty = position.quantity + quantity
                    new_cost = (position.cost_basis() + quantity * price) / new_qty
                    self.repository.update_position(symbol, quantity=new_qty, avg_cost=new_cost, add_trade=trade.trade_id)
                else:
                    self.repository.create_position(symbol, quantity=quantity, avg_cost=price, trades=[trade.trade_id])
                logger.info(f"[PORTFOLIO DEBUG] Position after update: {self.repository.get_position(symbol)}")
            elif side == "SELL":
                logger.info(f"[PORTFOLIO DEBUG] Creating SELL trade for {symbol}")
                trade = self.repository.create_trade(
                    task_id=trade_id,
                    symbol=symbol, side="SELL", quantity=quantity, price=price,
                    decision={}, confidence=1.0, reason="Executed Trade"
                )
                position = self.repository.get_position(symbol)
                if position:
                    new_qty = position.quantity - quantity
                    if new_qty == 0:
                        self.repository.close_position(symbol)
                    else:
                        self.repository.update_position(symbol, quantity=new_qty, add_trade=trade.trade_id)
                else:
                    self.repository.create_position(symbol, quantity=-quantity, avg_cost=price, trades=[trade.trade_id])
            else:
                msg = f"Unknown trade side: {side}"
                logger.error(msg)
                return AgentReport(agent_id=self.agent_id, status="error", message=msg)
            
            # Mark trade as filled (since execution is immediate in paper trading)
            self.repository.update_trade_status(trade.trade_id, TradeStatus.FILLED, filled_quantity=quantity, executed_by="system")
            
            self.updated_at = datetime.utcnow()
            logger.info(f"Portfolio updated after {side} trade: {trade_id}")
            return AgentReport(agent_id=self.agent_id, status="success", message=f"Trade {trade_id} processed", payload=trade.to_dict())
        except Exception as e:
            logger.error(f"Error processing trade {trade_id}: {e}", exc_info=True)
            return AgentReport(agent_id=self.agent_id, status="error", message=f"Error processing trade: {e}")


    async def update_prices_from_data_agent(self):
        """Fetch latest prices for all positions with limited concurrency (5) and cache, protected by lock."""
        if not self.data_agent:
            return
        
        async with self._price_update_lock:
            symbols = list(self.repository.positions.keys())
            if not symbols:
                return
            
            logger.info(f"Updating prices for {len(symbols)} positions (concurrency=5, cache=yes, 30d lookback)")
            
            semaphore = asyncio.Semaphore(2)  # Reduce concurrency to 2 to avoid overwhelming provider
            from datetime import datetime, timedelta
            end_dt = datetime.now().date()
            start_dt = end_dt - timedelta(days=30)
            start_str = start_dt.strftime("%Y-%m-%d")
            end_str = end_dt.strftime("%Y-%m-%d")
            
            async def fetch_one(symbol: str):
                async with semaphore:
                    try:
                        report = await self.data_agent.run(
                            symbol=symbol,
                            interval="1d",
                            emit_events=False,
                            use_cache=True,
                            start_date=start_str,
                            end_date=end_str
                        )
                        return symbol, report
                    except Exception as e:
                        logger.warning(f"Error fetching {symbol}: {e}")
                        return symbol, None
            
            tasks = [fetch_one(sym) for sym in symbols]
            results = await asyncio.gather(*tasks, return_exceptions=False)
            
            updated_count = 0
            for symbol, report in results:
                if report is None:
                    continue
                if report.status == "success" and "dataframe" in report.payload:
                    df_dict = report.payload["dataframe"]
                    try:
                        import pandas as pd
                        df = pd.DataFrame.from_dict(df_dict)
                        if not df.empty:
                            latest_price = df.iloc[-1]['close']
                            if isinstance(latest_price, (int, float)) and latest_price == latest_price and latest_price > 0:
                                self.repository.update_position(symbol, current_price=latest_price)
                                updated_count += 1
                                logger.debug(f"Updated {symbol} current price to {latest_price}")
                            else:
                                logger.warning(f"Invalid price fetched for {symbol}: {latest_price}")
                    except Exception as e:
                        logger.warning(f"Failed to process price data for {symbol}: {e}")
                else:
                    logger.warning(f"Failed to fetch price for {symbol}: {report.message if report else 'no report'}")
            
            logger.info(f"Updated prices for {updated_count}/{len(symbols)} positions")
            self._last_price_update = datetime.utcnow()

    async def get_detailed_portfolio_state(self, chat_id: Optional[str] = None) -> AgentReport:
        """Retrieves detailed portfolio state and can publish it or return in a report."""
        logger.info("PortfolioAgent generating detailed portfolio state.")
        # Refresh timestamp to indicate state generation time
        self.updated_at = datetime.utcnow()
        
        # Rate limit price updates: skip if updated recently
        now = datetime.utcnow()
        elapsed = (now - self._last_price_update).total_seconds()
        if elapsed >= self._price_update_interval:
            logger.debug(f"Price update needed (last: {elapsed:.0f}s ago).")
            await self.update_prices_from_data_agent()
        else:
            logger.debug(f"Skipping price update (last: {elapsed:.0f}s ago < {self._price_update_interval}s).")
        
        portfolio = self.repository.calculate_portfolio(self.initial_cash)
        positions_data = [pos.to_dict() for pos in self.repository.get_positions()]
        trades_data = [trade.to_dict() for trade in self.repository.trades]
        
        equity_metrics = self.get_equity_metrics() # Use the existing helper

        # This is the data that will be sent back to the orchestrator/TelegramAgent
        portfolio_state = {
            "overview": portfolio.to_dict(),
            "positions": positions_data,
            "trades": trades_data,
            "equity_metrics": equity_metrics,
            "last_updated": self.updated_at.isoformat()
        }

        if chat_id:
            # If a chat_id is provided, we can directly send it via the TelegramAgent (via event bus)
            # The orchestrator will pick this up from the GET_PORTFOLIO_STATE event response and send it.
            pass # Orchestrator will handle the response via handle_get_portfolio_state

        return AgentReport(agent_id=self.agent_id, status="success", message="Portfolio state retrieved", payload=portfolio_state)

    async def handle_analysis_complete(self, payload: Dict[str, Any]) -> AgentReport:
        """
        Handles ANALYSIS_COMPLETE event by updating position prices from latest data
        and refreshing the portfolio state timestamp.
        """
        logger.info("PortfolioAgent received ANALYSIS_COMPLETE event – updating prices.")
        await self.update_prices_from_data_agent()
        self.updated_at = datetime.utcnow()
        # Optionally, we could persist state here if needed: self.repository.save_state()
        return AgentReport(agent_id=self.agent_id, status="success", message="Portfolio prices updated from analysis")

    # The following methods are adapted from PortfolioManager, made async if they involve I/O

    # Note: TradeRepository methods will need to be made async for true non-blocking I/O.
    # For this exercise, we're assuming repository methods are fast enough or will be async-adapted.

    async def execute_buy(
        self,
        task_id: str,
        symbol: str,
        quantity: float,
        price: float,
        decision: Dict[str, Any],
        confidence: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        reason: str = "",
    ) -> Trade:
        trade = self.repository.create_trade(
            task_id=task_id,
            symbol=symbol,
            side="BUY",
            quantity=quantity,
            price=price,
            decision=decision,
            confidence=confidence,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reason=reason,
        )
        position = self.repository.get_position(symbol)
        if position:
            new_qty = position.quantity + quantity
            new_cost = (position.cost_basis() + quantity * price) / new_qty
            self.repository.update_position(
                symbol,
                quantity=new_qty,
                avg_cost=new_cost,
                add_trade=trade.trade_id,
            )
        else:
            self.repository.create_position(
                symbol,
                quantity=quantity,
                avg_cost=price,
                trades=[trade.trade_id],
            )
        
        self.updated_at = datetime.utcnow()
        logger.info(f"BUY trade created: {trade.trade_id} {symbol} {quantity}@{price}")
        return trade
    
    async def execute_sell(
        self,
        task_id: str,
        symbol: str,
        quantity: float,
        price: float,
        decision: Dict[str, Any],
        confidence: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        reason: str = "",
    ) -> Trade:
        trade = self.repository.create_trade(
            task_id=task_id,
            symbol=symbol,
            side="SELL",
            quantity=quantity,
            price=price,
            decision=decision,
            confidence=confidence,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reason=reason,
        )
        position = self.repository.get_position(symbol)
        if position:
            new_qty = position.quantity - quantity
            if new_qty == 0:
                self.repository.close_position(symbol)
            else:
                self.repository.update_position(
                    symbol,
                    quantity=new_qty,
                    add_trade=trade.trade_id,
                )
        else:
            self.repository.create_position(
                symbol,
                quantity=-quantity,
                avg_cost=price,
                trades=[trade.trade_id],
            )
        
        self.updated_at = datetime.utcnow()
        logger.info(f"SELL trade created: {trade.trade_id} {symbol} {quantity}@{price}")
        return trade

    async def fill_trade(
        self,
        trade_id: str,
        filled_quantity: float = None,
        executed_by: str = "system",
    ) -> Optional[Trade]:
        trade = self.repository.get_trade(trade_id)
        if not trade:
            return None
        
        filled_qty = filled_quantity or trade.quantity
        trade = self.repository.update_trade_status(
            trade_id,
            TradeStatus.FILLED,
            filled_quantity=filled_qty,
            executed_by=executed_by,
        )
        if filled_qty < trade.quantity:
            trade.status = TradeStatus.PARTIALLY_FILLED
        
        self.updated_at = datetime.utcnow()
        logger.info(f"Trade filled: {trade_id} ({filled_qty}/{trade.quantity})")
        return trade
    
    async def cancel_trade(self, trade_id: str, reason: str = "") -> Optional[Trade]:
        trade = self.repository.get_trade(trade_id)
        if not trade:
            return None
        
        if trade.status not in [TradeStatus.PENDING, TradeStatus.APPROVED]:
            return None
        
        trade = self.repository.update_trade_status(
            trade_id,
            TradeStatus.CANCELLED,
            error_reason=reason,
        )
        position = self.repository.get_position(trade.symbol)
        if position and trade.trade_id in position.trades:
            position.trades.remove(trade.trade_id)
        
        self.updated_at = datetime.utcnow()
        logger.info(f"Trade cancelled: {trade_id} ({reason})")
        return trade
    
    async def update_position_price(self, symbol: str, price: float) -> Optional[Position]:
        position = self.repository.update_position(symbol, current_price=price)
        self.updated_at = datetime.utcnow()
        return position
    
    async def update_all_prices(self, prices: Dict[str, float]) -> None:
        self.repository.update_position_prices(prices)
        self.updated_at = datetime.utcnow()
    
    def get_portfolio(self) -> Portfolio:
        return self.repository.calculate_portfolio(self.initial_cash)
    
    def get_position(self, symbol: str) -> Optional[Position]:
        return self.repository.get_position(symbol)
    
    def get_positions(self) -> list:
        return self.repository.get_positions()
    
    def get_trade(self, trade_id: str) -> Optional[Trade]:
        return self.repository.get_trade(trade_id)
    
    def get_trades(self, symbol: str = None, status: TradeStatus = None):
        if symbol:
            trades = self.repository.get_trades_by_symbol(symbol)
        else:
            trades = self.repository.trades
        
        if status:
            trades = [t for t in trades if t.status == status]
        
        return trades
    
    def get_open_trades(self) -> list:
        return self.repository.get_open_trades()
    
    def get_position_pnl(self, symbol: str) -> Tuple[float, float]:
        position = self.get_position(symbol)
        if not position:
            return 0.0, 0.0
        
        return position.unrealized_pnl(), position.unrealized_pnl_pct()
    
    def get_portfolio_pnl(self) -> Tuple[float, float, float]:
        portfolio = self.get_portfolio()
        return (
            portfolio.realized_pnl(),
            portfolio.unrealized_pnl(),
            portfolio.total_pnl(),
        )
    
    def get_equity_metrics(self) -> Dict[str, Any]:
        portfolio = self.get_portfolio()
        return {
            "initial_cash": portfolio.initial_cash,
            "current_cash": portfolio.current_cash,
            "gross_position_value": portfolio.gross_position_value(),
            "net_position_value": portfolio.net_position_value(),
            "total_equity": portfolio.total_equity(),
            "total_pnl": portfolio.total_pnl(),
            "total_return_pct": portfolio.total_return_pct(),
            "unrealized_pnl": portfolio.unrealized_pnl(),
            "realized_pnl": portfolio.realized_pnl(),
            "drawdown_pct": portfolio.drawdown_pct(),
            "position_count": portfolio.position_count(),
            "trade_count": portfolio.trade_count(),
            "win_rate": portfolio.win_rate(),
        }
    
    def reset(self) -> None:
        self.repository.clear_all()
        self.updated_at = datetime.utcnow()
        logger.info("Portfolio reset to initial state")
