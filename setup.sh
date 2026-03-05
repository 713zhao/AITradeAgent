#!/bin/bash
# PicoClaw Finance Agent - Complete Setup Script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "🚀 PicoClaw Trading Agent - Complete Setup"
echo "=========================================="
echo ""

# 1. Check Python version
echo "📋 Checking Python version..."
python3 --version || { echo "❌ Python 3 not found"; exit 1; }

# 2. Create virtual environment
echo "🔧 Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "   ✅ Virtual environment created"
else
    echo "   ⚠️  Virtual environment already exists"
fi

# Activate virtual environment
source venv/bin/activate
echo "   ✅ Virtual environment activated"

# 3. Install dependencies
echo ""
echo "📦 Installing dependencies..."
if [ -f "requirements.txt" ]; then
    pip install -q -r requirements.txt
    echo "   ✅ Dependencies installed"
else
    echo "   ⚠️  requirements.txt not found, skipping"
fi

# 4. Create required directories
echo ""
echo "📁 Creating directories..."
mkdir -p storage logs config
echo "   ✅ storage/"
echo "   ✅ logs/"
echo "   ✅ config/"

# 5. Setup environment file
echo ""
echo "⚙️  Setting up environment..."
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "   ✅ Created .env from .env.example"
        echo "   ⚠️  Edit .env to configure API keys and channels"
    else
        echo "   ⚠️  No .env.example found"
    fi
else
    echo "   ✅ .env already exists"
fi

# 6. Run unit tests (optional)
echo ""
echo "🧪 Running unit tests..."
if command -v pytest &> /dev/null; then
    python -m pytest tests/ -v -x --tb=short 2>/dev/null || echo "   ⚠️  Some tests failed"
else
    echo "   ⚠️  pytest not installed, skipping tests"
    echo "   💡 Install with: pip install pytest pytest-asyncio"
fi

echo ""
echo "=========================================="
echo "✅ Setup Complete!"
echo "=========================================="
echo ""
echo "📖 NEXT STEPS:"
echo ""
echo "1️⃣  READ THE DOCUMENTATION"
echo "   → cat README.md"
echo "   → See doc/ folder for architecture & planning docs"
echo ""
echo "2️⃣  CONFIGURE (Optional)"
echo "   → Edit .env for Telegram/Slack integration"
echo "   → Check ~/.picoclaw/config.json for PicoClaw settings"
echo ""
echo "3️⃣  START THE SERVICE"
echo "   → python3 run_finance_service.py"
echo "   OR"
echo "   → ./start_finance_service.sh  (runs in background with logging)"
echo "   OR"
echo "   → ./run_dashboard.sh        (start Streamlit UI)"
echo ""
echo "4️⃣  TEST THE SERVICE"
echo "   → curl http://localhost:8801/health"
echo "   → curl http://localhost:8801/quote/AAPL"
echo "   → bash tests/run_tests.sh"
echo ""
echo "5️⃣  USE WITH PICOCLAW"
echo "   → from picoclaw_connector import get_connector"
echo "   → connector = get_connector()"
echo "   → analysis = connector.analyze('AAPL')"
echo ""
echo "📚 More help:"
echo "   • README.md - Complete usage guide"
echo "   • tests/run_tests.sh - Run full test suite"
echo "   • tail -f logs/finance_service.log - Monitor service"
echo ""
