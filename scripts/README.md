# Scripts Directory

This directory contains utility scripts, deployment tools, and analysis utilities for the PicoClaw Trading Agent project.

## 🎯 Main Entry Points (Start Here)

### Finance Service
- **`run_finance_service.py`** ⭐ **[Called by: start_all.sh]**
  - Main Flask backend for all trading operations
  - Runs on `http://localhost:8801`
  - Provides market data, analysis, portfolio management, trade execution
  - **Start command**: `python3 scripts/run_finance_service.py`
  
### Paper Trading Pipeline
- **`run_paper_trading.py`**
  - Full paper trading simulation
  - Runs backtests and strategy execution
  - **Start command**: `python3 scripts/run_paper_trading.py`

### Simple Execution
- **`run_simple.py`**
  - Lightweight execution mode
  - Quick strategy validation
  - **Start command**: `python3 scripts/run_simple.py`

### Setup & Configuration
- **`setup_paper_trading.py`** - Configure paper trading environment
- **`setup.sh`** - Initial project setup and dependencies

### Startup Scripts
- **`start_paper_trading.sh`** - Start paper trading pipeline
- **`run_dashboard.sh`** - Start Streamlit dashboard UI (called by start_all.sh)
- **`run_network_mode.sh`** - Run in network mode

---

## 📊 Monitoring & Automation

### Progress Monitor (Heartbeat Check) ⭐ **IMPORTANT**
- **`progress_monitor.py`**
  - **Purpose**: Automated heartbeat & performance check with Telegram notifications
  - **Frequency**: Every 30 minutes (1800 seconds)
  - **What it does**: 
    - Checks latest backtest results from database
    - Compares metrics against targets:
      - Target CAGR: 20%
      - Target Sharpe Ratio: 1.0
      - Target Max Drawdown: 30%
    - Sends Telegram notifications with performance summary and recommendations
    - Logs progress to `memory/progress_monitor.md`
    - Tracks state in `memory/progress_monitor_state.json`
  - **Notification Triggers**:
    1. New backtest results detected
    2. 30+ minutes have passed since last notification (to avoid spam)
  - **Requirements**: 
    - `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`
    - Backtest database with recent data (`finance_service/storage/backtest.sqlite`)
  - **Run command**: `python3 scripts/progress_monitor.py`
  - **Typical Usage**: Run in a cron job or systemd timer for continuous monitoring

---

## 🔍 Analysis & Optimization Scripts

### Market Analysis
- **`analyze_regime_detection.py`** - Analyze market regime detection algorithms
- **`analyze_fundamentals_distribution.py`** - Analyze distribution of fundamental indicators
- **`quick_regime_analysis.py`** - Quick market regime analysis (uses latest backtest data)

### Parameter Optimization
- **`optimize_drawdown.py`** - Optimize portfolio parameters for better drawdown control
- **`optimize_parameters.py`** - Optimize trading strategy parameters

---

## 🎯 Trading & Signal Scripts

### Signal Status
- **`check_current_signals.py`** - Check current trading signals and recommendations
- **`check_sma20_signals.py`** - Analyze SMA20 crossing signals

### Trading Utilities
- **`simulate_trade.py`** - Simulate trading scenarios and validate strategies
- **`manual_buy_asml.py`** - Manual ASML stock purchase script
- **`reset_and_book_asml.py`** - Reset and book ASML trades

---

## 💬 Telegram Integration Agents

### Automated Notifications
- **`telegram_forwarder_agent.py`** - Forward trade signals and alerts via Telegram
- **`telegram_notifier_agent.py`** - Send general notifications and updates
- **`telegram_watch_agent.py`** - Monitor trades and market conditions via Telegram
- **`notify_telegram.py`** - Utility for sending custom Telegram messages

---

## 📈 Reporting & Inspection

### Backtest Reports
- **`show_finance_backtest.py`** - Display detailed backtest results and metrics
- **`get_latest_backtest.py`** - Retrieve and display latest backtest data
- **`describe_backtest.py`** - Show backtest statistics summary

