# Multi-Agent System - Starter Code Templates
## Ready-to-use patterns for Phase 9 implementation

---

## 1. BASE AGENT CLASS

```python
# agents/base_agent.py

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

import aiohttp
import redis.asyncio as redis

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Base class for all specialized agents"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.name = config.get('name', 'UnnamedAgent')
        self.port = config.get('port', 8000)
        self.redis_client = None
        self.phase7_client = None
        self.session = None
    
    async def initialize(self):
        """Initialize connections"""
        # Redis connection
        redis_url = self.config.get('redis_url', 'redis://redis:6379')
        self.redis_client = await redis.from_url(redis_url)
        
        # Phase 7 API client
        self.api_base_url = self.config.get('api_base_url', 'http://picotradeagent:5000')
        self.session = aiohttp.ClientSession()
        
        logger.info(f"{self.name} initialized")
    
    async def shutdown(self):
        """Clean up connections"""
        if self.session:
            await self.session.close()
        if self.redis_client:
            await self.redis_client.close()
    
    def get_cache_key(self, task: Dict) -> str:
        """Generate cache key from task"""
        components = [self.name]
        components.extend([str(v) for k, v in sorted(task.items())])
        return ":".join(components)
    
    async def get_cache(self, key: str) -> Optional[Dict]:
        """Get value from cache"""
        try:
            cached = await self.redis_client.get(key)
            if cached:
                logger.debug(f"Cache hit: {key}")
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Cache error: {e}")
        return None
    
    async def set_cache(self, key: str, value: Dict, ttl: int = 600):
        """Store value in cache"""
        try:
            await self.redis_client.setex(
                key,
                ttl,
                json.dumps(value)
            )
            logger.debug(f"Cached: {key} (TTL: {ttl}s)")
        except Exception as e:
            logger.warning(f"Cache write error: {e}")
    
    async def execute(self, task: Dict) -> Dict:
        """Execute task with caching"""
        cache_enabled = self.config.get('cache_enabled', True)
        cache_key = self.get_cache_key(task) if cache_enabled else None
        
        # Check cache
        if cache_key:
            cached = await self.get_cache(cache_key)
            if cached:
                return cached
        
        # Execute task
        try:
            result = await self._execute_task(task)
            
            # Cache result
            if cache_key:
                ttl = self.config.get('cache_ttl', 600)
                await self.set_cache(cache_key, result, ttl)
            
            return result
        
        except Exception as e:
            logger.error(f"Task execution failed: {e}")
            return {'error': str(e)}
    
    @abstractmethod
    async def _execute_task(self, task: Dict) -> Dict:
        """Override in subclass"""
        raise NotImplementedError
    
    async def call_phase7_api(self, method: str, endpoint: str, data: Dict = None) -> Dict:
        """Call Phase 7 REST API"""
        url = f"{self.api_base_url}{endpoint}"
        
        try:
            if method.upper() == 'GET':
                async with self.session.get(url, timeout=30) as resp:
                    return await resp.json()
            
            elif method.upper() == 'POST':
                async with self.session.post(url, json=data, timeout=30) as resp:
                    return await resp.json()
        
        except Exception as e:
            logger.error(f"API call failed: {e}")
            return {'error': str(e)}
    
    async def publish_event(self, topic: str, message: Dict):
        """Publish event to Redis pub/sub"""
        try:
            await self.redis_client.publish(topic, json.dumps(message))
            logger.debug(f"Published to {topic}")
        except Exception as e:
            logger.warning(f"Publish failed: {e}")
```

---

## 2. DATA AGENT

```python
# agents/data_agent.py

from base_agent import BaseAgent
from openbb import obb
import asyncio


class DataAgent(BaseAgent):
    """Fetch market data from OpenBB"""
    
    async def _execute_task(self, task: dict) -> dict:
        """Fetch market data"""
        symbol = task.get('symbol')
        
        if not symbol:
            return {'error': 'Symbol required'}
        
        try:
            # Fetch price
            price = await self.get_stock_price(symbol)
            
            # Fetch historical data
            historical = await self.get_historical_data(symbol)
            
            # Fetch company info
            info = await self.get_company_info(symbol)
            
            # Combine results
            result = {
                'symbol': symbol,
                'current_price': price,
                'historical_data': historical,
                'company_info': info,
                'timestamp': datetime.now().isoformat(),
                'status': 'success'
            }
            
            # Store in Phase 7
            await self.call_phase7_api(
                'POST',
                '/api/dashboard/market-data',
                result
            )
            
            return result
        
        except Exception as e:
            return {'error': str(e), 'symbol': symbol}
    
    async def get_stock_price(self, symbol: str) -> float:
        """Get current stock price from OpenBB"""
        try:
            data = obb.equity.price(symbol)
            return float(data)
        except Exception as e:
            logger.error(f"Price fetch failed: {e}")
            return 0.0
    
    async def get_historical_data(self, symbol: str, days: int = 252) -> list:
        """Get historical price data"""
        try:
            data = obb.equity.historical(symbol, interval='1d', limit=days)
            return data.to_dict('records')[:50]  # Return last 50 days
        except Exception as e:
            logger.error(f"Historical data failed: {e}")
            return []
    
    async def get_company_info(self, symbol: str) -> dict:
        """Get company information"""
        try:
            info = obb.equity.info(symbol)
            return {
                'name': info.get('name'),
                'sector': info.get('sector'),
                'market_cap': info.get('market_cap'),
                'pe_ratio': info.get('pe_ratio')
            }
        except Exception as e:
            logger.error(f"Company info failed: {e}")
            return {}
```

