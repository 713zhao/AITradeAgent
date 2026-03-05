"""
System Control Page
System status, pause/resume trading, config reload, log viewer
"""

import streamlit as st
import requests
import pandas as pd
from datetime import datetime
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

API_BASE_URL = "http://localhost:5000"


class SystemAPI:
    """System control API client"""
    
    @staticmethod
    def get_system_status() -> Optional[Dict[str, Any]]:
        """Get system status"""
        try:
            response = requests.get(f"{API_BASE_URL}/api/system/status", timeout=5)
            response.raise_for_status()
            return response.json().get('data')
        except Exception as e:
            logger.error(f"Failed to get system status: {e}")
            return None
    
    @staticmethod
    def pause_trading() -> bool:
        """Pause live trading"""
        try:
            response = requests.post(f"{API_BASE_URL}/api/system/pause", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to pause trading: {e}")
            return False
    
    @staticmethod
    def resume_trading() -> bool:
        """Resume live trading"""
        try:
            response = requests.post(f"{API_BASE_URL}/api/system/resume", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to resume trading: {e}")
            return False
    
    @staticmethod
    def reload_config() -> bool:
        """Reload configuration"""
        try:
            response = requests.post(f"{API_BASE_URL}/api/system/reload-config", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to reload config: {e}")
            return False
    
    @staticmethod
    def send_test_alert() -> bool:
        """Send test alert"""
        try:
            response = requests.post(f"{API_BASE_URL}/api/system/test-alert", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to send test alert: {e}")
            return False
    
    @staticmethod
    def get_logs(limit: int = 100) -> list:
        """Get system logs"""
        try:
            response = requests.get(
                f"{API_BASE_URL}/api/system/logs",
                params={"limit": limit},
                timeout=5
            )
            response.raise_for_status()
            return response.json().get('data', [])
        except Exception as e:
            logger.error(f"Failed to get logs: {e}")
            return []


def display_system_status():
    """Display system status"""
    st.subheader("🟢 System Status")
    
    status = SystemAPI.get_system_status()
    
    if status:
        col1, col2, col3, col4 = st.columns(4)
        
        is_running = status.get('is_running', False)
        is_paused = status.get('is_paused', False)
        
        with col1:
            status_text = "🟢 RUNNING" if is_running and not is_paused else "🔴 STOPPED" if not is_running else "🟡 PAUSED"
            st.metric("Status", status_text)
        
        with col2:
            uptime = status.get('uptime_seconds', 0)
            hours = uptime // 3600
            minutes = (uptime % 3600) // 60
            st.metric("Uptime", f"{hours}h {minutes}m")
        
        with col3:
            st.metric("Orders Today", status.get('orders_today', 0))
        
        with col4:
            st.metric("Errors", status.get('error_count', 0))
    else:
        st.error("Unable to fetch system status")


def display_trading_controls():
    """Display trading pause/resume controls"""
    st.markdown("---")
    st.subheader("⚙️ Trading Controls")
    
    status = SystemAPI.get_system_status()
    
    if status:
        is_paused = status.get('is_paused', False)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if is_paused:
                if st.button("▶️ Resume Trading", use_container_width=True, key='resume'):
                    if SystemAPI.resume_trading():
                        st.success("✅ Trading resumed!")
                        st.rerun()
                    else:
                        st.error("❌ Failed to resume trading")
            else:
                if st.button("⏸️ Pause Trading", use_container_width=True, key='pause'):
                    if SystemAPI.pause_trading():
                        st.success("✅ Trading paused!")
                        st.rerun()
                    else:
                        st.error("❌ Failed to pause trading")
        
        with col2:
            if st.button("🔄 Reload Configuration", use_container_width=True, key='reload'):
                if SystemAPI.reload_config():
                    st.success("✅ Configuration reloaded!")
                else:
                    st.error("❌ Failed to reload configuration")
        
        with col3:
            if st.button("🔔 Test Alert", use_container_width=True, key='test_alert'):
                if SystemAPI.send_test_alert():
                    st.success("✅ Test alert sent!")
                else:
                    st.error("❌ Failed to send test alert")


def display_broker_status():
    """Display broker connection status"""
    st.markdown("---")
    st.subheader("🏦 Broker Status")
    
    status = SystemAPI.get_system_status()
    
    if status and 'brokers' in status:
        brokers = status['brokers']
        
        broker_data = []
        for broker_name, broker_info in brokers.items():
            broker_data.append({
                'Broker': broker_name,
                'Status': '🟢 Connected' if broker_info.get('connected') else '🔴 Disconnected',
                'Cash': f"${broker_info.get('cash', 0):,.2f}",
                'Positions': broker_info.get('positions', 0),
                'Last Update': broker_info.get('last_update', 'N/A')
            })
        
        if broker_data:
            df = pd.DataFrame(broker_data)
            st.dataframe(df, use_container_width=True)
    else:
        st.info("No broker information available")


def display_performance_stats():
    """Display performance statistics"""
    st.markdown("---")
    st.subheader("📊 Performance Stats")
    
    status = SystemAPI.get_system_status()
    
    if status:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Avg Fill Time", f"{status.get('avg_fill_time_ms', 0):.1f}ms")
        
        with col2:
            st.metric("API Latency", f"{status.get('api_latency_ms', 0):.1f}ms")
        
        with col3:
            st.metric("Memory Usage", f"{status.get('memory_mb', 0):.1f}MB")
        
        with col4:
            st.metric("CPU Usage", f"{status.get('cpu_percent', 0):.1f}%")


def display_configuration():
    """Display current configuration"""
    st.markdown("---")
    st.subheader("⚙️ Configuration")
    
    status = SystemAPI.get_system_status()
    
    if status and 'config' in status:
        config = status['config']
        
        with st.expander("View Configuration (JSON)", expanded=False):
            import json
            st.json(config)
    else:
        st.info("No configuration available")


def display_logs():
    """Display system logs"""
    st.markdown("---")
    st.subheader("📋 System Logs")
    
    col1, col2 = st.columns([1, 5])
    
    with col1:
        log_limit = st.selectbox("Show Last", [10, 25, 50, 100], index=3)
    
    logs = SystemAPI.get_logs(limit=log_limit)
    
    if logs:
        # Convert to dataframe
        log_df = pd.DataFrame(logs)
        
        # Format columns
        if 'timestamp' in log_df.columns:
            log_df['timestamp'] = pd.to_datetime(log_df['timestamp']).dt.strftime('%H:%M:%S')
        
        st.dataframe(log_df, use_container_width=True)
        
        # Download logs
        csv = log_df.to_csv(index=False)
        st.download_button(
            label="📥 Export Logs",
            data=csv,
            file_name=f"system_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
    else:
        st.info("No logs available")


def display():
    """Main system control page display"""
    st.title("⚙️ System Control")
    
    display_system_status()
    display_trading_controls()
    display_broker_status()
    display_performance_stats()
    display_configuration()
    display_logs()
    
    # Footer
    st.markdown(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")
