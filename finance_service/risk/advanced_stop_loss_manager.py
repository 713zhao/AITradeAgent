"""
Advanced Stop Loss Manager

Sophisticated stop-loss mechanisms including trailing stops,
volatility-based stops, and time-based exits.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class StopLossOrder:
    """Stop loss order configuration"""
    symbol: str
    stop_type: str  # FIXED, TRAILING, VOLATILITY, TIME_BASED
    entry_price: float
    stop_price: float
    current_price: Optional[float] = None
    trailing_amount: Optional[float] = None
    volatility: Optional[float] = None
    stops_atr: Optional[float] = None
    entry_time: Optional[datetime] = None
    max_holding_hours: Optional[int] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    triggered: bool = False


class AdvancedStopLossManager:
    """
    Advanced stop-loss management system.
    
    Implements multiple stop-loss mechanisms:
    - Trailing stops (follow price up, maintain fixed distance down)
    - Volatility-based stops (adjust to market volatility)
    - Time-based exits (exit after holding period)
    - Multi-timeframe coordination
    """
    
    def __init__(self, config: Dict[str, Any], event_manager):
        self.config = config
        self.event_manager = event_manager
        self.logger = logging.getLogger(__name__)
        
        # Stop loss configuration
        self.stop_config = config.get('stop_loss', {})
        self.trailing_stop_enabled = self.stop_config.get('trailing_stop_enabled', True)
        self.volatility_stop_enabled = self.stop_config.get('volatility_stop_enabled', True)
        self.time_based_exit_enabled = self.stop_config.get('time_based_exit_enabled', True)
        self.max_holding_period = self.stop_config.get('max_holding_period', 30)
        
        # Active stops
        self.active_stops: Dict[str, List[StopLossOrder]] = {}
    
    def create_trailing_stop(self, symbol: str, entry_price: float, 
                            trailing_amount: float) -> Dict[str, Any]:
        """
        Create a trailing stop order.
        
        Trailing stop follows price up but maintains fixed distance on downside.
        """
        stop = StopLossOrder(
            symbol=symbol,
            stop_type='TRAILING',
            entry_price=entry_price,
            stop_price=entry_price - trailing_amount,
            current_price=entry_price,
            trailing_amount=trailing_amount,
        )
        
        # Store stop
        if symbol not in self.active_stops:
            self.active_stops[symbol] = []
        self.active_stops[symbol].append(stop)
        
        self.logger.info(f"Created trailing stop for {symbol}: {entry_price} - {trailing_amount} = {stop.stop_price}")
        
        return {
            'symbol': symbol,
            'stop_type': 'TRAILING',
            'entry_price': entry_price,
            'trailing_amount': trailing_amount,
            'stop_price': stop.stop_price,
            'created_at': stop.created_at.isoformat(),
        }
    
    def create_volatility_stop(self, symbol: str, entry_price: float,
                              volatility: float, stops_atr: float = 2.0) -> Dict[str, Any]:
        """
        Create a volatility-based stop loss.
        
        Stop distance = Entry Price - (Volatility * Stops ATR)
        """
        # Calculate stop distance based on volatility
        # Use ATR multiple of volatility
        stop_distance = (entry_price * volatility) * stops_atr
        stop_price = entry_price - stop_distance
        
        stop = StopLossOrder(
            symbol=symbol,
            stop_type='VOLATILITY',
            entry_price=entry_price,
            stop_price=stop_price,
            current_price=entry_price,
            volatility=volatility,
            stops_atr=stops_atr,
        )
        
        # Store stop
        if symbol not in self.active_stops:
            self.active_stops[symbol] = []
        self.active_stops[symbol].append(stop)
        
        self.logger.info(f"Created volatility stop for {symbol}: {stop_price:.2f} (Vol: {volatility:.2%})")
        
        return {
            'symbol': symbol,
            'stop_type': 'VOLATILITY',
            'entry_price': entry_price,
            'volatility': volatility,
            'stops_atr': stops_atr,
            'stop_distance': stop_distance,
            'stop_price': stop_price,
            'created_at': stop.created_at.isoformat(),
        }
    
    def create_time_based_exit(self, symbol: str, entry_time: datetime,
                              max_holding_hours: int = 24) -> Dict[str, Any]:
        """
        Create a time-based exit order.
        
        Automatically exit position after specified holding period.
        """
        stop = StopLossOrder(
            symbol=symbol,
            stop_type='TIME_BASED',
            entry_price=0.0,  # Not applicable for time-based
            stop_price=0.0,   # Not applicable for time-based
            entry_time=entry_time,
            max_holding_hours=max_holding_hours,
        )
        
        # Store stop
        if symbol not in self.active_stops:
            self.active_stops[symbol] = []
        self.active_stops[symbol].append(stop)
        
        exit_time = entry_time + timedelta(hours=max_holding_hours)
        self.logger.info(f"Created time-based exit for {symbol}: Exit at {exit_time}")
        
        return {
            'symbol': symbol,
            'exit_type': 'TIME_BASED',
            'entry_time': entry_time.isoformat(),
            'max_holding_hours': max_holding_hours,
            'exit_time': exit_time.isoformat(),
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
    
    def update_trailing_stop(self, stop: StopLossOrder, current_price: float) -> Dict[str, Any]:
        """
        Update trailing stop as price moves.
        
        If price goes up, raise stop price. If price goes down, keep stop fixed.
        """
        stop.current_price = current_price
        
        if current_price > stop.entry_price:
            # Price moved up - raise the stop
            new_stop_price = current_price - stop.trailing_amount
            if new_stop_price > stop.stop_price:
                stop.stop_price = new_stop_price
                stop.updated_at = datetime.now(timezone.utc)
        
        return {
            'symbol': stop.symbol,
            'current_price': current_price,
            'stop_price': stop.stop_price,
            'distance': current_price - stop.stop_price,
            'triggered': current_price <= stop.stop_price,
            'updated_at': stop.updated_at.isoformat(),
        }
    
    def check_time_based_exit(self, stop: StopLossOrder) -> Dict[str, Any]:
        """
        Check if time-based exit should be triggered.
        """
        if stop.stop_type != 'TIME_BASED' or not stop.entry_time:
            return {'should_exit': False}
        
        exit_time = stop.entry_time + timedelta(hours=stop.max_holding_hours)
        should_exit = datetime.now(timezone.utc) >= exit_time
        
        return {
            'symbol': stop.symbol,
            'should_exit': should_exit,
            'entry_time': stop.entry_time.isoformat(),
            'exit_time': exit_time.isoformat(),
            'hours_held': (datetime.now(timezone.utc) - stop.entry_time).total_seconds() / 3600,
            'max_hours': stop.max_holding_hours,
        }
    
    def check_stop_triggered(self, stop: StopLossOrder, current_price: float) -> bool:
        """
        Check if stop loss has been triggered.
        """
        if stop.stop_type == 'TIME_BASED':
            return self.check_time_based_exit(stop)['should_exit']
        
        triggered = current_price <= stop.stop_price
        if triggered:
            stop.triggered = True
            self.logger.warning(f"Stop loss triggered for {stop.symbol} at {current_price}")
        
        return triggered
    
    def create_multi_timeframe_stops(self, symbol: str, entry_price: float,
                                    timeframes: List[str], 
                                    stop_loss_pcts: List[float]) -> List[Dict[str, Any]]:
        """
        Create coordinated stops across multiple timeframes.
        
        Each timeframe has its own stop loss percentage.
        Example: 1H stop at 2%, 4H at 3%, 1D at 5%
        """
        stops = []
        
        for timeframe, stop_pct in zip(timeframes, stop_loss_pcts):
            stop_distance = entry_price * stop_pct
            stop_price = entry_price - stop_distance
            
            stop = {
                'symbol': symbol,
                'timeframe': timeframe,
                'entry_price': entry_price,
                'stop_loss_pct': stop_pct,
                'stop_price': stop_price,
                'created_at': datetime.now(timezone.utc).isoformat(),
            }
            stops.append(stop)
        
        self.logger.info(f"Created {len(stops)} multi-timeframe stops for {symbol}")
        
        return stops
    
    def get_active_stops(self, symbol: str) -> List[StopLossOrder]:
        """Get all active stops for a symbol"""
        return self.active_stops.get(symbol, [])
    
    def remove_stop(self, symbol: str, stop_type: str) -> bool:
        """Remove a stop loss order"""
        if symbol not in self.active_stops:
            return False
        
        initial_count = len(self.active_stops[symbol])
        self.active_stops[symbol] = [
            s for s in self.active_stops[symbol] if s.stop_type != stop_type
        ]
        
        removed = initial_count > len(self.active_stops[symbol])
        if removed:
            self.logger.info(f"Removed {stop_type} stop for {symbol}")
        
        return removed
