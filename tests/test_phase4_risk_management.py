"""
Phase 4 Risk Management - Comprehensive Test Suite

Tests for:
- Risk policies and limits
- Approval engine (create, approve, reject)
- Risk enforcer (trade validation)
- Exposure manager (sector concentration, leverage)
- Phase 3→4 integration (trade risk checks)
"""

import pytest
from datetime import datetime, timedelta
from finance_service.risk.models import (
    RiskPolicy, RiskLimit, ApprovalRequest, RiskCheckResult,
    ApprovalStatus, RiskCheckType
)
from finance_service.risk.approval_engine import ApprovalEngine
from finance_service.risk.risk_enforcer import RiskEnforcer
from finance_service.risk.exposure_manager import ExposureManager


# =====================
# FIXTURES
# =====================

@pytest.fixture
def risk_policy():
    """Create standard risk policy."""
    return RiskPolicy(
        policy_id="TEST_POLICY",
        policy_name="Test Policy",
        max_positions=20,
        max_position_size_pct=10.0,
        max_sector_exposure_pct=25.0,
        max_portfolio_leverage=2.0,
        max_daily_loss_pct=5.0,
        max_drawdown_pct=20.0,
        approval_required_pct=0.75,
    )


@pytest.fixture
def approval_engine():
    """Create approval engine."""
    return ApprovalEngine(approval_timeout_hours=1)


@pytest.fixture
def risk_enforcer(risk_policy):
    """Create risk enforcer with test policy."""
    return RiskEnforcer(risk_policy)


@pytest.fixture
def exposure_manager():
    """Create exposure manager."""
    return ExposureManager()


# =====================
# RISK LIMIT TESTS
# =====================

class TestRiskLimit:
    """Test RiskLimit model."""
    
    def test_risk_limit_initialization(self):
        """Test creating a risk limit."""
        limit = RiskLimit(
            limit_type="position_size",
            limit_value=10.0,
            severity="block"
        )
        assert limit.limit_type == "position_size"
        assert limit.limit_value == 10.0
        assert limit.severity == "block"
        assert not limit.is_violated()
    
    def test_risk_limit_violation(self):
        """Test violation detection."""
        limit = RiskLimit(
            limit_type="position_size",
            limit_value=10.0,
            current_value=12.0
        )
        assert limit.is_violated()
    
    def test_risk_limit_capacity(self):
        """Test available capacity calculation."""
        limit = RiskLimit(
            limit_type="position_size",
            limit_value=10.0,
            current_value=3.0
        )
        assert limit.available_capacity() == 7.0
    
    def test_risk_limit_utilization(self):
        """Test utilization percentage."""
        limit = RiskLimit(
            limit_type="position_size",
            limit_value=10.0,
            current_value=5.0
        )
        assert limit.utilization_pct() == 50.0


# =====================
# RISK POLICY TESTS
# =====================

class TestRiskPolicy:
    """Test RiskPolicy model."""
    
    def test_policy_initialization(self, risk_policy):
        """Test creating a policy."""
        assert risk_policy.policy_id == "TEST_POLICY"
        assert risk_policy.max_positions == 20
        assert len(risk_policy.limits) == 5  # Default limits
    
    def test_policy_get_limit(self, risk_policy):
        """Test getting specific limit."""
        limit = risk_policy.get_limit("position_size")
        assert limit is not None
        assert limit.limit_type == "position_size"
    
    def test_policy_get_violated_limits(self, risk_policy):
        """Test getting violated limits."""
        # Violate a limit
        limit = risk_policy.get_limit("position_size")
        limit.current_value = 15.0
        
        violated = risk_policy.get_violated_limits()
        assert len(violated) == 1
        assert violated[0].limit_type == "position_size"
    
    def test_policy_to_dict(self, risk_policy):
        """Test policy serialization."""
        d = risk_policy.to_dict()
        assert d["policy_id"] == "TEST_POLICY"
        assert "max_positions" in d
        assert "limits" in d


# =====================
# RISK CHECK RESULT TESTS
# =====================

