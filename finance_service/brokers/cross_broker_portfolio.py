"""
Cross-Broker Portfolio Manager

This module provides unified portfolio management across multiple brokers,
enabling consolidated position tracking, P&L calculation, and risk management.

Key Features:
- Cross-broker position consolidation
- Unified P&L calculation
- Real-time portfolio valuation
- Risk monitoring and alerts
- Portfolio performance tracking
- Asset allocation analysis

Author: PicotradeAgent
Version: 6.3.0
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
import json

from finance_service.brokers.multi_broker_manager import BrokerType
from finance_service.brokers.base_broker import Position, AccountInfo, MarketData, AssetType
from finance_service.core.events import Event, EventType, EventManager


class PortfolioMetric(str, Enum):
    """Portfolio metrics"""
    TOTAL_VALUE = "TOTAL_VALUE"
    TOTAL_PNL = "TOTAL_PNL"
    DAILY_PNL = "DAILY_PNL"
    UNREALIZED_PNL = "UNREALIZED_PNL"
    REALIZED_PNL = "REALIZED_PNL"
    CASH_BALANCE = "CASH_BALANCE"
    BUYING_POWER = "BUYING_POWER"
    LEVERAGE_RATIO = "LEVERAGE_RATIO"
    CONCENTRATION_RATIO = "CONCENTRATION_RATIO"
    SHARPE_RATIO = "SHARPE_RATIO"


class RiskAlertType(str, Enum):
    """Risk alert types"""
    POSITION_LIMIT = "POSITION_LIMIT"
    CONCENTRATION = "CONCENTRATION"
    DRAWDOWN = "DRAWDOWN"
    MARGIN_CALL = "MARGIN_CALL"
    LEVERAGE = "LEVERAGE"
    SECTOR_EXPOSURE = "SECTOR_EXPOSURE"


@dataclass
class PortfolioPosition:
    """Unified portfolio position"""
    symbol: str
    asset_type: AssetType
    total_quantity: float
    avg_price: float
    market_price: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float
    position_weights: Dict[str, float]  # broker -> weight
    last_updated: datetime
    
    @property
    def pnl_percent(self) -> float:
        if self.avg_price == 0:
            return 0.0
        return (self.market_price - self.avg_price) / self.avg_price * 100
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "asset_type": self.asset_type.value,
            "total_quantity": self.total_quantity,
            "avg_price": self.avg_price,
            "market_price": self.market_price,
            "market_value": self.market_value,
            "unrealized_pnl": self.unrealized_pnl,
            "realized_pnl": self.realized_pnl,
            "pnl_percent": self.pnl_percent,
            "position_weights": self.position_weights,
            "last_updated": self.last_updated.isoformat()
        }


@dataclass
class PortfolioAccount:
    """Unified portfolio account"""
    broker: str
    account_id: str
    cash_balance: float
    buying_power: float
    total_value: float
    margin_used: float
    available_margin: float
    day_trade_count: int
    last_updated: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "broker": self.broker,
            "account_id": self.account_id,
            "cash_balance": self.cash_balance,
            "buying_power": self.buying_power,
            "total_value": self.total_value,
            "margin_used": self.margin_used,
            "available_margin": self.available_margin,
            "day_trade_count": self.day_trade_count,
            "last_updated": self.last_updated.isoformat()
        }


@dataclass
class PortfolioMetrics:
    """Portfolio performance metrics"""
    total_value: float = 0.0
    total_pnl: float = 0.0
    daily_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    cash_balance: float = 0.0
    buying_power: float = 0.0
    leverage_ratio: float = 0.0
    concentration_ratio: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    last_updated: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_value": self.total_value,
            "total_pnl": self.total_pnl,
            "daily_pnl": self.daily_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "realized_pnl": self.realized_pnl,
            "cash_balance": self.cash_balance,
            "buying_power": self.buying_power,
            "leverage_ratio": self.leverage_ratio,
            "concentration_ratio": self.concentration_ratio,
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown": self.max_drawdown,
            "win_rate": self.win_rate,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "last_updated": self.last_updated.isoformat()
        }


@dataclass
class RiskAlert:
    """Risk alert"""
    alert_type: RiskAlertType
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    message: str
    symbol: Optional[str] = None
    current_value: Optional[float] = None
    threshold_value: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_type": self.alert_type.value,
            "severity": self.severity,
            "message": self.message,
            "symbol": self.symbol,
            "current_value": self.current_value,
            "threshold_value": self.threshold_value,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class AllocationAnalysis:
    """Asset allocation analysis"""
    by_asset_type: Dict[str, float]  # asset_type -> percentage
    by_sector: Dict[str, float]  # sector -> percentage
    by_geography: Dict[str, float]  # region -> percentage
    by_currency: Dict[str, float]  # currency -> percentage
    concentration_risk: Dict[str, float]  # symbol -> percentage
    diversification_score: float
    last_updated: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "by_asset_type": self.by_asset_type,
            "by_sector": self.by_sector,
            "by_geography": self.by_geography,
            "by_currency": self.by_currency,
            "concentration_risk": self.concentration_risk,
            "diversification_score": self.diversification_score,
            "last_updated": self.last_updated.isoformat()
        }


@dataclass
class CrossBrokerPortfolioConfig:
    """Cross-broker portfolio configuration"""
    # Update settings
    update_interval_seconds: int = 30
    valuation_timeout_seconds: int = 10
    
    # Risk management
    max_position_size_pct: float = 10.0  # Max 10% in single position
    max_sector_exposure_pct: float = 30.0  # Max 30% in single sector
    max_single_broker_exposure_pct: float = 60.0  # Max 60% with single broker
    max_leverage_ratio: float = 4.0  # Max 4:1 leverage
    max_drawdown_pct: float = 20.0  # Max 20% drawdown
    
    # Alerts
    enable_risk_alerts: bool = True
    alert_cooldown_minutes: int = 15
    
    # Performance tracking
    track_performance_history: bool = True
    performance_history_days: int = 365
    benchmark_symbol: str = "SPY"
    
    # Market data
    require_market_data: bool = True
    market_data_timeout_seconds: int = 5
    
    # Logging
    log_level: str = "INFO"
    log_portfolio_updates: bool = False


class CrossBrokerPortfolio:
    """
    Cross-Broker Portfolio Manager
    
    Provides unified portfolio management across multiple brokers with consolidated
    positions, P&L calculation, risk monitoring, and performance tracking.
    """
    
    def __init__(self, config: CrossBrokerPortfolioConfig, event_manager: EventManager):
        self.config = config
        self.event_manager = event_manager
        self.logger = logging.getLogger(f"{__name__}.CrossBrokerPortfolio")
        
        # Portfolio data
        self.positions: Dict[str, PortfolioPosition] = {}
        self.accounts: Dict[str, PortfolioAccount] = {}
        self.metrics: PortfolioMetrics = PortfolioMetrics()
        self.allocation: AllocationAnalysis = AllocationAnalysis(
            by_asset_type={},
            by_sector={},
            by_geography={},
            by_currency={},
            concentration_risk={},
            diversification_score=0.0
        )
        
        # Risk management
        self.risk_alerts: List[RiskAlert] = []
        self.last_alert_times: Dict[str, datetime] = {}
        
        # Performance tracking
        self.performance_history: List[PortfolioMetrics] = []
        self.daily_pnl_history: List[float] = []
        
        # Broker data cache
        self.broker_positions: Dict[BrokerType, List[Position]] = {}
        self.broker_accounts: Dict[BrokerType, AccountInfo] = {}
        self.broker_market_data: Dict[str, MarketData] = {}
        
        # Threading and async support
        self.executor = ThreadPoolExecutor(max_workers=3)
        self._shutdown_event = asyncio.Event()
        self._update_lock = asyncio.Lock()
        
        # Performance tracking
        self.update_count: int = 0
        self.last_update_time: Optional[datetime] = None
        
        self.logger.info("Cross-Broker Portfolio Manager initialized")
    
    async def update_portfolio(self, broker_positions: Dict[BrokerType, List[Position]], 
                             broker_accounts: Dict[BrokerType, AccountInfo],
                             market_data: Dict[str, MarketData]) -> bool:
        """
        Update portfolio with latest broker data
        
        Args:
            broker_positions: Positions from each broker
            broker_accounts: Account info from each broker
            market_data: Current market data
            
        Returns:
            bool: True if update successful
        """
        try:
            async with self._update_lock:
                self.logger.debug("Updating cross-broker portfolio")
                
                # Store broker data
                self.broker_positions = broker_positions
                self.broker_accounts = broker_accounts
                self.broker_market_data = market_data
                
                # Update positions
                await self._update_positions()
                
                # Update accounts
                await self._update_accounts()
                
                # Calculate metrics
                await self._calculate_metrics()
                
                # Update allocation
                await self._update_allocation()
                
                # Check risk alerts
                if self.config.enable_risk_alerts:
                    await self._check_risk_alerts()
                
                # Update performance history
                if self.config.track_performance_history:
                    await self._update_performance_history()
                
                # Update tracking
                self.update_count += 1
                self.last_update_time = datetime.now()
                
                # Publish event
                self.event_manager.publish(Event(
                    event_type=EventType.PORTFOLIO_UPDATED,
                    data={
                        "total_value": self.metrics.total_value,
                        "total_pnl": self.metrics.total_pnl,
                        "position_count": len(self.positions),
                        "account_count": len(self.accounts),
                        "update_count": self.update_count
                    }
                ))
                
                if self.config.log_portfolio_updates:
                    self.logger.info(f"Portfolio updated: ${self.metrics.total_value:,.2f} ({self.metrics.total_pnl:+.2f})")
                
                return True
                
        except Exception as e:
            self.logger.error(f"Error updating portfolio: {e}")
            return False
    
    async def get_positions(self, symbol: Optional[str] = None) -> List[PortfolioPosition]:
        """
        Get portfolio positions
        
        Args:
            symbol: Optional symbol filter
            
        Returns:
            List[PortfolioPosition]: Portfolio positions
        """
        try:
            if symbol:
                position = self.positions.get(symbol)
                return [position] if position else []
            else:
                return list(self.positions.values())
                
        except Exception as e:
            self.logger.error(f"Error getting positions: {e}")
            return []
    
    async def get_accounts(self) -> List[PortfolioAccount]:
        """Get portfolio accounts"""
        try:
            return list(self.accounts.values())
        except Exception as e:
            self.logger.error(f"Error getting accounts: {e}")
            return []
    
    def get_metrics(self) -> PortfolioMetrics:
        """Get portfolio metrics"""
        return self.metrics
    
    def get_allocation(self) -> AllocationAnalysis:
        """Get allocation analysis"""
        return self.allocation
    
    def get_risk_alerts(self, severity: Optional[str] = None) -> List[RiskAlert]:
        """
        Get risk alerts
        
        Args:
            severity: Optional severity filter
            
        Returns:
            List[RiskAlert]: Risk alerts
        """
        try:
            if severity:
                return [alert for alert in self.risk_alerts if alert.severity == severity]
            else:
                return self.risk_alerts.copy()
                
        except Exception as e:
            self.logger.error(f"Error getting risk alerts: {e}")
            return []
    
    def get_performance_summary(self, days: int = 30) -> Dict[str, Any]:
        """
        Get performance summary
        
        Args:
            days: Number of days to analyze
            
        Returns:
            Dict[str, Any]: Performance summary
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            # Get recent performance data
            recent_metrics = [
                metrics for metrics in self.performance_history
                if metrics.last_updated >= cutoff_date
            ]
            
            # Calculate summary statistics
            if recent_metrics:
                total_returns = [
                    (metrics.total_value / recent_metrics[0].total_value - 1) * 100
                    for metrics in recent_metrics
                ]
                
                max_value = max(metrics.total_value for metrics in recent_metrics)
                min_value = min(metrics.total_value for metrics in recent_metrics)
                max_drawdown = ((max_value - min_value) / max_value) * 100
                
                daily_returns = []
                for i in range(1, len(recent_metrics)):
                    daily_return = (
                        (recent_metrics[i].total_value - recent_metrics[i-1].total_value) / 
                        recent_metrics[i-1].total_value * 100
                    )
                    daily_returns.append(daily_return)
                
                avg_daily_return = sum(daily_returns) / len(daily_returns) if daily_returns else 0.0
                volatility = (sum(r**2 for r in daily_returns) / len(daily_returns))**0.5 if daily_returns else 0.0
                sharpe_ratio = avg_daily_return / volatility if volatility > 0 else 0.0
                
            else:
                total_returns = []
                max_drawdown = 0.0
                avg_daily_return = 0.0
                volatility = 0.0
                sharpe_ratio = 0.0
            
            return {
                "period_days": days,
                "total_return_pct": total_returns[-1] if total_returns else 0.0,
                "max_drawdown_pct": max_drawdown,
                "avg_daily_return_pct": avg_daily_return,
                "volatility_pct": volatility,
                "sharpe_ratio": sharpe_ratio,
                "total_trades": self.metrics.total_trades,
                "win_rate_pct": self.metrics.win_rate,
                "current_value": self.metrics.total_value,
                "current_pnl": self.metrics.total_pnl
            }
            
        except Exception as e:
            self.logger.error(f"Error getting performance summary: {e}")
            return {}
    
    async def rebalance_portfolio(self, target_allocation: Dict[str, float], 
                                tolerance_pct: float = 5.0) -> List[Dict[str, Any]]:
        """
        Rebalance portfolio to target allocation
        
        Args:
            target_allocation: Target allocation by asset type or symbol
            tolerance_pct: Tolerance percentage for rebalancing
            
        Returns:
            List[Dict[str, Any]]: Rebalancing orders needed
        """
        try:
            rebalance_orders = []
            current_allocation = self.allocation.by_asset_type if any(k in ['STOCK', 'CRYPTO', 'OPTION'] for k in target_allocation.keys()) else self.allocation.concentration_risk
            
            for target_asset, target_pct in target_allocation.items():
                current_pct = current_allocation.get(target_asset, 0.0)
                deviation = abs(current_pct - target_pct)
                
                if deviation > tolerance_pct:
                    # Calculate rebalance amount
                    current_value = self.metrics.total_value * (current_pct / 100)
                    target_value = self.metrics.total_value * (target_pct / 100)
                    difference = target_value - current_value
                    
                    if abs(difference) > 100:  # Only rebalance if difference > $100
                        order = {
                            "action": "BUY" if difference > 0 else "SELL",
                            "asset": target_asset,
                            "amount": abs(difference),
                            "current_allocation_pct": current_pct,
                            "target_allocation_pct": target_pct,
                            "deviation_pct": deviation
                        }
                        rebalance_orders.append(order)
            
            if rebalance_orders:
                self.logger.info(f"Portfolio rebalancing needed: {len(rebalance_orders)} orders")
            
            return rebalance_orders
            
        except Exception as e:
            self.logger.error(f"Error in portfolio rebalancing: {e}")
            return []
    
    def add_risk_callback(self, callback: Callable):
        """Add risk alert callback"""
        # This would register a callback for risk alerts
        # Implementation depends on specific requirements
        pass
    
    def get_portfolio_summary(self) -> Dict[str, Any]:
        """Get comprehensive portfolio summary"""
        try:
            return {
                "metrics": self.metrics.to_dict(),
                "allocation": self.allocation.to_dict(),
                "positions_count": len(self.positions),
                "accounts_count": len(self.accounts),
                "risk_alerts_count": len(self.risk_alerts),
                "last_update": self.last_update_time.isoformat() if self.last_update_time else None,
                "update_count": self.update_count,
                "performance_summary": self.get_performance_summary(),
                "top_positions": self._get_top_positions(10),
                "broker_exposure": self._get_broker_exposure()
            }
            
        except Exception as e:
            self.logger.error(f"Error getting portfolio summary: {e}")
            return {}
    
    async def _update_positions(self):
        """Update portfolio positions"""
        try:
            # Consolidate positions by symbol
            symbol_positions: Dict[str, List[Position]] = {}
            
            for broker_type, positions in self.broker_positions.items():
                for position in positions:
                    symbol = position.symbol
                    if symbol not in symbol_positions:
                        symbol_positions[symbol] = []
                    symbol_positions[symbol].append(position)
            
            # Create unified positions
            new_positions = {}
            
            for symbol, broker_positions in symbol_positions.items():
                # Calculate consolidated quantities and weighted average price
                total_quantity = 0.0
                total_value = 0.0
                total_pnl = 0.0
                position_weights = {}
                
                for position in broker_positions:
                    quantity = position.quantity
                    market_value = position.market_value
                    pnl = position.unrealized_pnl
                    
                    total_quantity += quantity
                    total_value += market_value
                    total_pnl += pnl
                    
                    broker = position.broker
                    position_weights[broker] = quantity
                
                # Get current market price
                market_price = 0.0
                if symbol in self.broker_market_data:
                    market_price = self.broker_market_data[symbol].last
                elif broker_positions:
                    # Fallback to first position's avg price
                    market_price = broker_positions[0].avg_price
                
                # Calculate weighted average price
                avg_price = total_value / total_quantity if total_quantity != 0 else 0.0
                
                # Create portfolio position
                portfolio_position = PortfolioPosition(
                    symbol=symbol,
                    asset_type=broker_positions[0].asset_type,
                    total_quantity=total_quantity,
                    avg_price=avg_price,
                    market_price=market_price,
                    market_value=total_value,
                    unrealized_pnl=total_pnl,
                    realized_pnl=sum(p.realized_pnl for p in broker_positions),
                    position_weights=position_weights,
                    last_updated=datetime.now()
                )
                
                new_positions[symbol] = portfolio_position
            
            self.positions = new_positions
            
        except Exception as e:
            self.logger.error(f"Error updating positions: {e}")
    
    async def _update_accounts(self):
        """Update portfolio accounts"""
        try:
            new_accounts = {}
            
            for broker_type, account_info in self.broker_accounts.items():
                portfolio_account = PortfolioAccount(
                    broker=broker_type.value,
                    account_id=account_info.account_id,
                    cash_balance=account_info.cash_balance,
                    buying_power=account_info.buying_power,
                    total_value=account_info.total_value,
                    margin_used=account_info.maintenance_margin,
                    available_margin=account_info.buying_power - account_info.maintenance_margin,
                    day_trade_count=account_info.day_trade_count,
                    last_updated=datetime.now()
                )
                
                new_accounts[f"{broker_type.value}_{account_info.account_id}"] = portfolio_account
            
            self.accounts = new_accounts
            
        except Exception as e:
            self.logger.error(f"Error updating accounts: {e}")
    
    async def _calculate_metrics(self):
        """Calculate portfolio metrics"""
        try:
            # Calculate totals
            total_value = sum(account.total_value for account in self.accounts.values())
            total_cash = sum(account.cash_balance for account in self.accounts.values())
            total_buying_power = sum(account.buying_power for account in self.accounts.values())
            total_unrealized_pnl = sum(position.unrealized_pnl for position in self.positions.values())
            total_realized_pnl = sum(position.realized_pnl for position in self.positions.values())
            
            # Calculate daily P&L (simplified)
            daily_pnl = 0.0
            if self.performance_history:
                previous_value = self.performance_history[-1].total_value
                daily_pnl = total_value - previous_value
            
            # Calculate leverage ratio
            leverage_ratio = total_buying_power / total_value if total_value > 0 else 0.0
            
            # Calculate concentration ratio
            concentration_ratio = 0.0
            if self.positions:
                max_position_value = max(position.market_value for position in self.positions.values())
                concentration_ratio = (max_position_value / total_value * 100) if total_value > 0 else 0.0
            
            # Update metrics
            self.metrics = PortfolioMetrics(
                total_value=total_value,
                total_pnl=total_unrealized_pnl + total_realized_pnl,
                daily_pnl=daily_pnl,
                unrealized_pnl=total_unrealized_pnl,
                realized_pnl=total_realized_pnl,
                cash_balance=total_cash,
                buying_power=total_buying_power,
                leverage_ratio=leverage_ratio,
                concentration_ratio=concentration_ratio,
                last_updated=datetime.now()
            )
            
        except Exception as e:
            self.logger.error(f"Error calculating metrics: {e}")
    
    async def _update_allocation(self):
        """Update allocation analysis"""
        try:
            if not self.positions or self.metrics.total_value == 0:
                return
            
            # Reset allocation
            by_asset_type = {}
            by_sector = {}
            by_geography = {}
            by_currency = {}
            concentration_risk = {}
            
            # Calculate allocations
            for position in self.positions.values():
                weight_pct = (position.market_value / self.metrics.total_value) * 100
                
                # By asset type
                asset_type = position.asset_type.value
                by_asset_type[asset_type] = by_asset_type.get(asset_type, 0.0) + weight_pct
                
                # Concentration risk
                concentration_risk[position.symbol] = weight_pct
                
                # Sector and geography would need additional data sources
                # For now, using simplified mappings
                sector = self._get_sector_for_symbol(position.symbol)
                by_sector[sector] = by_sector.get(sector, 0.0) + weight_pct
                
                region = self._get_region_for_symbol(position.symbol)
                by_geography[region] = by_geography.get(region, 0.0) + weight_pct
                
                currency = self._get_currency_for_symbol(position.symbol)
                by_currency[currency] = by_currency.get(currency, 0.0) + weight_pct
            
            # Calculate diversification score
            diversification_score = self._calculate_diversification_score(by_asset_type, concentration_risk)
            
            self.allocation = AllocationAnalysis(
                by_asset_type=by_asset_type,
                by_sector=by_sector,
                by_geography=by_geography,
                by_currency=by_currency,
                concentration_risk=concentration_risk,
                diversification_score=diversification_score,
                last_updated=datetime.now()
            )
            
        except Exception as e:
            self.logger.error(f"Error updating allocation: {e}")
    
    async def _check_risk_alerts(self):
        """Check for risk alerts"""
        try:
            current_time = datetime.now()
            
            # Position size alerts
            for position in self.positions.values():
                weight_pct = (position.market_value / self.metrics.total_value * 100) if self.metrics.total_value > 0 else 0.0
                
                if weight_pct > self.config.max_position_size_pct:
                    await self._create_risk_alert(
                        RiskAlertType.POSITION_LIMIT,
                        "HIGH",
                        f"Position {position.symbol} exceeds limit: {weight_pct:.1f}% > {self.config.max_position_size_pct}%",
                        position.symbol,
                        weight_pct,
                        self.config.max_position_size_pct
                    )
            
            # Concentration alerts
            if self.metrics.concentration_ratio > self.config.max_sector_exposure_pct:
                await self._create_risk_alert(
                    RiskAlertType.CONCENTRATION,
                    "MEDIUM",
                    f"Portfolio concentration too high: {self.metrics.concentration_ratio:.1f}%",
                    None,
                    self.metrics.concentration_ratio,
                    self.config.max_sector_exposure_pct
                )
            
            # Leverage alerts
            if self.metrics.leverage_ratio > self.config.max_leverage_ratio:
                await self._create_risk_alert(
                    RiskAlertType.LEVERAGE,
                    "HIGH",
                    f"Leverage ratio too high: {self.metrics.leverage_ratio:.2f} > {self.config.max_leverage_ratio:.2f}",
                    None,
                    self.metrics.leverage_ratio,
                    self.config.max_leverage_ratio
                )
            
            # Clean old alerts
            self.risk_alerts = [
                alert for alert in self.risk_alerts
                if (current_time - alert.timestamp).total_seconds() < 86400  # Keep alerts for 24 hours
            ]
            
        except Exception as e:
            self.logger.error(f"Error checking risk alerts: {e}")
    
    async def _create_risk_alert(self, alert_type: RiskAlertType, severity: str, message: str,
                               symbol: Optional[str], current_value: Optional[float], 
                               threshold_value: Optional[float]):
        """Create a risk alert"""
        try:
            # Check cooldown
            alert_key = f"{alert_type.value}_{symbol or 'PORTFOLIO'}"
            last_alert_time = self.last_alert_times.get(alert_key)
            
            if last_alert_time:
                cooldown_seconds = self.config.alert_cooldown_minutes * 60
                if (datetime.now() - last_alert_time).total_seconds() < cooldown_seconds:
                    return  # Skip due to cooldown
            
            # Create alert
            alert = RiskAlert(
                alert_type=alert_type,
                severity=severity,
                message=message,
                symbol=symbol,
                current_value=current_value,
                threshold_value=threshold_value
            )
            
            self.risk_alerts.append(alert)
            self.last_alert_times[alert_key] = datetime.now()
            
            # Publish event
            self.event_manager.publish(Event(
                event_type=EventType.RISK_ALERT,
                data=alert.to_dict()
            ))
            
            self.logger.warning(f"Risk alert: {message}")
            
        except Exception as e:
            self.logger.error(f"Error creating risk alert: {e}")
    
    async def _update_performance_history(self):
        """Update performance history"""
        try:
            # Add current metrics to history
            self.performance_history.append(self.metrics)
            
            # Keep only recent history
            cutoff_date = datetime.now() - timedelta(days=self.config.performance_history_days)
            self.performance_history = [
                metrics for metrics in self.performance_history
                if metrics.last_updated >= cutoff_date
            ]
            
            # Update daily P&L history
            if self.performance_history:
                daily_pnl = self.metrics.daily_pnl
                self.daily_pnl_history.append(daily_pnl)
                
                # Keep only recent daily P&L
                if len(self.daily_pnl_history) > self.config.performance_history_days:
                    self.daily_pnl_history = self.daily_pnl_history[-self.config.performance_history_days:]
            
        except Exception as e:
            self.logger.error(f"Error updating performance history: {e}")
    
    def _get_sector_for_symbol(self, symbol: str) -> str:
        """Get sector for symbol (simplified)"""
        # This would use a proper sector classification service
        # For now, using simple heuristics
        tech_symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META']
        finance_symbols = ['JPM', 'BAC', 'WFC', 'GS', 'MS']
        
        symbol_upper = symbol.upper()
        if any(tech in symbol_upper for tech in tech_symbols):
            return "Technology"
        elif any(fin in symbol_upper for fin in finance_symbols):
            return "Financials"
        else:
            return "Other"
    
    def _get_region_for_symbol(self, symbol: str) -> str:
        """Get region for symbol (simplified)"""
        # This would use proper geographic classification
        if symbol.upper() in ['BTC', 'ETH', 'LTC']:
            return "Global"
        else:
            return "US"
    
    def _get_currency_for_symbol(self, symbol: str) -> str:
        """Get currency for symbol (simplified)"""
        if symbol.upper() in ['BTC', 'ETH', 'LTC', 'XRP', 'ADA', 'DOT']:
            return "CRYPTO"
        else:
            return "USD"
    
    def _calculate_diversification_score(self, by_asset_type: Dict[str, float], 
                                       concentration_risk: Dict[str, float]) -> float:
        """Calculate diversification score (0.0 to 1.0)"""
        try:
            # Score based on asset type diversification
            asset_type_count = len([pct for pct in by_asset_type.values() if pct > 5.0])
            asset_type_score = min(asset_type_count / 4.0, 1.0)  # Max score for 4+ asset types
            
            # Score based on concentration (lower concentration = higher score)
            max_concentration = max(concentration_risk.values()) if concentration_risk else 0.0
            concentration_score = max(0.0, 1.0 - (max_concentration / 20.0))  # Penalty for >20% single position
            
            # Combined score
            diversification_score = (asset_type_score + concentration_score) / 2.0
            return min(1.0, max(0.0, diversification_score))
            
        except Exception as e:
            self.logger.error(f"Error calculating diversification score: {e}")
            return 0.0
    
    def _get_top_positions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top positions by value"""
        try:
            sorted_positions = sorted(
                self.positions.values(),
                key=lambda p: p.market_value,
                reverse=True
            )
            
            return [position.to_dict() for position in sorted_positions[:limit]]
            
        except Exception as e:
            self.logger.error(f"Error getting top positions: {e}")
            return []
    
    def _get_broker_exposure(self) -> Dict[str, float]:
        """Get exposure by broker"""
        try:
            broker_exposure = {}
            total_value = self.metrics.total_value
            
            for account in self.accounts.values():
                if total_value > 0:
                    exposure_pct = (account.total_value / total_value) * 100
                    broker_exposure[account.broker] = exposure_pct
            
            return broker_exposure
            
        except Exception as e:
            self.logger.error(f"Error getting broker exposure: {e}")
            return {}
    
    async def close(self):
        """Close the portfolio manager"""
        self._shutdown_event.set()
        self.logger.info("Cross-Broker Portfolio Manager closed")