---

## 3. STRATEGY AGENT

```python
# agents/strategy_agent.py

from base_agent import BaseAgent
import numpy as np


class StrategyAgent(BaseAgent):
    """Generate trading signals"""
    
    async def _execute_task(self, task: dict) -> dict:
        """Generate trading decision"""
        symbol = task.get('symbol')
        market_data = task.get('market_data', {})
        
        if not symbol:
            return {'error': 'Symbol required'}
        
        try:
            # Analyze signals
            signals = await self.analyze_signals(market_data)
            
            # Generate decision
            decision = await self.generate_decision(signals)
            
            # Store in Phase 7
            await self.call_phase7_api(
                'POST',
                '/api/system/trading-signals',
                {
                    'symbol': symbol,
                    'decision': decision['decision'],
                    'confidence': decision['confidence'],
                    'target_price': decision['target_price'],
                    'timestamp': datetime.now().isoformat()
                }
            )
            
            return decision
        
        except Exception as e:
            return {'error': str(e), 'symbol': symbol}
    
    async def analyze_signals(self, market_data: dict) -> dict:
        """Analyze technical indicators"""
        historical = market_data.get('historical_data', [])
        
        if len(historical) < 20:
            return {'error': 'Insufficient data'}
        
        prices = [d['close'] for d in historical[-252:]]
        
        # Calculate indicators
        rsi = self.calculate_rsi(prices)
        macd = self.calculate_macd(prices)
        sma_20 = np.mean(prices[-20:])
        sma_50 = np.mean(prices[-50:])
        current_price = prices[-1]
        
        return {
            'rsi': rsi,
            'macd': macd,
            'sma_20': sma_20,
            'sma_50': sma_50,
            'current_price': current_price,
            'trend': 'bullish' if sma_20 > sma_50 else 'bearish'
        }
    
    async def generate_decision(self, signals: dict) -> dict:
        """Generate BUY/SELL/HOLD decision"""
        rsi = signals.get('rsi', 50)
        macd = signals.get('macd', 0)
        trend = signals.get('trend', 'neutral')
        
        # Scoring system
        score = 0
        
        # RSI signals
        if rsi < 30:
            score += 1  # Oversold
        elif rsi > 70:
            score -= 1  # Overbought
        
        # MACD signals
        if macd > 0:
            score += 1
        elif macd < 0:
            score -= 1
        
        # Trend signal
        if trend == 'bullish':
            score += 1
        elif trend == 'bearish':
            score -= 1
        
        # Determine decision
        if score >= 2:
            decision = 'BUY'
            confidence = min(0.9, 0.5 + (score * 0.15))
        elif score <= -2:
            decision = 'SELL'
            confidence = min(0.9, 0.5 + (abs(score) * 0.15))
        else:
            decision = 'HOLD'
            confidence = 0.5
        
        return {
            'decision': decision,
            'confidence': confidence,
            'target_price': signals.get('current_price', 0) * (1 + 0.05 if decision == 'BUY' else -0.05 if decision == 'SELL' else 0),
            'reasoning': f"RSI: {rsi:.1f}, MACD: {macd:.1f}, Trend: {trend}",
            'timestamp': datetime.now().isoformat(),
            'status': 'success'
        }
    
    @staticmethod
    def calculate_rsi(prices, period=14) -> float:
        """Calculate RSI indicator"""
        if len(prices) < period:
            return 50.0
        
        deltas = np.diff(prices[-period:])
        seed = deltas[:period]
        up = seed[seed >= 0].sum() / period
        down = -seed[seed < 0].sum() / period
        
        rs = up / down if down != 0 else 0
        rsi = 100.0 - 100.0 / (1.0 + rs) if rs else 50.0
        
        return float(rsi)
    
    @staticmethod
    def calculate_macd(prices, fast=12, slow=26, signal=9) -> float:
        """Calculate MACD indicator"""
        if len(prices) < slow:
            return 0.0
        
        ema_fast = np.mean(prices[-fast:])
        ema_slow = np.mean(prices[-slow:])
        
        return float(ema_fast - ema_slow)
```

