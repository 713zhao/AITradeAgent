# Portfolio Monitoring Architecture

**Last Updated:** 2026-03-29  
**Status:** ✅ Resolved — Option C implemented

---

## Current Situation

You've identified an important architectural question:

**Question:** Does MarketScannerAgent include **held/portfolio symbols** for continuous monitoring?  
**Answer:** **No** — Currently, MarketScannerAgent only discovers NEW opportunities from configured themes.

---

## Current Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    MARKET SCANNING PHASE                        │
│ Discover new opportunities from configured themes               │
└──────────────────────┬──────────────────────────────────────────┘
                       │
        ┌──────────────▼──────────────┐
        │  MarketScannerAgent         │
        │  (NEW opportunities only)   │
        │ - AI theme (5 symbols)      │
        │ - Semiconductor (5)         │
        │ - Cloud (5)                 │
        │ - MegaCap (5)               │
        │ - Hong Kong (5)             │
        │ = 25 total symbols          │
        └──────────────┬──────────────┘
                       │
                       ▼
        [ DataAgent → AnalysisAgent → StrategyAgent ]
        (Analyze each new symbol, decide to BUY?)
                       │
                       ▼
        [ ExecutionAgent → PortfolioAgent ]
        (Execute BUY orders, track positions)

┌─────────────────────────────────────────────────────────────────┐
│              PORTFOLIO MONITORING PHASE (SEPARATE)              │
│ Watch held positions for exit conditions (every 5 min)         │
└──────────────────────┬──────────────────────────────────────────┘
                       │
        ┌──────────────▼──────────────┐
        │  ExitAgent (new!)           │
        │  - Check all OPEN positions │
        │  - Monitor stop-loss        │
        │  - Monitor take-profit      │
        │  - Emit exit signals        │
        └──────────────┬──────────────┘
                       │
                       ▼
        [ PortfolioAgent updates positions ]
```

---

## Key Insight: Separation of Concerns

### MarketScannerAgent = "Discovery"
- **Purpose:** Find NEW promising opportunities
- **Input:** Configured symbol themes (25 total)
- **Output:** List of candidates worth analyzing (e.g., top 10)
- **Called:** Once daily at market open (9:30 AM)
- **Does NOT include:** Portfolio holdings

### ExitAgent = "Position Monitoring"
- **Purpose:** Watch HELD positions for exit conditions
- **Input:** All open positions from PortfolioAgent
- **Output:** Exit signals (stop-loss / take-profit triggered)
- **Called:** Every 5 minutes (continuous)
- **Does NOT:** Search for new opportunities

---

## Current Workflow Timeline

```
9:30 AM (Market Opens)
    │
    ├─▶ SchedulerAgent fires MARKET_SCAN_TRIGGER
    │
    ├─▶ MarketScannerAgent.run()
    │   ├─ Scans 25 configured symbols
    │   ├─ Filters by liquidity (optional)
    │   ├─ Ranks by composite score
    │   └─ Returns top 10 candidates
    │
    ├─▶ For each candidate:
    │   ├─ DataAgent fetches OHLCV + fundamentals
    │   ├─ AnalysisAgent computes technical indicators
    │   ├─ StrategyAgent decides BUY signal?
    │   └─ ExecutionAgent executes if signal
    │
    └─▶ PortfolioAgent records trade
        (e.g., "Bought 100 NVDA @ $120")

Every 5 minutes (9:30 AM - 4:00 PM)
    │
    ├─▶ SchedulerAgent fires EXIT_CHECK_TRIGGER
    │
    ├─▶ ExitAgent.run(positions=portfolio.get_positions())
    │   ├─ Check all HELD positions
    │   │   ├─ Position: 100 NVDA @ $120 (stop: $115, profit: $130)
    │   │   ├─ Current price: $128
    │   │   └─ → No exit condition yet
    │   │
    │   ├─ Check next position...
    │   └─ If exit condition triggered:
    │       ├─ ExecutionAgent sells position
    │       └─ PortfolioAgent records exit
    │
    └─▶ Continue monitoring

4:00 PM (Market Closes)
    │
    └─▶ SchedulerAgent can run end-of-day reports
```

---

## YOUR CONCERN: Should Portfolio Symbols Be Included?

### Option 1: Current Design (Separate Agents)
**Pros:**
- ✅ Clean separation: Scanner finds new, ExitAgent monitors held
- ✅ Flexible timing: Scanner runs daily, ExitAgent runs every 5 min
- ✅ Modular: Each agent has single responsibility
- ✅ Scalable: Can have many ExitAgents for different portfolios

**Cons:**
- ❌ Held symbols don't get fresh technical analysis
- ❌ No ranking/scoring updates for existing positions
- ❌ ExitAgent only checks stop-loss/take-profit, not "should I exit based on new analysis?"

### Option 2: Include Portfolio in Scanner (Proposed Enhancement)
**Concept:** MarketScannerAgent calls `portfolio_agent.get_positions()` and includes held symbols in the analysis.

```python
async def run(self, include_themes=None, min_liquidity=0.0, limit=10, data_agent=None):
    # Current behavior (NEW opportunities)
    candidate_symbols = self._scan_by_themes(include_themes)
    
    # NEW: Add held positions for monitoring
    held_positions = portfolio_agent.get_positions()  # Get current holdings
    held_symbols = [pos.symbol for pos in held_positions if pos.quantity > 0]
    
    # Combine and analyze
    all_symbols = list(set(candidate_symbols + held_symbols))
    # ... rank, filter, limit as before
