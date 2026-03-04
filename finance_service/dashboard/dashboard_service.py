"""Dashboard service for aggregating and serving UI data."""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """Metric data types."""
    POSITION = "position"
    ORDER = "order"
    TRADE = "trade"
    PERFORMANCE = "performance"
    RISK = "risk"
    PORTFOLIO = "portfolio"


@dataclass
class PortfolioSnapshot:
    """Current portfolio state snapshot."""
    timestamp: datetime
    total_value: float
    cash: float
    buying_power: float
    equity: float
    return_pct: float
    daily_return_pct: float
    unrealized_pnl: float
    realized_pnl: float
    positions_count: int
    open_orders_count: int
    

@dataclass
class PositionView:
    """Position for dashboard display."""
    symbol: str
    quantity: float
    avg_cost: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    weight: float  # % of portfolio
    status: str  # "long", "short", "closing"


@dataclass
class OrderView:
    """Order for dashboard display."""
    order_id: str
    symbol: str
    side: str  # "BUY" or "SELL"
    quantity: float
    filled_quantity: float
    fill_pct: float
    avg_fill_price: float
    status: str
    order_type: str
    submitted_at: datetime
    updated_at: datetime
    slippage_bps: float


@dataclass
class TradeView:
    """Executed trade for dashboard display."""
    trade_id: str
    symbol: str
    side: str
    quantity: float
    entry_price: float
    exit_price: Optional[float]
    pnl: float
    pnl_pct: float
    duration_seconds: int
    filled_at: datetime
    closed_at: Optional[datetime]
    status: str  # "open", "closed", "closing"


@dataclass
class PerformanceMetrics:
    """Performance metrics for dashboard."""
    total_return_pct: float
    daily_return_pct: float
    ytd_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate_pct: float
    profit_factor: float
    avg_win_pct: float
    avg_loss_pct: float
    largest_win_pct: float
    largest_loss_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int


@dataclass
class RiskMetrics:
    """Risk metrics for dashboard."""
    var_95: float  # Value at Risk 95%
    cvar_95: float  # Conditional VaR
    beta: float
    volatility_pct: float
    correlation_spy: float
    max_position_loss: float
    portfolio_concentration: float  # Herfindahl index
    sector_concentration: float


@dataclass
class DashboardState:
    """Complete dashboard state snapshot."""
    snapshot: PortfolioSnapshot
    positions: List[PositionView]
    open_orders: List[OrderView]
    recent_trades: List[TradeView]
    performance: PerformanceMetrics
    risk: RiskMetrics
    alerts: List[Dict[str, Any]]


