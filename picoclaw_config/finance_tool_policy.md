## Finance Tool Policy

### Mandatory Tool Usage

**Never compute indicators in LLM text**. Always delegate to tools.

### Data Retrieval Tools

- `get_price_historical(symbol, start_date, end_date)` - OHLCV candles
- `get_fundamentals(symbol, statement_type)` - Income/balance/cashflow statements
- `get_company_profile(symbol)` - Company info
- `get_quote(symbol)` - Latest price + bid/ask

### Indicator Computation Tools

- `calc_rsi(prices, period)` - Relative Strength Index
- `calc_macd(prices, fast, slow, signal)` - MACD + signal + histogram
- `calc_sma(prices, window)` - Simple Moving Average
- `calc_ema(prices, window)` - Exponential Moving Average
- `calc_atr(highs, lows, closes, period)` - Average True Range
- `calc_bollinger_bands(prices, window)` - BB upper/middle/lower
- `calc_stochastic(highs, lows, closes, k_period)` - %K and %D

### Risk & Sizing Tools

- `calc_position_size(symbol, current_price, atr)` - Returns qty, stop_loss, risk
- `validate_trade(symbol, action, qty, price)` - Checks constraints
- `analyze_symbol(symbol)` - Full analysis: data + indicators + strategy decision

### Portfolio Tools

- `portfolio_get_state()` - Cash, positions, PnL
- `portfolio_propose_trade(decision)` - Dry-run validation
- `portfolio_execute_trade(task_id, approval_id)` - Execute after approval
- `portfolio_mark_to_market(prices)` - Update positions
- `portfolio_get_performance()` - Returns, Sharpe, drawdown

### Caching

- Data cached for 1 hour (avoid redundant OpenBB calls)
- Quotes cached for 5 minutes
- Fundamentals cached for 24 hours
- Manual cache clear on demand

### Rate Limiting

- Max 3 retries per OpenBB request
- 30-second timeout per request
- 10 analyze requests per minute per symbol
- Batch up to 5 symbols in single session

### Error Handling

If tool fails:
1. Log error with task_id
2. Return "data unavailable" to user
3. Suggest alternative:
   - Different symbol
   - Extended date range
   - Check if market is open

If insufficient data:
- Ask for symbol verification
- Suggest longer lookback period
- Request manual price input (as fallback, not ideal)

### No Hallucination

- If price is not retrieved, don't invent it
- If indicator can't be computed, don't guess
- If historical data is missing, say so
- Always reference tool output, not assumptions
