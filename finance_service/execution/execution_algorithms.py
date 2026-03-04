"""
Execution Algorithms - Phase 6.5

Implementations of TWAP, VWAP, ICEBERG, and other algorithms.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from abc import ABC, abstractmethod

from .order_optimization import (
    ExecutionAlgorithm,
    ExecutionConfig,
    ExecutionSlice,
)

logger = logging.getLogger(__name__)


class BaseAlgorithm(ABC):
    """Base class for execution algorithms."""
    
    def __init__(self, config: ExecutionConfig):
        """
        Initialize algorithm.
        
        Args:
            config: Execution configuration
        """
        self.config = config
        self.slices: List[ExecutionSlice] = []
        self.total_filled = 0.0
        self.execution_start = None
        self.execution_end = None
    
    @abstractmethod
    def generate_slices(
        self,
        order_id: str,
        symbol: str,
        side: str,
        quantity: float,
        current_price: float,
        market_data: Dict
    ) -> List[ExecutionSlice]:
        """
        Generate execution slices for the order.
        
        Args:
            order_id: Parent order ID
            symbol: Stock symbol
            side: BUY or SELL
            quantity: Total shares to execute
            current_price: Current market price
            market_data: Market information (volume, volatility, etc.)
            
        Returns:
            List of ExecutionSlice objects
        """
        pass
    
    @abstractmethod
    def should_adjust_slices(self, market_data: Dict) -> bool:
        """Check if slices should be adjusted based on market conditions."""
        pass
    
    @abstractmethod
    def adjust_slices(self, market_data: Dict):
        """Adjust slice timing/sizing based on market conditions."""
        pass
    
    def get_next_slice(self, current_time: datetime) -> Optional[ExecutionSlice]:
        """Get next slice to execute."""
        for slice_ in self.slices:
            if slice_.status == "PENDING" and slice_.scheduled_at <= current_time:
                return slice_
        return None
    
    def mark_slice_submitted(self, slice_id: str, broker_order_id: str, broker: str):
        """Mark slice as submitted."""
        for slice_ in self.slices:
            if slice_.slice_id == slice_id:
                slice_.status = "SUBMITTED"
                slice_.broker_order_id = broker_order_id
                slice_.broker = broker
                break
    
    def mark_slice_filled(self, slice_id: str, filled_qty: float, fill_price: float):
        """Mark slice as filled."""
        for slice_ in self.slices:
            if slice_.slice_id == slice_id:
                slice_.filled_quantity = filled_qty
                slice_.filled_price = fill_price
                slice_.execution_cost = filled_qty * fill_price
                slice_.status = "FILLED"
                slice_.executed_at = datetime.utcnow()
                self.total_filled += filled_qty
                break
    
    def get_total_filled(self) -> float:
        """Get total filled quantity across all slices."""
        return sum(s.filled_quantity for s in self.slices)
    
    def get_average_price(self) -> float:
        """Get weighted average fill price."""
        total_qty = self.get_total_filled()
        if total_qty == 0:
            return 0.0
        
        total_value = sum(s.filled_quantity * s.filled_price for s in self.slices)
        return total_value / total_qty


class TWAPAlgorithm(BaseAlgorithm):
    """
    TWAP (Time-Weighted Average Price) Algorithm.
    
    Splits order into equal-sized slices across time window.
    """
    
    def generate_slices(
        self,
        order_id: str,
        symbol: str,
        side: str,
        quantity: float,
        current_price: float,
        market_data: Dict
    ) -> List[ExecutionSlice]:
        """Generate TWAP slices."""
        self.slices = []
        self.execution_start = datetime.utcnow()
        
        # Calculate slice parameters
        time_window = timedelta(minutes=self.config.time_window_minutes)
        end_time = self.execution_start + time_window
        
        # Determine number of slices (1 per minute, min 2, max 20)
        num_slices = max(2, min(20, self.config.time_window_minutes))
        slice_qty = quantity / num_slices
        slice_interval = time_window / num_slices
        
        # Generate slices
        for i in range(num_slices):
            slice_id = f"SLICE_{order_id}_{i:02d}"
            scheduled_time = self.execution_start + (slice_interval * i)
            
            slice_ = ExecutionSlice(
                slice_id=slice_id,
                parent_order_id=order_id,
                symbol=symbol,
                side=side,
                quantity=slice_qty,
                target_price=current_price,
                estimated_arrival_price=current_price,
                submitted_at=datetime.utcnow(),
                scheduled_at=scheduled_time,
            )
            
            self.slices.append(slice_)
        
        logger.info(
            f"TWAP: Generated {num_slices} slices of {slice_qty:.0f} shares "
            f"over {self.config.time_window_minutes} minutes"
        )
        
        return self.slices
    
    def should_adjust_slices(self, market_data: Dict) -> bool:
        """Check if should adjust based on market conditions."""
        # Check for extreme volatility
        if market_data.get("volatility_pct", 0) > 3.0:
            return True
        
        # Check for volume surge/drop
        volume = market_data.get("volume", 0)
        avg_volume = market_data.get("avg_volume", volume)
        if avg_volume > 0:
            volume_ratio = volume / avg_volume
            if volume_ratio < 0.5 or volume_ratio > 2.0:
                return True
        
        return False
    
    def adjust_slices(self, market_data: Dict):
        """Adjust slices dynamically."""
        # For TWAP, we might increase wait time if volume is low
        volume_ratio = market_data.get("volume", 1) / max(1, market_data.get("avg_volume", 1))
        
        if volume_ratio < 0.5:
            # Low volume - extend execution window
            logger.info("Low volume detected - extending TWAP window")
            for slice_ in self.slices:
                if slice_.status == "PENDING":
                    slice_.scheduled_at = slice_.scheduled_at + timedelta(minutes=2)


class VWAPAlgorithm(BaseAlgorithm):
    """
    VWAP (Volume-Weighted Average Price) Algorithm.
    
    Splits order proportionally to expected volume throughout day.
    """
    
    def generate_slices(
        self,
        order_id: str,
        symbol: str,
        side: str,
        quantity: float,
        current_price: float,
        market_data: Dict
    ) -> List[ExecutionSlice]:
        """Generate VWAP slices."""
        self.slices = []
        self.execution_start = datetime.utcnow()
        
        # Get expected volume distribution (typically higher at open/close)
        volume_profile = market_data.get("volume_profile", [0.1, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.08, 0.15, 0.10])
        
        # Normalize to ensure sum = 1.0
        total_profile = sum(volume_profile)
        volume_profile = [v / total_profile for v in volume_profile]
        
        time_window = timedelta(minutes=self.config.time_window_minutes)
        time_per_slice = time_window / len(volume_profile)
        
        # Generate slices proportional to volume
        for i, volume_pct in enumerate(volume_profile):
            slice_id = f"SLICE_{order_id}_{i:02d}"
            slice_qty = quantity * volume_pct
            scheduled_time = self.execution_start + (time_per_slice * i)
            
            slice_ = ExecutionSlice(
                slice_id=slice_id,
                parent_order_id=order_id,
                symbol=symbol,
                side=side,
                quantity=slice_qty,
                target_price=current_price,
                estimated_arrival_price=current_price,
                submitted_at=datetime.utcnow(),
                scheduled_at=scheduled_time,
            )
            
            self.slices.append(slice_)
        
        logger.info(
            f"VWAP: Generated {len(self.slices)} slices "
            f"weighted by volume profile"
        )
        
        return self.slices
    
    def should_adjust_slices(self, market_data: Dict) -> bool:
        """Check if should adjust based on market conditions."""
        # VWAP is typically not adjusted mid-execution
        return False
    
    def adjust_slices(self, market_data: Dict):
        """Adjust slices (VWAP typically doesn't adjust)."""
        pass


class IcebergAlgorithm(BaseAlgorithm):
    """
    Iceberg Algorithm.
    
    Shows only visible chunk, hides rest of order.
    """
    
    def generate_slices(
        self,
        order_id: str,
        symbol: str,
        side: str,
        quantity: float,
        current_price: float,
        market_data: Dict
    ) -> List[ExecutionSlice]:
        """Generate iceberg slices."""
        self.slices = []
        self.execution_start = datetime.utcnow()
        
        # Calculate chunk size
        if self.config.iceberg_chunk_size > 0:
            chunk_size = self.config.iceberg_chunk_size
        else:
            # Auto: 5-10% of total or 5% of market volume
            market_volume = market_data.get("market_volume", quantity * 10)
            chunk_size = max(
                quantity * 0.05,
                market_volume * 0.05
            )
        
        # Generate hidden slices
        remaining = quantity
        slice_index = 0
        
        while remaining > 0:
            slice_id = f"SLICE_{order_id}_{slice_index:02d}"
            slice_qty = min(chunk_size, remaining)
            
            slice_ = ExecutionSlice(
                slice_id=slice_id,
                parent_order_id=order_id,
                symbol=symbol,
                side=side,
                quantity=slice_qty,
                target_price=current_price,
                estimated_arrival_price=current_price,
                submitted_at=datetime.utcnow(),
                scheduled_at=datetime.utcnow(),  # Immediate for iceberg
            )
            
            self.slices.append(slice_)
            remaining -= slice_qty
            slice_index += 1
        
        logger.info(
            f"Iceberg: Split {quantity:.0f} shares into "
            f"{len(self.slices)} chunks of {chunk_size:.0f}"
        )
        
        return self.slices
    
    def should_adjust_slices(self, market_data: Dict) -> bool:
        """Check if should adjust iceberg chunk size."""
        # Adjust if market volume changes significantly
        volume = market_data.get("volume", 0)
        avg_volume = market_data.get("avg_volume", volume)
        
        if avg_volume > 0:
            ratio = volume / avg_volume
            return ratio < 0.5 or ratio > 1.5
        
        return False
    
    def adjust_slices(self, market_data: Dict):
        """Adjust iceberg visibility."""
        # Could adjust iceberg chunk size based on real-time volume
        pass


class ArrivalPriceAlgorithm(BaseAlgorithm):
    """
    Arrival Price Algorithm.
    
    Attempts to match the price when order was submitted.
    """
    
    def generate_slices(
        self,
        order_id: str,
        symbol: str,
        side: str,
        quantity: float,
        current_price: float,
        market_data: Dict
    ) -> List[ExecutionSlice]:
        """Generate arrival price slices."""
        self.slices = []
        self.execution_start = datetime.utcnow()
        
        # Target is current arrival price
        target_price = current_price
        
        # Use TWAP-like strategy to achieve arrival price
        time_window = timedelta(minutes=self.config.time_window_minutes)
        num_slices = max(2, min(20, self.config.time_window_minutes))
        slice_qty = quantity / num_slices
        slice_interval = time_window / num_slices
        
        for i in range(num_slices):
            slice_id = f"SLICE_{order_id}_{i:02d}"
            scheduled_time = self.execution_start + (slice_interval * i)
            
            slice_ = ExecutionSlice(
                slice_id=slice_id,
                parent_order_id=order_id,
                symbol=symbol,
                side=side,
                quantity=slice_qty,
                target_price=target_price,
                estimated_arrival_price=target_price,
                submitted_at=datetime.utcnow(),
                scheduled_at=scheduled_time,
            )
            
            self.slices.append(slice_)
        
        logger.info(f"Arrival Price: Target {target_price:.2f} using {num_slices} slices")
        
        return self.slices
    
    def should_adjust_slices(self, market_data: Dict) -> bool:
        """Adjust if price deviates too much from target."""
        if not self.slices:
            return False
        
        current_price = market_data.get("price", self.slices[0].target_price)
        target_price = self.slices[0].target_price
        
        # Adjust if price deviates more than 0.5%
        price_deviation = abs(current_price - target_price) / target_price
        return price_deviation > 0.005
    
    def adjust_slices(self, market_data: Dict):
        """Adjust execution pace based on price deviation."""
        current_price = market_data.get("price", 0)
        target_price = self.slices[0].target_price if self.slices else current_price
        
        if target_price == 0:
            return
        
        price_deviation = (current_price - target_price) / target_price
        
        if price_deviation > 0.005:
            # Price moved against us - slow down execution
            logger.info(f"Price deviation +{price_deviation:.2%}, slowing execution")
            for slice_ in self.slices:
                if slice_.status == "PENDING":
                    slice_.scheduled_at = slice_.scheduled_at + timedelta(seconds=30)
        elif price_deviation < -0.005:
            # Price moved in our favor - speed up execution
            logger.info(f"Price deviation {price_deviation:.2%}, accelerating execution")
            for slice_ in self.slices:
                if slice_.status == "PENDING":
                    if slice_.scheduled_at > datetime.utcnow():
                        slice_.scheduled_at = slice_.scheduled_at - timedelta(seconds=15)


class AlgorithmFactory:
    """Factory for creating execution algorithms."""
    
    ALGORITHMS = {
        ExecutionAlgorithm.MARKET: lambda cfg: TWAPAlgorithm(cfg),  # Market = immediate, TWAP ok
        ExecutionAlgorithm.TWAP: TWAPAlgorithm,
        ExecutionAlgorithm.VWAP: VWAPAlgorithm,
        ExecutionAlgorithm.ICEBERG: IcebergAlgorithm,
        ExecutionAlgorithm.ARRIVAL_PRICE: ArrivalPriceAlgorithm,
    }
    
    @staticmethod
    def create_algorithm(config: ExecutionConfig) -> BaseAlgorithm:
        """Create algorithm instance."""
        algo_class = AlgorithmFactory.ALGORITHMS.get(
            config.algorithm,
            TWAPAlgorithm  # Default to TWAP
        )
        
        if callable(algo_class):
            return algo_class(config)
        else:
            return algo_class(config)
