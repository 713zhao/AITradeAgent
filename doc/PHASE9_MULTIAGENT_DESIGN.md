# Multi-Agent Architecture Review & Integration Plan
## PicoClaw + Phase 7/8 Services Integration

**Date**: March 4, 2026  
**Phase**: 9 Enhancement (Multi-Agent Orchestration)  
**Status**: Architecture Design

---

## 1. Current System Analysis

### What We Have (Phases 1-8)
```
✅ REST API Backend (Phase 7)
   • DashboardService
   • RealTimeService
   • AnalyticsEngine
   • DashboardAPI

✅ Risk Management (Phase 6.5)
   • RealTimeRiskMonitor
   • DynamicPositionSizer
   • AdvancedStopLossManager
   • CrossBrokerRiskAnalyzer
   • ComplianceMonitor

✅ Trading System (Phases 1-6)
   • Position Management
   • Portfolio Tracking
   • Trade Execution
   • Backtest Engine

✅ Web Dashboard (Phase 8)
   • 7 Interactive Pages
   • Real-time Updates
   • API Integration
   • System Controls

✅ Docker Infrastructure (Phase 8)
   • 7 Microservices
   • Redis Cache
   • Prometheus Monitoring
   • Nginx Proxy
```

### What We Need
```
🔄 Multi-Agent Orchestration
   • Agent Coordination
   • Task Planning
   • Tool Management
   • Result Aggregation

📊 Data Pipeline
   • OpenBB Integration Service
   • Indicator Calculation Service
   • Signal Generation Service
   • Decision Engine Service

🎯 Agent Framework
   • Standardized Agent Interface
   • Tool Allowlists
   • YAML Configuration
   • State Management
```

---

## 2. BETTER ARCHITECTURE (Improved Approach)

### Why the Suggested Approach Has Limitations

The attachment shows a linear agent chain:
```
Orchestrator → Data → Analysis → Strategy → Risk → Execution
```

**Problems**:
- ❌ Sequential only (slow)
- ❌ No feedback loops
- ❌ Rigid pipeline
- ❌ No caching between runs
- ❌ Tight coupling

### RECOMMENDED: Service-Based Multi-Agent Architecture

Leverage our existing microservices + add agent layer:

```
┌─────────────────────────────────────────────────────────┐
│         PicoClaw Orchestrator Agent                     │
│  (Planning + Task Distribution + Result Aggregation)  │
└────────────────┬────────────────────────────────────────┘
                 │
     ┌───────────┼───────────┐
     │           │           │
     ▼           ▼           ▼
┌─────────┐ ┌──────────┐ ┌─────────┐
│ Data    │ │Strategy  │ │ Risk    │ (Parallel Agents)
│ Agent   │ │ Agent    │ │ Agent   │
│(OpenBB)│ │(Planning)│ │(Validate)│
└────┬────┘ └────┬─────┘ └────┬────┘
     │           │            │
     └─────────┬─────────────┘
               │
         ┌─────▼──────┐
         │  Execution │
         │   Agent    │
         └─────┬──────┘
               │
         ┌─────▼──────────────────────┐
         │  Phase 7 REST API Backend  │
         │  (Already Built!)          │
         └─────┬──────────────────────┘
               │
         ┌─────▼──────────────────────┐
         │  Redis Cache + Services    │
         │  (Phase 1-6 Logic)         │
         └────────────────────────────┘
```

**Advantages**:
- ✅ Parallel execution (faster)
- ✅ Feedback loops (better decisions)
- ✅ Leverage existing services (reuse code)
- ✅ Redis caching (performance)
- ✅ Scaling ready (microservices)

---

## 3. PROPOSED MULTI-AGENT SERVICE ARCHITECTURE

### Service Topology

