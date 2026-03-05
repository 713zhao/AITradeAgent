#!/bin/bash
# Start both dashboard and finance service with virtual environment
set -e

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

# Color codes for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 PicotradeAgent Startup${NC}"
echo "Project root: $PROJECT_ROOT"

# Check virtual environment
VENV_PATH="$PROJECT_ROOT/venv"

if [ ! -d "$VENV_PATH/bin" ]; then
    echo "❌ Virtual environment not found at $VENV_PATH"
    exit 1
fi

echo -e "${GREEN}✓ Virtual environment: $VENV_PATH${NC}"

# Activate virtual environment
source "$VENV_PATH/bin/activate"

# Set environment variables
export OPENBB_USE_YFINANCE=true
export OPENBB_PROVIDER=yfinance
export FLASK_ENV=production
export PYTHONUNBUFFERED=1
export LOG_LEVEL=INFO

echo -e "${GREEN}✓ Environment activated${NC}"

# Change to project directory
cd "$PROJECT_ROOT"

# Start finance service in background
echo -e "${BLUE}📊 Starting Finance Service (port 8801)...${NC}"
python3 run_finance_service.py &
FINANCE_PID=$!
echo -e "${GREEN}✓ Finance Service PID: $FINANCE_PID${NC}"

# Wait a bit for finance service to start
sleep 2

# Start dashboard if script exists
if [ -f "$PROJECT_ROOT/run_dashboard.sh" ]; then
    echo -e "${BLUE}📈 Starting Dashboard...${NC}"
    bash "$PROJECT_ROOT/run_dashboard.sh" &
    DASHBOARD_PID=$!
    echo -e "${GREEN}✓ Dashboard PID: $DASHBOARD_PID${NC}"
else
    echo -e "${BLUE}⚠️  run_dashboard.sh not found, skipping dashboard${NC}"
fi

echo ""
echo -e "${GREEN}✓ Services started!${NC}"
echo "Finance Service: http://localhost:8801"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Trap Ctrl+C to stop all background processes
trap "kill $FINANCE_PID; [ ! -z '$DASHBOARD_PID' ] && kill $DASHBOARD_PID; echo 'Services stopped'; exit 0" INT

# Keep script running
wait
