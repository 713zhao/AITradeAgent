"""
Performance Page
Displays strategy performance metrics, returns distribution, and trade analysis
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import logging
import numpy as np

logger = logging.getLogger(__name__)

API_BASE_URL = "http://localhost:5000"


class PerformanceAPI:
    """Performance data API client"""
    
    @staticmethod
    def get_performance_metrics() -> Optional[Dict[str, Any]]:
        """Get performance metrics"""
        try:
            response = requests.get(f"{API_BASE_URL}/api/dashboard/performance", timeout=5)
            response.raise_for_status()
            return response.json().get('data')
        except Exception as e:
            logger.error(f"Failed to get performance metrics: {e}")
            return None
    
    @staticmethod
    def get_trades(limit: int = 100) -> pd.DataFrame:
        """Get trades for analysis"""
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


def display_performance_metrics():
    """Display key performance metrics"""
    st.subheader("📊 Performance Metrics")
    
    perf = PerformanceAPI.get_performance_metrics()
    
    if perf:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Sharpe Ratio", f"{perf.get('sharpe_ratio', 0):.2f}")
        
        with col2:
            st.metric("Sortino Ratio", f"{perf.get('sortino_ratio', 0):.2f}")
        
        with col3:
            st.metric("Calmar Ratio", f"{perf.get('calmar_ratio', 0):.2f}")
        
        with col4:
            st.metric("Max Drawdown", f"{perf.get('max_drawdown_pct', 0):.2f}%")
        
        st.markdown("---")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Win Rate", f"{perf.get('win_rate_pct', 0):.1f}%")
        
        with col2:
            st.metric("Profit Factor", f"{perf.get('profit_factor', 0):.2f}")
        
        with col3:
            st.metric("Total Trades", perf.get('total_trades', 0))
        
        with col4:
            st.metric("Expectancy", f"${perf.get('expectancy', 0):.2f}")
    else:
        st.error("Unable to load performance metrics")


def display_daily_returns():
    """Display daily returns distribution"""
    st.subheader("📈 Daily Returns Distribution")
    
    trades = PerformanceAPI.get_trades()
    
    if not trades.empty and 'pnl' in trades.columns:
        # Generate sample daily returns (in production, from API)
        returns = trades['pnl'].values if len(trades) > 0 else np.array([])
        
        if len(returns) > 0:
            fig = go.Figure(data=[
                go.Histogram(
                    x=returns,
                    nbinsx=30,
                    name='Daily Returns',
                    marker=dict(color='#1f77b4')
                )
            ])
            
            fig.update_layout(
                title='Distribution of Trade P&L',
                xaxis_title='P&L ($)',
                yaxis_title='Frequency',
                height=400,
                template='plotly_white'
            )
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No return data available")
    else:
        st.info("No trade data available")


def display_monthly_returns():
    """Display monthly returns heatmap"""
    st.subheader("📅 Monthly Returns Heatmap")
    
    trades = PerformanceAPI.get_trades()
    
    if not trades.empty and 'timestamp' in trades.columns and 'pnl_pct' in trades.columns:
        trades['month'] = pd.to_datetime(trades['timestamp']).dt.to_period('M')
        monthly_returns = trades.groupby('month')['pnl_pct'].sum()
        
        if len(monthly_returns) > 0:
            # Convert to dataframe for heatmap
            heatmap_data = monthly_returns.values.reshape(-1, 1)
            
            fig = go.Figure(data=go.Heatmap(
                z=heatmap_data,
                x=['Month'],
                y=[str(m) for m in monthly_returns.index],
                colorscale='RdYlGn',
                zmid=0
            ))
            
            fig.update_layout(
                title='Monthly Returns (%)',
                height=400,
                template='plotly_white'
            )
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No monthly data available")
    else:
        st.info("No trade data for monthly analysis")


def display_trade_statistics():
    """Display trade statistics"""
    st.subheader("📊 Trade Statistics")
    
    trades = PerformanceAPI.get_trades()
    
    if not trades.empty and 'pnl' in trades.columns:
        # Calculate statistics
        winning_trades = trades[trades['pnl'] > 0]
        losing_trades = trades[trades['pnl'] <= 0]
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total Trades", len(trades))
        
        with col2:
            st.metric("Winning Trades", len(winning_trades))
        
        with col3:
            st.metric("Losing Trades", len(losing_trades))
        
        st.markdown("---")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            avg_win = winning_trades['pnl'].mean() if len(winning_trades) > 0 else 0
            st.metric("Avg Win", f"${avg_win:,.2f}")
        
        with col2:
            avg_loss = losing_trades['pnl'].mean() if len(losing_trades) > 0 else 0
            st.metric("Avg Loss", f"${avg_loss:,.2f}")
        
        with col3:
            total_pnl = trades['pnl'].sum()
            st.metric("Total P&L", f"${total_pnl:,.2f}")
    else:
        st.info("No trade data available")


def display_best_worst_trades():
    """Display best and worst trades"""
    st.subheader("🎯 Best & Worst Trades")
    
    trades = PerformanceAPI.get_trades()
    
    if not trades.empty and 'pnl' in trades.columns:
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Best Trades**")
            best_trades = trades.nlargest(5, 'pnl')[['symbol', 'pnl', 'pnl_pct']]
            best_trades['pnl'] = best_trades['pnl'].apply(lambda x: f"${x:,.2f}")
            best_trades['pnl_pct'] = best_trades['pnl_pct'].apply(lambda x: f"{x:.2f}%")
            st.dataframe(best_trades, use_container_width=True)
        
        with col2:
            st.write("**Worst Trades**")
            worst_trades = trades.nsmallest(5, 'pnl')[['symbol', 'pnl', 'pnl_pct']]
            worst_trades['pnl'] = worst_trades['pnl'].apply(lambda x: f"${x:,.2f}")
            worst_trades['pnl_pct'] = worst_trades['pnl_pct'].apply(lambda x: f"{x:.2f}%")
            st.dataframe(worst_trades, use_container_width=True)
    else:
        st.info("No trade data available")


def display():
    """Main performance page display"""
    st.title("📊 Performance")
    
    display_performance_metrics()
    st.markdown("---")
    
    col1, col2 = st.columns([1.2, 1])
    
    with col1:
        display_daily_returns()
        display_monthly_returns()
    
    with col2:
        display_trade_statistics()
        display_best_worst_trades()
    
    # Footer
    st.markdown(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")