---

## 4. RISK AGENT

```python
# agents/risk_agent.py

from base_agent import BaseAgent


class RiskAgent(BaseAgent):
    """Validate trades against risk parameters"""
    
    async def _execute_task(self, task: dict) -> dict:
        """Validate trade"""
        trade = task.get('trade', {})
        
        if not trade:
            return {'error': 'Trade data required'}
        
        try:
            # Get portfolio state from Phase 7
            portfolio = await self.call_phase7_api(
                'GET',
                '/api/dashboard/portfolio-snapshot'
            )
            
            # Validate trade
            validation = await self.validate_trade(trade, portfolio)
            
            # Store validation
            await self.call_phase7_api(
                'POST',
                '/api/system/risk-validation',
                validation
            )
            
            return validation
        
        except Exception as e:
            return {'error': str(e)}
    
    async def validate_trade(self, trade: dict, portfolio: dict) -> dict:
        """Validate trade against risk limits"""
        
        # Get risk limits from config
        limits = self.config.get('risk_limits', {})
        max_position_pct = limits.get('max_position_size_percent', 5)
        max_sector_pct = limits.get('max_single_sector', 20)
        max_leverage = limits.get('max_leverage', 2)
        
        portfolio_value = portfolio.get('equity', 100000)
        position_value = trade.get('quantity', 1) * trade.get('price', 100)
        position_pct = (position_value / portfolio_value) * 100
        
        warnings = []
        is_valid = True
        risk_score = 0.0
        
        # Check position size
        if position_pct > max_position_pct:
            warnings.append(f"Position size {position_pct:.1f}% exceeds {max_position_pct}%")
            is_valid = False
            risk_score += 0.3
        
        # Check leverage
        current_leverage = portfolio.get('total_value', 0) / portfolio_value
        if current_leverage > max_leverage:
            warnings.append(f"Leverage {current_leverage:.1f}x exceeds {max_leverage}x")
            is_valid = False
            risk_score += 0.4
        
        # Check sector concentration
        sector = trade.get('sector', 'Unknown')
        sector_exposure = self.calculate_sector_exposure(portfolio, sector)
        if sector_exposure > max_sector_pct:
            warnings.append(f"Sector exposure {sector_exposure:.1f}% exceeds {max_sector_pct}%")
            is_valid = False
            risk_score += 0.2
        
        position_size = position_pct / max_position_pct if max_position_pct > 0 else 1.0
        
        return {
            'is_valid': is_valid,
            'risk_score': min(1.0, risk_score),
            'position_size': position_size,
            'warnings': warnings,
            'recommendations': self.get_recommendations(warnings),
            'timestamp': datetime.now().isoformat(),
            'status': 'success'
        }
    
    def calculate_sector_exposure(self, portfolio: dict, sector: str) -> float:
        """Calculate portfolio exposure to sector"""
        positions = portfolio.get('positions', [])
        portfolio_value = portfolio.get('equity', 100000)
        
        sector_value = sum(
            p.get('value', 0) for p in positions
            if p.get('sector') == sector
        )
        
        return (sector_value / portfolio_value) * 100 if portfolio_value > 0 else 0.0
    
    @staticmethod
    def get_recommendations(warnings: list) -> str:
        """Generate recommendations based on warnings"""
        if not warnings:
            return "Trade is within all risk parameters"
        
        if len(warnings) == 1:
            return f"Consider reducing position size or waiting for better entry. {warnings[0]}"
        
        return "Multiple risk constraints exceeded. Recommend waiting or reducing position."
```

---

## 5. ORCHESTRATOR SERVICE