class DashboardService:
    """
    Service that aggregates data from various modules for dashboard display.
    
    Provides snapshots of portfolio, positions, orders, trades, and metrics.
    """
    
    def __init__(self, finance_service, market_data_service, risk_manager):
        """
        Initialize dashboard service.
        
        Args:
            finance_service: Reference to main FinanceService
            market_data_service: Reference to real-time market data
            risk_manager: Reference to risk management module
        """
        self.finance_service = finance_service
        self.market_data_service = market_data_service
        self.risk_manager = risk_manager
        
        # Historical snapshots for charting
        self.snapshots: List[PortfolioSnapshot] = []
        self.max_snapshots = 1000  # Keep last 1000 snapshots (24 hours at 1min interval)
        
    def get_dashboard_state(self) -> DashboardState:
        """Get complete dashboard state."""
        return DashboardState(
            snapshot=self._get_portfolio_snapshot(),
            positions=self._get_positions(),
            open_orders=self._get_open_orders(),
            recent_trades=self._get_recent_trades(),
            performance=self._get_performance_metrics(),
            risk=self._get_risk_metrics(),
            alerts=self._get_alerts(),
        )
    
    def _get_portfolio_snapshot(self) -> PortfolioSnapshot:
        """Get current portfolio snapshot."""
        # Get account info
        account = self.finance_service.get_account()
        broker = self.finance_service.broker
        
        total_value = broker.get_account_value()
        cash = broker.get_cash()
        buying_power = broker.get_buying_power()
        equity = total_value - cash
        
        # Calculate returns
        initial_value = account.initial_capital if hasattr(account, 'initial_capital') else total_value
        return_pct = ((total_value - initial_value) / initial_value * 100) if initial_value > 0 else 0
        
        # Daily return (from today's open or last session close)
        daily_return_pct = 0.0
        if hasattr(account, 'last_close_value'):
            daily_return_pct = ((total_value - account.last_close_value) / account.last_close_value * 100)
        
        # Get P&L
        unrealized_pnl = sum(
            pos.unrealized_pnl 
            for pos in broker.get_positions().values()
        )
        realized_pnl = account.realized_pnl if hasattr(account, 'realized_pnl') else 0.0
        
        # Count open orders
        open_orders = len([o for o in broker.get_orders() if o.status not in ['FILLED', 'CANCELLED']])
        
        snapshot = PortfolioSnapshot(
            timestamp=datetime.now(),
            total_value=total_value,
            cash=cash,
            buying_power=buying_power,
            equity=equity,
            return_pct=return_pct,
            daily_return_pct=daily_return_pct,
            unrealized_pnl=unrealized_pnl,
            realized_pnl=realized_pnl,
            positions_count=len(broker.get_positions()),
            open_orders_count=open_orders,
        )
        
        # Store in history
        self.snapshots.append(snapshot)
        if len(self.snapshots) > self.max_snapshots:
            self.snapshots.pop(0)
        
        return snapshot
    
    def _get_positions(self) -> List[PositionView]:
        """Get list of positions."""
        broker = self.finance_service.broker
        positions = broker.get_positions()
        portfolio_value = broker.get_account_value()
        
        position_views = []
        for symbol, pos in positions.items():
            current_price = self.market_data_service.get_last_price(symbol) if self.market_data_service else pos.avg_cost
            
            market_value = pos.quantity * current_price
            unrealized_pnl = market_value - (pos.quantity * pos.avg_cost)
            unrealized_pnl_pct = (unrealized_pnl / (pos.quantity * pos.avg_cost) * 100) if pos.quantity != 0 else 0
            weight = (market_value / portfolio_value * 100) if portfolio_value > 0 else 0
            
            position_views.append(PositionView(
                symbol=symbol,
                quantity=pos.quantity,
                avg_cost=pos.avg_cost,
                current_price=current_price,
                market_value=market_value,
                unrealized_pnl=unrealized_pnl,
                unrealized_pnl_pct=unrealized_pnl_pct,
                weight=weight,
                status="long" if pos.quantity > 0 else "short",
            ))
        
        # Sort by market value (largest first)
        return sorted(position_views, key=lambda p: abs(p.market_value), reverse=True)
    
    def _get_open_orders(self) -> List[OrderView]:
        """Get list of open orders."""
        broker = self.finance_service.broker
        orders = broker.get_orders()
        
        order_views = []
        for order in orders:
            if order.status not in ['FILLED', 'CANCELLED', 'REJECTED']:
                fill_pct = (order.filled_quantity / order.quantity * 100) if order.quantity > 0 else 0
                slippage_bps = 0.0  # TODO: Calculate from order execution
                
                order_views.append(OrderView(
                    order_id=order.order_id,
                    symbol=order.symbol,
                    side=order.side.value,
                    quantity=order.quantity,
                    filled_quantity=order.filled_quantity,
                    fill_pct=fill_pct,
                    avg_fill_price=order.avg_fill_price,
                    status=order.status.value,
                    order_type=order.order_type.value,
                    submitted_at=order.submitted_at,
                    updated_at=order.updated_at,
                    slippage_bps=slippage_bps,
                ))
        
        return order_views
    
    def _get_recent_trades(self, limit: int = 50) -> List[TradeView]:
        """Get recent closed trades."""
        # Get from execution history
        trades = self.finance_service.get_trade_history(limit=limit)
        
        trade_views = []
        for trade in trades:
            pnl = trade.get('pnl', 0.0)
            entry_price = trade.get('entry_price', 0.0)
            pnl_pct = (pnl / (trade.get('quantity', 1) * entry_price) * 100) if entry_price > 0 else 0
            
            duration_seconds = 0
            if trade.get('closed_at') and trade.get('filled_at'):
                duration_seconds = int((trade['closed_at'] - trade['filled_at']).total_seconds())
            
            trade_views.append(TradeView(
                trade_id=trade.get('trade_id', ''),
                symbol=trade.get('symbol', ''),
                side=trade.get('side', 'BUY'),
                quantity=trade.get('quantity', 0.0),
                entry_price=entry_price,
                exit_price=trade.get('exit_price'),
                pnl=pnl,
                pnl_pct=pnl_pct,
                duration_seconds=duration_seconds,
                filled_at=trade.get('filled_at', datetime.now()),
                closed_at=trade.get('closed_at'),
                status=trade.get('status', 'open'),
            ))
        
        return trade_views
    
    def _get_performance_metrics(self) -> PerformanceMetrics:
        """Calculate performance metrics."""
        trades = self.finance_service.get_trade_history()
        
        if not trades:
            return PerformanceMetrics(
                total_return_pct=0.0, daily_return_pct=0.0, ytd_return_pct=0.0,
                sharpe_ratio=0.0, max_drawdown_pct=0.0, win_rate_pct=0.0,
                profit_factor=0.0, avg_win_pct=0.0, avg_loss_pct=0.0,
                largest_win_pct=0.0, largest_loss_pct=0.0,
                total_trades=0, winning_trades=0, losing_trades=0
            )
        
        # Calculate metrics from trade history
        winning = [t for t in trades if t.get('pnl', 0) > 0]
        losing = [t for t in trades if t.get('pnl', 0) < 0]
        
        total_trades = len(trades)
        winning_trades = len(winning)
        losing_trades = len(losing)
        winning_pnl = sum(t.get('pnl', 0) for t in winning)
        losing_pnl = sum(abs(t.get('pnl', 0)) for t in losing)
        
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        profit_factor = (winning_pnl / losing_pnl) if losing_pnl > 0 else 0
        
        win_pnls = [t.get('pnl_pct', 0) for t in winning]
        loss_pnls = [abs(t.get('pnl_pct', 0)) for t in losing]
        
        avg_win_pct = (sum(win_pnls) / len(win_pnls)) if win_pnls else 0
        avg_loss_pct = (sum(loss_pnls) / len(loss_pnls)) if loss_pnls else 0
        largest_win_pct = max(win_pnls) if win_pnls else 0
        largest_loss_pct = max(loss_pnls) if loss_pnls else 0
        
        # Get returns from snapshots
        broker = self.finance_service.broker
        account = self.finance_service.get_account()
        total_value = broker.get_account_value()
        initial_value = account.initial_capital if hasattr(account, 'initial_capital') else total_value
        total_return_pct = ((total_value - initial_value) / initial_value * 100) if initial_value > 0 else 0
        
        return PerformanceMetrics(
            total_return_pct=total_return_pct,
            daily_return_pct=0.0,  # Calculated separately
            ytd_return_pct=total_return_pct,  # Simplified
            sharpe_ratio=0.0,  # Requires volatility calculation
            max_drawdown_pct=0.0,  # Requires drawdown calculation
            win_rate_pct=win_rate,
            profit_factor=profit_factor,
            avg_win_pct=avg_win_pct,
            avg_loss_pct=avg_loss_pct,
            largest_win_pct=largest_win_pct,
            largest_loss_pct=largest_loss_pct,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
        )
    
    def _get_risk_metrics(self) -> RiskMetrics:
        """Calculate risk metrics."""
        # Use risk manager if available
        if self.risk_manager:
            var_95 = self.risk_manager.calculate_var(confidence=0.95)
            max_dd = self.risk_manager.calculate_max_drawdown()
        else:
            var_95 = 0.0
            max_dd = 0.0
        
        return RiskMetrics(
            var_95=var_95,
            cvar_95=0.0,  # Requires advanced calculation
            beta=0.0,  # Requires market correlation
            volatility_pct=0.0,  # Requires price history
            correlation_spy=0.0,  # Requires SPY data
            max_position_loss=0.0,  # Worst single position loss
            portfolio_concentration=0.0,  # Herfindahl index
            sector_concentration=0.0,  # Sector concentration
        )
    
    def _get_alerts(self) -> List[Dict[str, Any]]:
        """Get active alerts."""
        alerts = []
        
        broker = self.finance_service.broker
        account = self.finance_service.get_account()
        
        # Alert 1: Low cash warning
        if broker.get_cash() < 1000:
            alerts.append({
                "id": "low_cash",
                "severity": "warning",
                "title": "Low Cash Balance",
                "message": f"Cash balance is ${broker.get_cash():,.2f}",
                "timestamp": datetime.now(),
            })
        
        # Alert 2: High concentration
        positions = broker.get_positions()
        if positions:
            portfolio_value = broker.get_account_value()
            largest_pos = max(
                (abs(pos.quantity * pos.avg_cost) / portfolio_value for pos in positions.values()),
                default=0
            )
            if largest_pos > 0.3:  # Single position > 30%
                alerts.append({
                    "id": "high_concentration",
                    "severity": "warning",
                    "title": "High Position Concentration",
                    "message": f"Largest position is {largest_pos*100:.1f}% of portfolio",
                    "timestamp": datetime.now(),
                })
        
        # Alert 3: Open orders
        open_orders = len([o for o in broker.get_orders() if o.status not in ['FILLED', 'CANCELLED']])
        if open_orders > 10:
            alerts.append({
                "id": "many_open_orders",
                "severity": "info",
                "title": "Many Open Orders",
                "message": f"You have {open_orders} open orders",
                "timestamp": datetime.now(),
            })
        
        return alerts
    
    def get_performance_chart_data(
        self, 
        period: str = "1d",
        interval: str = "1m"
    ) -> Dict[str, Any]:
        """
        Get chart data for portfolio performance.
        
        Args:
            period: "1d", "1w", "1m", "3m", "6m", "1y", "all"
            interval: "1m", "5m", "15m", "1h", "1d"
            
        Returns:
            Chart data with timestamps and values
        """
        filtered_snapshots = self._filter_snapshots(period)
        
        return {
            "timestamps": [s.timestamp.isoformat() for s in filtered_snapshots],
            "total_value": [s.total_value for s in filtered_snapshots],
            "equity": [s.equity for s in filtered_snapshots],
            "cash": [s.cash for s in filtered_snapshots],
            "return_pct": [s.return_pct for s in filtered_snapshots],
        }
    
    def get_positions_chart_data(self) -> Dict[str, Any]:
        """Get position allocation data for pie chart."""
        positions = self._get_positions()
        
        return {
            "symbols": [p.symbol for p in positions],
            "values": [p.market_value for p in positions],
            "weights": [p.weight for p in positions],
            "pnls": [p.unrealized_pnl for p in positions],
        }
    
    def _filter_snapshots(self, period: str) -> List[PortfolioSnapshot]:
        """Filter snapshots by time period."""
        if not self.snapshots:
            return []
        
        now = datetime.now()
        period_map = {
            "1d": timedelta(hours=24),
            "1w": timedelta(days=7),
            "1m": timedelta(days=30),
            "3m": timedelta(days=90),
            "6m": timedelta(days=180),
            "1y": timedelta(days=365),
            "all": timedelta(days=10000),
        }
        
        cutoff = now - period_map.get(period, timedelta(hours=24))
        return [s for s in self.snapshots if s.timestamp >= cutoff]
    
    def reset(self):
        """Reset dashboard state."""
        self.snapshots.clear()
        logger.info("Dashboard state reset")
