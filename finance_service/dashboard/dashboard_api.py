"""Dashboard REST API endpoints."""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class DashboardAPI:
    """
    REST API endpoints for dashboard.
    
    Provides Flask/FastAPI route handlers for dashboard data.
    """
    
    def __init__(self, dashboard_service, real_time_service):
        """
        Initialize dashboard API.
        
        Args:
            dashboard_service: DashboardService instance
            real_time_service: RealTimeService instance
        """
        self.dashboard_service = dashboard_service
        self.real_time_service = real_time_service
    
    # Dashboard endpoints
    
    def get_dashboard_overview(self) -> Dict[str, Any]:
        """GET /api/dashboard/overview - Get complete dashboard state."""
        try:
            state = self.dashboard_service.get_dashboard_state()
            return {
                "status": "success",
                "data": {
                    "portfolio": {
                        "total_value": state.snapshot.total_value,
                        "cash": state.snapshot.cash,
                        "buying_power": state.snapshot.buying_power,
                        "equity": state.snapshot.equity,
                        "return_pct": state.snapshot.return_pct,
                        "daily_return_pct": state.snapshot.daily_return_pct,
                        "unrealized_pnl": state.snapshot.unrealized_pnl,
                        "realized_pnl": state.snapshot.realized_pnl,
                        "timestamp": state.snapshot.timestamp.isoformat(),
                    },
                    "positions_count": state.snapshot.positions_count,
                    "open_orders_count": state.snapshot.open_orders_count,
                    "alerts_count": len(state.alerts),
                }
            }
        except Exception as e:
            logger.error(f"Error in get_dashboard_overview: {e}")
            return {"status": "error", "message": str(e)}
    
    def get_portfolio_snapshot(self) -> Dict[str, Any]:
        """GET /api/dashboard/portfolio - Get portfolio snapshot."""
        try:
            snapshot = self.dashboard_service._get_portfolio_snapshot()
            return {
                "status": "success",
                "data": {
                    "total_value": snapshot.total_value,
                    "cash": snapshot.cash,
                    "buying_power": snapshot.buying_power,
                    "equity": snapshot.equity,
                    "return_pct": snapshot.return_pct,
                    "daily_return_pct": snapshot.daily_return_pct,
                    "unrealized_pnl": snapshot.unrealized_pnl,
                    "realized_pnl": snapshot.realized_pnl,
                    "positions_count": snapshot.positions_count,
                    "open_orders_count": snapshot.open_orders_count,
                    "timestamp": snapshot.timestamp.isoformat(),
                }
            }
        except Exception as e:
            logger.error(f"Error in get_portfolio_snapshot: {e}")
            return {"status": "error", "message": str(e)}
    
    def get_positions(self) -> Dict[str, Any]:
        """GET /api/dashboard/positions - Get all positions."""
        try:
            positions = self.dashboard_service._get_positions()
            return {
                "status": "success",
                "data": [
                    {
                        "symbol": p.symbol,
                        "quantity": p.quantity,
                        "avg_cost": p.avg_cost,
                        "current_price": p.current_price,
                        "market_value": p.market_value,
                        "unrealized_pnl": p.unrealized_pnl,
                        "unrealized_pnl_pct": p.unrealized_pnl_pct,
                        "weight": p.weight,
                        "status": p.status,
                    }
                    for p in positions
                ]
            }
        except Exception as e:
            logger.error(f"Error in get_positions: {e}")
            return {"status": "error", "message": str(e)}
    
    def get_position(self, symbol: str) -> Dict[str, Any]:
        """GET /api/dashboard/positions/{symbol} - Get specific position."""
        try:
            positions = self.dashboard_service._get_positions()
            position = next((p for p in positions if p.symbol == symbol), None)
            
            if not position:
                return {"status": "error", "message": f"Position {symbol} not found"}
            
            return {
                "status": "success",
                "data": {
                    "symbol": position.symbol,
                    "quantity": position.quantity,
                    "avg_cost": position.avg_cost,
                    "current_price": position.current_price,
                    "market_value": position.market_value,
                    "unrealized_pnl": position.unrealized_pnl,
                    "unrealized_pnl_pct": position.unrealized_pnl_pct,
                    "weight": position.weight,
                    "status": position.status,
                }
            }
        except Exception as e:
            logger.error(f"Error in get_position: {e}")
            return {"status": "error", "message": str(e)}
    
    def get_orders(self) -> Dict[str, Any]:
        """GET /api/dashboard/orders - Get all open orders."""
        try:
            orders = self.dashboard_service._get_open_orders()
            return {
                "status": "success",
                "data": [
                    {
                        "order_id": o.order_id,
                        "symbol": o.symbol,
                        "side": o.side,
                        "quantity": o.quantity,
                        "filled_quantity": o.filled_quantity,
                        "fill_pct": o.fill_pct,
                        "avg_fill_price": o.avg_fill_price,
                        "status": o.status,
                        "order_type": o.order_type,
                        "submitted_at": o.submitted_at.isoformat(),
                        "updated_at": o.updated_at.isoformat(),
                        "slippage_bps": o.slippage_bps,
                    }
                    for o in orders
                ]
            }
        except Exception as e:
            logger.error(f"Error in get_orders: {e}")
            return {"status": "error", "message": str(e)}
    
    def get_order(self, order_id: str) -> Dict[str, Any]:
        """GET /api/dashboard/orders/{order_id} - Get specific order."""
        try:
            orders = self.dashboard_service._get_open_orders()
            order = next((o for o in orders if o.order_id == order_id), None)
            
            if not order:
                return {"status": "error", "message": f"Order {order_id} not found"}
            
            return {
                "status": "success",
                "data": {
                    "order_id": order.order_id,
                    "symbol": order.symbol,
                    "side": order.side,
                    "quantity": order.quantity,
                    "filled_quantity": order.filled_quantity,
                    "fill_pct": order.fill_pct,
                    "avg_fill_price": order.avg_fill_price,
                    "status": order.status,
                    "order_type": order.order_type,
                    "submitted_at": order.submitted_at.isoformat(),
                    "updated_at": order.updated_at.isoformat(),
                    "slippage_bps": order.slippage_bps,
                }
            }
        except Exception as e:
            logger.error(f"Error in get_order: {e}")
            return {"status": "error", "message": str(e)}
    
    def get_trades(self, limit: int = 50) -> Dict[str, Any]:
        """GET /api/dashboard/trades - Get recent trades."""
        try:
            trades = self.dashboard_service._get_recent_trades(limit)
            return {
                "status": "success",
                "data": [
                    {
                        "trade_id": t.trade_id,
                        "symbol": t.symbol,
                        "side": t.side,
                        "quantity": t.quantity,
                        "entry_price": t.entry_price,
                        "exit_price": t.exit_price,
                        "pnl": t.pnl,
                        "pnl_pct": t.pnl_pct,
                        "duration_seconds": t.duration_seconds,
                        "filled_at": t.filled_at.isoformat(),
                        "closed_at": t.closed_at.isoformat() if t.closed_at else None,
                        "status": t.status,
                    }
                    for t in trades
                ]
            }
        except Exception as e:
            logger.error(f"Error in get_trades: {e}")
            return {"status": "error", "message": str(e)}
    
    def get_performance(self) -> Dict[str, Any]:
        """GET /api/dashboard/performance - Get performance metrics."""
        try:
            metrics = self.dashboard_service._get_performance_metrics()
            return {
                "status": "success",
                "data": {
                    "total_return_pct": metrics.total_return_pct,
                    "daily_return_pct": metrics.daily_return_pct,
                    "ytd_return_pct": metrics.ytd_return_pct,
                    "sharpe_ratio": metrics.sharpe_ratio,
                    "max_drawdown_pct": metrics.max_drawdown_pct,
                    "win_rate_pct": metrics.win_rate_pct,
                    "profit_factor": metrics.profit_factor,
                    "avg_win_pct": metrics.avg_win_pct,
                    "avg_loss_pct": metrics.avg_loss_pct,
                    "largest_win_pct": metrics.largest_win_pct,
                    "largest_loss_pct": metrics.largest_loss_pct,
                    "total_trades": metrics.total_trades,
                    "winning_trades": metrics.winning_trades,
                    "losing_trades": metrics.losing_trades,
                }
            }
        except Exception as e:
            logger.error(f"Error in get_performance: {e}")
            return {"status": "error", "message": str(e)}
    
    def get_risk(self) -> Dict[str, Any]:
        """GET /api/dashboard/risk - Get risk metrics."""
        try:
            risk = self.dashboard_service._get_risk_metrics()
            return {
                "status": "success",
                "data": {
                    "var_95": risk.var_95,
                    "cvar_95": risk.cvar_95,
                    "beta": risk.beta,
                    "volatility_pct": risk.volatility_pct,
                    "correlation_spy": risk.correlation_spy,
                    "max_position_loss": risk.max_position_loss,
                    "portfolio_concentration": risk.portfolio_concentration,
                    "sector_concentration": risk.sector_concentration,
                }
            }
        except Exception as e:
            logger.error(f"Error in get_risk: {e}")
            return {"status": "error", "message": str(e)}
    
    def get_alerts(self) -> Dict[str, Any]:
        """GET /api/dashboard/alerts - Get active alerts."""
        try:
            alerts = self.dashboard_service._get_alerts()
            return {
                "status": "success",
                "data": alerts
            }
        except Exception as e:
            logger.error(f"Error in get_alerts: {e}")
            return {"status": "error", "message": str(e)}
    
    # Chart data endpoints
    
    def get_portfolio_chart(self, period: str = "1d", interval: str = "1m") -> Dict[str, Any]:
        """GET /api/dashboard/charts/portfolio - Get portfolio performance chart."""
        try:
            data = self.dashboard_service.get_performance_chart_data(period, interval)
            return {"status": "success", "data": data}
        except Exception as e:
            logger.error(f"Error in get_portfolio_chart: {e}")
            return {"status": "error", "message": str(e)}
    
    def get_positions_chart(self) -> Dict[str, Any]:
        """GET /api/dashboard/charts/positions - Get position allocation chart."""
        try:
            data = self.dashboard_service.get_positions_chart_data()
            return {"status": "success", "data": data}
        except Exception as e:
            logger.error(f"Error in get_positions_chart: {e}")
            return {"status": "error", "message": str(e)}
    
    # WebSocket management
    
    async def set_price_alert(self, symbol: str, high: Optional[float] = None, low: Optional[float] = None) -> Dict[str, Any]:
        """POST /api/dashboard/alerts/price - Set price alert."""
        try:
            self.real_time_service.set_price_alert(symbol, high, low)
            return {"status": "success", "message": f"Price alert set for {symbol}"}
        except Exception as e:
            logger.error(f"Error in set_price_alert: {e}")
            return {"status": "error", "message": str(e)}
    
    async def remove_price_alert(self, symbol: str) -> Dict[str, Any]:
        """DELETE /api/dashboard/alerts/price/{symbol} - Remove price alert."""
        try:
            self.real_time_service.remove_price_alert(symbol)
            return {"status": "success", "message": f"Price alert removed for {symbol}"}
        except Exception as e:
            logger.error(f"Error in remove_price_alert: {e}")
            return {"status": "error", "message": str(e)}
    
    def get_event_history(self) -> Dict[str, Any]:
        """GET /api/dashboard/events - Get recent events."""
        try:
            events = self.real_time_service.get_event_history()
            return {
                "status": "success",
                "data": [
                    {
                        "event_type": e.event_type.value,
                        "timestamp": e.timestamp.isoformat(),
                        "data": e.data,
                    }
                    for e in events
                ]
            }
        except Exception as e:
            logger.error(f"Error in get_event_history: {e}")
            return {"status": "error", "message": str(e)}
