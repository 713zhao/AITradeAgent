"""
Approval Engine

Manages trade approval requests, approvals, and rejections.
"""

import uuid
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from .models import ApprovalRequest, ApprovalStatus, RiskCheckResult

logger = logging.getLogger(__name__)


class ApprovalEngine:
    """
    Manages approval workflows for pending trades.
    
    Responsibilities:
    - Create approval requests
    - Track pending approvals
    - Approve/reject trades
    - Manage approval expiration
    """
    
    def __init__(self, approval_timeout_hours: int = 1):
        """
        Initialize approval engine.
        
        Args:
            approval_timeout_hours: Hours before approval request expires
        """
        self.approval_timeout_hours = approval_timeout_hours
        self.requests: List[ApprovalRequest] = []
        self._request_counter = 0
    
    def create_approval_request(
        self,
        trade_id: str,
        symbol: str,
        trade_details: Dict[str, Any],
        risk_check: Optional[RiskCheckResult] = None,
        reason: str = "Manual approval required",
    ) -> ApprovalRequest:
        """
        Create a new approval request for a trade.
        
        Args:
            trade_id: The trade ID requiring approval
            symbol: Trading symbol
            trade_details: Complete trade information
            risk_check: Associated RiskCheckResult
            reason: Why approval is required
        
        Returns:
            Created ApprovalRequest object
        """
        self._request_counter += 1
        request_id = f"APPROVAL_{self._request_counter:06d}"
        
        expires_at = datetime.utcnow() + timedelta(hours=self.approval_timeout_hours)
        
        request = ApprovalRequest(
            request_id=request_id,
            trade_id=trade_id,
            symbol=symbol,
            trade_details=trade_details,
            risk_check=risk_check,
            reason=reason,
            expires_at=expires_at,
        )
        
        self.requests.append(request)
        logger.info(f"Approval request created: {request_id} for {symbol} (expires in {self.approval_timeout_hours}h)")
        return request
    
    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """Get approval request by ID."""
        for req in self.requests:
            if req.request_id == request_id:
                return req
        return None
    
    def get_pending_requests(self) -> List[ApprovalRequest]:
        """Get all pending (not expired) approval requests."""
        return [r for r in self.requests if r.is_pending()]
    
    def get_requests_by_symbol(self, symbol: str) -> List[ApprovalRequest]:
        """Get approval requests for a symbol."""
        return [r for r in self.requests if r.symbol == symbol]
    
    def get_requests_by_status(self, status: ApprovalStatus) -> List[ApprovalRequest]:
        """Get requests with specific status."""
        return [r for r in self.requests if r.status == status]
    
    def get_expired_requests(self) -> List[ApprovalRequest]:
        """Get expired pending requests."""
        return [r for r in self.requests if r.is_expired() and r.status == ApprovalStatus.PENDING]
    
    def approve_request(
        self,
        request_id: str,
        approved_by: str = "system",
        notes: str = "",
    ) -> Optional[ApprovalRequest]:
        """
        Approve a pending request.
        
        Args:
            request_id: Request to approve
            approved_by: User/system approving
            notes: Approval notes
        
        Returns:
            Updated ApprovalRequest or None
        """
        request = self.get_request(request_id)
        if not request:
            return None
        
        if not request.is_pending():
            logger.warning(f"Cannot approve non-pending request: {request_id} (status={request.status.value})")
            return None
        
        request.approve(approved_by, notes)
        logger.info(f"Approval request approved: {request_id} by {approved_by}")
        return request
    
    def reject_request(
        self,
        request_id: str,
        rejected_by: str = "system",
        reason: str = "",
    ) -> Optional[ApprovalRequest]:
        """
        Reject a pending request.
        
        Args:
            request_id: Request to reject
            rejected_by: User/system rejecting
            reason: Rejection reason
        
        Returns:
            Updated ApprovalRequest or None
        """
        request = self.get_request(request_id)
        if not request:
            return None
        
        if not request.is_pending():
            logger.warning(f"Cannot reject non-pending request: {request_id} (status={request.status.value})")
            return None
        
        request.reject(rejected_by, reason)
        logger.info(f"Approval request rejected: {request_id} by {rejected_by} ({reason})")
        return request
    
    def expire_old_requests(self) -> int:
        """
        Mark expired pending requests as expired.
        
        Returns:
            Number of requests expired
        """
        expired = self.get_expired_requests()
        for req in expired:
            req.status = ApprovalStatus.EXPIRED
            logger.warning(f"Approval request expired: {req.request_id}")
        return len(expired)
    
    def pending_approval_count(self) -> int:
        """Get number of pending approvals."""
        return len(self.get_pending_requests())
    
    def get_approval_stats(self) -> Dict[str, int]:
        """Get approval statistics."""
        return {
            "pending": len(self.get_requests_by_status(ApprovalStatus.PENDING)),
            "approved": len(self.get_requests_by_status(ApprovalStatus.APPROVED)),
            "rejected": len(self.get_requests_by_status(ApprovalStatus.REJECTED)),
            "expired": len(self.get_requests_by_status(ApprovalStatus.EXPIRED)),
            "total": len(self.requests),
        }
    
    def clear_all(self) -> None:
        """Clear all requests (testing only)."""
        self.requests.clear()
        self._request_counter = 0
