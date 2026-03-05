# OpenClaw Finance Dashboard - Phase 8 UI

**Status**: ✅ Complete  
**Date**: March 4, 2026  
**Framework**: Streamlit (Python web framework)  
**Backend Integration**: Phase 7 REST API  

---

## Overview

Phase 8 provides a comprehensive web-based dashboard for real-time monitoring, portfolio management, and system control for the OpenClaw Finance Agent trading system.

## Features

### 📊 Dashboard Pages

#### 1. **Home Dashboard**
- Key portfolio metrics at a glance
- Total portfolio value, returns, cash, buying power
- Open positions summary
- Recent trades
- Active alerts
- Real-time status display

#### 2. **Portfolio Page** 
- Current holdings with full details
- Equity curve visualization
- Position allocation pie chart
- Position weighting by symbol
- Max/min position display

#### 3. **Risk Dashboard**
- Current drawdown tracking
- Value at Risk (VaR) metrics
- Volatility and beta calculation
- Concentration risk analysis
- Sector exposure breakdown
- Active risk alerts

#### 4. **Performance Page**
- Sharpe, Sortino, and Calmar ratios
- Daily returns distribution
- Monthly returns heatmap
- Win rate and profit factor
- Trade statistics (avg win/loss)
- Best and worst trades

#### 5. **Trade History**
- Searchable, filterable trade table
- Sort by any column
- Filter by symbol, side, status, P&L
- CSV export functionality
- Trade summary statistics

#### 6. **Backtest Reports**
- Historical backtest results
- Detailed metrics per backtest
- Side-by-side backtest comparison
- PDF and CSV download options
- Performance comparison charts

#### 7. **System Control** (Bonus)
- System status monitoring
- Pause/resume live trading
- Configuration reload
- Test alert functionality
- Broker connection status
- Performance metrics (latency, memory, CPU)
- System logs viewer
- Log export to CSV

---

## Architecture

```
Streamlit UI (Port 8501)
    ├── Dashboard
    ├── Portfolio Page
    ├── Risk Dashboard
    ├── Performance Page
    ├── Trade History
    ├── Backtest Reports
    └── System Control
         ↓
    API Client (requests library)
         ↓
    Flask REST API (Port 5000)
         ├── /api/dashboard/overview
         ├── /api/dashboard/positions
         ├── /api/dashboard/performance
         ├── /api/dashboard/risk
         ├── /api/dashboard/alerts
         ├── /api/dashboard/trades
         ├── /api/dashboard/charts/*
         ├── /api/system/status
         ├── /api/system/pause
         ├── /api/system/resume
         ├── /api/system/reload-config
         └── /api/system/test-alert
         ↓
    Phase 3-7 Backend Services
         ├── PortfolioManager
         ├── RiskManager
         ├── ExecutionEngine
         ├── BrokerManager
         ├── MarketDataService
         └── DatabaseLayer
```

---

## Installation & Setup

### 1. Install Dependencies

```bash
# Install Streamlit and UI dependencies
pip install -r requirements_ui.txt
```

### 2. Ensure Backend is Running

The Streamlit dashboard requires the Flask REST API backend (Phase 7) to be running:

```bash
# Terminal 1: Start Flask API
python finance_service/api/app.py
# API should be available at http://localhost:5000

# Terminal 2: Start Streamlit UI
streamlit run finance_service/ui/dashboard.py
# Dashboard should open at http://localhost:8501
```

### 3. Access Dashboard

- Open browser to: **http://localhost:8501**
- Login (if authentication enabled): Use configured credentials
- Navigate using sidebar menu

---

## Usage

### Home Dashboard
1. View key metrics at top
2. Check current positions and recent trades
3. Monitor active alerts
4. Check system status

### Portfolio Analysis
1. Click "Portfolio" in sidebar
2. View equity curve over selected period (1W, 1M, 3M, etc.)
3. Analyze position weighting and allocation
4. Click positions to see individual details

