"""
FX Rate Service - Daily currency exchange rate fetcher with persistent fallback.

Fetches USD conversion rates via yfinance once per day. On failure, falls back
to the last successfully cached rates stored in storage/fx_rates_cache.json.

Usage:
    from finance_service.core.fx_rates import fx_rate_service
    rate = fx_rate_service.get_usd_rate_for_symbol("0002.HK")  # e.g. 0.1286
    rate = fx_rate_service.get_usd_rate("HKD")                 # e.g. 0.1286
"""

import json
import logging
import os
import threading
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Maps symbol suffix -> ISO currency code
_SUFFIX_TO_CURRENCY: Dict[str, str] = {
    ".HK": "HKD",
    ".L":  "GBP",
    ".PA": "EUR",
    ".DE": "EUR",
    ".T":  "JPY",
    ".SS": "CNY",
    ".SZ": "CNY",
    ".AX": "AUD",
    ".TO": "CAD",
}

# yfinance FX tickers to fetch (currency -> USD).
# Use XXXUSD=X format which gives "1 XXX = ? USD" directly.
_CURRENCY_TICKERS: Dict[str, str] = {
    "HKD": "HKDUSD=X",
    "GBP": "GBPUSD=X",
    "EUR": "EURUSD=X",
    "JPY": "JPYUSD=X",
    "CNY": "CNYUSD=X",
    "AUD": "AUDUSD=X",
    "CAD": "CADUSD=X",
}

# Hardcoded approximate fallback rates (last resort if no cache file exists)
_STATIC_FALLBACK_RATES: Dict[str, float] = {
    "USD": 1.0,
    "HKD": 0.1286,
    "GBP": 1.2650,
    "EUR": 1.0820,
    "JPY": 0.00667,
    "CNY": 0.1381,
    "AUD": 0.6350,
    "CAD": 0.7320,
}

_CACHE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "storage", "fx_rates_cache.json"
)


def _detect_currency(symbol: str) -> str:
    """Return ISO currency code for a trading symbol."""
    upper = symbol.upper()
    for suffix, currency in _SUFFIX_TO_CURRENCY.items():
        if upper.endswith(suffix.upper()):
            return currency
    return "USD"


