# TODO: LLM Integration & Trading Bot Enhancements

**Date:** 2026-04-04
**Branch:** improve/llm-regime-phase1
**Status:** Phase 2 Complete ✅ | Phase 3 Complete ✅

---

## ✅ Completed

- [x] Merge master into feature branch (portfolio performance fix)
- [x] Add MarketRegimeAgent (broad market context from indices)
- [x] Add MacroNewsAgent (macroeconomic news aggregation)
- [x] Add SymbolSelectorAgent (LLM-powered ranking)
- [x] Integrate SymbolSelector into orchestrator pipeline
- [x] Create unit tests for 3 new agents (22 tests)
- [x] Fix config path issues (top-level sections)
- [x] Append LLM config to `config/finance.yaml`
- [x] Enable `llm.enabled` and `symbol_selector.enabled` in config
- [x] Add environment variable overrides for LLM provider/model
- [x] Push all changes to origin

---

## ⏳ Pending (Must Do)

### 1. Fix Edit Tool wipeouts (CRITICAL)
- [x] **RegimeAgent.py** was wiped - need to re-add os import and env override logic
- [x] **SymbolSelectorAgent.py** - verify os import and env override intact
- [x] **NewsAgent.py** - verify os import and env override intact
- [x] **finance.yaml** - verify LLM sections present (use `git diff` to confirm)

**Action:** Manually edit these files to add missing code, then commit.

---

### 2. Environment Variable Configuration ✅

- [x] Update `.env` with:
  ```bash
  LLM_PROVIDER=google
  GOOGLE_API_KEY=<set>
  TA_QUICK_THINK_MODEL=gemini-2.5-flash-v1  # for SymbolSelector
  TA_DEEP_THINK_MODEL=gemini-2.5-pro-v1      # for News/Regime
  ```
- [x] Using OpenRouter as API gateway (OPENROUTER_API_KEY set), routing to Gemini models
- [ ] Document env var usage in README or config comments

---

### 3. Restart & Validate AITradeAgent ✅

- [x] Restart service with clean pycache
- [x] `SymbolSelectorAgent LLM initialized` confirmed in logs
- [x] Trigger discovery scan via `/admin/force_scan` endpoint
- [x] Confirmed logs: `SymbolSelector evaluating 50 candidates`
- [x] Rankings appear in Telegram with scores, breakdown, rationale, token count

---

### 4. Test LLM Pipeline End-to-End ✅

- [x] Verified SymbolSelectorAgent calls LLM (Gemini via OpenRouter) and returns ranked JSON
- [x] Confirmed top 5–10 symbols passed to analysis after ranking (from 50 candidates)
- [x] Telegram receives ranked list with score, breakdown, rationale, token usage (~12k tokens/run)
- [x] Verify MarketRegimeAgent returns valid regime context (fixed: 300-day lookback, col normalization, SMA200 NaN guard; yfinance confirmed 206 rows)
- [x] Verify MacroNewsAgent fetches and filters macro news (fixed: yfinance new API format; confirmed 3 relevant articles, sentiment 0.107)
- [ ] Check that trades execute if strategy generates proposals

---

## 📝 Optional (Nice-to-Have)

### 1. Improve SymbolSelectorAgent
- [ ] Add proper error handling for async news_agent.run (currently called directly in gather loop)
- [ ] Implement caching for individual symbol data to reduce DataAgent calls
- [ ] Add more fundamental data (PE, EPS growth, revenue) when FundamentalsAgent ready
- [ ] Tune prompt based on live results (adjust scoring weights)

### 2. Enhance MacroNewsAgent
- [ ] Add more macro news sources (Benzinga API, Seeking Alpha RSS)
- [ ] Implement proper deduplication across sources
- [ ] Add calendar awareness (FOMC dates, CPI releases from known schedule)
- [ ] Cache raw article content (not just JSON metadata)

### 3. Test Suite Improvements
- [ ] Add integration test for full SymbolSelector pipeline (mock LLM)
- [ ] Add test for MarketRegimeAgent with real-ish index data
- [ ] Add test for MacroNewsAgent with sample articles
- [ ] Fix remaining pre-existing test failures:
  - `test_backtesting_engine.py` (NaN propagation)
  - `test_phase0_bootstrap.py` (obsolete Flask tests)
  - `test_news_agent.py` AlphaVantage fetch tests (31 failures)

