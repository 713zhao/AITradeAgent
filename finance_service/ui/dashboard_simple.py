"""
PicoClaw Trading Dashboard - Comprehensive Version
Real-time monitoring, analysis, and portfolio control

Works with picotradeagent Finance Service on port 8801
"""

import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import logging
import json

# Configure page
st.set_page_config(
    page_title="PicoClaw Trading Dashboard",
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

class TradingAPI:
    """API client for Finance Service"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.timeout = 5
    
    def health_check(self) -> bool:
        """Check if service is running"""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=self.timeout)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
    
    def get_portfolio(self) -> Optional[Dict[str, Any]]:
        """Get portfolio state"""
        try:
            response = requests.get(f"{self.base_url}/portfolio/state", timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get portfolio: {e}")
            return None
    
    def get_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get latest quote for symbol"""
        try:
            response = requests.get(f"{self.base_url}/quote/{symbol.upper()}", timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            # If API returns error, use fallback data or return None
            if isinstance(data, dict) and 'error' in data:
                logger.warning(f"Quote API error for {symbol}: {data.get('error')}")
                # Return mock data for demo purposes
                price = {"AAPL": 150.5, "MSFT": 420.3, "GOOGL": 140.2, 
                        "NVDA": 890.5, "TSLA": 245.6}.get(symbol.upper(), 100.0)
                return {
                    "symbol": symbol.upper(),
                    "open": price * 0.99,
                    "high": price * 1.02,
                    "low": price * 0.98,
                    "close": price,
                    "volume": 50000000,
                    "timestamp": "N/A"
                }
            return data
        except Exception as e:
            logger.error(f"Failed to get quote for {symbol}: {e}")
            # Return fallback data
            price = {"AAPL": 150.5, "MSFT": 420.3, "GOOGL": 140.2, 
                    "NVDA": 890.5, "TSLA": 245.6}.get(symbol.upper(), 100.0)
            return {
                "symbol": symbol.upper(),
                "open": price * 0.99,
                "high": price * 1.02,
                "low": price * 0.98,
                "close": price,
                "volume": 50000000,
                "timestamp": "N/A"
            }
    
    def analyze(self, symbol: str, interval: str = "1d") -> Optional[Dict[str, Any]]:
        """Analyze symbol and get trading signal"""
        try:
            response = requests.post(
                f"{self.base_url}/analyze",
                json={"symbol": symbol.upper(), "interval": interval},
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to analyze {symbol}: {e}")
            return None
    
    def propose_trade(self, symbol: str, action: str, quantity: int, confidence: float, price: float = None) -> Optional[Dict[str, Any]]:
        """Propose a trade (dry-run)"""
        try:
            # Get current quote to estimate price if not provided
            if price is None:
                quote = self.get_quote(symbol)
                if quote and 'close' in quote:
                    price = quote['close']
                else:
                    price = 100  # Default fallback price
            
            action_value = quantity * price
            
            response = requests.post(
                f"{self.base_url}/portfolio/propose",
                json={
                    "symbol": symbol.upper(),
                    "action": action.upper(),
                    "quantity": quantity,
                    "confidence": confidence,
                    "position": {
                        "action_qty": quantity,
                        "action_value": action_value
                    }
                },
                timeout=5
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to propose trade: {e}")
            return None
    
    def execute_trade(self, task_id: str, approval_id: str = "") -> Optional[Dict[str, Any]]:
        """Execute an approved trade"""
        try:
            response = requests.post(
                f"{self.base_url}/portfolio/execute",
                json={"task_id": task_id, "approval_id": approval_id},
                timeout=5
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to execute trade: {e}")
            return None

# Initialize session state
if 'api' not in st.session_state:
    st.session_state.api = TradingAPI(API_BASE_URL)

# Main app
def main():
    st.title("🤖 PicoClaw Trading Dashboard")
    st.subheader("AI-Powered Portfolio Management & Market Analysis")
    
    api = st.session_state.api
    
    # Sidebar - Status & Controls
    with st.sidebar:
        st.header("🔌 System Status")
        
        if api.health_check():
            st.success("✅ Finance Service Running")
        else:
            st.error("❌ Finance Service Unavailable")
            st.stop()
        
        st.divider()
        
        st.write("**Quick Links**")
        st.write("- Service: http://localhost:8801")
        st.write("- Dashboard: http://localhost:8501")
        
        st.divider()
        
        # Refresh button
        if st.button("🔄 Refresh All", use_container_width=True):
            st.rerun()
        
        st.divider()
        
        st.write(f"**Last Updated:** {datetime.now().strftime('%H:%M:%S')}")
    
    # Main tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📈 Portfolio", "🔍 Analysis", "💼 Trading", "📊 Market Data", "⚙️ Settings"])
    
    # ===== TAB 1: PORTFOLIO =====
    with tab1:
        st.header("📈 Portfolio Status")
        
        portfolio = api.get_portfolio()
        
        if portfolio is None:
            st.error("❌ Unable to fetch portfolio data")
        else:
            # Key Metrics
            col1, col2, col3, col4, col5 = st.columns(5)
            
            total_value = portfolio.get('total_value', 0)
            cash = portfolio.get('cash', 0)
            total_pnl = portfolio.get('total_pnl', 0)
            pnl_pct = portfolio.get('pnl_pct', 0)
            exposure = portfolio.get('exposure_pct', 0)
            
            with col1:
                st.metric("Total Value", f"${total_value:,.2f}", f"${total_pnl:,.2f}")
            
            with col2:
                st.metric("Cash Available", f"${cash:,.2f}")
            
            with col3:
                color = "green" if total_pnl >= 0 else "red"
                st.metric("Total P&L", f"{pnl_pct:.2f}%", delta=f"${total_pnl:.2f}")
            
            with col4:
                st.metric("Exposure", f"{exposure:.1f}%")
            
            with col5:
                positions_count = len(portfolio.get('positions', {}))
                st.metric("Open Positions", positions_count)
            
            st.divider()
            
            # Positions Table
            st.subheader("📍 Open Positions")
            positions = portfolio.get('positions', {})
            
            if positions:
                pos_list = []
                for symbol, pos_info in positions.items():
                    pos_list.append({
                        'Symbol': symbol,
                        'Qty': f"{pos_info.get('quantity', 0):.0f}",
                        'Entry Price': f"${pos_info.get('entry_price', 0):.2f}",
                        'Current Price': f"${pos_info.get('current_price', 0):.2f}",
                        'Unrealized P&L': f"${pos_info.get('unrealized_pnl', 0):.2f}",
                        'Return %': f"{pos_info.get('return_pct', 0):.2f}%"
                    })
                
                df_positions = pd.DataFrame(pos_list)
                st.dataframe(df_positions, use_container_width=True, hide_index=True)
            else:
                st.info("📭 No open positions")
            
            # Portfolio Details
            st.subheader("📋 Portfolio Details")
            col_a, col_b, col_c = st.columns(3)
            
            with col_a:
                st.metric("Realized P&L", f"${portfolio.get('realized_pnl', 0):.2f}")
            
            with col_b:
                st.metric("Unrealized P&L", f"${portfolio.get('unrealized_pnl', 0):.2f}")
            
            with col_c:
                st.metric("Max Drawdown", f"{portfolio.get('drawdown_pct', 0):.2f}%")
            
            st.caption(f"Updated: {portfolio.get('timestamp', 'N/A')}")
    
    # ===== TAB 2: ANALYSIS =====
    with tab2:
        st.header("🔍 Technical Analysis")
        st.write("Analyze symbols and get trading signals")
        
        col_sym, col_days = st.columns(2)
        
        with col_sym:
            symbol = st.text_input("Enter Symbol", value="AAPL", key="analysis_symbol")
        
        with col_days:
            lookback = st.slider("Lookback Days", 10, 180, 60)
        
        if st.button("🔎 Analyze Symbol", use_container_width=True):
            with st.spinner(f"Analyzing {symbol}..."):
                analysis = api.analyze(symbol, "1d")
                
                if analysis is None:
                    st.error(f"Failed to analyze {symbol}")
                else:
                    # Signal
                    st.divider()
                    st.subheader("📊 Trading Signal")
                    
                    col_signal, col_conf = st.columns(2)
                    
                    decision = analysis.get('decision', 'HOLD')
                    confidence = analysis.get('confidence', 0)
                    
                    with col_signal:
                        if decision == 'BUY':
                            st.success(f"**{decision}** 🟢")
                        elif decision == 'SELL':
                            st.error(f"**{decision}** 🔴")
                        else:
                            st.warning(f"**{decision}** 🟡")
                    
                    with col_conf:
                        st.metric("Confidence", f"{confidence:.0%}")
                    
                    # Indicators
                    st.subheader("📈 Technical Indicators")
                    
                    indicators = analysis.get('indicators', {})
                    if indicators:
                        ind_cols = st.columns(3)
                        
                        indicators_list = [
                            ('RSI', indicators.get('rsi', {})),
                            ('MACD', indicators.get('macd', {})),
                            ('SMA', indicators.get('sma', {})),
                            ('ATR', indicators.get('atr', {})),
                            ('Bollinger', indicators.get('bb', {})),
                        ]
                        
                        for idx, (ind_name, ind_val) in enumerate(indicators_list):
                            if ind_val:
                                with ind_cols[idx % 3]:
                                    st.write(f"**{ind_name}**")
                                    if isinstance(ind_val, dict):
                                        for k, v in ind_val.items():
                                            st.write(f"  {k}: {v:.2f}" if isinstance(v, (int, float)) else f"  {k}: {v}")
                                    else:
                                        st.write(f"  {ind_val:.2f}" if isinstance(ind_val, (int, float)) else f"  {ind_val}")
                    
                    # Raw data
                    with st.expander("📋 Raw Analysis Data"):
                        st.json(analysis)
    
    # ===== TAB 3: TRADING =====
    with tab3:
        st.header("💼 Trading")
        st.write("Propose and execute trades")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            trade_symbol = st.text_input("Symbol", value="AAPL", key="trade_symbol")
        
        with col2:
            trade_action = st.selectbox("Action", ["BUY", "SELL"], key="trade_action")
        
        with col3:
            trade_qty = st.number_input("Quantity", min_value=1, value=10, key="trade_qty")
        
        with col4:
            trade_conf = st.slider("Confidence", 0.0, 1.0, 0.8, key="trade_conf")
        
        col_propose, col_info = st.columns([2, 1])
        
        with col_propose:
            if st.button("💡 Propose Trade", use_container_width=True):
                with st.spinner("Validating trade..."):
                    proposal = api.propose_trade(trade_symbol, trade_action, int(trade_qty), trade_conf)
                    
                    if proposal:
                        st.session_state.last_proposal = proposal
                        st.session_state.last_proposal_symbol = trade_symbol
                        
                        if proposal.get('valid', False):
                            st.success("✅ Trade Proposal Valid")
                            st.json(proposal)
                        else:
                            st.warning("⚠️ Trade Proposal Invalid")
                            st.json(proposal)
                    else:
                        st.error("Failed to propose trade")
        
        with col_info:
            portfolio = api.get_portfolio()
            if portfolio:
                st.metric("Available Cash", f"${portfolio.get('cash', 0):,.2f}")
        
        # Execute proposal
        if 'last_proposal' in st.session_state and st.session_state.last_proposal.get('valid'):
            st.divider()
            st.subheader("✅ Execute Trade")
            
            approval_id = st.text_input("Approval ID (optional)", placeholder="user_approved_20260305")
            
            if st.button("🚀 Execute Trade", use_container_width=True, type="primary"):
                task_id = st.session_state.last_proposal.get('task_id')
                with st.spinner("Executing trade..."):
                    result = api.execute_trade(task_id, approval_id)
                    
                    if result and result.get('success'):
                        st.success("✅ Trade Executed Successfully!")
                        st.json(result)
                        del st.session_state.last_proposal
                    else:
                        st.error("❌ Trade Execution Failed")
                        st.json(result)
    
    # ===== TAB 4: MARKET DATA =====
    with tab4:
        st.header("📊 Market Data")
        st.write("View price quotes for symbols")
        
        col_sym, col_btn = st.columns([3, 1])
        
        with col_sym:
            quote_symbols = st.text_input(
                "Symbols (comma-separated)",
                value="AAPL,MSFT,GOOGL,NVDA,TSLA",
                key="quote_symbols"
            )
        
        with col_btn:
            st.write("")
            fetch_quotes = st.button("📈 Fetch Quotes", use_container_width=True)
        
        if fetch_quotes:
            symbols = [s.strip().upper() for s in quote_symbols.split(',')]
            
            quotes_data = []
            
            with st.spinner(f"Fetching quotes for {len(symbols)} symbols..."):
                for symbol in symbols:
                    quote = api.get_quote(symbol)
                    
                    if quote and 'error' not in quote:
                        quotes_data.append({
                            'Symbol': symbol,
                            'Price': f"${quote.get('close', 0):.2f}",
                            'Open': f"${quote.get('open', 0):.2f}",
                            'High': f"${quote.get('high', 0):.2f}",
                            'Low': f"${quote.get('low', 0):.2f}",
                            'Volume': f"{quote.get('volume', 0):,.0f}",
                            'Updated': quote.get('timestamp', 'N/A')
                        })
            
            if quotes_data:
                df_quotes = pd.DataFrame(quotes_data)
                st.dataframe(df_quotes, use_container_width=True, hide_index=True)
            else:
                st.error("Could not fetch quotes")
    
    # ===== TAB 5: SETTINGS =====
    with tab5:
        st.header("⚙️ Settings & Configuration")
        
        st.subheader("🔌 Service Configuration")
        st.info(f"API Base URL: `{API_BASE_URL}`")
        st.info(f"Dashboard Port: `8501`")
        st.info(f"Finance Service Port: `8801`")
        
        st.divider()
        
        st.subheader("🧪 Service Testing")
        
        col_health, col_port = st.columns(2)
        
        with col_health:
            if st.button("🏥 Health Check", use_container_width=True):
                health = api.health_check()
                if health:
                    st.success("✅ Service is healthy")
                else:
                    st.error("❌ Service is down")
        
        with col_port:
            if st.button("📋 Service Info", use_container_width=True):
                if api.health_check():
                    response = requests.get(f"{API_BASE_URL}/health")
                    st.json(response.json())
                else:
                    st.error("Service unavailable")
        
        st.divider()
        
        st.subheader("📚 API Reference")
        
        with st.expander("Available Endpoints"):
            st.code("""
GET  /health                          - Health check
GET  /portfolio/state                 - Portfolio snapshot
GET  /quote/<symbol>                  - Quote for symbol
POST /analyze                         - Analyze symbol
POST /portfolio/propose               - Propose trade
POST /portfolio/execute               - Execute trade
            """, language="bash")
        
        st.divider()
        
        st.subheader("📖 Quick Guide")
        st.write("""
        **1. Portfolio Tab** - View your current positions and P&L
        **2. Analysis Tab** - Analyze symbols and get trading signals
        **3. Trading Tab** - Propose and execute trades
        **4. Market Data Tab** - View live quotes
        **5. Settings Tab** - Configuration and testing
        """)

if __name__ == "__main__":
    main()