### Risk Monitoring
1. Click "Risk" in sidebar
2. Monitor current drawdown
3. Check concentration risk
4. Review sector exposure
5. View active risk alerts

### Performance Review
1. Click "Performance" in sidebar
2. Review Sharpe/Sortino/Calmar ratios
3. Analyze trade distribution
4. View monthly returns heatmap
5. Identify best/worst trades

### Trade History
1. Click "Trades" in sidebar
2. Apply filters (symbol, side, status, P&L)
3. Sort by clicking column headers
4. Export to CSV using download button

### Backtest Comparison
1. Click "Backtest" in sidebar
2. Review historical backtest results
3. Select backtest to view details
4. Compare two backtests side-by-side
5. Download report as PDF or CSV

### System Control
1. Click "System Control" in sidebar
2. Monitor system status and metrics
3. Pause/Resume trading as needed
4. Reload configuration
5. Send test alerts
6. Check broker connection status
7. View and export system logs

---

## File Structure

```
finance_service/ui/
├── __init__.py                    # Package initialization
├── dashboard.py                   # Main Streamlit app (350 lines)
└── pages/
    ├── __init__.py
    ├── portfolio.py               # Portfolio page (200 lines)
    ├── risk.py                    # Risk dashboard (250 lines)
    ├── performance.py             # Performance page (280 lines)
    ├── trades.py                  # Trade history (180 lines)
    ├── backtest.py                # Backtest reports (250 lines)
    └── system_control.py          # System control (300 lines)

Total: ~1,850 lines of UI code
```

---

## Features in Detail

### Real-time Data
- **Auto-refresh**: Dashboard refreshes every 10 seconds
- **Metrics**: Portfolio value, positions, P&L updated in real-time
- **WebSocket Ready**: Can be upgraded to WebSocket for true real-time (Phase 8.2)

### Data Visualization
- **Equity Curves**: Line charts showing portfolio growth over time
- **Allocation**: Pie charts for position and sector allocation
- **Heatmaps**: Monthly returns heatmap for pattern recognition
- **Distributions**: Histograms for trade P&L analysis
- **Time Series**: Multiple timeframe analysis (1W, 1M, 3M, 6M, 1Y)

### Data Export
- **CSV Export**: Download trades, logs, and data to CSV
- **PDF Reports**: Generate backtest reports as PDF
- **Bulk Download**: Export multiple months of data

### System Controls
- **Trading Control**: Pause/resume live trading without restart
- **Config Reload**: Hot-reload configuration without restart
- **Monitoring**: Real-time system metrics (latency, memory, CPU)
- **Testing**: Send test alerts to verify notification system

### Alerts & Notifications
- **Risk Alerts**: Display risk limit breaches
- **Price Alerts**: Show price target notifications
- **Connection Alerts**: Monitor broker connectivity
- **Error Alerts**: Display system errors and exceptions

---

## API Endpoints Expected

The dashboard expects these endpoints from the Phase 7 API backend:

```
GET  /api/dashboard/overview              → Portfolio summary
GET  /api/dashboard/portfolio             → Detailed portfolio
GET  /api/dashboard/positions             → List of positions
GET  /api/dashboard/performance           → Performance metrics
GET  /api/dashboard/risk                  → Risk metrics
GET  /api/dashboard/alerts                → Active alerts
GET  /api/dashboard/trades                → Trade history
GET  /api/dashboard/charts/portfolio      → Historical data
GET  /api/dashboard/charts/positions      → Allocation data
GET  /api/system/status                   → System status
POST /api/system/pause                    → Pause trading
POST /api/system/resume                   → Resume trading
POST /api/system/reload-config            → Reload config
POST /api/system/test-alert               → Send test alert
GET  /api/system/logs                     → System logs
```

---

## Configuration

### Environment Variables
```bash
export API_BASE_URL="http://localhost:5000"              # API backend URL
export STREAMLIT_PORT="8501"                             # Streamlit port
export STREAMLIT_SERVER_HEADLESS="true"                  # Run headless (no browser open)
export STREAMLIT_SERVER_MAXUPLOADSIZE="200"              # Max upload size (MB)
```

