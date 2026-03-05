"""
Risk Dashboard Page
Displays drawdown, exposure, concentration, and risk alerts
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import requests
from datetime import datetime
from typing import Dict, Any, Optional
import logging
import numpy as np

logger = logging.getLogger(__name__)

API_BASE_URL = "http://localhost:5000"


class RiskAPI:
    """Risk data API client"""
    
    @staticmethod
    def get_risk_metrics() -> Optional[Dict[str, Any]]:
        """Get current risk metrics"""
        try:
            response = requests.get(f"{API_BASE_URL}/api/dashboard/risk", timeout=5)
            response.raise_for_status()
            return response.json().get('data')
        except Exception as e:
            logger.error(f"Failed to get risk metrics: {e}")
            return None
    
    @staticmethod
    def get_alerts() -> pd.DataFrame:
        """Get active risk alerts"""
        try:
            response = requests.get(f"{API_BASE_URL}/api/dashboard/alerts", timeout=5)
            response.raise_for_status()
            data = response.json().get('data', [])
            return pd.DataFrame(data) if data else pd.DataFrame()
        except Exception as e:
            logger.error(f"Failed to get alerts: {e}")
            return pd.DataFrame()
    
    @staticmethod
    def get_positions() -> pd.DataFrame:
        """Get positions for risk analysis"""
        try:
            response = requests.get(f"{API_BASE_URL}/api/dashboard/positions", timeout=5)
            response.raise_for_status()
            data = response.json().get('data', [])
            return pd.DataFrame(data) if data else pd.DataFrame()
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return pd.DataFrame()


def display_risk_summary():
    """Display risk metrics summary"""
    st.subheader("⚠️ Risk Metrics")
    
    risk = RiskAPI.get_risk_metrics()
    
    if risk:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            drawdown_pct = risk.get('current_drawdown_pct', 0)
            max_drawdown = risk.get('max_drawdown_pct', 0)
            st.metric(
                "Current Drawdown",
                f"{drawdown_pct:.2f}%",
                delta=f"Max: {max_drawdown:.2f}%"
            )
        
        with col2:
            var_95 = risk.get('var_95_pct', 0)
            st.metric("Value at Risk (95%)", f"{var_95:.2f}%")
        
        with col3:
            volatility = risk.get('volatility_pct', 0)
            st.metric("Volatility", f"{volatility:.2f}%")
        
        with col4:
            beta = risk.get('beta', 0)
            st.metric("Beta", f"{beta:.2f}")
    else:
        st.error("Unable to load risk metrics")


def display_drawdown_chart():
    """Display drawdown over time"""
    st.subheader("📉 Drawdown History")
    
    # Create sample drawdown data (in production, comes from API)
    risk = RiskAPI.get_risk_metrics()
    
    if risk:
        # Create simple drawdown visualization
        drawdown_pct = risk.get('current_drawdown_pct', 0)
        
        fig = go.Figure(data=[
            go.Bar(
                y=[drawdown_pct],
                name='Current Drawdown',
                marker=dict(color='#d62728')
            )
        ])
        
        fig.update_layout(
            title="Current Drawdown Level",
            yaxis_title="Drawdown (%)",
            height=300,
            showlegend=False,
            template="plotly_white"
        )
        
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No drawdown data available")


def display_concentration_risk():
    """Display concentration risk analysis"""
    st.subheader("🎯 Concentration Risk")
    
    positions = RiskAPI.get_positions()
    
    if not positions.empty and 'market_value' in positions.columns:
        total_value = positions['market_value'].sum()
        
        if total_value > 0:
            positions['weight'] = (positions['market_value'] / total_value * 100)
            positions = positions.sort_values('weight', ascending=False)
            
            # Display concentration metrics
            col1, col2, col3 = st.columns(3)
            
            with col1:
                top_position = positions.iloc[0] if len(positions) > 0 else None
                if top_position is not None:
                    st.metric(
                        "Top Position",
                        f"{positions.iloc[0]['symbol']}",
                        f"{positions.iloc[0]['weight']:.1f}%"
                    )
            
            with col2:
                top5_weight = positions.head(5)['weight'].sum()
                st.metric("Top 5 Weight", f"{top5_weight:.1f}%")
            
            with col3:
                herfindahl = (positions['weight'] ** 2).sum()
                st.metric("Herfindahl Index", f"{herfindahl:.2f}")
            
            # Bar chart of top positions
            st.markdown("**Top Positions by Weight**")
            fig = px.bar(
                positions.head(10),
                x='symbol',
                y='weight',
                title='Top 10 Positions by Portfolio Weight',
                labels={'weight': 'Weight (%)', 'symbol': 'Symbol'}
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No positions for concentration analysis")
    else:
        st.info("No position data available")


def display_risk_alerts():
    """Display active risk alerts"""
    st.subheader("🚨 Active Alerts")
    
    alerts = RiskAPI.get_alerts()
    
    if not alerts.empty:
        # Filter to risk alerts
        risk_alerts = alerts[alerts['alert_type'].str.contains('RISK|LIMIT|DRAWDOWN', case=False, na=False)]
        
        if not risk_alerts.empty:
            st.dataframe(risk_alerts, use_container_width=True)
        else:
            st.success("✅ No active risk alerts")
    else:
        st.success("✅ No active alerts")


def display_sector_exposure():
    """Display sector exposure analysis"""
    st.subheader("🏭 Sector Exposure")
    
    positions = RiskAPI.get_positions()
    
    if not positions.empty and 'sector' in positions.columns:
        sector_exposure = positions.groupby('sector')['market_value'].sum()
        
        if len(sector_exposure) > 0:
            fig = px.pie(
                values=sector_exposure.values,
                names=sector_exposure.index,
                title='Portfolio Exposure by Sector'
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No sector data available")
    else:
        st.info("Sector data not available")


def display():
    """Main risk dashboard display"""
    st.title("⚠️ Risk Dashboard")
    
    display_risk_summary()
    st.markdown("---")
    
    col1, col2 = st.columns([1.5, 1])
    
    with col1:
        display_concentration_risk()
        display_drawdown_chart()
    
    with col2:
        display_sector_exposure()
        display_risk_alerts()
    
    # Footer
    st.markdown(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")
