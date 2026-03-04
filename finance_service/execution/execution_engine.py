"""
Execution Engine - Phase 5: Trade Execution & Monitoring
Integration with Phase 6: Live Trading via BrokerManager

Handles:
- Approval request processing (approve/reject)
- Trade execution with broker order placement
- Execution report generation
- Integration with portfolio manager and brokers
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, List
from enum import Enum

from finance_service.portfolio.models import Trade, TradeStatus
from finance_service.risk.models import ApprovalRequest, ApprovalStatus
from finance_service.brokers.broker_manager import BrokerManager


class ExecutionType(Enum):
    """Execution type classification."""
    AUTO_APPROVAL = "auto_approval"      # Risk check passed, high confidence
    MANUAL_APPROVAL = "manual_approval"  # Risk manager approved
    REJECTED = "rejected"                # Manual rejection
    TIMEOUT = "timeout"                  # Approval request expired


@dataclass
class ExecutionReport:
    """Report from trade execution."""
    
    execution_id: str
    trade_id: str
    symbol: str
    execution_type: ExecutionType
    
    # Execution timing
    requested_at: datetime
    executed_at: Optional[datetime] = None
    
    # Execution details
    filled_price: float = 0.0
    filled_quantity: int = 0
    
    # Status
    status: str = "PENDING"  # EXECUTED, REJECTED, PENDING
    reason: str = ""
    
    # Risk context
    approval_request_id: Optional[str] = None
    approval_notes: str = ""
    
    # Portfolio impact
    portfolio_impact: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Serialize execution report."""
        return {
            "execution_id": self.execution_id,
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "execution_type": self.execution_type.value,
            "requested_at": self.requested_at.isoformat(),
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "filled_price": self.filled_price,
            "filled_quantity": self.filled_quantity,
            "status": self.status,
            "reason": self.reason,
            "approval_request_id": self.approval_request_id,
            "approval_notes": self.approval_notes,
            "portfolio_impact": self.portfolio_impact,
        }


@dataclass
class ExecutionContext:
    """Context for trade execution."""
    
    trade_id: str
    symbol: str
    side: str  # BUY or SELL
    quantity: int
    target_price: float
    confidence: float
    
    # Risk context
    approval_required: bool = False
    risk_score: float = 0.0
    violated_limits: List[str] = field(default_factory=list)
    
    # Approval context
    approval_request: Optional[ApprovalRequest] = None
    approval_decision: Optional[str] = None  # APPROVED, REJECTED
    
    def to_dict(self) -> Dict:
        """Serialize execution context."""
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "target_price": self.target_price,
            "confidence": self.confidence,
            "approval_required": self.approval_required,
            "risk_score": self.risk_score,
            "violated_limits": self.violated_limits,
            "approval_decision": self.approval_decision,
        }