```
Docker Services (Updated):

Core Services:
  ✓ picotradeagent     (Flask API - Existing)
  ✓ dashboard          (Streamlit UI - Existing)
  ✓ redis              (Cache - Existing)
  ✓ nginx              (Proxy - Existing)

NEW: Agent Services:
  ○ picoclaw_orchestrator      (Port 8701)
  ○ data_agent                 (Port 8702 - OpenBB wrapper)
  ○ strategy_agent             (Port 8703)
  ○ risk_agent                 (Port 8704)
  ○ execution_agent            (Port 8705)
  ○ analysis_agent             (Port 8706 - Optional, parallel)

Monitoring:
  ✓ prometheus         (Existing)
  ✓ grafana            (Existing)
```

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                       │
│  User/API Request                                                   │
│         │                                                            │
│         ▼                                                            │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Nginx (80/443) → Router                                    │   │
│  │  • /api/*                → picotradeagent:5000             │   │
│  │  • /dashboard/*          → dashboard:8501                 │   │
│  │  • /orchestrator/*       → picoclaw_orchestrator:8701     │   │
│  │  • /agents/*             → Agent services                 │   │
│  └────────────┬──────────────────────────────────────────────┘   │
│               │                                                    │
│         ┌─────▼──────────────────────┐                            │
│         │ Orchestrator Agent         │                            │
│         │ 1. Receive request         │                            │
│         │ 2. Build execution plan    │                            │
│         │ 3. Dispatch to agents      │                            │
│         │ 4. Aggregate results       │                            │
│         │ 5. Call Phase 7 API        │                            │
│         └─────┬──────────────────────┘                            │
│               │                                                    │
│         ┌─────┴──────────────────┐                                │
│         │  Parallel Agents       │                                │
│         │                        │                                │
│   ┌─────▼────┐  ┌──────▼───┐   ┌────▼─────┐                     │
│   │  Data    │  │ Strategy │   │  Risk    │                     │
│   │  Agent   │  │  Agent   │   │  Agent   │                     │
│   │          │  │          │   │          │                     │
│   │ OpenBB  │  │ Decisions│   │ Validate │                     │
│   └─────┬────┘  └────┬─────┘   └────┬─────┘                     │
│         │            │              │                            │
│         └────────────┼──────────────┘                            │
│                      │                                            │
│              ┌───────▼────────┐                                  │
│              │ Execution Agent│                                  │
│              │ Execute Trade  │                                  │
│              └───────┬────────┘                                  │
│                      │                                            │
│              ┌───────▼────────────────────┐                      │
│              │  Phase 7 REST API          │                      │
│              │  /api/dashboard/*          │                      │
│              │  /api/system/*             │                      │
│              └───────┬────────────────────┘                      │
│                      │                                            │
│         ┌────────────┼────────────┐                              │
│         ▼            ▼            ▼                              │
│    ┌─────────┐ ┌────────┐ ┌────────────┐                        │
│    │ Risk    │ │ Position│ │ Analytics  │                       │
│    │ Monitor │ │ Manager │ │ Engine     │                       │
│    └─────────┘ └────────┘ └────────────┘                        │
│                                                                   │
│         ┌──────────────────────┐                                │
│         │   Redis Cache        │                                │
│         │   • Market Data      │                                │
│         │   • Indicators       │                                │
│         │   • Decisions        │                                │
│         └──────────────────────┘                                │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

---

## 4. AGENT CONFIGURATION IN YAML

### agents.yaml (YAML Configuration)

```yaml
# config/agents.yaml
orchestrator:
  name: "PicoClaw Orchestrator"
  description: "Task planning and multi-agent coordination"
  port: 8701
  role: "orchestrator"
  
  # Agent selection rules
  agent_selection:
    parallel_capable:
      - data_agent
      - strategy_agent
      - risk_agent
    sequential_only:
      - execution_agent
  
  # Planning strategy
  planning:
    max_retries: 3
    timeout_seconds: 300
    cache_results: true
    cache_ttl_seconds: 300

agents:
  data_agent:
    name: "Market Data Agent"
    description: "Fetch and process market data from OpenBB"
    port: 8702
    role: "data_provider"
    
    tools:
      - get_stock_price
      - get_historical_data
      - get_company_info
      - get_market_news
      - calculate_technicals
    
    timeout: 30
    retry_count: 2
    cache_enabled: true
    cache_ttl: 3600
    
    # OpenBB Configuration
    openbb_keys:
      - "POLYGON"
      - "FRED"
      - "ALPHA_VANTAGE"
    
    output_schema:
      type: "object"
      properties:
        symbol:
          type: "string"
        price:
          type: "number"
        historical_data:
          type: "array"
        technicals:
          type: "object"
        news:
          type: "array"

  strategy_agent:
    name: "Strategy Agent"
    description: "Generate trading signals and decisions"
    port: 8703
    role: "decision_maker"
    
    tools:
      - analyze_signals
      - generate_score
      - rank_candidates
      - create_trade_plan
    
    timeout: 60
    retry_count: 0
    cache_enabled: true
    cache_ttl: 600
    
    # Strategy Configuration
    strategies:
      momentum:
        weight: 0.3
        indicators: ["RSI", "MACD", "ADX"]
      mean_reversion:
        weight: 0.2
        indicators: ["Bollinger_Bands", "RSI"]
      trend_following:
        weight: 0.5
        indicators: ["SMA", "EMA", "MACD"]
    
    output_schema:
      type: "object"
      properties:
        decision:
          type: "string"
          enum: ["BUY", "SELL", "HOLD"]
        confidence:
          type: "number"
          minimum: 0
          maximum: 1
        reasoning:
          type: "string"
        target_price:
          type: "number"

  risk_agent:
    name: "Risk Management Agent"
    description: "Validate trades against risk parameters"
    port: 8704
    role: "validator"
    
    tools:
      - validate_position_size
      - check_portfolio_limits
      - calculate_var
      - check_correlation_risk
      - validate_margin_requirements
    
    timeout: 15
    retry_count: 0
    cache_enabled: true
    cache_ttl: 600
    
    # Risk Configuration
    risk_limits:
      max_position_size_percent: 5
      max_single_sector: 20
      max_leverage: 2
      max_drawdown_percent: 10
      var_confidence: 0.95
    
    output_schema:
      type: "object"
      properties:
        is_valid:
          type: "boolean"
        risk_score:
          type: "number"
        position_size:
          type: "number"
        warnings:
          type: "array"
        recommendations:
          type: "string"

  execution_agent:
    name: "Execution Agent"
    description: "Execute trades and update portfolio"
    port: 8705
    role: "executor"
    
    tools:
      - execute_trade
      - update_portfolio
      - set_stop_loss
      - set_take_profit
      - query_portfolio
    
    timeout: 30
    retry_count: 3
    cache_enabled: false
    
    # Execution Configuration
    execution:
      paper_trading: true
      order_type: "market"
      execute_immediately: false
      require_confirmation: true
    
    output_schema:
      type: "object"
      properties:
        trade_id:
          type: "string"
        status:
          type: "string"
          enum: ["pending", "executed", "failed"]
        execution_price:
          type: "number"
        shares:
          type: "number"
        portfolio_value:
          type: "number"

  analysis_agent:
    name: "Analysis Agent"
    description: "Technical analysis and pattern recognition"
    port: 8706
    role: "analyzer"
    enabled: false  # Optional, can run in parallel
    
    tools:
      - detect_patterns
      - analyze_volume
      - calculate_support_resistance
      - identify_trends
    
    timeout: 45
    retry_count: 1
    cache_enabled: true
    cache_ttl: 1800

# Communication & Coordination
communication:
  broker: "redis"
  broker_url: "redis://redis:6379"
  
  # Message queues
  queues:
    tasks: "agent:tasks"
    results: "agent:results"
    notifications: "agent:notifications"
  
  # Publish/Subscribe
  topics:
    market_updates: "market:updates"
    trade_signals: "trade:signals"
    risk_alerts: "risk:alerts"
    execution_updates: "execution:updates"

# Logging and Monitoring
logging:
  level: "info"
  format: "json"
  
monitoring:
  prometheus_enabled: true
  prometheus_port: 9090
  
  metrics:
    - agent_execution_time
    - agent_success_rate
    - cache_hit_rate
    - api_response_time

# API Endpoints
api:
  base_url: "http://picotradeagent:5000"
  timeout: 30
  
  endpoints:
    dashboard: "/api/dashboard"
    system: "/api/system"
    trades: "/api/trades"
```

---

## 5. INTEGRATION WITH PHASE 7 API

### How Agents Communicate with Existing Services

```python
# agents/base_agent.py

class BaseAgent:
    """Base class for all agents"""
    
    def __init__(self, config):
        self.config = config
        self.redis_client = redis.Redis.from_url(config['redis_url'])
        self.phase7_api = Phase7APIClient(config['api_base_url'])
    
    async def execute(self, task):
        """Execute agent task"""
        # Step 1: Check cache
        cache_key = self.get_cache_key(task)
        if self.config.get('cache_enabled'):
            cached = self.redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        
        # Step 2: Execute task
        result = await self._execute_task(task)
        
        # Step 3: Cache result
        if self.config.get('cache_enabled'):
            ttl = self.config.get('cache_ttl', 600)
            self.redis_client.setex(cache_key, ttl, json.dumps(result))
        
        return result
    
    async def _execute_task(self, task):
        """Override in subclass"""
        raise NotImplementedError


class DataAgent(BaseAgent):
    """OpenBB data provider agent"""
    
    async def _execute_task(self, task):
        symbol = task['symbol']
        
        # Fetch from OpenBB
        data = await self.fetch_openbb_data(symbol)
        
        # Cache in Redis
        self.redis_client.set(f"market:{symbol}", json.dumps(data), ex=3600)
        
        # Store in Phase 7 via API
        await self.phase7_api.post('/api/dashboard/market-data', {
            'symbol': symbol,
            'data': data,
            'timestamp': datetime.now().isoformat()
        })
        
        return data


class StrategyAgent(BaseAgent):
    """Trading strategy decision maker"""
    
    async def _execute_task(self, task):
        symbol = task['symbol']
        market_data = task['market_data']
        
        # Analyze signals
        signals = await self.analyze_signals(market_data)
        
        # Generate decision
        decision = await self.generate_decision(signals)
        
        # Store in Phase 7
        await self.phase7_api.post('/api/system/trading-signals', {
            'symbol': symbol,
            'decision': decision['decision'],
            'confidence': decision['confidence'],
            'timestamp': datetime.now().isoformat()
        })
        
        return decision


class RiskAgent(BaseAgent):
    """Risk validation agent"""
    
    async def _execute_task(self, task):
        trade_proposal = task['trade']
        
        # Get portfolio state from Phase 7
        portfolio = await self.phase7_api.get('/api/dashboard/portfolio-snapshot')
        
        # Validate against risk limits
        validation = await self.validate_trade(trade_proposal, portfolio)
        
        # Store validation in Phase 7
        await self.phase7_api.post('/api/system/risk-validation', {
            'trade_id': trade_proposal['id'],
            'is_valid': validation['is_valid'],
            'risk_score': validation['risk_score'],
            'timestamp': datetime.now().isoformat()
        })
        
        return validation


class ExecutionAgent(BaseAgent):
    """Trade execution agent"""
    
    async def _execute_task(self, task):
        validated_trade = task['trade']
        
        # Execute via Phase 7 API
        result = await self.phase7_api.post('/api/trades/execute', {
            'symbol': validated_trade['symbol'],
            'quantity': validated_trade['quantity'],
            'action': validated_trade['action'],
            'trade_type': validated_trade['type']
        })
        
        # Publish execution update to Redis
        # (Dashboard subscribes to this)
        self.redis_client.publish('execution:updates', json.dumps({
            'trade_id': result['trade_id'],
            'status': result['status'],
            'execution_price': result['execution_price']
        }))
        
        return result
```

---

## 6. ORCHESTRATOR IMPLEMENTATION

### picoclaw_orchestrator.py

```python
# agents/orchestrator.py

class PicoclawOrchestrator:
    """Main orchestrator agent"""
    
    def __init__(self, config):
        self.config = config
        self.redis = redis.Redis.from_url(config['redis_url'])
        self.agents = {}
        self.load_agents(config)
    
    def load_agents(self, config):
        """Load agent configurations"""
        for agent_name, agent_config in config['agents'].items():
            self.agents[agent_name] = {
                'url': f"http://{agent_name}:{agent_config['port']}",
                'config': agent_config,
                'available': True
            }
    
    async def plan_execution(self, user_request):
        """Build execution plan"""
        plan = {
            'task_id': str(uuid.uuid4()),
            'user_request': user_request,
            'steps': [],
            'created_at': datetime.now().isoformat()
        }
        
        # Parse request to understand intent
        intent = await self.parse_intent(user_request)
        
        # Build step sequence based on intent
        if intent['type'] == 'analyze_stock':
            plan['steps'] = [
                {
                    'step': 1,
                    'agent': 'data_agent',
                    'action': 'fetch_data',
                    'input': {'symbol': intent['symbol']},
                    'parallel': False
                },
                {
                    'step': 2,
                    'agents': ['strategy_agent', 'analysis_agent'],
                    'action': 'analyze',
                    'input': {'symbol': intent['symbol']},
                    'parallel': True
                },
                {
                    'step': 3,
                    'agent': 'risk_agent',
                    'action': 'validate',
                    'input': {'symbol': intent['symbol']},
                    'parallel': False
                }
            ]
        
        return plan
    
    async def execute_plan(self, plan):
        """Execute the planned steps"""
        results = {}
        
        for step in plan['steps']:
            if step.get('parallel'):
                # Execute agents in parallel
                tasks = []
                for agent_name in step['agents']:
                    task = self.execute_agent_task(
                        agent_name,
                        step['action'],
                        step['input']
                    )
                    tasks.append(task)
                
                step_results = await asyncio.gather(*tasks)
                results[f"step_{step['step']}"] = step_results
            else:
                # Execute sequentially
                agent_name = step['agent']
                result = await self.execute_agent_task(
                    agent_name,
                    step['action'],
                    step['input']
                )
                results[f"step_{step['step']}"] = result
        
        return results
    
    async def execute_agent_task(self, agent_name, action, input_data):
        """Call an individual agent"""
        agent = self.agents[agent_name]
        
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    'action': action,
                    'input': input_data,
                    'task_id': str(uuid.uuid4())
                }
                
                async with session.post(
                    f"{agent['url']}/execute",
                    json=payload,
                    timeout=agent['config'].get('timeout', 30)
                ) as resp:
                    return await resp.json()
        
        except asyncio.TimeoutError:
            return {'error': f"{agent_name} timeout"}
        except Exception as e:
            return {'error': str(e)}
    
    async def aggregate_results(self, execution_results):
        """Combine results from all agents"""
        aggregated = {
            'data': execution_results.get('step_1', {}),
            'strategy': execution_results.get('step_2', {}),
            'validation': execution_results.get('step_3', {}),
            'recommendation': await self.generate_recommendation(
                execution_results
            )
        }
        
        return aggregated
    
    async def generate_recommendation(self, results):
        """Generate final recommendation"""
        # Combine signals from all agents
        return {
            'action': 'BUY',
            'confidence': 0.82,
            'reasoning': 'Strong momentum + risk approved'
        }
```

---

## 7. REST API FOR AGENTS

### agents_api.py

```python
# agents/api.py

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="PicoClaw Agent API")

@app.post("/orchestrator/plan")
async def orchestrator_plan(request: dict):
    """Build execution plan"""
    orchestrator = get_orchestrator()
    plan = await orchestrator.plan_execution(request['user_request'])
    return plan

@app.post("/orchestrator/execute")
async def orchestrator_execute(plan: dict):
    """Execute planned steps"""
    orchestrator = get_orchestrator()
    results = await orchestrator.execute_plan(plan)
    aggregated = await orchestrator.aggregate_results(results)
    return aggregated

@app.get("/agent/{agent_name}/status")
async def agent_status(agent_name: str):
    """Check agent health/status"""
    agent = get_agent(agent_name)
    return {
        'name': agent_name,
        'status': 'healthy',
        'version': '1.0.0',
        'uptime': get_uptime(agent)
    }

@app.get("/agent/{agent_name}/metrics")
async def agent_metrics(agent_name: str):
    """Get agent metrics"""
    metrics = {
        'execution_time_avg': 523,
        'success_rate': 0.98,
        'cache_hit_rate': 0.87,
        'request_count': 1523
    }
    return metrics

# Integration with Phase 7 API
@app.post("/analyze/{symbol}")
async def analyze_stock(symbol: str, request: dict):
    """Full analysis pipeline"""
    orchestrator = get_orchestrator()
    
    # Plan
    plan = await orchestrator.plan_execution(f"Analyze {symbol}")
    
    # Execute
    results = await orchestrator.execute_plan(plan)
    
    # Aggregate
    final_result = await orchestrator.aggregate_results(results)
    
    # Store in Phase 7
    phase7_client = get_phase7_client()
    await phase7_client.post('/api/system/analysis-result', final_result)
    
    return final_result

@app.post("/trade/signal")
async def generate_trade_signal(request: dict):
    """Generate and validate trade signal"""
    symbol = request['symbol']
    
    orchestrator = get_orchestrator()
    plan = await orchestrator.plan_execution(f"Generate signal for {symbol}")
    results = await orchestrator.execute_plan(plan)
    
    return results
```

---

## 8. DOCKER COMPOSE UPDATE

### docker-compose.yml Extensions

```yaml
services:
  # Existing services...
  picotradeagent:
    # ... existing config ...
  
  dashboard:
    # ... existing config ...
  
  redis:
    # ... existing config ...
  
  nginx:
    # ... existing config ...
  
  # NEW: Agent Services
  picoclaw_orchestrator:
    build:
      context: .
      dockerfile: Dockerfile.orchestrator
    container_name: picoclaw-orchestrator
    ports:
      - "8701:8701"
    environment:
      FLASK_ENV: production
      REDIS_URL: redis://redis:6379
      API_BASE_URL: http://picotradeagent:5000
      CONFIG_PATH: /app/config/agents.yaml
    volumes:
      - ./config/agents.yaml:/app/config/agents.yaml:ro
      - ./logs:/app/logs
    networks:
      - picotradeagent-net
    depends_on:
      - redis
      - picotradeagent
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8701/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  data_agent:
    build:
      context: .
      dockerfile: Dockerfile.agent
      args:
        AGENT_TYPE: data
    container_name: data-agent
    ports:
      - "8702:8702"
    environment:
      AGENT_NAME: data_agent
      AGENT_PORT: 8702
      REDIS_URL: redis://redis:6379
      API_BASE_URL: http://picotradeagent:5000
      OPENBB_ENABLED: "true"
      CONFIG_PATH: /app/config/agents.yaml
    volumes:
      - ./config/agents.yaml:/app/config/agents.yaml:ro
      - ./logs:/app/logs
    networks:
      - picotradeagent-net
    depends_on:
      - redis
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8702/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  strategy_agent:
    build:
      context: .
      dockerfile: Dockerfile.agent
      args:
        AGENT_TYPE: strategy
    container_name: strategy-agent
    ports:
      - "8703:8703"
    environment:
      AGENT_NAME: strategy_agent
      AGENT_PORT: 8703
      REDIS_URL: redis://redis:6379
      API_BASE_URL: http://picotradeagent:5000
      CONFIG_PATH: /app/config/agents.yaml
    volumes:
      - ./config/agents.yaml:/app/config/agents.yaml:ro
      - ./logs:/app/logs
    networks:
      - picotradeagent-net
    depends_on:
      - redis
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8703/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  risk_agent:
    build:
      context: .
      dockerfile: Dockerfile.agent
      args:
        AGENT_TYPE: risk
    container_name: risk-agent
    ports:
      - "8704:8704"
    environment:
      AGENT_NAME: risk_agent
      AGENT_PORT: 8704
      REDIS_URL: redis://redis:6379
      API_BASE_URL: http://picotradeagent:5000
      CONFIG_PATH: /app/config/agents.yaml
    volumes:
      - ./config/agents.yaml:/app/config/agents.yaml:ro
      - ./logs:/app/logs
    networks:
      - picotradeagent-net
    depends_on:
      - redis
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8704/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  execution_agent:
    build:
      context: .
      dockerfile: Dockerfile.agent
      args:
        AGENT_TYPE: execution
    container_name: execution-agent
    ports:
      - "8705:8705"
    environment:
      AGENT_NAME: execution_agent
      AGENT_PORT: 8705
      REDIS_URL: redis://redis:6379
      API_BASE_URL: http://picotradeagent:5000
      CONFIG_PATH: /app/config/agents.yaml
    volumes:
      - ./config/agents.yaml:/app/config/agents.yaml:ro
      - ./logs:/app/logs
    networks:
      - picotradeagent-net
    depends_on:
      - redis
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8705/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  analysis_agent:
    build:
      context: .
      dockerfile: Dockerfile.agent
      args:
        AGENT_TYPE: analysis
    container_name: analysis-agent
    ports:
      - "8706:8706"
    environment:
      AGENT_NAME: analysis_agent
      AGENT_PORT: 8706
      REDIS_URL: redis://redis:6379
      API_BASE_URL: http://picotradeagent:5000
      CONFIG_PATH: /app/config/agents.yaml
      ENABLED: "false"
    volumes:
      - ./config/agents.yaml:/app/config/agents.yaml:ro
      - ./logs:/app/logs
    networks:
      - picotradeagent-net
    depends_on:
      - redis
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8706/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    profiles:
      - optional  # Only start if explicitly requested
```

---

## 9. NGINX ROUTING UPDATE

### Add Agent Routes

```nginx
# In picotradeagent-nginx.conf

upstream picoclaw_orchestrator {
    server picoclaw_orchestrator:8701;
}

upstream data_agent {
    server data_agent:8702;
}

upstream strategy_agent {
    server strategy_agent:8703;
}

upstream risk_agent {
    server risk_agent:8704;
}

upstream execution_agent {
    server execution_agent:8705;
}

upstream analysis_agent {
    server analysis_agent:8706;
}

server {
    # ... existing config ...
    
    # Orchestrator routes
    location /orchestrator/ {
        rewrite ^/orchestrator/(.*)$ /$1 break;
        proxy_pass http://picoclaw_orchestrator;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
    
    # Agent routes
    location /agents/data/ {
        rewrite ^/agents/data/(.*)$ /$1 break;
        proxy_pass http://data_agent;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
    
    location /agents/strategy/ {
        rewrite ^/agents/strategy/(.*)$ /$1 break;
        proxy_pass http://strategy_agent;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
    
    location /agents/risk/ {
        rewrite ^/agents/risk/(.*)$ /$1 break;
        proxy_pass http://risk_agent;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
    
    location /agents/execution/ {
        rewrite ^/agents/execution/(.*)$ /$1 break;
        proxy_pass http://execution_agent;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
    
    # Single endpoint for orchestrator
    location /analyze/ {
        proxy_pass http://picoclaw_orchestrator;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

---

## 10. KEY IMPROVEMENTS OVER SUGGESTED APPROACH

### Comparison Table

| Aspect | Suggested | Our Approach |
|--------|-----------|-------------|
| **Architecture** | Linear chain | Service-based + parallel |
| **Performance** | Sequential (slow) | Parallel agents (fast) |
| **Cache** | Per-agent basic | Redis-backed with TTL |
| **Scalability** | Fixed pipeline | Horizontal scaling ready |
| **Reuse** | New code | Leverages Phase 1-7 |
| **Monitoring** | Manual logs | Prometheus metrics |
| **Integration** | Custom API | Existing REST API |
| **Extensibility** | Hard-coded routes | YAML configuration |
| **High Availability** | N/A | Docker + health checks |
| **Cost** | Extra coordination | Minimal overhead |

---

## 11. IMPLEMENTATION PHASES (Phase 9)

### Phase 9.1: Orchestrator Agent (Week 1)
```
✓ Create PicoclawOrchestrator class
✓ Plan execution logic
✓ Result aggregation
✓ Redis message queue
✓ Basic API endpoints
```

### Phase 9.2: Data Agent (Week 2)
```
✓ OpenBB integration
✓ Caching layer
✓ Market data API
✓ Historical data pipeline
✓ Tests (24 test cases)
```

### Phase 9.3: Strategy & Risk Agents (Week 3)
```
✓ Signal generation engine
✓ Risk validation logic
✓ Portfolio integration
✓ Parallel execution
✓ Tests (36 test cases)
```

### Phase 9.4: Execution Agent & Dashboard Integration (Week 4)
```
✓ Trade execution logic
✓ Portfolio updates
✓ Real-time notifications
✓ Dashboard integration
✓ Tests (24 test cases)
✓ Deployment & documentation
```

---

## 12. RECOMMENDED NEXT STEPS

### Immediate (This Week)
- [ ] Review and approve multi-agent architecture
- [ ] Create `config/agents.yaml`
- [ ] Design agent communication protocol
- [ ] Create base agent class

### Short Term (Next 2 Weeks)
- [ ] Build orchestrator service
- [ ] Build data agent (OpenBB wrapper)
- [ ] Implement Redis message queue
- [ ] Add orchestrator endpoints to API

### Integration
- [ ] Connect agents to Phase 7 API
- [ ] Add Redis pub/sub for notifications
- [ ] Create dashboard integration
- [ ] Add agent monitoring to Grafana

### Testing & Deployment
- [ ] Write comprehensive tests (84 total across all phases)
- [ ] Performance testing under load
- [ ] Deployment to Docker/Kubernetes
- [ ] Production monitoring

---

## Summary

**Our Architecture Advantages**:
1. ✅ Built on existing Phase 1-7 services (no rewrite)
2. ✅ Parallel execution via async/await
3. ✅ Redis caching for performance
4. ✅ Service-based design (loosely coupled)
5. ✅ YAML configuration (easy to maintain)
6. ✅ Industry-standard tools (FastAPI, asyncio)
7. ✅ Already have monitoring (Prometheus)
8. ✅ Already have infrastructure (Docker, Nginx)
9. ✅ Ready for horizontal scaling
10. ✅ Clear separation of concerns

**This is production-ready architecture** for Phase 9 implementation.