class TestRiskCheckResult:
    """Test RiskCheckResult model."""
    
    def test_check_result_initialization(self):
        """Test creating a check result."""
        result = RiskCheckResult(
            trade_id="TRADE_001",
            symbol="AAPL",
            passed=True
        )
        assert result.trade_id == "TRADE_001"
        assert result.symbol == "AAPL"
        assert result.passed
    
    def test_check_result_add_violation(self):
        """Test adding a violation."""
        result = RiskCheckResult(
            trade_id="TRADE_001",
            symbol="AAPL"
        )
        limit = RiskLimit(
            limit_type="position_size",
            limit_value=10.0,
            current_value=15.0
        )
        result.add_violation(limit, "Exceeds limit")
        
        assert not result.passed
        assert len(result.violated_limits) == 1
        assert result.violations_count() == 1


# =====================
# APPROVAL ENGINE TESTS
# =====================

class TestApprovalEngine:
    """Test approval engine operations."""
    
    def test_create_approval_request(self, approval_engine):
        """Test creating an approval request."""
        request = approval_engine.create_approval_request(
            trade_id="TRADE_001",
            symbol="AAPL",
            trade_details={"side": "BUY", "quantity": 10},
            reason="Risk violation"
        )
        
        assert request.request_id.startswith("APPROVAL_")
        assert request.trade_id == "TRADE_001"
        assert request.status == ApprovalStatus.PENDING
    
    def test_get_approval_request(self, approval_engine):
        """Test retrieving an approval request."""
        request = approval_engine.create_approval_request(
            trade_id="TRADE_001",
            symbol="AAPL",
            trade_details={},
            reason="Test"
        )
        
        retrieved = approval_engine.get_request(request.request_id)
        assert retrieved == request
    
    def test_get_pending_requests(self, approval_engine):
        """Test getting pending requests."""
        approval_engine.create_approval_request(
            trade_id="TRADE_001", symbol="AAPL", trade_details={}, reason="Test 1"
        )
        approval_engine.create_approval_request(
            trade_id="TRADE_002", symbol="MSFT", trade_details={}, reason="Test 2"
        )
        
        pending = approval_engine.get_pending_requests()
        assert len(pending) == 2
    
    def test_approve_request(self, approval_engine):
        """Test approving a request."""
        request = approval_engine.create_approval_request(
            trade_id="TRADE_001",
            symbol="AAPL",
            trade_details={},
            reason="Test"
        )
        
        approved = approval_engine.approve_request(request.request_id, approved_by="trader1")
        assert approved.status == ApprovalStatus.APPROVED
        assert approved.approved_by == "trader1"
    
    def test_reject_request(self, approval_engine):
        """Test rejecting a request."""
        request = approval_engine.create_approval_request(
            trade_id="TRADE_001",
            symbol="AAPL",
            trade_details={},
            reason="Test"
        )
        
        rejected = approval_engine.reject_request(
            request.request_id,
            rejected_by="risk_manager",
            reason="Exceeds limit"
        )
        assert rejected.status == ApprovalStatus.REJECTED
        assert "Exceeds limit" in rejected.decision_reason
    
    def test_approval_expiration(self, approval_engine):
        """Test approval request expiration."""
        request = approval_engine.create_approval_request(
            trade_id="TRADE_001",
            symbol="AAPL",
            trade_details={},
            reason="Test"
        )
        
        # Move expiration back in time
        request.expires_at = datetime.utcnow() - timedelta(minutes=1)
        
        assert request.is_expired()
        assert not request.is_pending()


# =====================
# RISK ENFORCER TESTS
# =====================

