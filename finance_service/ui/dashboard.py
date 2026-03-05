"""
Main Streamlit Dashboard Application

Real-time monitoring and control for OpenClaw Finance Agent.
Connects to Phase 7 REST API backend for data.
"""

import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import logging

# Configure page
st.set_page_config(
    page_title="OpenClaw Finance Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
API_BASE_URL = "http://localhost:8801"
REFRESH_INTERVAL = 10  # seconds

# Custom styling
st.markdown("""
<style>
    .metric-box {
        padding: 20px;
        border-radius: 10px;
        background-color: #f0f2f6;
        margin: 10px 0;
    }
    .positive {
        color: green;
        font-weight: bold;
    }
    .negative {
        color: red;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)


class DashboardAPI:
    """API client for dashboard backend"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url
    
    def get_overview(self) -> Optional[Dict[str, Any]]:
        """Get portfolio overview"""
        try:
            response = requests.get(f"{self.base_url}/api/dashboard/overview", timeout=5)
            response.raise_for_status()
            return response.json().get('data')
        except Exception as e:
            logger.error(f"Failed to get overview: {e}")
            return None
    
    def get_positions(self) -> Optional[pd.DataFrame]:
        """Get current positions"""
        try:
            response = requests.get(f"{self.base_url}/api/dashboard/positions", timeout=5)
            response.raise_for_status()
            data = response.json().get('data', [])
            return pd.DataFrame(data) if data else pd.DataFrame()
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return pd.DataFrame()
    
    def get_performance(self) -> Optional[Dict[str, Any]]:
        """Get performance metrics"""
        try:
            response = requests.get(f"{self.base_url}/api/dashboard/performance", timeout=5)
            response.raise_for_status()
            return response.json().get('data')
        except Exception as e:
            logger.error(f"Failed to get performance: {e}")
            return None
    
    def get_risk(self) -> Optional[Dict[str, Any]]:
        """Get risk metrics"""
        try:
            response = requests.get(f"{self.base_url}/api/dashboard/risk", timeout=5)
            response.raise_for_status()
            return response.json().get('data')
        except Exception as e:
            logger.error(f"Failed to get risk metrics: {e}")
            return None
    
    def get_alerts(self) -> Optional[pd.DataFrame]:
        """Get active alerts"""
        try:
            response = requests.get(f"{self.base_url}/api/dashboard/alerts", timeout=5)
            response.raise_for_status()
            data = response.json().get('data', [])
            return pd.DataFrame(data) if data else pd.DataFrame()
        except Exception as e:
            logger.error(f"Failed to get alerts: {e}")
            return pd.DataFrame()
    
    def get_trades(self, limit: int = 50) -> Optional[pd.DataFrame]:
        """Get recent trades"""
        try:
            response = requests.get(
                f"{self.base_url}/api/dashboard/trades",
                params={"limit": limit},
                timeout=5
            )
            response.raise_for_status()
            data = response.json().get('data', [])
            return pd.DataFrame(data) if data else pd.DataFrame()
        except Exception as e:
            logger.error(f"Failed to get trades: {e}")
            return pd.DataFrame()
    
    def pause_trading(self) -> bool:
        """Pause live trading"""
        try:
            response = requests.post(f"{self.base_url}/api/system/pause", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to pause trading: {e}")
            return False
    
    def resume_trading(self) -> bool:
        """Resume live trading"""
        try:
            response = requests.post(f"{self.base_url}/api/system/resume", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to resume trading: {e}")
            return False
    
    def get_system_status(self) -> Optional[Dict[str, Any]]:
        """Get system status"""
        try:
            response = requests.get(f"{self.base_url}/api/system/status", timeout=5)
            response.raise_for_status()
            return response.json().get('data')
        except Exception as e:
            logger.error(f"Failed to get system status: {e}")
            return None


def display_header():
    """Display dashboard header with key metrics"""
    st.title("📊 OpenClaw Finance Dashboard")
    st.markdown("---")
    
    api = DashboardAPI(API_BASE_URL)
    overview = api.get_overview()
    
    if overview:
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric(
                "Portfolio Value",
                f"${overview.get('total_value', 0):,.2f}",
                delta=f"${overview.get('daily_pnl', 0):,.2f}"
            )
        
        with col2:
            return_pct = overview.get('return_pct', 0)
            st.metric(
                "Total Return",
                f"{return_pct:.2f}%",
                delta=f"{overview.get('daily_return_pct', 0):.2f}%"
            )
        
        with col3:
            st.metric(
                "Cash",
                f"${overview.get('cash', 0):,.2f}"
            )
        
        with col4:
            st.metric(
                "Buying Power",
                f"${overview.get('buying_power', 0):,.2f}"
            )
        
        with col5:
            st.metric(
                "Open Positions",
                overview.get('positions_count', 0)
            )
    else:
        st.warning("⚠️ Unable to fetch portfolio data. Check backend connection.")


def display_alerts_summary():
    """Display active alerts summary"""
    api = DashboardAPI(API_BASE_URL)
    alerts = api.get_alerts()
    
    if not alerts.empty:
        st.warning(f"🚨 {len(alerts)} Active Alerts")
        with st.expander("View Alerts", expanded=False):
            st.dataframe(alerts, use_container_width=True)
    else:
        st.success("✅ No active alerts")


def display_positions_summary():
    """Display current positions summary"""
    st.subheader("📈 Current Positions")
    
    api = DashboardAPI(API_BASE_URL)
    positions = api.get_positions()
    
    if not positions.empty:
        # Format columns
        display_cols = ['symbol', 'quantity', 'avg_cost', 'current_price', 'unrealized_pnl', 'unrealized_pnl_pct', 'weight']
        display_positions = positions[[col for col in display_cols if col in positions.columns]]
        
        st.dataframe(display_positions, use_container_width=True)
    else:
        st.info("No open positions")


def display_performance_summary():
    """Display performance metrics"""
    st.subheader("📊 Performance Metrics")
    
    api = DashboardAPI(API_BASE_URL)
    perf = api.get_performance()
    
    if perf:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Sharpe Ratio", f"{perf.get('sharpe_ratio', 0):.2f}")
        
        with col2:
            st.metric("Win Rate", f"{perf.get('win_rate', 0):.1f}%")
        
        with col3:
            st.metric("Profit Factor", f"{perf.get('profit_factor', 0):.2f}")
        
        with col4:
            st.metric("Max Drawdown", f"{perf.get('max_drawdown', 0):.2f}%")
    else:
        st.info("No performance data available")


def display_recent_trades():
    """Display recent trades"""
    st.subheader("💼 Recent Trades")
    
    api = DashboardAPI(API_BASE_URL)
    trades = api.get_trades(limit=10)
    
    if not trades.empty:
        display_cols = ['symbol', 'side', 'quantity', 'entry_price', 'exit_price', 'pnl', 'pnl_pct', 'duration_seconds']
        display_trades = trades[[col for col in display_cols if col in trades.columns]]
        st.dataframe(display_trades, use_container_width=True)
    else:
        st.info("No trades yet")


def main():
    """Main dashboard application"""
    
    # Sidebar navigation
    st.sidebar.title("🗺️ Navigation")
    page = st.sidebar.radio(
        "Select Page",
        ["Home", "Portfolio", "Risk", "Performance", "Trades", "Backtest", "System Control"]
    )
    
    # Display selected page
    if page == "Home":
        display_header()
        st.markdown("---")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            display_positions_summary()
            display_recent_trades()
        
        with col2:
            display_alerts_summary()
            display_performance_summary()
        
        # Auto-refresh info
        st.info(f"ℹ️ Last updated: {datetime.now().strftime('%H:%M:%S')} | Auto-refresh every {REFRESH_INTERVAL}s")
    
    elif page == "Portfolio":
        from pages import portfolio
        portfolio.display()
    
    elif page == "Risk":
        from pages import risk
        risk.display()
    
    elif page == "Performance":
        from pages import performance
        performance.display()
    
    elif page == "Trades":
        from pages import trades
        trades.display()
    
    elif page == "Backtest":
        from pages import backtest
        backtest.display()
    
    elif page == "System Control":
        from pages import system_control
        system_control.display()
    
    # Footer
    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; color: gray;'>
        OpenClaw Finance Agent v4.0 | Phase 7 Backend | Built with Streamlit
        </div>
        """,
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()
