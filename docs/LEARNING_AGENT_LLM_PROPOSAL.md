# LearningAgent Enhancement Proposal - LLM-Powered Learning from Trading Experience

**Date:** May 9, 2026  
**Phase:** 4 (LLM-driven adaptive trading)  
**Priority:** High (core competitive advantage)

## Executive Summary

Enhance the existing `LearningAgent` with a **3-layer LLM system** to learn from past trades and adaptively improve strategy parameters:

| Layer | Timing | Technology | Purpose |
|-------|--------|-----------|---------|
| **Layer 1** | Real-time (per trade) | LLM analysis | Pattern recognition + coaching |
| **Layer 2** | Weekly (Sundays 20:00 UTC) | LLM aggregation | Root cause analysis |
| **Layer 3** | Bi-weekly (Mondays 18:00 UTC) | Optuna + LLM | Parameter optimization |

**Expected Impact:**
- Win rate: +3-5%
- Sharpe ratio: +0.5-1.0
- Parameter drift: Eliminated

## Architecture

```
TRADE_EXECUTED (real-time)
  ├─→ Layer 1: LLM Pattern Analysis → Telegram coaching
  ├─→ Layer 2: Weekly Root Cause → Pattern metrics
  └─→ Layer 3: Bi-weekly Optimization → Paper trading deployment
```

## Layer 1: Post-Trade Pattern Analysis (LLM)

**Trigger:** Immediately after each trade  
**Input:** Trade details + market context  
**Output:** Entry score (0-10), skill rating, pattern type, recommendations  
**Schema:**
```python
trade_analysis = {
    "trade_id": "TRADE_000451",
    "symbol": "NVDA",
    "entry_score": 8.5,
    "skill_rating": 0.78,
    "pattern_type": "continuation_breakout",
    "mistakes": [],
    "psychological_notes": [],
    "recommendations": [{"type": "parameter_adjustment", ...}],
    "tags": ["bullish_continuation", "technical_excellence"]
}
```

**Database:** `trade_analysis` table

## Layer 2: Weekly Root Cause Analysis

**Trigger:** Sundays 20:00 UTC  
**Process:** Aggregate 5-50 trades, group by pattern, run LLM analysis  
**Output:** Per-pattern statistics (win rate, profit factor, failure analysis)  
**Database:** `trading_analysis_weekly` table  
**Telegram:** Weekly report with pattern metrics

## Layer 3: Parameter Optimization with Optuna

**Trigger:** Mondays 18:00 UTC  
**Process:**
1. Run Optuna with 300 trials over parameter space
2. LLM recommends best parameter set
3. Deploy to paper trading (2-week test)
4. If successful, deploy to live trading (25% position scaling)
5. Rollback if metrics drop

**Parameter Space Example:**
- RSI entry threshold: 20-50
- ATR stop-loss multiplier: 1.0-2.5
- Trailing stop %: 1.0-5.0
- Volume filter multiplier: 1.0-2.5

**Deployment Strategy:**
- Week 1-2: Paper trading (100% paper)
- Week 3: Live trading with 25% position size
- Week 4+: Full position size if metrics hold

## LLM Prompts

**Layer 1 Prompt Template:**
```
You are an expert trading coach. Analyze this trade:

Symbol: {symbol}
Duration: {duration_hours}h
Result: +{pnl_pct}% (${pnl})

Entry RSI: {rsi} | MACD: {macd} | Trend: {trend}
Market Regime: {regime}
News Sentiment: {sentiment}

TASK:
1. Score entry timing (early/perfect/late)
2. Pattern type (momentum/reversal/continuation)
3. Luck vs skill assessment
4. Mistakes made (if any)
5. Confidence in similar future trades

Respond as JSON.
```

**Layer 2 Prompt (aggregated trades):**
```
You are a quantitative trading coach. Analyze these 12 breakout trades:

Win Rate: 75% (9 wins, 3 losses)
Avg Win: +3.2% | Avg Loss: -1.8%
Profit Factor: 2.34

Success factors: MACD positive crossover, volume confirmation
Failures: False breakouts in low-volume sessions

TASK:
1. Why did winners succeed?
2. Why did losers fail?
3. System issues detected?
4. Recommended action: KEEP_AS_IS | ADJUST_THRESHOLDS | ADD_FILTERS

Respond as JSON.
```

