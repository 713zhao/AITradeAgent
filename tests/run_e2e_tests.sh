#!/bin/bash
# End-to-End Feature Test Runner
# Runs comprehensive tests to check for side effects and regressions

set -e

cd "$(dirname "$0")/.."

echo "=========================================="
echo "🧪 PicoClaw Trading Agent - E2E Test Suite"
echo "=========================================="
echo ""

# Check if Finance Service is running
echo "📋 Checking Finance Service..."
if ! curl -s http://localhost:8801/health > /dev/null 2>&1; then
    echo "❌ Finance Service not running!"
    echo "   Start with: python3 run_finance_service.py"
    exit 1
fi
echo "✅ Finance Service is running"
echo ""

# Check if pytest is installed
if ! python3 -c "import pytest" 2>/dev/null; then
    echo "📦 Installing pytest..."
    pip install -q pytest pytest-asyncio
    echo "✅ pytest installed"
fi

echo ""
echo "=========================================="
echo "🚀 Running Feature Tests..."
echo "=========================================="
echo ""

# Run tests with verbose output
python3 -m pytest tests/test_e2e_features.py -v --tb=short -x

echo ""
echo "=========================================="
echo "✅ Test Suite Complete"
echo "=========================================="
echo ""
echo "📊 Test Summary:"
echo "   • Feature 1: Service Health & Connectivity (4 tests)"
echo "   • Feature 2: Portfolio Management (4 tests)"
echo "   • Feature 3: Market Data & Quotes (4 tests)"
echo "   • Feature 4: Technical Analysis (6 tests)"
echo "   • Feature 5: Trade Proposal & Execution (7 tests)"
echo "   • Feature 6: Data Consistency (4 tests)"
echo "   • Feature 7: Error Handling (4 tests)"
echo "   • Feature 8: Performance (4 tests)"
echo "   • Feature 9: Integration Workflows (2 tests)"
echo ""
echo "Total: 39 test cases"
echo ""
echo "💡 Run specific feature:"
echo "   pytest tests/test_e2e_features.py::TestFeature1ServiceHealth -v"
echo ""
echo "💡 Run with detailed output:"
echo "   pytest tests/test_e2e_features.py -vv --tb=long"
echo ""
