#!/bin/bash
# Quick start script for OpenClaw Finance Dashboard

set -e

echo "🚀 OpenClaw Finance Dashboard - Quick Start"
echo "==========================================="
echo ""

# Get the directory of this script FIRST
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

# Activate virtual environment BEFORE installing dependencies
echo "📦 Activating virtual environment..."
VENV_PATH="$PROJECT_ROOT/venv"
if [ -d "$VENV_PATH/bin" ]; then
    source "$VENV_PATH/bin/activate"
    echo "✅ Virtual environment activated"
else
    echo "⚠️  Virtual environment not found at $VENV_PATH"
    exit 1
fi

# Check if dependencies are installed
echo "📦 Checking dependencies..."
pip install -r requirements_ui.txt > /dev/null 2>&1 && echo "✅ Dependencies installed" || echo "❌ Failed to install dependencies"

# Check if API backend is accessible
echo ""
echo "🔍 Checking API backend..."
API_URL="http://localhost:8801"
if timeout 2 bash -c "echo | nc -q1 localhost 8801" 2>/dev/null; then
    echo "✅ API backend is running at $API_URL"
else
    echo "⚠️  API backend not detected at $API_URL"
    echo "   Please start the API backend first:"
    echo "   python3 run_finance_service.py"
    echo ""
fi

# Start Streamlit
echo ""
echo "🎯 Starting Streamlit Dashboard..."
echo "   Dashboard will open at: http://localhost:8501"
echo "   Press Ctrl+C to stop"
echo ""

streamlit run finance_service/ui/dashboard.py
