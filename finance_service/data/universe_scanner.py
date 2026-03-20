"""Compatibility shim for tests referencing old module structure"""
# This module provides backward compatibility for tests that import
# from finance_service.data.universe_scanner import UniverseScanner
# The actual implementation is in finance_service.agents.market_scanner_agent.MarketScannerAgent

from finance_service.agents.market_scanner_agent import MarketScannerAgent

# Export with the old name for test compatibility
UniverseScanner = MarketScannerAgent

__all__ = ['UniverseScanner']
