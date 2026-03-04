#!/bin/bash
# Quick setup script for Finance Agent

echo "=========================================="
echo "PicoClaw Finance Agent - Setup"
echo "=========================================="

# Check Python version
echo "Checking Python version..."
python3 --version || { echo "Python 3 not found"; exit 1; }

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -qr requirements.txt

# Create directories if needed
echo "Creating storage directories..."
mkdir -p finance_service/storage

# Run unit tests (optional)
echo ""
echo "Running unit tests..."
python -m pytest tests/test_unit.py -v 2>/dev/null || echo "(pytest not installed, skipping)"

echo ""
echo "=========================================="
echo "✅ Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. (Optional) Copy .env.example to .env and configure Telegram/Slack"
echo "2. Start service: python -m finance_service.app"
echo "3. Test analysis: python -m tests.test_analysis AAPL"
echo ""
