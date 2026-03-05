"""
Trades Page
Displays trade history with filtering and export capabilities
"""

import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)

API_BASE_URL = "http://localhost:5000"


class TradesAPI:
    """Trades data API client"""
    
    @staticmethod
    def get_trades(limit: int = 100) -> pd.DataFrame:
        """Get trades"""
        try:
            response = requests.get(
                f"{API_BASE_URL}/api/dashboard/trades",
                params={"limit": limit},
                timeout=5
            )
            response.raise_for_status()
            data = response.json().get('data', [])
            df = pd.DataFrame(data) if data else pd.DataFrame()
            if not df.empty and 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df
        except Exception as e:
            logger.error(f"Failed to get trades: {e}")
            return pd.DataFrame()


def display_trade_filters():
    """Display trade filter controls"""
    st.subheader("🔍 Filters")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        limit = st.selectbox("Limit", [10, 25, 50, 100, 250, 500])
    
    with col2:
        side_filter = st.multiselect("Side", ["BUY", "SELL", "LONG", "SHORT"], default=None)
    
    with col3:
        status_filter = st.multiselect("Status", ["CLOSED", "OPEN", "EXECUTED"], default=None)
    
    with col4:
        min_pnl = st.number_input("Min P&L ($)", value=-10000, step=100)
    
    return {
        'limit': limit,
        'side_filter': side_filter,
        'status_filter': status_filter,
        'min_pnl': min_pnl
    }


def display_trades_table():
    """Display trades table with sorting capabilities"""
    st.subheader("📋 Trade History")
    
    filters = display_trade_filters()
    
    trades = TradesAPI.get_trades(limit=filters['limit'])
    
    if not trades.empty:
        # Apply filters
        filtered_trades = trades.copy()
        
        if filters['side_filter']:
            filtered_trades = filtered_trades[filtered_trades['side'].isin(filters['side_filter'])]
        
        if filters['status_filter']:
            filtered_trades = filtered_trades[filtered_trades['status'].isin(filters['status_filter'])]
        
        if 'pnl' in filtered_trades.columns:
            filtered_trades = filtered_trades[filtered_trades['pnl'] >= filters['min_pnl']]
        
        if not filtered_trades.empty:
            # Format display columns
            display_cols = ['symbol', 'side', 'quantity', 'entry_price', 'exit_price', 'pnl', 'pnl_pct', 'duration_seconds', 'status']
            display_df = filtered_trades[[col for col in display_cols if col in filtered_trades.columns]].copy()
            
            # Format numeric columns
            for col in ['entry_price', 'exit_price']:
                if col in display_df.columns:
                    display_df[col] = display_df[col].apply(lambda x: f"${x:,.2f}")
            
            if 'pnl' in display_df.columns:
                display_df['pnl'] = display_df['pnl'].apply(lambda x: f"${x:,.2f}")
            
            if 'pnl_pct' in display_df.columns:
                display_df['pnl_pct'] = display_df['pnl_pct'].apply(lambda x: f"{x:.2f}%")
            
            if 'duration_seconds' in display_df.columns:
                display_df['duration_seconds'] = display_df['duration_seconds'].apply(lambda x: f"{x:.0f}s")
            
            st.dataframe(display_df, use_container_width=True)
            
            # Summary statistics
            st.markdown("---")
            st.write(f"**Showing {len(display_df)} of {len(filtered_trades)} trades**")
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total Trades", len(display_df))
            
            with col2:
                if 'pnl' in filtered_trades.columns:
                    total_pnl = filtered_trades['pnl'].sum()
                    st.metric("Total P&L", f"${total_pnl:,.2f}")
            
            with col3:
                if 'pnl_pct' in filtered_trades.columns:
                    avg_return = filtered_trades['pnl_pct'].mean()
                    st.metric("Avg Return", f"{avg_return:.2f}%")
            
            with col4:
                if 'pnl' in filtered_trades.columns:
                    win_rate = (filtered_trades['pnl'] > 0).sum() / len(filtered_trades) * 100
                    st.metric("Win Rate", f"{win_rate:.1f}%")
            
            # Export button
            st.markdown("---")
            csv = display_df.to_csv(index=False)
            st.download_button(
                label="📥 Export to CSV",
                data=csv,
                file_name=f"trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
        else:
            st.info("No trades match the selected filters")
    else:
        st.info("No trades available")


def display():
    """Main trades page display"""
    st.title("💼 Trade History")
    
    display_trades_table()
    
    # Footer
    st.markdown(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")
