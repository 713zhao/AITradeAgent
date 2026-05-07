"""OptionsDataAgent - Fetches and analyzes options chain data.

Provides options metrics: IV, IV rank, put/call ratio, open interest, Greeks (via OpenBB).
"""
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from dataclasses import dataclass, asdict

from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.yaml_config import YAMLConfigEngine

logger = logging.getLogger(__name__)


@dataclass
class OptionsChain:
    """Options chain for a symbol"""
    symbol: str
    timestamp: datetime
    underlying_price: float
    expirations: List[str]  # e.g., ['2026-04-17', '2026-05-15']
    chains: Dict[str, List[Dict]]  # expiration -> list of strikes with calls/puts
    # Aggregated metrics
    put_call_ratio: float = 0.0
    avg_call_iv: float = 0.0
    avg_put_iv: float = 0.0
    max_oi_strike: Optional[float] = None  # strike with highest open interest

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


@dataclass
class OptionContract:
    """Single option contract"""
    symbol: str
    expiration: str
    strike: float
    option_type: str  # 'CALL' or 'PUT'
    bid: float
    ask: float
    last: float
    volume: int
    open_interest: int
    iv: float  # implied volatility
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    rho: Optional[float] = None


class OptionsDataAgent(Agent):
    """Fetches options data for a symbol using OpenBB.

    Trigger: Called on-demand (e.g., after StrategyAgent identifies a position candidate).
    Caching: 1 hour (options change frequently).

    Config:
        finance.data.fetch_options: true/false
        finance.data.options_expirations: ['30d', '60d', '90d'] (durations to include)
    """

    @property
    def agent_id(self) -> str:
        return "options_data_agent"

    @property
    def goal(self) -> str:
        return "Provide options chain data and Greeks for strategy and risk management."

    def __init__(self, config_engine: YAMLConfigEngine):
        self.config_engine = config_engine
        self.cache_ttl = 3600  # 1 hour
        logger.info("OptionsDataAgent initialized")

    async def run(self, payload: Dict[str, Any]) -> Optional[AgentReport]:
        symbol = payload.get("symbol")
        if not symbol:
            return AgentReport(self.agent_id, "error", "Missing symbol", {})

        logger.info(f"OptionsDataAgent: fetching options for {symbol}")

        # Check cache
        cached = self._get_from_cache(symbol)
        if cached:
            logger.debug(f"Cache hit for {symbol} options")
            return AgentReport(
                self.agent_id,
                "success",
                "Options data (cached)",
                {"options_chain": cached.to_dict()}
            )

        try:
            import openbb as obb
            # Get options chain
            options = obb.stocks.optionschains(symbol=symbol, expiry='')  # all expirations
            if options.empty:
                return AgentReport(self.agent_id, "error", f"No options data for {symbol}", {})

            # Parse OpenBB output (format varies; placeholder logic)
            # Assume options DataFrame with columns: 'expiration', 'strike', 'type' (C/P), 'bid', 'ask', 'volume', 'open_interest', 'implied_volatility'
            df = options
            underlying_price = obb.stocks.quote(symbol=symbol).close.iloc[0]

            # Group by expiration
            expirations = sorted(df['expiration'].unique())
            chains = {}
            for exp in expirations:
                chain_df = df[df['expiration'] == exp]
                strikes = []
                for _, row in chain_df.iterrows():
                    strikes.append({
                        'strike': row['strike'],
                        'option_type': 'CALL' if row['type'] in ('call', 'c', 'C') else 'PUT',
                        'bid': row['bid'],
                        'ask': row['ask'],
                        'last': row.get('last', (row['bid'] + row['ask']) / 2),
                        'volume': int(row.get('volume', 0)),
                        'open_interest': int(row.get('open_interest', 0)),
                        'iv': row.get('implied_volatility', 0.0),
                        'delta': row.get('delta'),
                        'gamma': row.get('gamma'),
                        'theta': row.get('theta'),
                        'vega': row.get('vega'),
                    })
                chains[exp] = strikes

            # Compute aggregated metrics
            total_oi_call = sum(c['open_interest'] for chain in chains.values() for c in chain if c['option_type'] == 'CALL')
            total_oi_put = sum(c['open_interest'] for chain in chains.values() for c in chain if c['option_type'] == 'PUT')
            put_call_ratio = total_oi_put / total_oi_call if total_oi_call > 0 else 0.0

            all_ivs = [c['iv'] for chain in chains.values() for c in chain if c['iv']]
            avg_call_iv = np.mean([c['iv'] for chain in chains.values() for c in chain if c['option_type'] == 'CALL' and c['iv']])
            avg_put_iv = np.mean([c['iv'] for chain in chains.values() for c in chain if c['option_type'] == 'PUT' and c['iv']])

            # Find max OI strike
            max_oi = 0
            max_strike = None
            for chain in chains.values():
                for c in chain:
                    if c['open_interest'] > max_oi:
                        max_oi = c['open_interest']
                        max_strike = c['strike']

            chain = OptionsChain(
                symbol=symbol,
                timestamp=datetime.now(),
                underlying_price=underlying_price,
                expirations=expirations,
                chains=chains,
                put_call_ratio=put_call_ratio,
                avg_call_iv=avg_call_iv,
                avg_put_iv=avg_put_iv,
                max_oi_strike=max_strike,
            )
            self._save_to_cache(symbol, chain)
            return AgentReport(
                self.agent_id,
                "success",
                f"Options chain loaded for {symbol}",
                {"options_chain": chain.to_dict()}
            )

        except Exception as e:
            logger.error(f"Options fetch failed for {symbol}: {e}")
            return AgentReport(self.agent_id, "error", str(e), {})

    def _get_from_cache(self, symbol: str) -> Optional[OptionsChain]:
        import json, os
        storage = os.getenv("STORAGE_DIR", "storage")
        path = os.path.join(storage, "options_cache", f"{symbol}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            ts = datetime.fromisoformat(data['timestamp'])
            if (datetime.now() - ts).total_seconds() > self.cache_ttl:
                return None
            return OptionsChain(**data)
        except Exception as e:
            logger.warning(f"Options cache read failed: {e}")
            return None

    def _save_to_cache(self, symbol: str, chain: OptionsChain):
        import json, os
        storage = os.getenv("STORAGE_DIR", "storage")
        path = os.path.join(storage, "options_cache", f"{symbol}.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, 'w') as f:
                json.dump(chain.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"Options cache write failed: {e}")
