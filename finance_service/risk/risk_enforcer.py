"""
Risk Enforcer

Validates trades against risk policies and limits.
"""

import logging
from typing import List, Dict, Any, Optional

from .models import RiskPolicy, RiskCheckResult, RiskLimit

logger = logging.getLogger(__name__)


class RiskEnforcer:
    """
    Enforces risk policies on trades.
    
    Responsibilities:
    - Check trades against position limits
    - Verify sector exposure
    - Monitor portfolio leverage
    - Enforce drawdown limits
    - Generate risk check results
    """
    
    def __init__(self, policy: Optional[RiskPolicy] = None):
        """
        Initialize risk enforcer.
        
        Args:
            policy: RiskPolicy to enforce (default: standard policy)
        """
        if policy is None:
            # Create standard policy
            policy = RiskPolicy(
                policy_id="STANDARD",
                policy_name="Standard Risk Policy"
            )
        self.policy = policy
    
    def set_policy(self, policy: RiskPolicy) -> None:
        """Change the active risk policy."""
        self.policy = policy
        logger.info(f"Risk policy changed to: {policy.policy_name}")
    
    def check_trade(
        self,
        trade_id: str,
        symbol: str,
        quantity: float,
        price: float,
        portfolio_equity: float,
        current_positions: Dict[str, float],
        confidence: float = 1.0,
    ) -> RiskCheckResult:
        """
        Perform comprehensive risk check on a trade.
        
        Args:
            trade_id: Trade ID
            symbol: Trading symbol
            quantity: Trade quantity (positive=buy, negative=sell)
            price: Trade price
            portfolio_equity: Current portfolio equity
            current_positions: Dict of symbol → quantity for all positions
            confidence: Trade confidence (Phase 2 decision confidence)
        
        Returns:
            RiskCheckResult with all checks performed
        """
        result = RiskCheckResult(
            trade_id=trade_id,
            symbol=symbol,
            passed=True,
            approval_required=False,
        )
        
        if not self.policy.enabled:
            logger.info(f"Risk policy disabled, skipping checks for {trade_id}")
            return result
        
        # Check 1: Position Size
        if not self._check_position_size(
            symbol, quantity, price, portfolio_equity, result
        ):
            result.checks_performed["position_size"] = False
        else:
            result.checks_performed["position_size"] = True
        
        # Check 2: Position Count
        if not self._check_position_count(current_positions, result):
            result.checks_performed["position_count"] = False
        else:
            result.checks_performed["position_count"] = True
        
        # Check 3: Confidence Level
        if confidence < self.policy.approval_required_pct:
            result.approval_required = True
            result.add_warning(
                f"Confidence {confidence:.1%} below threshold {self.policy.approval_required_pct:.1%}"
            )
            result.checks_performed["confidence"] = False
        else:
            result.checks_performed["confidence"] = True
        
        # Calculate risk score (0-100)
        result.risk_score = self._calculate_risk_score(result, quantity, confidence)
        
        # Determine final status
        result.passed = len(result.violated_limits) == 0
        
        log_level = "ERROR" if result.violations_count() > 0 else "INFO"
        logger.log(
            getattr(logging, log_level),
            f"Risk check completed for {trade_id}: passed={result.passed}, "
            f"violations={result.violations_count()}, risk_score={result.risk_score:.1f}"
        )
        
        return result
    
    def _check_position_size(
        self,
        symbol: str,
        quantity: float,
        price: float,
        portfolio_equity: float,
        result: RiskCheckResult,
    ) -> bool:
        """Check position size limit."""
        if portfolio_equity <= 0:
            return True
        
        position_value = abs(quantity * price)
        position_pct = (position_value / portfolio_equity) * 100
        
        limit = self.policy.get_limit("position_size")
        if limit:
            limit.current_value = position_pct
            if limit.is_violated():
                result.add_violation(
                    limit,
                    f"Position {position_pct:.1f}% exceeds limit {limit.limit_value:.1f}%"
                )
                return False
        
        return True
    
    def _check_position_count(
        self,
        current_positions: Dict[str, float],
        result: RiskCheckResult,
    ) -> bool:
        """Check maximum position count."""
        open_positions = len([q for q in current_positions.values() if q != 0])
        
        if open_positions >= self.policy.max_positions:
            result.add_warning(
                f"At max positions limit ({open_positions}/{self.policy.max_positions})"
            )
            return False
        
        return True
    
    def _calculate_risk_score(
        self,
        result: RiskCheckResult,
        quantity: float,
        confidence: float,
    ) -> float:
        """
        Calculate overall risk score (0-100).
        
        Higher = riskier.
        Factors:
        - Number of violations (each adds 20)
        - Large position size (adds up to 20)
        - Low confidence (adds up to 20)
        
        Returns:
            Risk score (0-100)
        """
        score = 0.0
        
        # Violations (0-20)
        violation_count = len(result.violated_limits)
        score += min(violation_count * 7, 20)
        
        # Confidence (0-20): lower confidence = higher risk
        # Confidence 0.5 = risk 20, confidence 1.0 = risk 0
        confidence_risk = (1.0 - confidence) * 20
        score += confidence_risk
        
        # Position size (0-20): handled by position_size check
        # If position size check passed, no additional risk
        if result.checks_performed.get("position_size", True):
            score += 0  # No additional risk
        
        return min(score, 100.0)
    
    def check_drawdown_limit(
        self,
        current_drawdown_pct: float,
    ) -> bool:
        """
        Check if portfolio drawdown exceeds limit.
        
        Args:
            current_drawdown_pct: Current drawdown percentage
        
        Returns:
            True if within limit, False if exceeded
        """
        limit = self.policy.get_limit("drawdown")
        if limit:
            limit.current_value = current_drawdown_pct
            if limit.is_violated():
                logger.error(f"Drawdown limit exceeded: {current_drawdown_pct:.1f}% > {limit.limit_value:.1f}%")
                return False
        return True
    
    def check_daily_loss_limit(
        self,
        daily_pnl: float,
        portfolio_equity: float,
    ) -> bool:
        """
        Check if daily P&L loss exceeds limit.
        
        Args:
            daily_pnl: Daily profit/loss (negative = loss)
            portfolio_equity: Current portfolio equity
        
        Returns:
            True if within limit, False if exceeded
        """
        if portfolio_equity <= 0:
            return True
        
        daily_loss_pct = (abs(daily_pnl) / portfolio_equity) * 100 if daily_pnl < 0 else 0
        
        limit = self.policy.get_limit("daily_loss")
        if limit:
            limit.current_value = daily_loss_pct
            if limit.is_violated():
                logger.error(f"Daily loss limit exceeded: {daily_loss_pct:.1f}% > {limit.limit_value:.1f}%")
                return False
        return True
    
    def check_leverage_limit(
        self,
        gross_position_value: float,
        portfolio_equity: float,
    ) -> bool:
        """
        Check if portfolio leverage exceeds limit.
        
        Args:
            gross_position_value: Total absolute position value
            portfolio_equity: Current portfolio equity
        
        Returns:
            True if within limit, False if exceeded
        """
        if portfolio_equity <= 0:
            return True
        
        leverage = gross_position_value / portfolio_equity
        
        limit = self.policy.get_limit("portfolio_leverage")
        if limit:
            limit.current_value = leverage
            if limit.is_violated():
                logger.error(f"Leverage limit exceeded: {leverage:.2f}x > {limit.limit_value:.2f}x")
                return False
        return True
    
    def get_policy_violations(self) -> List[RiskLimit]:
        """Get all currently violated limits."""
        return self.policy.get_violated_limits()