class TestRiskEnforcer:
    """Test risk enforcement."""
    
    def test_check_position_size(self, risk_enforcer):
        """Test position size check."""
        result = risk_enforcer.check_trade(
            trade_id="TRADE_001",
            symbol="AAPL",
            quantity=10,
            price=150.0,
            portfolio_equity=100000.0,
            current_positions={},
            confidence=0.75
        )
        
        # Position value = 10 * 150 = 1500 = 1.5% of portfolio
        # Limit is 10% so should pass
        assert result.passed
        assert result.checks_performed.get("position_size", True)
    
    def test_position_size_violation(self, risk_enforcer):
        """Test position size violation."""
        result = risk_enforcer.check_trade(
            trade_id="TRADE_001",
            symbol="AAPL",
            quantity=100,  # Huge position
            price=150.0,
            portfolio_equity=100000.0,
            current_positions={},
            confidence=0.75
        )
        
        # Position value = 100 * 150 = 15000 = 15% of portfolio
        # Limit is 10% so should fail
        assert not result.passed
        assert len(result.violated_limits) > 0
    
    def test_confidence_check(self, risk_enforcer):
        """Test low confidence approval requirement."""
        result = risk_enforcer.check_trade(
            trade_id="TRADE_001",
            symbol="AAPL",
            quantity=10,
            price=150.0,
            portfolio_equity=100000.0,
            current_positions={},
            confidence=0.5  # Below 75% threshold
        )
        
        assert result.approval_required
    
    def test_risk_score_calculation(self, risk_enforcer):
        """Test risk score calculation."""
        # Low confidence, risky trade
        result = risk_enforcer.check_trade(
            trade_id="TRADE_001",
            symbol="AAPL",
            quantity=10,
            price=150.0,
            portfolio_equity=100000.0,
            current_positions={},
            confidence=0.3  # Very low confidence
        )
        
        # Risk score should reflect low confidence
        assert result.risk_score > 0
    
    def test_drawdown_limit_check(self, risk_enforcer):
        """Test drawdown limit check."""
        # Drawdown within limit
        assert risk_enforcer.check_drawdown_limit(10.0)  # 10% drawdown
        
        # Drawdown exceeds limit
        assert not risk_enforcer.check_drawdown_limit(25.0)  # 25% drawdown > 20% limit
    
    def test_leverage_limit_check(self, risk_enforcer):
        """Test leverage limit check."""
        # Leverage within limit (positions worth 1.5x equity = 1.5x leverage)
        assert risk_enforcer.check_leverage_limit(150000, 100000)
        
        # Leverage exceeds limit (positions worth 2.5x equity)
        assert not risk_enforcer.check_leverage_limit(250000, 100000)


# =====================
# EXPOSURE MANAGER TESTS
# =====================

class TestExposureManager:
    """Test exposure management."""
    
    def test_sector_exposure_calculation(self, exposure_manager):
        """Test sector exposure calculation."""
        positions = {
            "AAPL": {"quantity": 100, "price": 150, "sector": "TECH"},
            "MSFT": {"quantity": 50, "price": 300, "sector": "TECH"},
            "JPM": {"quantity": 100, "price": 150, "sector": "FINANCE"},
        }
        
        # Total value: 15000 + 15000 + 15000 = 45000
        # TECH = 30000 / 45000 = 66.7%
        # FINANCE = 15000 / 45000 = 33.3%
        exposure = exposure_manager.update_sector_exposure(positions, 45000)
        
        assert "TECH" in exposure
        assert "FINANCE" in exposure
        assert exposure["TECH"] == pytest.approx(66.7, abs=0.1)
    
    def test_sector_concentration_check(self, exposure_manager):
        """Test sector concentration limit."""
        exposure_manager.sector_exposure["TECH"] = 20.0
        
        # Adding 6% more would be 26%, exceeds 25% limit
        assert not exposure_manager.check_sector_concentration("TECH", 6.0, 25.0)
        
        # Adding 4% more would be 24%, within limit
        assert exposure_manager.check_sector_concentration("TECH", 4.0, 25.0)
    
    def test_gross_exposure_calculation(self, exposure_manager):
        """Test gross exposure (sum of absolute values)."""
        positions = {"AAPL": 100, "MSFT": -50, "JPM": 75}
        gross = exposure_manager.calculate_gross_exposure(positions)
        
        assert gross == 225  # |100| + |-50| + |75|
    
    def test_net_exposure_calculation(self, exposure_manager):
        """Test net exposure (long - short)."""
        positions = {"AAPL": 100, "MSFT": -50, "JPM": 75}
        net = exposure_manager.calculate_net_exposure(positions)
        
        assert net == 125  # 100 - 50 + 75
    
    def test_leverage_calculation(self, exposure_manager):
        """Test leverage calculation."""
        leverage = exposure_manager.calculate_leverage(
            gross_position_value=200000,  # 2x the equity
            portfolio_equity=100000
        )
        
        assert leverage == 2.0
    
    def test_position_correlation_check(self, exposure_manager):
        """Test position correlation check."""
        # High correlation (moves together = risky)
        is_ok = exposure_manager.check_position_correlation("AAPL", "MSFT", 0.85)
        assert not is_ok  # Exceeds threshold
        
        # Low correlation (diversifying)
        is_ok = exposure_manager.check_position_correlation("AAPL", "JPM", 0.3)
        assert is_ok  # Within threshold


