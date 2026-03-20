"""Compatibility shim for tests referencing old module structure"""
# This module provides backward compatibility for tests that import
# from finance_service.data.data_manager import DataManager
# The actual implementation is in finance_service.portfolio.portfolio_manager.PortfolioManager

from finance_service.portfolio.portfolio_manager import PortfolioManager

# Export with the old name for test compatibility
DataManager = PortfolioManager

__all__ = ['DataManager']