class FXRateService:
    """
    Thread-safe singleton that provides daily-refreshed FX rates (-> USD).

    Refresh strategy:
      1. On first access, load from cache file (if today's date).
      2. If cache is stale or missing, fetch via yfinance.
      3. If yfinance fetch fails, use previously cached rates.
      4. If no cached rates exist, use static hardcoded fallback rates.
    """

    def __init__(self, cache_file: str = _CACHE_FILE):
        self._cache_file = cache_file
        self._rates: Dict[str, float] = {"USD": 1.0}
        self._last_refresh: Optional[datetime] = None
        self._lock = threading.Lock()
        self._load_from_file()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_usd_rate(self, currency: str) -> float:
        """
        Return how many USD one unit of currency is worth.
        E.g. get_usd_rate("HKD") ~= 0.1286  (1 HKD = 0.1286 USD)
        """
        currency = currency.upper()
        if currency == "USD":
            return 1.0
        self._refresh_if_stale()
        return self._rates.get(currency, _STATIC_FALLBACK_RATES.get(currency, 1.0))

    def get_usd_rate_for_symbol(self, symbol: str) -> float:
        """Return the USD conversion rate derived from a trading symbol's exchange suffix."""
        return self.get_usd_rate(_detect_currency(symbol))

    def refresh_now(self, currencies: Optional[list] = None) -> bool:
        """
        Force a rate refresh from yfinance.
        Returns True if at least one rate was updated, False on total failure.
        """
        return self._fetch_from_yfinance(currencies or list(_CURRENCY_TICKERS.keys()))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _refresh_if_stale(self) -> None:
        """Refresh once per calendar day (UTC)."""
        today = datetime.utcnow().date()
        if self._last_refresh and self._last_refresh.date() >= today:
            return
        with self._lock:
            # Double-checked locking
            if self._last_refresh and self._last_refresh.date() >= today:
                return
            self._fetch_from_yfinance(list(_CURRENCY_TICKERS.keys()))

    def _fetch_from_yfinance(self, currencies: list) -> bool:
        """Fetch rates from yfinance. Returns True if at least one rate was updated."""
        try:
            import yfinance as yf
        except ImportError:
            logger.warning("yfinance not available; using cached FX rates")
            return False

        tickers = [_CURRENCY_TICKERS[c] for c in currencies if c in _CURRENCY_TICKERS]
        if not tickers:
            return False

        updated = 0
        try:
            data = yf.download(
                tickers,
                period="5d",
                interval="1d",
                progress=False,
                auto_adjust=True,
                threads=True,
            )

            for currency in currencies:
                ticker = _CURRENCY_TICKERS.get(currency)
                if not ticker:
                    continue
                try:
                    if len(tickers) == 1:
                        close_series = data["Close"]
                    else:
                        close_series = data["Close"][ticker]
                    rate = float(close_series.dropna().iloc[-1])
                    if rate > 0:
                        self._rates[currency] = rate
                        updated += 1
                        logger.debug(f"FX rate updated: 1 {currency} = {rate:.6f} USD")
                except Exception as e:
                    logger.warning(f"Could not extract rate for {currency} ({ticker}): {e}")

        except Exception as e:
            logger.error(f"yfinance FX batch download failed: {e}")

        if updated > 0:
            self._rates["USD"] = 1.0
            self._last_refresh = datetime.utcnow()
            self._save_to_file()
            logger.info(f"FX rates refreshed: {updated}/{len(currencies)} currencies updated")
            return True
        else:
            logger.warning("FX rate refresh produced no results; retaining previous rates")
            return False

    def _load_from_file(self) -> None:
        """Load persisted rates from cache file."""
        try:
            if not os.path.exists(self._cache_file):
                logger.debug(f"FX cache file not found at {self._cache_file}; using static fallbacks")
                self._rates = dict(_STATIC_FALLBACK_RATES)
                return

            with open(self._cache_file, "r") as f:
                payload = json.load(f)

            rates = payload.get("rates", {})
            saved_at_str = payload.get("saved_at", "")
            saved_at = datetime.fromisoformat(saved_at_str) if saved_at_str else None

            if rates:
                self._rates = {**_STATIC_FALLBACK_RATES, **rates}
                self._rates["USD"] = 1.0
                if saved_at:
                    self._last_refresh = saved_at
                    age_hours = (datetime.utcnow() - saved_at).total_seconds() / 3600
                    logger.info(f"FX rates loaded from cache (age: {age_hours:.1f}h): {rates}")
                else:
                    logger.info(f"FX rates loaded from cache: {rates}")
            else:
                self._rates = dict(_STATIC_FALLBACK_RATES)

        except Exception as e:
            logger.warning(f"Failed to load FX rate cache: {e}; using static fallbacks")
            self._rates = dict(_STATIC_FALLBACK_RATES)

    def _save_to_file(self) -> None:
        """Persist rates to cache file for fallback on next startup."""
        try:
            os.makedirs(os.path.dirname(self._cache_file), exist_ok=True)
            payload = {
                "saved_at": datetime.utcnow().isoformat(),
                "rates": {k: v for k, v in self._rates.items() if k != "USD"},
            }
            with open(self._cache_file, "w") as f:
                json.dump(payload, f, indent=2)
            logger.debug(f"FX rates saved to {self._cache_file}")
        except Exception as e:
            logger.warning(f"Failed to save FX rate cache: {e}")

    def __repr__(self) -> str:
        return (
            f"FXRateService(last_refresh={self._last_refresh}, "
            f"rates={self._rates})"
        )


# Module-level singleton - import and use directly
fx_rate_service = FXRateService()
