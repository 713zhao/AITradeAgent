import logging
from typing import Dict, Any, Optional, List, Tuple, Union, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.events import Event, Events, get_event_bus
from finance_service.core.models import TradeProposal, Position # Import Position for risk checks

logger = logging.getLogger(__name__)

class ApprovalStatus(Enum):
    """Approval request status."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class RiskCheckType(Enum):
    """Types of risk checks."""
    POSITION_SIZE = "position_size"        # Single position max
    SECTOR_EXPOSURE = "sector_exposure"    # Sector concentration
    PORTFOLIO_LEVERAGE = "portfolio_leverage"  # Total leverage
    VOLATILITY_LIMIT = "volatility_limit"   # Max portfolio volatility
    DRAWDOWN_LIMIT = "drawdown_limit"      # Max current drawdown
    DAILY_LOSS_LIMIT = "daily_loss_limit"  # Max daily P&L loss
    CORRELATION_CHECK = "correlation_check"  # Position correlation


@dataclass
class RiskLimit:
    """
    Individual risk limit configuration.
    
    Attributes:
        limit_type: Type of limit (position_size, sector_exposure, etc.)
        limit_value: Maximum allowed value
        current_value: Current actual value
        enabled: Whether limit is active
        description: Human-readable description
        severity: "warning" (log only) or "block" (prevent execution)
    """
    limit_type: str
    limit_value: float
    severity: str = "block"  # "warning" or "block"
    enabled: bool = True
    current_value: float = 0.0
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_violated(self) -> bool:
        """Check if limit is violated."""
        if not self.enabled:
            return False
        return self.current_value > self.limit_value
    
    def available_capacity(self) -> float:
        """Calculate remaining capacity."""
        return max(0.0, self.limit_value - self.current_value)
    
    def utilization_pct(self) -> float:
        """Calculate utilization percentage."""
        if self.limit_value == 0:
            return 0.0
        return (self.current_value / self.limit_value) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "limit_type": self.limit_type,
            "limit_value": self.limit_value,
            "current_value": self.current_value,
            "severity": self.severity,
            "enabled": self.enabled,
            "is_violated": self.is_violated(),
            "available_capacity": self.available_capacity(),
            "utilization_pct": self.utilization_pct(),
            "description": self.description,
        }


@dataclass
class RiskPolicy:
    """
    Risk policy configuration with multiple limits.
    
    Attributes:
        policy_id: Unique policy identifier
        policy_name: Human-readable policy name
        limits: Dict of limit_type -> RiskLimit
        approval_required_pct: Confidence threshold requiring approval (0.0-1.0)
        max_positions: Maximum number of open positions
        max_position_size_pct: Max position as % of portfolio
        max_sector_exposure_pct: Max sector concentration
        max_portfolio_leverage: Max total leverage (long + short)
        max_daily_loss_pct: Max daily loss % of equity
        max_drawdown_pct: Max drawdown from peak
        created_at: Policy creation timestamp
        updated_at: Last modification timestamp
        enabled: Whether policy is active
        description: Policy description
    """
    policy_id: str
    policy_name: str
    max_positions: int = 20
    max_position_size_pct: float = 10.0      # 10% of portfolio per position
    max_sector_exposure_pct: float = 25.0    # 25% per sector
    max_portfolio_leverage: float = 2.0      # 2x leverage
    max_daily_loss_pct: float = 5.0          # 5% daily loss limit
    max_drawdown_pct: float = 20.0           # 20% max drawdown
    approval_required_pct: float = 0.75      # Require approval if confidence < 75%
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    enabled: bool = True
    description: str = ""
    limits: Dict[str, RiskLimit] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Initialize default limits if empty."""
        if not self.limits:
            self.limits = {
                "position_size": RiskLimit(
                    limit_type="position_size",
                    limit_value=self.max_position_size_pct,
                    description=f"Max {self.max_position_size_pct}% per position"
                ),
                "sector_exposure": RiskLimit(
                    limit_type="sector_exposure",
                    limit_value=self.max_sector_exposure_pct,
                    description=f"Max {self.max_sector_exposure_pct}% sector concentration"
                ),
                "portfolio_leverage": RiskLimit(
                    limit_type="portfolio_leverage",
                    limit_value=self.max_portfolio_leverage,
                    description=f"Max {self.max_portfolio_leverage}x leverage"
                ),
                "daily_loss": RiskLimit(
                    limit_type="daily_loss",
                    limit_value=self.max_daily_loss_pct,
                    description=f"Max {self.max_daily_loss_pct}% daily loss"
                ),
                "drawdown": RiskLimit(
                    limit_type="drawdown",
                    limit_value=self.max_drawdown_pct,
                    description=f"Max {self.max_drawdown_pct}% drawdown"
                ),
            }
    
    def get_limit(self, limit_type: str) -> Optional[RiskLimit]:
        """Get specific limit by type."""
        return self.limits.get(limit_type)
    
    def get_violated_limits(self) -> List[RiskLimit]:
        """Get all violated limits."""
        return [limit for limit in self.limits.values() if limit.is_violated()]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "policy_id": self.policy_id,
            "policy_name": self.policy_name,
            "max_positions": self.max_positions,
            "max_position_size_pct": self.max_position_size_pct,
            "max_sector_exposure_pct": self.max_sector_exposure_pct,
            "max_portfolio_leverage": self.max_portfolio_leverage,
            "max_daily_loss_pct": self.max_daily_loss_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "approval_required_pct": self.approval_required_pct,
            "enabled": self.enabled,
            "description": self.description,
            "limits": {
                k: v.to_dict()
                for k, v in self.limits.items()
            },
        }


