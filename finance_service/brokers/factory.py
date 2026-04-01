"""Broker factory for creating broker instances."""
import os
from typing import Dict, Any, Optional
import logging

from .interface import BrokerInterface, PaperBroker, TigerBrokersBroker

logger = logging.getLogger(__name__)


class BrokerFactory:
    """Factory to instantiate brokers based on configuration."""

    _BROKERS = {
        'paper': PaperBroker,
        'tiger': TigerBrokersBroker,
        'alpaca': None,  # Placeholder for future
    }

    @classmethod
    def create(cls, broker_type: str, config: Optional[Dict[str, Any]] = None) -> BrokerInterface:
        """
        Create a broker instance.

        Args:
            broker_type: 'paper', 'tiger', 'alpaca'
            config: Broker-specific configuration dict

        Returns:
            BrokerInterface instance

        Raises:
            ValueError: Unknown broker type
        """
        broker_class = cls._BROKERS.get(broker_type.lower())
        if not broker_class:
            raise ValueError(f"Unknown broker type: {broker_type}. Available: {list(cls._BROKERS.keys())}")

        initial_cash = 100000.0
        if config:
            initial_cash = config.get('initial_cash', initial_cash)

        if broker_type == 'paper':
            return broker_class(initial_cash=initial_cash)
        else:
            return broker_class(config=config or {})

    @classmethod
    def list_available(cls) -> list:
        """List available broker types"""
        return list(cls._BROKERS.keys())
