#!/bin/bash
# Comprehensive Test Suite Runner
# Tests all components of the Finance Agent

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test counters
PASSED=0
FAILED=0
SKIPPED=0

# Helper functions
log_test() {
    echo -e "${BLUE}[TEST]${NC} $1"
}

log_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((PASSED++))
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((FAILED++))
}

log_skip() {
    echo -e "${YELLOW}[SKIP]${NC} $1"
    ((SKIPPED++))
}

log_section() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${BLUE}$1${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# Activate venv
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi
source venv/bin/activate

log_section "PHASE 1: Import Tests"

log_test "Testing config import..."
if python3 -c "from finance_service.core.config import Config; Config.validate(); print('✓')" 2>/dev/null; then
    log_pass "Config imports and validates"
else
    log_fail "Config import failed"
    exit 1
fi

log_test "Testing models import..."
if python3 -c "from finance_service.core.models import Position, Decision, Trade; print('✓')" 2>/dev/null; then
    log_pass "Models import successfully"
else
    log_fail "Models import failed"
fi

log_test "Testing tools import..."
if python3 -c "from finance_service.tools.indicator_tools import IndicatorTools; from finance_service.tools.risk_tools import RiskTools; print('✓')" 2>/dev/null; then
    log_pass "Tools import successfully"
else
    log_fail "Tools import failed"
fi

log_test "Testing portfolio import..."
if python3 -c "from finance_service.sim.portfolio import Portfolio; from finance_service.sim.execution import Execution; print('✓')" 2>/dev/null; then
    log_pass "Portfolio simulation imports"
else
    log_fail "Portfolio import failed"
fi

log_test "Testing strategy import..."
if python3 -c "from finance_service.strategies.baseline_rule_strategy import BaselineRuleStrategy; print('✓')" 2>/dev/null; then
    log_pass "Strategy imports successfully"
else
    log_fail "Strategy import failed"
fi

log_section "PHASE 2: Unit Tests (Core Functionality)"

log_test "Running indicator tests..."
if python3 << 'EOF' 2>/dev/null
from finance_service.tools.indicator_tools import IndicatorTools
import sys

# Test RSI
prices = list(range(100, 150))
rsi = IndicatorTools.calc_rsi(prices)
assert len(rsi) > 0 and all(0 <= r <= 100 for r in rsi), "RSI validation failed"

# Test SMA
sma = IndicatorTools.calc_sma(prices, 10)
assert len(sma) > 0, "SMA validation failed"

# Test ATR
highs = [p + 1 for p in prices]
lows = [p - 1 for p in prices]
atr = IndicatorTools.calc_atr(highs, lows, prices)
assert len(atr) > 0, "ATR validation failed"

print("✓")
EOF
then
    log_pass "Indicator calculations work correctly"
else
    log_fail "Indicator tests failed"
fi

log_test "Running portfolio tests..."
if python3 << 'EOF' 2>/dev/null
from finance_service.sim.portfolio import Portfolio

# Test initialization
p = Portfolio(100000)
assert p.total_value == 100000, "Portfolio initialization failed"

# Test buy
success, msg = p.buy("AAPL", 10, 150.0)
assert success and "AAPL" in p.positions, "Buy operation failed"

# Test state
state = p.get_state()
assert "cash" in state and "positions" in state, "Portfolio state failed"

print("✓")
EOF
then
    log_pass "Portfolio operations work correctly"
else
    log_fail "Portfolio tests failed"
fi

log_test "Running risk validation tests..."
if python3 << 'EOF' 2>/dev/null
from finance_service.tools.risk_tools import RiskTools

# Test position sizing
result = RiskTools.calc_position_size("AAPL", 150.0, 2.0, 100000)
assert result["shares"] > 0 and result["stop_loss"] < 150, "Position sizing failed"

# Test trade validation
result = RiskTools.validate_trade("AAPL", "BUY", 10, 150.0, 100000, {})
assert result["valid"] == True, "Trade validation failed"

print("✓")
EOF
then
    log_pass "Risk management validated"
else
    log_fail "Risk validation tests failed"
fi

log_section "PHASE 3: Integration Tests"

log_test "Running analysis pipeline test..."
if python3 -m tests.test_analysis AAPL 2>&1 | grep -q "Decision:"; then
    log_pass "Analysis pipeline works"
else
    log_fail "Analysis pipeline test failed"
fi

log_test "Running portfolio simulation test..."
if python3 -m tests.test_portfolio 2>&1 | grep -q "Performance Metrics"; then
    log_pass "Portfolio simulation works"
else
    log_fail "Portfolio simulation test failed"
fi

log_section "PHASE 4: End-to-End Flow Test"

log_test "Running full end-to-end test..."
if python3 << 'EOF' 2>/dev/null
from finance_service.app import finance_service
from uuid import uuid4

# Step 1: Analyze
analysis = finance_service.analyze("AAPL")
assert "task_id" in analysis and "decision" in analysis, "Analysis failed"

task_id = analysis["task_id"]

# Step 2: Propose (if not HOLD)
if analysis.get("decision") != "HOLD":
    proposal = finance_service.portfolio_propose_trade(analysis)
    assert "valid" in proposal, "Proposal failed"
    
    # Step 3: Execute (test dry-run)
    state_before = finance_service.portfolio_get_state()
    
    if proposal["valid"]:
        execution = finance_service.portfolio_execute_trade(task_id, "test-approval")
        state_after = finance_service.portfolio_get_state()
        assert execution["success"], "Execution failed"

print("✓")
EOF
then
    log_pass "End-to-end flow works"
else
    log_fail "End-to-end test failed"
fi

log_section "PHASE 5: REST API Tests"

log_test "Starting Flask service..."
if python3 -m finance_service.app &>/dev/null &
then
    SERVICE_PID=$!
    sleep 2
    
    log_test "Testing /health endpoint..."
    if curl -s http://localhost:5000/health | grep -q "ok"; then
        log_pass "Health check passed"
    else
        log_fail "Health check failed"
    fi
    
    log_test "Testing /analyze endpoint..."
    if curl -s -X POST http://localhost:5000/analyze \
        -H "Content-Type: application/json" \
        -d '{"symbol": "AAPL"}' | grep -q "decision"; then
        log_pass "Analyze endpoint works"
    else
        log_fail "Analyze endpoint failed"
    fi
    
    log_test "Testing /portfolio/state endpoint..."
    if curl -s http://localhost:5000/portfolio/state | grep -q "cash"; then
        log_pass "Portfolio state endpoint works"
    else
        log_fail "Portfolio state endpoint failed"
    fi
    
    # Cleanup
    kill $SERVICE_PID 2>/dev/null || true
    sleep 1
else
    log_skip "Flask service startup failed"
fi

log_section "PHASE 6: Data Persistence Tests"

log_test "Testing SQLite cache..."
if [ -f "finance_service/storage/cache.sqlite" ]; then
    log_pass "Cache database created"
else
    log_fail "Cache database not found"
fi

log_test "Testing SQLite runs database..."
if [ -f "finance_service/storage/runs.sqlite" ]; then
    log_pass "Runs database created"
else
    log_fail "Runs database not found"
fi

log_section "Test Summary"

TOTAL=$((PASSED + FAILED + SKIPPED))
echo ""
echo -e "Total Tests:  ${TOTAL}"
echo -e "${GREEN}Passed:     ${PASSED}${NC}"
echo -e "${RED}Failed:     ${FAILED}${NC}"
echo -e "${YELLOW}Skipped:    ${SKIPPED}${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ ALL TESTS PASSED!${NC}"
    exit 0
else
    echo -e "${RED}❌ SOME TESTS FAILED${NC}"
    exit 1
fi