```

**Pros:**
- ✅ Held symbols get fresh technical analysis
- ✅ StrategyAgent updates scoring for existing positions
- ✅ Single analysis pipeline for discovery + monitoring

**Cons:**
- ❌ Mixes responsibilities: discovery + monitoring in one agent
- ❌ Held symbols take up "limit" slots (fewer new opportunities discovered)
- ❌ Less frequent updates (daily) vs. ExitAgent (every 5 min)

---

## Recommended Architecture

### Current + ExitAgent trigger improvement:

We should keep the separation but enhance it:

```python
# 1. Daily discovery (9:30 AM)
MarketScannerAgent → NEW opportunities (top 10)

# 2. Continuous monitoring (every 5 min)
ExitAgent → Check all HELD positions for exit conditions

# 3. ENHANCEMENT IDEA: Re-analyze held positions
StrategyAgent could periodically re-check ALL positions:
    - Fetch fresh data via DataAgent
    - Run AnalysisAgent on held symbols
    - Check if still meets "BUY" criteria (or triggers "SELL")
    - Emit POSITION_ANALYSIS_COMPLETE event
```

This way:
- ✅ Scanner finds NEW candidates (efficient, frequent discovery)
- ✅ ExitAgent monitors exits (continuous, reactive)
- ✅ Strategy agent can re-analyze held positions (periodic, strategic)

---

## Current Code Status

### PortfolioAgent API (for monitoring held positions):

```python
# Get all current holdings
positions = portfolio_agent.get_positions()
# Returns: List[Position] with symbol, quantity, avg_cost, current_price, unrealized_pnl, etc.

# Get open trades
open_trades = portfolio_agent.get_open_trades()
# Returns: List[Trade] with symbol, side, quantity, price, status

# Get specific position P&L
pnl = portfolio_agent.get_position_pnl("NVDA")
# Returns: (unrealized_pnl, realized_pnl)

# Get full portfolio state
portfolio = portfolio_agent.get_portfolio()
# Returns: Portfolio object with all positions, cash, equity
```

### ExitAgent (current implementation):

```python
async def run(self, positions: List[Dict]) -> AgentReport:
    """Monitor positions for stop-loss / take-profit exits"""
    exits = []
    for pos in positions:
        symbol = pos.get("symbol")
        current_price = pos.get("current_price")
        stop_loss = pos.get("stop_loss_price")
        take_profit = pos.get("take_profit_price")
        
        if stop_loss and current_price <= stop_loss:
            exits.append({...})  # Exit signal
        elif take_profit and current_price >= take_profit:
            exits.append({...})  # Exit signal
    
    return AgentReport(...)
```

---

## Action Items

### To Enable Portfolio Monitoring in MarketScanner:

**Option A: Minimal (Add held symbols to scanner)**
```python
# In MarketScannerAgent.run():
1. Get held positions from portfolio_agent parameter
2. Include them in the scan alongside theme-based symbols
3. Return combined list (with held flagged as "monitoring")
```
**Complexity:** Low | **Impact:** Medium

**Option B: Create PortfolioMonitoringAgent (New)**
```python
# Separate agent that:
1. Gets all held positions
2. Fetches fresh data for each
3. Runs AnalysisAgent on each
4. Compares to entry criteria (should still hold?)
5. Emits events for re-analysis
```
**Complexity:** Medium | **Impact:** High

**Option C: Enhance ExitAgent to include strategy re-check**
```python
# Extend ExitAgent to:
1. Monitor stop-loss / take-profit (current)
2. PLUS check if position fails BUY criteria (new signal type: "REANALYZE")
3. Emit event for StrategyAgent to decide HOLD vs SELL
```
**Complexity:** Low-Medium | **Impact:** High

---

## Recommendation for Your Use Case

**Implement Option C (Hybrid):**

1. **Keep MarketScannerAgent as-is** → Discovers NEW opportunities daily
2. **Keep ExitAgent for reactive exits** → Stops running every 5 min
3. **Enhance with periodic re-analysis loop:**
   ```
   Quarterly (or weekly):
       ├─ For each held position:
       │   ├─ Fetch latest data
       │   ├─ Run AnalysisAgent
       │   ├─ Check if meets current BUY criteria
       │   └─ If NO → Emit "POSITION_DEGRADED" signal
       │       └─ StrategyAgent reviews for exit
       └─ Report: "Position X failed criteria at {date}, recommending review"
   ```

This approach:
- ✅ Maintains clean architecture (separate agents for separate jobs)
- ✅ Ensures continuous monitoring (ExitAgent every 5 min for exits)
- ✅ Enables strategic re-analysis (periodic for held positions)
- ✅ Minimizes new Symbol scanning overhead (scanner stays focused)

---

## Summary

| Aspect | Current State | Status |
|--------|---------------|--------|
| **New symbol discovery** | ✅ MarketScanner (daily) | Working as intended |
| **Exit condition monitoring** | ✅ ExitAgent (every 5 min) | Reactive: stop-loss/take-profit |
| **Held position re-analysis** | ✅ ExitAgent strategic mode | RSI > 70 / bearish trend detection |
| **Should portfolio symbols be included?** | ✅ Separate loop (Option C) | Clean architecture maintained |

**Decision:** ✅ **Option C implemented** — ExitAgent enhanced with dual-mode monitoring (reactive exits + strategic re-analysis). Triggered every 5 minutes via `EXIT_CHECK_TRIGGER` from SchedulerAgent. Orchestrator retrieves positions from PortfolioAgent and passes to ExitAgent with `perform_strategy_check=True`.
