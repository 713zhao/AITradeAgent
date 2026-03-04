"""
Exposure Manager

Monitors real-time portfolio exposure and risk metrics.
"""

import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class ExposureManager:
    """
    Monitors portfolio exposure and real-time risk metrics.
    
    Responsibilities:
    - Track sector exposure
    - Monitor position correlation
    - Calculate portfolio risk metrics
    - Alert on exposure breaches
    """
    
    def __init__(self):
        """Initialize exposure manager."""
        self.sector_exposure: Dict[str, float] = {}  # sector → % of portfolio
        self.correlation_matrix: Dict[str, Dict[str, float]] = {}  # symbol correlations
        self.position_correlation_threshold = 0.7  # Alert if > 0.7
    
    def update_sector_exposure(
        self,
        positions: Dict[str, Dict[str, Any]],  # symbol → {quantity, price, sector}
        portfolio_equity: float,
    ) -> Dict[str, float]:
        """
        Update sector exposure percentages.
        
        Args:
            positions: Dict of symbol → {quantity, price, sector, ...}
            portfolio_equity: Total portfolio equity
        
        Returns:
            Updated sector_exposure dict
        """
        self.sector_exposure.clear()
        
        if portfolio_equity <= 0:
            return self.sector_exposure
        
        # Group positions by sector and calculate exposure
        sector_values: Dict[str, float] = {}
        for symbol, pos_data in positions.items():
            sector = pos_data.get("sector", "UNKNOWN")
            quantity = pos_data.get("quantity", 0)
            price = pos_data.get("price", 0)
            
            position_value = abs(quantity * price)
            sector_values[sector] = sector_values.get(sector, 0) + position_value
        
        # Convert to percentages
        for sector, value in sector_values.items():
            exposure_pct = (value / portfolio_equity) * 100
            self.sector_exposure[sector] = exposure_pct
        
        return self.sector_exposure
    
    def get_sector_exposure(self, sector: str = None) -> float:
        """
        Get sector exposure percentage.
        
        Args:
            sector: Sector to check (all if None)
        
        Returns:
            Exposure percentage
        """
        if sector is None:
            return sum(self.sector_exposure.values())
        return self.sector_exposure.get(sector, 0.0)
    
    def check_sector_concentration(
        self,
        sector: str,
        new_exposure_pct: float,
        max_sector_pct: float = 25.0,
    ) -> bool:
        """
        Check if sector exposure would exceed limit.
        
        Args:
            sector: Sector to check
            new_exposure_pct: Additional exposure being added
            max_sector_pct: Maximum allowed sector exposure
        
        Returns:
            True if within limit, False if would exceed
        """
        current = self.sector_exposure.get(sector, 0)
        total = current + new_exposure_pct
        
        if total > max_sector_pct:
            logger.warning(
                f"Sector {sector} exposure would be {total:.1f}%, exceeds limit {max_sector_pct:.1f}%"
            )
            return False
        
        return True
    
    def calculate_gross_exposure(self, positions: Dict[str, float]) -> float:
        """
        Calculate gross exposure (sum of absolute position values).
        
        Args:
            positions: Dict of symbol → quantity
        
        Returns:
            Total gross exposure
        """
        return sum(abs(qty) for qty in positions.values())
    
    def calculate_net_exposure(self, positions: Dict[str, float]) -> float:
        """
        Calculate net exposure (long - short).
        
        Args:
            positions: Dict of symbol → quantity
        
        Returns:
            Net exposure (negative for net short)
        """
        return sum(positions.values())
    
    def calculate_leverage(
        self,
        gross_position_value: float,
        portfolio_equity: float,
    ) -> float:
        """
        Calculate portfolio leverage ratio.
        
        Args:
            gross_position_value: Total absolute position value
            portfolio_equity: Portfolio equity
        
        Returns:
            Leverage ratio (e.g., 2.0 = 2x leverage)
        """
        if portfolio_equity <= 0:
            return 0.0
        return gross_position_value / portfolio_equity
    
    def set_correlation_threshold(self, threshold: float) -> None:
        """Set the position correlation threshold for alerts."""
        self.position_correlation_threshold = max(0.0, min(threshold, 1.0))
    
    def check_position_correlation(
        self,
        symbol1: str,
        symbol2: str,
        correlation: float,
    ) -> bool:
        """
        Check if two positions are too correlated (risky).
        
        Args:
            symbol1: First symbol
            symbol2: Second symbol
            correlation: Correlation coefficient (-1 to 1)
        
        Returns:
            True if acceptable, False if concerning
        """
        # Store correlation
        if symbol1 not in self.correlation_matrix:
            self.correlation_matrix[symbol1] = {}
        self.correlation_matrix[symbol1][symbol2] = correlation
        
        # Check if correlation is too high (moves together = concentration risk)
        if abs(correlation) > self.position_correlation_threshold:
            logger.warning(
                f"High correlation between {symbol1} and {symbol2}: {correlation:.2f}"
            )
            return False
        
        return True
    
    def get_exposure_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive exposure summary.
        
        Returns:
            Dict with all exposure metrics
        """
        return {
            "sector_exposure": self.sector_exposure.copy(),
            "total_sector_exposure": sum(self.sector_exposure.values()),
            "correlation_issues": self._get_correlation_issues(),
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    def _get_correlation_issues(self) -> List[Dict[str, Any]]:
        """Find all high-correlation position pairs."""
        issues = []
        for symbol1, correlations in self.correlation_matrix.items():
            for symbol2, correlation in correlations.items():
                if symbol1 < symbol2:  # Avoid duplicates
                    if abs(correlation) > self.position_correlation_threshold:
                        issues.append({
                            "symbol1": symbol1,
                            "symbol2": symbol2,
                            "correlation": correlation,
                        })
        return issues
    
    def clear_exposure_data(self) -> None:
        """Clear all exposure data."""
        self.sector_exposure.clear()
        self.correlation_matrix.clear()
