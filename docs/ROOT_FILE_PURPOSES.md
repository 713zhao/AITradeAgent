# Root Cleanup Notes

## Kept in root (startup-focused)

- `start.sh`: one-command startup wrapper (loads env, stops old process, starts service)
- `finance_service/run_finance_service.py`: direct service entrypoint
- `README.md`: main project overview
- `AGENTS.md`: agent/workflow instructions

## Moved from root

### `scripts/tools/`
Utility and analysis scripts (signal checks, optimization, inspection, backtest helpers, validation).

### `scripts/tests/`
Standalone test runner scripts formerly in root.

### `scripts/backtest/`
Backtest and paper-trading runner scripts.

### `scripts/setup/`
Environment/setup helpers (telegram/paper trading/setup shell).

### `scripts/integration/`
Telegram/integration helper scripts.

### `scripts/ops/`
Operational scripts (alternate starts, network/dashboard, docker helper scripts).

### `docs/archive/root-notes/`
Historical status reports and one-off markdown/txt docs.

## Why

- Reduce top-level noise.
- Keep startup path obvious.
- Preserve all legacy scripts/docs in organized folders.
