import re

filepath = 'tests/run_tests.sh'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

coverage_section = """
log_section "PHASE 7: Test Coverage"
log_test "Running pytest-cov coverage report..."
if python3 -m pytest tests/ --cov=finance_service --cov-report=html --cov-fail-under=80 2>/dev/null; then
    log_pass "Coverage is above 80%"
else
    log_fail "Coverage check failed (or tests failed)"
fi
"""

# Insert before "Test Summary"
content = content.replace('log_section "Test Summary"', coverage_section + '\nlog_section "Test Summary"')

with open(filepath, 'w', encoding='utf-8', newline='\n') as f:
    f.write(content)