## Events & Integration

**New Events:**
- `LEARNING_ANALYSIS_TRIGGER` (weekly)
- `LEARNING_OPTIMIZATION_TRIGGER` (bi-weekly)
- `LEARNING_FEEDBACK` (per trade)

**Modified Events:**
- `TRADE_EXECUTED` → triggers Layer 1 analysis (non-blocking)

## Database Schema

```sql
-- Layer 1: Per-trade analysis
CREATE TABLE trade_analysis (
  id INT PRIMARY KEY AUTO_INCREMENT,
  trade_id VARCHAR(50) UNIQUE,
  symbol VARCHAR(20),
  entry_score FLOAT,
  skill_rating FLOAT,
  pattern_type VARCHAR(100),
  llm_response JSON,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_symbol (symbol),
  INDEX idx_created_at (created_at)
);

-- Layer 2: Weekly summaries
CREATE TABLE trading_analysis_weekly (
  id INT PRIMARY KEY AUTO_INCREMENT,
  week_ending DATE,
  pattern VARCHAR(100),
  sample_size INT,
  win_rate FLOAT,
  profit_factor FLOAT,
  recommendations JSON,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY unique_week_pattern (week_ending, pattern)
);

-- Layer 3: Optimization history
CREATE TABLE optimization_history (
  id INT PRIMARY KEY AUTO_INCREMENT,
  optimization_id VARCHAR(100) UNIQUE,
  baseline_params JSON,
  proposed_params JSON,
  status VARCHAR(50),  -- PROPOSED, PAPER_TESTING, LIVE, ROLLED_BACK
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_status (status)
);

CREATE TABLE parameter_versions (
  id INT PRIMARY KEY AUTO_INCREMENT,
  version_number INT UNIQUE,
  parameters JSON,
  source VARCHAR(50),  -- MANUAL, LLM_OPTIMIZATION
  active_from TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  active_to TIMESTAMP,
  INDEX idx_version (version_number)
);
```

## Implementation Timeline

**Phase 4.1 (Week 1-2):** Layer 1 - Per-trade pattern analysis
- Create SQL tables
- Implement LLM calling logic
- Event integration

**Phase 4.2 (Week 3-4):** Layer 2 - Weekly root cause
- Weekly scheduler
- Pattern grouping & statistics
- LLM analysis per pattern

**Phase 4.3 (Week 5-8):** Layer 3 - Parameter optimization
- Optuna integration
- Backtesting engine
- Paper trading pipeline
- Rollback logic

**Phase 4.4 (Week 9):** Testing & deployment

## Success Metrics

| Layer | KPI | Target |
|-------|-----|--------|
| Layer 1 | LLM feedback quality | 90%+ actionable |
| Layer 2 | Pattern classification accuracy | 85%+ correct grouping |
| Layer 3 | Win rate improvement | +3-5% within 4 weeks |
| Layer 3 | Sharpe ratio improvement | +0.5-1.0 |

## Configuration (YAML)

```yaml
finance:
  learning:
    enabled: true
    
    layer1:
      enabled: true
      llm_model: "gemini-2.5-flash-v1"
      temperature: 0.3
    
    layer2:
      enabled: true
      schedule: "0 20 * * 0"  # Weekly Sunday 20:00 UTC
      llm_model: "gemini-2.5-pro-v1"
    
    layer3:
      enabled: true
      schedule: "0 18 * * 1"  # Monday 18:00 UTC
      optuna_trials: 300
      deployment_strategy: "paper_first"
      paper_test_days: 14
```

## Next Steps

1. Review & approve this proposal
2. Begin Phase 4.1 (Layer 1) implementation
3. Create sprint tasks in project management tool
4. Set up monitoring dashboard for metrics

---

**Document Version:** 1.0  
**Status:** Ready for approval