@dataclass
class RiskCheckResult:
    """
    Result of a risk check on a trade.
    
    Attributes:
        trade_id: Trade being checked
        symbol: Trading symbol
        passed: Whether trade passed all risk checks
        violated_limits: List of violated RiskLimit objects
        warnings: List of warning messages
        approval_required: Whether manual approval is needed
        risk_score: Overall risk score (0-100, higher = riskier)
        checks_performed: Dict of check_type -> passed
    """
    trade_id: str
    symbol: str
    passed: bool = True
    approval_required: bool = False
    risk_score: float = 0.0
    violated_limits: List[RiskLimit] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    checks_performed: Dict[str, bool] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_violation(self, limit: RiskLimit, reason: str = ""):
        """Add a violated limit."""
        if limit not in self.violated_limits:
            self.violated_limits.append(limit)
        self.passed = False
        if reason:
            self.warnings.append(f"{limit.limit_type}: {reason}")
    
    def add_warning(self, message: str):
        """Add a warning message."""
        if message not in self.warnings:
            self.warnings.append(message)
    
    def violations_count(self) -> int:
        """Count number of violated limits."""
        return len(self.violated_limits)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "passed": self.passed,
            "approval_required": self.approval_required,
            "risk_score": self.risk_score,
            "violation_count": len(self.violated_limits),
            "violated_limits": [
                l.limit_type for l in self.violated_limits
            ],
            "warnings": self.warnings,
            "checks_performed": self.checks_performed,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ApprovalRequest:
    """
    Request for manual trade approval.
    
    Attributes:
        request_id: Unique approval request ID
        trade_id: Associated trade ID
        symbol: Trading symbol
        trade_details: Complete trade details JSON
        risk_check: RiskCheckResult from risk enforcer
        status: ApprovalStatus (pending, approved, rejected, expired)
        reason: Reason for approval requirement
        created_at: When request was created
        expires_at: When approval request expires
        approved_by: User who approved (if approved)
        approval_notes: Notes from approver
        decision_reason: Why approved or rejected
    """
    request_id: str
    trade_id: str
    symbol: str
    trade_details: Dict[str, Any] = field(default_factory=dict)
    risk_check: Optional[RiskCheckResult] = None
    status: ApprovalStatus = ApprovalStatus.PENDING
    reason: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime = field(default_factory=lambda: datetime.utcnow() + timedelta(hours=1))
    approved_by: Optional[str] = None
    approval_notes: str = ""
    decision_reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_expired(self) -> bool:
        """Check if approval request has expired."""
        return datetime.utcnow() > self.expires_at
    
    def is_pending(self) -> bool:
        """Check if still awaiting approval."""
        return not self.is_expired() and self.status == ApprovalStatus.PENDING
    
    def approve(self, approved_by: str, notes: str = ""):
        """Approve the trade."""
        self.status = ApprovalStatus.APPROVED
        self.approved_by = approved_by
        self.approval_notes = notes
        self.decision_reason = "Approved"
    
    def reject(self, rejected_by: str, reason: str = ""):
        """Reject the trade."""
        self.status = ApprovalStatus.REJECTED
        self.approved_by = rejected_by  # Track who made decision
        self.decision_reason = reason or "Rejection reason not provided"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "request_id": self.request_id,
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "status": self.status.value,
            "reason": self.reason,
            "is_pending": self.is_pending(),
            "is_expired": self.is_expired(),
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "approved_by": self.approved_by,
            "approval_notes": self.approval_notes,
            "decision_reason": self.decision_reason,
            "trade_details": self.trade_details,
            "risk_check": self.risk_check.to_dict() if self.risk_check else None,
        }