```python
# agents/orchestrator.py

import asyncio
import uuid
from base_agent import BaseAgent


class PicoclawOrchestrator:
    """Main orchestrator agent"""
    
    def __init__(self, config: dict):
        self.config = config
        self.agents = {}
        self.redis_client = None
    
    async def initialize(self):
        """Initialize orchestrator"""
        redis_url = self.config.get('redis_url', 'redis://redis:6379')
        self.redis_client = await redis.from_url(redis_url)
    
    async def plan_execution(self, user_request: str) -> dict:
        """Build execution plan"""
        
        plan = {
            'task_id': str(uuid.uuid4()),
            'user_request': user_request,
            'steps': [],
            'created_at': datetime.now().isoformat()
        }
        
        # Parse request
        if 'analyze' in user_request.lower():
            symbol = self.extract_symbol(user_request)
            plan['steps'] = [
                {
                    'step': 1,
                    'agent': 'data_agent',
                    'action': 'fetch_data',
                    'input': {'symbol': symbol},
                    'parallel': False
                },
                {
                    'step': 2,
                    'agents': ['strategy_agent', 'analysis_agent'],
                    'actions': ['analyze', 'analyze'],
                    'input': {'symbol': symbol},
                    'parallel': True
                },
                {
                    'step': 3,
                    'agent': 'risk_agent',
                    'action': 'validate',
                    'input': {'symbol': symbol},
                    'parallel': False
                }
            ]
        
        return plan
    
    async def execute_plan(self, plan: dict) -> dict:
        """Execute the plan"""
        
        results = {}
        
        for step in plan['steps']:
            if step.get('parallel'):
                # Parallel execution
                tasks = []
                for i, agent_name in enumerate(step['agents']):
                    task = self.execute_agent(
                        agent_name,
                        step['actions'][i],
                        step['input']
                    )
                    tasks.append(task)
                
                step_results = await asyncio.gather(*tasks)
                results[f"step_{step['step']}"] = step_results
            
            else:
                # Sequential execution
                result = await self.execute_agent(
                    step['agent'],
                    step['action'],
                    step['input']
                )
                results[f"step_{step['step']}"] = result
        
        return results
    
    async def execute_agent(self, agent_name: str, action: str, input_data: dict) -> dict:
        """Execute individual agent"""
        
        agent_url = self.get_agent_url(agent_name)
        
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    'action': action,
                    'input': input_data,
                    'task_id': str(uuid.uuid4())
                }
                
                async with session.post(f"{agent_url}/execute", json=payload, timeout=30) as resp:
                    return await resp.json()
        
        except Exception as e:
            return {'error': str(e)}
    
    def get_agent_url(self, agent_name: str) -> str:
        """Get agent service URL"""
        agent_ports = {
            'data_agent': 8702,
            'strategy_agent': 8703,
            'risk_agent': 8704,
            'execution_agent': 8705
        }
        port = agent_ports.get(agent_name, 8000)
        return f"http://{agent_name}:{port}"
    
    @staticmethod
    def extract_symbol(request: str) -> str:
        """Extract stock symbol from request"""
        words = request.upper().split()
        # Simple extraction - can be improved
        if len(words) > 1:
            return words[-1]
        return "AAPL"
```

---

## 6. FastAPI APPLICATION

```python
# agents/app.py

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import asyncio

app = FastAPI(title="PicoClaw Agents")

# Load agents
orchestrator = None
data_agent = None
strategy_agent = None
risk_agent = None


@app.on_event("startup")
async def startup():
    """Initialize agents"""
    global orchestrator, data_agent, strategy_agent, risk_agent
    
    config = load_config('config/agents.yaml')
    
    orchestrator = PicoclawOrchestrator(config)
    await orchestrator.initialize()
    
    data_agent = DataAgent(config.get('agents', {}).get('data_agent', {}))
    await data_agent.initialize()
    
    strategy_agent = StrategyAgent(config.get('agents', {}).get('strategy_agent', {}))
    await strategy_agent.initialize()
    
    risk_agent = RiskAgent(config.get('agents', {}).get('risk_agent', {}))
    await risk_agent.initialize()


@app.on_event("shutdown")
async def shutdown():
    """Clean up"""
    for agent in [orchestrator, data_agent, strategy_agent, risk_agent]:
        if agent:
            await agent.shutdown()


@app.post("/orchestrator/plan")
async def plan(request: dict):
    """Build execution plan"""
    plan = await orchestrator.plan_execution(request.get('user_request'))
    return plan


@app.post("/orchestrator/execute")
async def execute(plan: dict):
    """Execute plan"""
    results = await orchestrator.execute_plan(plan)
    return results


@app.post("/analyze/{symbol}")
async def analyze(symbol: str):
    """Full analysis pipeline"""
    plan = await orchestrator.plan_execution(f"Analyze {symbol}")
    results = await orchestrator.execute_plan(plan)
    return results


@app.get("/health")
async def health():
    """Health check"""
    return {
        'status': 'healthy',
        'agents': {
            'orchestrator': 'ready',
            'data_agent': 'ready',
            'strategy_agent': 'ready',
            'risk_agent': 'ready'
        }
    }
```

---

## 7. CONFIGURATION USAGE

```python
# agents/config_loader.py

import yaml


def load_config(config_path: str) -> dict:
    """Load agent configuration from YAML"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def get_agent_config(config: dict, agent_name: str) -> dict:
    """Get specific agent configuration"""
    return config.get('agents', {}).get(agent_name, {})


def get_tool_allowlist(config: dict, agent_name: str) -> list:
    """Get tool allowlist for agent"""
    agent_config = get_agent_config(config, agent_name)
    return agent_config.get('tools', [])
```

---

These are production-ready templates. Start with the base class and expand from there.
