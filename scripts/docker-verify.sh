#!/bin/bash

# Docker Deployment Verification Script
# This script verifies that the Docker deployment is correctly configured

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_header() {
    echo ""
    echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${NC} $1"
    echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

print_header "Docker Deployment Verification"

PASS=0
FAIL=0
WARN=0

# Check 1: Docker files exist
print_info "Checking Docker configuration files..."
test -f "Dockerfile" && { print_success "Dockerfile found"; ((PASS++)); } || { print_error "Dockerfile not found"; ((FAIL++)); }
test -f "Dockerfile.ui" && { print_success "Dockerfile.ui found"; ((PASS++)); } || { print_error "Dockerfile.ui not found"; ((FAIL++)); }
test -f "docker-compose.yml" && { print_success "docker-compose.yml found"; ((PASS++)); } || { print_error "docker-compose.yml not found"; ((FAIL++)); }
test -f ".dockerignore" && { print_success ".dockerignore found"; ((PASS++)); } || { print_warning ".dockerignore not found"; ((WARN++)); }

# Check 2: Application structure
print_info "\nChecking application structure..."
test -d "finance_service/ui" && { print_success "finance_service/ui directory found"; ((PASS++)); } || { print_error "finance_service/ui directory not found"; ((FAIL++)); }
test -f "finance_service/ui/dashboard.py" && { print_success "dashboard.py found"; ((PASS++)); } || { print_error "dashboard.py not found"; ((FAIL++)); }
test -d "finance_service/ui/pages" && { print_success "UI pages directory found"; PAGE_COUNT=$(ls -1 finance_service/ui/pages/*.py 2>/dev/null | wc -l); echo "    Pages: $PAGE_COUNT files"; ((PASS++)); } || { print_error "UI pages directory not found"; ((FAIL++)); }

# Check 3: Requirements files
print_info "\nChecking requirements files..."
if test -f "requirements.txt"; then
    print_success "requirements.txt found"
    LINE_COUNT=$(wc -l < requirements.txt)
    echo "    Dependencies: $LINE_COUNT"
    ((PASS++))
else
    print_error "requirements.txt not found"
    ((FAIL++))
fi

if test -f "requirements_ui.txt"; then
    print_success "requirements_ui.txt found"
    LINE_COUNT=$(wc -l < requirements_ui.txt)
    echo "    UI Dependencies: $LINE_COUNT"
    ((PASS++))
else
    print_error "requirements_ui.txt not found"
    ((FAIL++))
fi

# Check 4: Test files
print_info "\nChecking test configuration..."
if test -f "tests/test_phase8_integration.py"; then
    print_success "Test suite found"
    TEST_COUNT=$(grep -c "def test_" tests/test_phase8_integration.py || echo "0")
    echo "    Test cases: $TEST_COUNT"
    ((PASS++))
else
    print_warning "Test suite not found"
    ((WARN++))
fi

# Check 5: Documentation
print_info "\nChecking documentation..."
if test -f "PHASE8_DOCKER_DEPLOYMENT.md"; then
    print_success "Docker deployment guide found"
    ((PASS++))
else
    print_warning "Docker deployment guide not found"
    ((WARN++))
fi

if test -f "PHASE8_DASHBOARD.md"; then
    print_success "Dashboard documentation found"
    ((PASS++))
else
    print_warning "Dashboard documentation not found"
    ((WARN++))
fi

# Check 6: Scripts
print_info "\nChecking deployment scripts..."
if test -f "docker-deploy.sh"; then
    if test -x "docker-deploy.sh"; then
        print_success "docker-deploy.sh found and executable"
        ((PASS++))
    else
        print_warning "docker-deploy.sh found but not executable"
        ((WARN++))
    fi
else
    print_error "docker-deploy.sh not found"
    ((FAIL++))
fi

# Check 7: Configuration
print_info "\nChecking configuration files..."
test -f ".env.template" && { print_success ".env.template found"; ((PASS++)); } || { print_warning ".env.template not found"; ((WARN++)); }

# Verify docker-compose services
print_info "\nChecking docker-compose services..."
if test -f "docker-compose.yml"; then
    echo "    Essential services:"
    for svc in picotradeagent dashboard redis nginx; do
        if grep -q "^  $svc:" "docker-compose.yml"; then
            print_success "$svc service configured"
            ((PASS++))
        else
            print_error "$svc service not configured"
            ((FAIL++))
        fi
    done
fi

# Summary
print_header "Verification Summary"
echo -e "${GREEN}Passed:${NC} $PASS"
echo -e "${YELLOW}Warnings:${NC} $WARN"
echo -e "${RED}Failed:${NC} $FAIL"

total=$((PASS + WARN + FAIL))
echo ""
echo "Total checks: $total"

# Final status
if [ $FAIL -eq 0 ]; then
    echo ""
    print_success "All checks passed! System ready to deploy."
    echo ""
    echo "Next steps:"
    echo "  1. Copy .env.template to .env"
    echo "     cp .env.template .env"
    echo ""
    echo "  2. Build and start services:"
    echo "     ./docker-deploy.sh up"
    exit 0
else
    echo ""
    print_error "Some critical checks failed!"
    exit 1
fi