class ExecutionEngine:
    """
    Trade execution engine for Phase 5.
    
    Responsibilities:
    - Process approval decisions (approve/reject)
    - Execute trades (update portfolio, record execution)
    - Generate execution reports
    - Track execution history
    """
    
    def __init__(self, broker_manager: Optional[BrokerManager] = None):
        """
        Initialize execution engine.
        
        Args:
            broker_manager: BrokerManager instance for actual order placement (optional)
        """
        self.execution_history: Dict[str, ExecutionReport] = {}
        self.execution_contexts: Dict[str, ExecutionContext] = {}
        self.pending_executions: Dict[str, ExecutionContext] = {}
        self.broker_manager = broker_manager
    
    def create_execution_context(
        self,
        trade_id: str,
        symbol: str,
        side: str,
        quantity: int,
        target_price: float,
        confidence: float,
        risk_assessment: Dict
    ) -> ExecutionContext:
        """
        Create execution context from trade and risk assessment.
        
        Args:
            trade_id: Trade identifier
            symbol: Stock symbol
            side: BUY or SELL
            quantity: Number of shares
            target_price: Target entry price
            confidence: Indicator confidence 0.0-1.0
            risk_assessment: Risk check result dict
            
        Returns:
            ExecutionContext ready for approval/execution
        """
        context = ExecutionContext(
            trade_id=trade_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            target_price=target_price,
            confidence=confidence,
            approval_required=risk_assessment.get("approval_required", False),
            risk_score=risk_assessment.get("risk_score", 0.0),
            violated_limits=risk_assessment.get("violated_limits", []),
        )
        
        self.execution_contexts[trade_id] = context
        self.pending_executions[trade_id] = context
        
        return context
    
    def approve_and_execute(
        self,
        trade_id: str,
        approval_request: Optional[ApprovalRequest] = None,
        approved_by: str = "auto"
    ) -> ExecutionReport:
        """
        Approve execution context and execute trade.
        
        Places actual order with broker if broker_manager available.
        
        Args:
            trade_id: Trade to execute
            approval_request: Approval request object (if manual approval)
            approved_by: User who approved
            
        Returns:
            ExecutionReport with execution details
        """
        if trade_id not in self.pending_executions:
            raise ValueError(f"No pending execution for trade {trade_id}")
        
        context = self.pending_executions[trade_id]
        execution_type = (
            ExecutionType.MANUAL_APPROVAL if approval_request
            else ExecutionType.AUTO_APPROVAL
        )
        
        # Generate execution ID
        execution_id = f"EXEC_{datetime.utcnow().timestamp()}_{trade_id}"
        
        # Attempt to place order with broker
        broker_order = None
        broker_order_id = None
        execution_status = "EXECUTED"
        filled_price = context.target_price
        filled_quantity = context.quantity
        execution_reason = "Trade executed successfully"
        
        if self.broker_manager:
            try:
                # Place order with broker
                broker_order = self.broker_manager.place_order(
                    trade_id=trade_id,
                    symbol=context.symbol,
                    side=context.side,
                    quantity=context.quantity,
                    price=context.target_price,
                    order_type="MARKET"
                )
                
                broker_order_id = broker_order.order_id
                
                # For market orders, use broker's filled price if available
                if broker_order.filled_quantity > 0:
                    filled_price = broker_order.avg_fill_price
                    filled_quantity = broker_order.filled_quantity
                
                # Order status depends on broker order status
                if broker_order.status.name == "FILLED":
                    execution_status = "EXECUTED"
                elif broker_order.status.name == "PARTIAL":
                    execution_status = "PARTIAL"
                else:
                    execution_status = "PENDING"
                    execution_reason = f"Order {broker_order_id} pending with broker"
            
            except Exception as e:
                execution_status = "REJECTED"
                execution_reason = f"Broker order failed: {str(e)}"
        
        # Create execution report
        report = ExecutionReport(
            execution_id=execution_id,
            trade_id=trade_id,
            symbol=context.symbol,
            execution_type=execution_type,
            requested_at=datetime.utcnow(),
            executed_at=datetime.utcnow() if execution_status == "EXECUTED" else None,
            filled_price=filled_price,
            filled_quantity=filled_quantity,
            status=execution_status,
            reason=execution_reason,
            approval_request_id=approval_request.request_id if approval_request else None,
            approval_notes=approval_request.approval_notes if approval_request else "Auto-executed",
            portfolio_impact={"broker_order_id": broker_order_id} if broker_order_id else {},
        )
        
        # Record execution
        self.execution_history[execution_id] = report
        
        # Clean up pending
        del self.pending_executions[trade_id]
        
        return report
    
    def reject_execution(
        self,
        trade_id: str,
        approval_request: Optional[ApprovalRequest] = None,
        rejected_by: str = "auto",
        reason: str = ""
    ) -> ExecutionReport:
        """
        Reject execution context and cancel trade.
        
        Args:
            trade_id: Trade to reject
            approval_request: Approval request object
            rejected_by: User who rejected
            reason: Rejection reason
            
        Returns:
            ExecutionReport with rejection details
        """
        if trade_id not in self.pending_executions:
            raise ValueError(f"No pending execution for trade {trade_id}")
        
        context = self.pending_executions[trade_id]
        
        # Generate execution ID
        execution_id = f"EXEC_{datetime.utcnow().timestamp()}_{trade_id}"
        
        # Create execution report
        report = ExecutionReport(
            execution_id=execution_id,
            trade_id=trade_id,
            symbol=context.symbol,
            execution_type=ExecutionType.REJECTED,
            requested_at=datetime.utcnow(),
            status="REJECTED",
            reason=reason or (
                approval_request.decision_reason if approval_request else "Execution rejected"
            ),
            approval_request_id=approval_request.request_id if approval_request else None,
        )
        
        # Record rejection
        self.execution_history[execution_id] = report
        
        # Clean up pending
        del self.pending_executions[trade_id]
        
        return report
    
    def handle_expired_request(
        self,
        trade_id: str,
        approval_request: Optional[ApprovalRequest] = None
    ) -> ExecutionReport:
        """
        Handle expired approval request (auto-reject).
        
        Args:
            trade_id: Trade with expired request
            approval_request: Expired approval request
            
        Returns:
            ExecutionReport with expiration details
        """
        if trade_id not in self.pending_executions:
            raise ValueError(f"No pending execution for trade {trade_id}")
        
        context = self.pending_executions[trade_id]
        
        # Generate execution ID
        execution_id = f"EXEC_{datetime.utcnow().timestamp()}_{trade_id}"
        
        # Create execution report
        report = ExecutionReport(
            execution_id=execution_id,
            trade_id=trade_id,
            symbol=context.symbol,
            execution_type=ExecutionType.TIMEOUT,
            requested_at=datetime.utcnow(),
            status="REJECTED",
            reason="Approval request expired (1 hour timeout)",
            approval_request_id=approval_request.request_id if approval_request else None,
        )
        
        # Record expiration
        self.execution_history[execution_id] = report
        
        # Clean up pending
        del self.pending_executions[trade_id]
        
        return report
    
    def get_execution_report(self, execution_id: str) -> Optional[ExecutionReport]:
        """Get execution report by ID."""
        return self.execution_history.get(execution_id)
    
    def get_execution_history(self, symbol: Optional[str] = None) -> List[ExecutionReport]:
        """
        Get execution history.
        
        Args:
            symbol: Filter by symbol (optional)
            
        Returns:
            List of ExecutionReport objects
        """
        history = list(self.execution_history.values())
        
        if symbol:
            history = [r for r in history if r.symbol == symbol]
        
        return sorted(history, key=lambda r: r.executed_at or r.requested_at, reverse=True)
    
    def get_pending_count(self) -> int:
        """Get count of pending executions."""
        return len(self.pending_executions)
    
    def get_execution_stats(self) -> Dict:
        """Get execution statistics."""
        reports = list(self.execution_history.values())
        
        executed = [r for r in reports if r.status == "EXECUTED"]
        rejected = [r for r in reports if r.status == "REJECTED"]
        
        auto_approvals = [r for r in executed if r.execution_type == ExecutionType.AUTO_APPROVAL]
        manual_approvals = [r for r in executed if r.execution_type == ExecutionType.MANUAL_APPROVAL]
        
        return {
            "total_executions": len(reports),
            "executed_count": len(executed),
            "rejected_count": len(rejected),
            "pending_count": self.get_pending_count(),
            "auto_approval_count": len(auto_approvals),
            "manual_approval_count": len(manual_approvals),
            "execution_rate": len(executed) / len(reports) if reports else 0.0,
            "auto_approval_rate": len(auto_approvals) / len(executed) if executed else 0.0,
        }
