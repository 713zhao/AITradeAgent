#!/bin/bash
# Start Finance Service and Dashboard accessible from local network

LOCAL_IP=$(hostname -I | awk '{print $1}')
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🌐 PicoClaw Trading System - Network Mode"
echo "========================================"
echo ""
echo "📍 Local Network IP: $LOCAL_IP"
echo ""
echo "Access Points:"
echo "  • Finance Service API:  http://$LOCAL_IP:8801"
echo "  • Dashboard:            http://$LOCAL_IP:8501"
echo "  • Health Check:         http://$LOCAL_IP:8801/health"
echo "  • Portfolio State:      http://$LOCAL_IP:8801/portfolio/state"
echo ""
echo "From other machines on the network, use:"
echo "  • curl http://$LOCAL_IP:8801/portfolio/state"
echo "  • Open browser: http://$LOCAL_IP:8501"
echo ""

# Check if API is running
echo "Checking if API backend is already running..."
if timeout 2 curl -s http://127.0.0.1:8801/health > /dev/null 2>&1; then
    echo "✅ API is already running on port 8801"
    echo ""
    echo "Starting Dashboard only..."
    cd "$PROJECT_DIR"
    source venv/bin/activate 2>/dev/null
    streamlit run finance_service/ui/dashboard.py
else
    echo "⚠️  API backend not running. Please start it first:"
    echo "   python3 finance_service/run_finance_service.py"
    echo ""
    echo "Then run this script again to start the dashboard."
fi