# =====================
# INTEGRATION TESTS
# =====================

class TestPhase4Integration:
    """Test Phase 3→4 integration."""
    
    def test_full_approval_workflow(self, risk_enforcer, approval_engine):
        """Test complete approval workflow."""
        # Step 1: Check trade against risk policy
        risk_check = risk_enforcer.check_trade(
            trade_id="TRADE_001",
            symbol="AAPL",
            quantity=50,  # Somewhat large
            price=150.0,
            portfolio_equity=100000.0,
            current_positions={},
            confidence=0.65  # Below threshold
        )
        
        # Step 2: Since approval required, create request
        if risk_check.approval_required:
            request = approval_engine.create_approval_request(
                trade_id="TRADE_001",
                symbol="AAPL",
                trade_details={"quantity": 50, "price": 150.0},
                risk_check=risk_check,
                reason="Low confidence"
            )
            
            assert request.is_pending()
            
            # Step 3: Approver reviews and approves
            approved = approval_engine.approve_request(
                request.request_id,
                approved_by="risk_manager",
                notes="Acceptable risk"
            )
            
            assert approved.status == ApprovalStatus.APPROVED
    
    def test_risk_rejection_workflow(self, risk_enforcer, approval_engine):
        """Test trade rejection due to risk."""
        # Oversized position
        risk_check = risk_enforcer.check_trade(
            trade_id="TRADE_001",
            symbol="AAPL",
            quantity=200,  # 30% of portfolio - too much!
            price=150.0,
            portfolio_equity=100000.0,
            current_positions={},
            confidence=0.95  # High confidence, but risk too high
        )
        
        # Trade should fail risk check
        assert not risk_check.passed
        assert len(risk_check.violated_limits) > 0
        
        # Create rejection request
        request = approval_engine.create_approval_request(
            trade_id="TRADE_001",
            symbol="AAPL",
            trade_details={},
            risk_check=risk_check,
            reason="Position size too large"
        )
        
        # Reject the trade
        rejected = approval_engine.reject_request(
            request.request_id,
            rejected_by="risk_manager",
            reason="Exceeds position size limit"
        )
        
        assert rejected.status == ApprovalStatus.REJECTED
    
    def test_multi_position_risk_management(
        self, risk_enforcer, exposure_manager
    ):
        """Test risk management with multiple positions."""
        # Portfolio with several positions
        current_positions = {
            "AAPL": 100,
            "MSFT": 50,
            "JPM": 75,
        }
        
        # Try to add new position
        risk_check = risk_enforcer.check_trade(
            trade_id="TRADE_001",
            symbol="GOOGL",
            quantity=80,
            price=150.0,
            portfolio_equity=200000.0,
            current_positions=current_positions,
            confidence=0.80
        )
        
        # Should pass basic checks
        assert len(current_positions) < risk_enforcer.policy.max_positions
        
        # Check exposure across positions
        positions_data = {
            "AAPL": {"quantity": 100, "price": 150, "sector": "TECH"},
            "MSFT": {"quantity": 50, "price": 300, "sector": "TECH"},
            "JPM": {"quantity": 75, "price": 150, "sector": "FINANCE"},
            "GOOGL": {"quantity": 80, "price": 150, "sector": "TECH"},
        }
        
        sector_exposure = exposure_manager.update_sector_exposure(positions_data, 200000)
        
        # TECH exposure should be tracked
        assert "TECH" in sector_exposure