class RiskAgent(Agent):
    """Risk Agent - Enforces risk policies and manages trade approvals."""

    @property
    def agent_id(self) -> str:
        return "risk_agent"

    @property
    def goal(self) -> str:
        return "Enforce risk management policies and facilitate trade approval workflows."

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.event_bus = get_event_bus()
        # Initialize risk policy (from config or default)
        policy_config = config.get("policy", {})
        self.policy = RiskPolicy(
            policy_id=policy_config.get("policy_id", "STANDARD"),
            policy_name=policy_config.get("policy_name", "Standard Risk Policy"),
            max_positions=policy_config.get("max_positions", 20),
            max_position_size_pct=policy_config.get("max_position_size_pct", 10.0),
            max_sector_exposure_pct=policy_config.get("max_sector_exposure_pct", 25.0),
            max_portfolio_leverage=policy_config.get("max_portfolio_leverage", 2.0),
            max_daily_loss_pct=policy_config.get("max_daily_loss_pct", 5.0),
            max_drawdown_pct=policy_config.get("max_drawdown_pct", 20.0),
            approval_required_pct=policy_config.get("approval_required_pct", 0.75),
        )
        logger.info(f"RiskAgent initialized with policy: {self.policy.policy_name}")

    async def run(self, trade_proposal_report: AgentReport) -> Optional[AgentReport]:
        """
        Evaluates a trade proposal against risk policies and potentially initiates an approval process.
        """
        logger.info("RiskAgent run: Evaluating trade proposal for risk.")

        try:
            proposal = TradeProposal(**trade_proposal_report.payload["proposal"])
            # For now, current_positions and portfolio_equity are placeholders.
            # These would typically come from a PortfolioAgent or external source.
            current_positions: Dict[str, Position] = {}
            portfolio_equity: float = 100000.0

            risk_check_result = self._check_trade(
                trade_id=f"trade_{proposal.symbol}_{datetime.utcnow().timestamp()}", # Generate unique ID
                symbol=proposal.symbol,
                quantity=1.0, # Placeholder quantity, assuming 1 unit for now or infer from proposal
                price=proposal.target_price or 1.0, # Use target price as trade price for risk assessment
                portfolio_equity=portfolio_equity,
                current_positions=current_positions,
                confidence=proposal.confidence,
            )
            
            message = f"Risk assessment complete for {proposal.symbol}. Approval Required: {risk_check_result.approval_required}"
            payload = {"risk_assessment": risk_check_result.to_dict(), "trade_proposal": proposal.model_dump()}

            # Publish event based on approval required status
            if risk_check_result.approval_required:
                self.event_bus.publish(Event(
                    event_type=Events.APPROVAL_REQUIRED,
                    data=payload
                ))
            else:
                self.event_bus.publish(Event(
                    event_type=Events.RISK_CHECK_COMPLETE,
                    data=payload
                ))

            return AgentReport(
                agent_id=self.agent_id,
                status="success",
                message=message,
                payload=payload
            )
        except Exception as e:
            logger.error(f"Error in RiskAgent run: {e}")
            return AgentReport(
                agent_id=self.agent_id,
                status="error",
                message=f"Error evaluating risk for trade proposal: {e}"
            )
    
    def _check_trade(
        self,
        trade_id: str,
        symbol: str,
        quantity: float,
        price: float,
        portfolio_equity: float,
        current_positions: Dict[str, Position],
        confidence: float = 1.0,
    ) -> RiskCheckResult:
        """
        Perform comprehensive risk check on a trade.
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
        current_positions: Dict[str, Position],
        result: RiskCheckResult,
    ) -> bool:
        """Check maximum position count."""
        open_positions = len([pos for pos in current_positions.values() if pos.qty != 0])
        
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

    def __repr__(self) -> str:
        return f"<RiskAgent(id='{self.agent_id}')>"