### 4. Configuration
- [ ] Add `finance/symbol_selector/use_market_context: true` toggle
- [ ] Consider separate models for SymbolSelector vs News/Regime (already supported via env vars)
- [ ] Add `symbol_selector/min_conviction_threshold` to filter low scores
- [ ] Document config sections in `docs/`

### 5. Monitoring & Observability
- [ ] Add Prometheus metrics:
  - `symbol_selector_runs_total`
  - `symbol_selector_llm_tokens_total`
  - `symbol_selector_rankings_generated`
  - `market_regime_compute_duration_seconds`
- [ ] Add structured logging (JSON) for easier parsing
- [ ] Create Grafana dashboard for LLM usage vs cost

### 6. Cost Optimization
- [ ] Implement circuit breaker if LLM costs exceed threshold (e.g., $5/day)
- [ ] Add daily budget limit check before LLM calls
- [ ] Cache market_regime and macro_news separately (TTL already set)
- [ ] Consider batch processing all candidate data before LLM call to reduce tokens

### 7. Documentation
- [ ] Write full README for SymbolSelectorAgent (prompt engineering, cost analysis)
- [ ] Document environment variable overrides in `docs/LLM_AUGMENTATION_GUIDE.md`
- [ ] Add architecture diagram showing new agents in pipeline
- [ ] Create troubleshooting guide for common LLM errors (rate limits, auth)

---

## 🔍 Known Issues

1. ~~**RegimeAgent.py** file wiped by edit tool~~ - **FIXED** (os import + env overrides added)
2. **test_phase1_data_layer.py** fails due to config path mismatch - need to verify test fixtures use correct YAML structure
3. **Options pipeline** still runs even when disabled - should be cleaned up or fully disabled
4. **NewsAgent** uses old-style `AgentReport` positional args in some places - may cause crashes
5. ~~**LLM API key** - currently using OpenRouter; need to switch to Google~~ - **RESOLVED**: Using OpenRouter as gateway with `openai/gpt-4o-mini` model (16k output tokens, avoids truncation)

---

## 📊 Test Coverage

| Component | Tests | Status |
|-----------|-------|--------|
| MarketRegimeAgent | 8 | ✅ all passing |
| MacroNewsAgent | 8 | ✅ passing (but with small mocks) |
| SymbolSelectorAgent | 8 | ✅ all passing |
| test_phase2_indicators | 30 | ✅ passing |
| test_portfolio | 1 | ✅ passing |
| test_phase3_portfolio | 41 | ✅ passing |
| test_news_agent (core) | 34 | ✅ passing |

**Goal:** All 22 new tests + existing core tests passing after manual fixes.

---

## 🎯 Success Criteria

1. **No file corruption** - all agent files intact and importable
2. **LLM initialization** - agents load LLM manager without errors
3. **Discovery scan** - SymbolSelector ranks candidates on first run
4. **Trade execution** - at least 1 trade executed within 24h of enabling
5. **Cost control** - daily token usage < 50K tokens (< $1/day)
6. **Test pass rate** - >90% of tests passing (excluding obsolete)

---

## 🚀 Deployment Checklist

- [x] All code committed and pushed
- [x] `.env` configured with LLM provider and API key (Google Gemini via OpenRouter)
- [x] `config/finance.yaml` has `llm.enabled: true` and `symbol_selector.enabled: true`
- [x] Service starts without errors
- [x] Logs confirm `SymbolSelectorAgent LLM initialized`
- [x] `/admin/force_scan` trigger produces ranked watchlist (validated in Telegram)
- [x] Token usage tracked and reported: ~12,795 tokens per scan
- [ ] Monitor first 24h: trades executed, P&L calculated, no crashes
- [ ] Review LLM costs (est. ~$0.01–0.10/scan at current token usage)
- [ ] Tag release: `v0.3-llm-selector`

---

## 📞 Questions / Blockers

- Should SymbolSelector use `TA_QUICK_THINK_MODEL` (fast, cheap) or `TA_DEEP_THINK_MODEL` (slow, expensive)? Decision needed.
- Do we want LLM for News ONLY (sentiment) or also Regime? Currently both can use LLM but config `modules.market_regime.enabled` is false by default.
- How to handle LLM API downtime? Should we fallback to rule-based scoring automatically?
- What is the desired frequency for SymbolSelector runs? After every discovery? Or daily?

---

**Next Action:** Monitor 24h live run — verify trades execute, review LLM costs, validate MarketRegimeAgent + MacroNewsAgent context used in rankings.
