"""
Backtest Reports Page
Displays historical backtest results and comparison
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

API_BASE_URL = "http://localhost:5000"


class BacktestAPI:
    """Backtest data API client"""
    
    @staticmethod
    def get_backtest_list() -> pd.DataFrame:
        """Get list of backtest runs"""
        # In production, this would fetch from API
        # For now, return empty dataframe
        return pd.DataFrame({
            'backtest_id': ['BT001', 'BT002', 'BT003'],
            'name': ['Test Strategy v1', 'Test Strategy v2', 'Test Strategy v3'],
            'start_date': ['2024-01-01', '2024-01-15', '2024-02-01'],
            'end_date': ['2024-03-31', '2024-03-31', '2024-03-31'],
            'total_return': [0.125, 0.185, 0.095],
            'sharpe_ratio': [1.2, 1.8, 0.9],
            'max_drawdown': [-0.10, -0.08, -0.12],
            'win_rate': [0.55, 0.62, 0.48],
            'trades': [45, 52, 38]
        })
    
    @staticmethod
    def get_backtest_details(backtest_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed backtest results"""
        # In production, fetch from API
        return {
            'backtest_id': backtest_id,
            'name': f'Backtest {backtest_id}',
            'total_return': 0.125,
            'sharpe_ratio': 1.2,
            'sortino_ratio': 1.5,
            'max_drawdown': -0.10,
            'win_rate': 0.55,
            'profit_factor': 1.8,
            'total_trades': 45,
            'winning_trades': 25,
            'losing_trades': 20,
            'avg_win': 250.0,
            'avg_loss': -150.0,
            'expectancy': 95.0
        }


def display_backtest_list():
    """Display list of backtest runs"""
    st.subheader("📊 Backtest Runs")
    
    backtests = BacktestAPI.get_backtest_list()
    
    if not backtests.empty:
        # Format display
        display_df = backtests[['name', 'start_date', 'end_date', 'total_return', 'sharpe_ratio', 'max_drawdown', 'win_rate', 'trades']].copy()
        display_df['total_return'] = display_df['total_return'].apply(lambda x: f"{x:.2%}")
        display_df['sharpe_ratio'] = display_df['sharpe_ratio'].apply(lambda x: f"{x:.2f}")
        display_df['max_drawdown'] = display_df['max_drawdown'].apply(lambda x: f"{x:.2%}")
        display_df['win_rate'] = display_df['win_rate'].apply(lambda x: f"{x:.1%}")
        
        st.dataframe(display_df, use_container_width=True)
        
        return backtests
    else:
        st.info("No backtest results available")
        return backtests


def display_backtest_selector():
    """Display backtest selection dropdown"""
    backtests = BacktestAPI.get_backtest_list()
    
    if not backtests.empty:
        selected = st.selectbox(
            "Select Backtest",
            backtests['backtest_id'],
            format_func=lambda x: backtests[backtests['backtest_id'] == x]['name'].values[0]
        )
        return selected
    return None


def display_backtest_metrics():
    """Display detailed backtest metrics"""
    backtest_id = display_backtest_selector()
    
    if backtest_id:
        st.markdown("---")
        st.subheader("📈 Backtest Metrics")
        
        details = BacktestAPI.get_backtest_details(backtest_id)
        
        if details:
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total Return", f"{details['total_return']:.2%}")
            
            with col2:
                st.metric("Sharpe Ratio", f"{details['sharpe_ratio']:.2f}")
            
            with col3:
                st.metric("Sortino Ratio", f"{details['sortino_ratio']:.2f}")
            
            with col4:
                st.metric("Max Drawdown", f"{details['max_drawdown']:.2%}")
            
            st.markdown("---")
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Win Rate", f"{details['win_rate']:.1%}")
            
            with col2:
                st.metric("Profit Factor", f"{details['profit_factor']:.2f}")
            
            with col3:
                st.metric("Total Trades", details['total_trades'])
            
            with col4:
                st.metric("Expectancy", f"${details['expectancy']:.2f}")
            
            st.markdown("---")
            
            # Trade breakdown
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Winning Trades", details['winning_trades'])
            
            with col2:
                st.metric("Losing Trades", details['losing_trades'])
            
            with col3:
                st.metric("Break-even Trades", 
                         details['total_trades'] - details['winning_trades'] - details['losing_trades'])
            
            st.markdown("---")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.metric("Avg Win", f"${details['avg_win']:.2f}")
            
            with col2:
                st.metric("Avg Loss", f"${details['avg_loss']:.2f}")


def display_backtest_comparison():
    """Display backtest comparison tool"""
    st.markdown("---")
    st.subheader("🔄 Compare Backtests")
    
    backtests = BacktestAPI.get_backtest_list()
    
    if len(backtests) >= 2:
        col1, col2 = st.columns(2)
        
        with col1:
            bt1 = st.selectbox("Backtest 1", backtests['backtest_id'], key='bt1')
        
        with col2:
            bt2 = st.selectbox("Backtest 2", backtests['backtest_id'], key='bt2')
        
        if bt1 != bt2:
            details1 = BacktestAPI.get_backtest_details(bt1)
            details2 = BacktestAPI.get_backtest_details(bt2)
            
            if details1 and details2:
                # Create comparison table
                comparison_data = {
                    'Metric': ['Total Return', 'Sharpe Ratio', 'Max Drawdown', 'Win Rate', 'Total Trades'],
                    'Backtest 1': [
                        f"{details1['total_return']:.2%}",
                        f"{details1['sharpe_ratio']:.2f}",
                        f"{details1['max_drawdown']:.2%}",
                        f"{details1['win_rate']:.1%}",
                        f"{details1['total_trades']}"
                    ],
                    'Backtest 2': [
                        f"{details2['total_return']:.2%}",
                        f"{details2['sharpe_ratio']:.2f}",
                        f"{details2['max_drawdown']:.2%}",
                        f"{details2['win_rate']:.1%}",
                        f"{details2['total_trades']}"
                    ]
                }
                
                comparison_df = pd.DataFrame(comparison_data)
                st.dataframe(comparison_df, use_container_width=True)
        else:
            st.info("Select different backtests to compare")
    else:
        st.info("At least 2 backtests needed for comparison")


def display_download_section():
    """Display download options"""
    st.markdown("---")
    st.subheader("📥 Download")
    
    backtest_id = display_backtest_selector()
    
    if backtest_id:
        col1, col2 = st.columns(2)
        
        with col1:
            st.download_button(
                label="📊 Download Report (PDF)",
                data=b"PDF Report Data",
                file_name=f"backtest_{backtest_id}_{datetime.now().strftime('%Y%m%d')}.pdf",
                mime="application/pdf"
            )
        
        with col2:
            # Sample CSV data
            csv_data = "symbol,entry_price,exit_price,pnl\nAAPL,150.00,155.00,500.00\nGOOG,2800.00,2850.00,1000.00"
            st.download_button(
                label="📋 Download Trades (CSV)",
                data=csv_data,
                file_name=f"trades_{backtest_id}_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )


def display():
    """Main backtest page display"""
    st.title("📊 Backtest Reports")
    
    display_backtest_list()
    display_backtest_metrics()
    display_backtest_comparison()
    display_download_section()
    
    # Footer
    st.markdown(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")