### System Inspection
- **`show_tables.py`** - Display database table contents
- **`inspect_cache.py`** - Inspect cached data and state
- **`validate_system.py`** - Validate system configuration and readiness
- **`verify_fixes.py`** - Verify that system fixes have been applied

---

## 🚀 Deployment Tools

### Docker Deployment
- **`docker-deploy.sh`** - Deploy the trading agent using Docker
- **`docker-verify.sh`** - Verify Docker deployment and configuration

---

## 🧪 Development & Testing

### Code Coverage & Testing
- **`add_cov.py`** - Add code coverage metrics to test reports

---

## 📋 Usage Examples

### Quick Start
```bash
# Start main finance service (from project root)
./start_all.sh

# Or start services individually
python3 scripts/run_finance_service.py
bash scripts/run_dashboard.sh
```

### Monitoring (with Telegram notifications every 30 mins)
```bash
# Run heartbeat check - sends performance summary via Telegram
python3 scripts/progress_monitor.py

# Check current signals
python3 scripts/check_current_signals.py

# Validate system configuration
python3 scripts/validate_system.py
```

### Analysis
```bash
# Analyze market regime
python3 scripts/quick_regime_analysis.py

# Show latest backtest results
python3 scripts/get_latest_backtest.py
```

### Trading
```bash
# Simulate a trade scenario
python3 scripts/simulate_trade.py

# Check SMA20 signals
python3 scripts/check_sma20_signals.py
```

### Deployment
```bash
# Deploy with Docker
bash scripts/docker-deploy.sh

# Verify deployment
bash scripts/docker-verify.sh
```

---

## ⚙️ Before Running Scripts

Ensure that:
1. **Environment variables** are set in `.env` file in project root
2. **Dependencies installed**: `pip install -r requirements.txt`
3. **Virtual environment activated** (if running directly, not via start_all.sh)
4. **For Telegram scripts** (including progress_monitor.py): Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`
5. **For Docker scripts**: Docker and Docker Compose are installed
6. **For progress_monitor.py**: Ensure backtest database has recent data

---

## 📍 Key Paths & Locations

| Resource | Location |
|----------|----------|
| Finance Database | `finance_service/storage/finance.db` |
| Backtest Database | `finance_service/storage/backtest.sqlite` |
| Progress Monitor State | `memory/progress_monitor_state.json` |
| Progress Monitor Log | `memory/progress_monitor.md` |
| Test Configuration | `tests/pytest.ini` |
| Environment Template | `.env.template` |
| Active Configuration | `.env` |

---

## 🔗 Related Documentation

- **Main README**: `../README.md` - Project overview and architecture
- **Finance Service**: `../finance_service/` - Core backend implementation
- **Tests**: `../tests/` - Test suite with pytest.ini configuration
- **PicoClaw Config**: `../picoclaw_config/` - PicoClaw agent integration
- **Documentation**: `../doc/` - Additional documentation

---

## 📝 Notes

- **Import scripts use relative paths** - Run them from project root or with `python3 scripts/script_name.py`
- **Main application entry points remain in root** - `./start_all.sh` is the primary way to start services
- **Test files stay in tests/ directory** - Use pytest to run: `python3 -m pytest tests/ -v`
- **Scripts are organized by category** - For new scripts, add to appropriate category and update this file
- **Progress Monitor is your heartbeat** - Run it continuously (via cron/systemd timer) for 30-minute performance checks

---

## 🆘 Troubleshooting

### Progress Monitor Not Sending Telegram Notifications
- Check `.env` has both `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` 
- Verify `memory/progress_monitor_state.json` exists and is writable
- Ensure backtest database has recent data: `ls -la finance_service/storage/backtest.sqlite`
- Check Telegram bot token is valid and chat ID is correct
- Run manually to see error messages: `python3 scripts/progress_monitor.py`

### Script Import Errors
If scripts can't find `finance_service` module:
```bash
cd /path/to/project/root
python3 scripts/script_name.py
```

### Finance Service Won't Start
- Check if port 8801 is already in use: `lsof -i :8801`
- Verify dependencies: `pip install -r requirements.txt`
- Check logs: `tail -f finance_service.log`

### Scripts Timing Out
- Ensure database is not locked (close other processes)
- Check system resources: `free -h` and `df -h`