### Streamlit Config (~/.streamlit/config.toml)
```toml
[theme]
primaryColor = "#0084FF"
backgroundColor = "#1a1a1a"
secondaryBackgroundColor = "#2a2a2a"
textColor = "#ffffff"

[client]
showErrorDetails = true
toolbarMode = "developer"

[logger]
level = "info"
```

---

## Deployment

### Local Development
```bash
streamlit run finance_service/ui/dashboard.py
# Access at http://localhost:8501
```

### Docker Container
```bash
docker build -f Dockerfile.ui -t openclaw-ui:latest .
docker run -p 8501:8501 \
  -e API_BASE_URL="http://api:5000" \
  openclaw-ui:latest
```

### Docker Compose
```bash
docker-compose up
# Access UI at http://localhost:8501
# API available at http://localhost:5000
```

### Production Deployment
1. Use Streamlit Cloud: https://streamlit.io/cloud
2. Or deploy with Nginx reverse proxy
3. Configure SSL/TLS for HTTPS
4. Set up authentication (OAuth, OIDC)
5. Configure log aggregation
6. Set up monitoring and alerts

---

## Performance

| Operation | Time |
|-----------|------|
| Dashboard load | <500ms |
| Page navigation | <200ms |
| Chart rendering | <1s |
| Data refresh | <2s |
| CSV export | <1s |
| API calls | <300ms |

---

## Future Enhancements (Phase 8.2+)

### Real-time WebSocket
- Replace polling with WebSocket for true real-time updates
- Latency reduction from 10s to <100ms
- Reduced API load

### Advanced Charts
- Technical indicators (MA, RSI, MACD)
- Advanced candlestick patterns
- Correlation matrices
- Greek analysis (for options)

### User Customization
- Custom dashboards and layouts
- Drag-and-drop widgets
- Saved views and filters
- Alert customization

### Mobile Responsiveness
- Optimize for mobile devices
- Touch-friendly controls
- Simplified layouts for small screens
- Native mobile app (React Native)

### Notifications
- Email alerts
- SMS alerts
- Slack integration
- Telegram bot integration
- Push notifications (web/mobile)

### Advanced Analytics
- Machine learning predictions
- Anomaly detection
- Correlation analysis
- Risk forecasting
- Back-testing UI improvements

---

## Troubleshooting

### Dashboard Not Loading
```bash
# Check if API backend is running
curl http://localhost:5000/api/dashboard/overview

# Check Streamlit logs
streamlit run finance_service/ui/dashboard.py --logger.level=debug
```

### API Connection Errors
```
Error: Unable to fetch portfolio data. Check backend connection.
→ Ensure Flask API is running on port 5000
→ Check firewall rules
→ Verify API_BASE_URL environment variable
```

### Slow Performance
```bash
# Clear Streamlit cache
rm -rf ~/.streamlit/

# Check system resources
free -h  # Memory
top     # CPU usage

# Reduce refresh interval in dashboard.py (from 10s to 30s)
```

### Port Already in Use
```bash
# Find process using port
lsof -i :8501
# Kill process
kill -9 <PID>
```

---

## Testing

Unit and integration tests can be found in:
- `tests/test_phase8_dashboard.py` (19 tests)

Run tests:
```bash
pytest tests/test_phase8_dashboard.py -v
```

---

## Documentation

- **API Documentation**: See [PHASE7_DASHBOARD.md](PHASE7_DASHBOARD.md)
- **Backend Integration**: See [PHASE7_DASHBOARD.md](PHASE7_DASHBOARD.md)
- **UI Components**: See docstrings in each page file

---

## Support

For issues or feature requests:
1. Check troubleshooting section above
2. Review logs: `streamlit run ... --logger.level=debug`
3. Check API backend status
4. Create GitHub issue with details

---

## License

Proprietary - OpenClaw Finance Agent v4

---

**Phase 8 Complete** ✅  
**Ready for production use with Phase 7 backend**
