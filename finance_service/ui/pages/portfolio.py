"""
Portfolio Page
Displays current holdings, allocation, and equity curve
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

API_BASE_URL = "http://localhost:5000"


class PortfolioAPI:
    """Portfolio data API client"""
    
    @staticmethod
    def get_portfolio_snapshot() -> Optional[Dict[str, Any]]:
        """Get current portfolio snapshot"""
        try:
            response = requests.get(f"{API_BASE_URL}/api/dashboard/portfolio", timeout=5)
            response.raise_for_status()
            return response.json().get('data')
        except Exception as e:
            logger.error(f"Failed to get portfolio: {e}")
            return None
    
    @staticmethod
    def get_positions() -> pd.DataFrame:
        """Get list of current positions"""
        try:
            response = requests.get(f"{API_BASE_URL}/api/dashboard/positions", timeout=5)
            response.raise_for_status()
            data = response.json().get('data', [])
            return pd.DataFrame(data) if data else pd.DataFrame()
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return pd.DataFrame()
    
    @staticmethod
    def get_portfolio_history(period_days: int = 30) -> pd.DataFrame:
        """Get historical portfolio values"""
        try:
            response = requests.get(
                f"{API_BASE_URL}/api/dashboard/charts/portfolio",
                params={"period": f"{period_days}d", "interval": "1h"},
                timeout=5
            )
            response.raise_for_status()
            data = response.json().get('data', [])
            df = pd.DataFrame(data) if data else pd.DataFrame()
            if not df.empty and 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df
        except Exception as e:
            logger.error(f"Failed to get portfolio history: {e}")
            return pd.DataFrame()


def display_portfolio_summary():
    """Display portfolio summary metrics"""
    st.subheader("💼 Portfolio Summary")
    
    snapshot = PortfolioAPI.get_portfolio_snapshot()
    
    if snapshot:
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric(
                "Total Value",
                f"${snapshot.get('total_value', 0):,.2f}",
                delta=f"${snapshot.get('daily_return_pct', 0):.2f}%"
            )
        
        with col2:
            st.metric(
                "Equity",
                f"${snapshot.get('equity', 0):,.2f}"
            )
        
        with col3:
            st.metric(
                "Cash",
                f"${snapshot.get('cash', 0):,.2f}"
            )
        
        with col4:
            st.metric(
                "Buying Power",
                f"${snapshot.get('buying_power', 0):,.2f}"
            )
        
        with col5:
            st.metric(
                "Total Return",
                f"{snapshot.get('return_pct', 0):.2f}%"
            )
    else:
        st.error("Unable to load portfolio data")


def display_equity_curve():
    """Display equity curve chart"""
    st.subheader("📈 Equity Curve")
    
    # Period selector
    col1, col2 = st.columns([1, 5])
    with col1:
        period = st.selectbox("Period", ["1W", "1M", "3M", "6M", "1Y"], index=1)
    
    # Convert period to days
    period_map = {"1W": 7, "1M": 30, "3M": 90, "6M": 180, "1Y": 365}
    days = period_map.get(period, 30)
    
    history = PortfolioAPI.get_portfolio_history(days)
    
    if not history.empty:
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=history['timestamp'],
            y=history['portfolio_value'],
            mode='lines',
            name='Portfolio Value',
            line=dict(color='#1f77b4', width=2),
            fill='tozeroy'
        ))
        
        fig.update_layout(
            title="Portfolio Value Over Time",
            xaxis_title="Date",
            yaxis_title="Value ($)",
            hovermode='x unified',
            height=400,
            template="plotly_white"
        )
        
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No historical data available")


def display_positions_table():
    """Display detailed positions table"""
    st.subheader("📊 Current Positions")
    
    positions = PortfolioAPI.get_positions()
    
    if not positions.empty:
        # Format display columns
        display_cols = {
            'symbol': 'Symbol',
            'quantity': 'Quantity',
            'avg_cost': 'Avg Cost',
            'current_price': 'Current Price',
            'market_value': 'Market Value',
            'unrealized_pnl': 'Unrealized P&L',
            'unrealized_pnl_pct': 'Return %',
            'weight': 'Portfolio Weight'
        }
        
        # Create display dataframe
        display_df = pd.DataFrame()
        for col, label in display_cols.items():
            if col in positions.columns:
                if 'pnl_pct' in col or 'weight' in col:
                    display_df[label] = positions[col].apply(lambda x: f"{x:.2f}%")
                elif col in ['avg_cost', 'current_price', 'market_value', 'unrealized_pnl']:
                    display_df[label] = positions[col].apply(lambda x: f"${x:,.2f}")
                else:
                    display_df[label] = positions[col]
        
        st.dataframe(display_df, use_container_width=True)
        
        # Summary stats
        st.markdown("---")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            total_value = positions['market_value'].sum() if 'market_value' in positions.columns else 0
            st.metric("Total Position Value", f"${total_value:,.2f}")
        
        with col2:
            total_pnl = positions['unrealized_pnl'].sum() if 'unrealized_pnl' in positions.columns else 0
            st.metric("Total Unrealized P&L", f"${total_pnl:,.2f}")
        
        with col3:
            count = len(positions)
            st.metric("Number of Positions", count)
    else:
        st.info("No open positions")


def display_allocation_chart():
    """Display position allocation pie chart"""
    st.subheader("🥧 Position Allocation")
    
    positions = PortfolioAPI.get_positions()
    
    if not positions.empty and 'market_value' in positions.columns and 'symbol' in positions.columns:
        # Create allocation dataframe
        alloc_df = positions[['symbol', 'market_value']].copy()
        alloc_df = alloc_df[alloc_df['market_value'] > 0]
        
        if not alloc_df.empty:
            fig = px.pie(
                alloc_df,
                values='market_value',
                names='symbol',
                title='Portfolio Allocation by Symbol'
            )
            
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No positions with positive value")
    else:
        st.info("Unable to display allocation")


def display():
    """Main portfolio page display"""
    st.title("💼 Portfolio")
    
    display_portfolio_summary()
    st.markdown("---")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        display_equity_curve()
        display_positions_table()
    
    with col2:
        display_allocation_chart()
    
    # Footer
    st.markdown(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")
