# Agent Guidelines for AITradeAgent Repository

This document provides essential information for AI agents working within the `AITradeAgent` codebase. It outlines the project's purpose, structure, key commands, conventions, and specific integration patterns, particularly concerning its interaction with the PicoClaw framework and external services.

## 1. Project Overview

The `AITradeAgent` is a Python-based finance agent designed to perform automated stock analysis, trading, and portfolio management. It integrates with various data providers (e.g., yfinance, OpenBB), brokers (e.g., Alpaca), and uses an AI agent framework (PicoClaw) for decision-making and trade execution approvals. It includes a Flask-based finance service and a Streamlit dashboard.

## 2. Project Structure

The core logic resides in `finance_service/`.
- `finance_service/brokers/`: Integrations with various trading brokers (Alpaca, Binance, IBKR, etc.).
- `finance_service/core/`: Core utilities like configuration, logging, data types, and event management.
- `finance_service/data/`: Data providers and cache management.
- `finance_service/dashboard/`: Backend logic for the Streamlit dashboard.
- `finance_service/execution/`: Trade execution algorithms and monitoring.
- `finance_service/indicators/`: Technical indicator calculations.
- `finance_service/market_data/`: Real-time market data aggregation.
- `finance_service/portfolio/`: Portfolio management and equity calculation.
- `finance_service/risk/`: Risk management and compliance.
- `finance_service/sim/`: Simulation environment for backtesting.
- `finance_service/storage/`: Database interaction (SQLite for cache and runs).
- `finance_service/strategies/`: Trading strategies and decision engine.
- `finance_service/tools/`: Helper tools (indicator, risk, OpenBB).
- `finance_service/ui/`: Streamlit dashboard UI components.

Other important directories:
- `config/`: Configuration files for finance, providers, and scheduling.
- `picoclaw_config/`: Configuration files for PicoClaw AI agent integration (system prompts, tool schemas, policies, router rules).
- `picoclaw_tools/`: Custom tools exposed to the PicoClaw agent.
- `tests/`: Unit, integration, and end-to-end tests.
- `doc/`: Project documentation and action plans.

## 3. Dependencies

Dependencies are managed via `pip`.
- Core dependencies: `requirements.txt`
- UI dependencies (for Streamlit dashboard): `requirements_ui.txt`

## 4. Essential Commands

### Setup
- **Initialize virtual environment and install dependencies:**
  ```bash
  ./setup.sh
  ```
  *(Note: This script creates a `venv` and installs `requirements.txt` and `requirements_ui.txt`)*

### Run
- **Start only the finance service:**
  ```bash
  python3 run_finance_service.py
  ```
  *(Runs the Flask API on `http://localhost:8801`)*

- **Start only the Streamlit dashboard:**
  ```bash
  ./run_dashboard.sh
  ```
  *(Requires the finance service to be running. Dashboard on `http://localhost:8501`)*

- **Start both finance service and dashboard:**
  ```bash
  ./start_all.sh
  ```
  *(Convenience script to run both in the background.)*

### Test
- **Run all tests (unit, integration, E2E, REST API):**
  ```bash
  ./tests/run_tests.sh
  ```
- **Run Pytest tests directly:**
  ```bash
  source venv/bin/activate # Activate virtual environment first
  pytest -v tests/
  ```
  *(Specific test files can be run, e.g., `pytest tests/test_analysis.py`)*

### Docker
- **Build and run all services with Docker Compose:**
  ```bash
  docker-compose up --build -d
  ```
  *(Services include `picotradeagent` (finance service), `dashboard`, `redis`, `nginx`, `prometheus`, `grafana`, `adminer`)*
- **Verify Docker deployment:**
  ```bash
  ./docker-verify.sh
  ```
- **Deploy Docker services:**
  ```bash
  ./docker-deploy.sh
  ```

## 5. Code Organization and Patterns

- **Configuration:** The `finance_service.core.config.Config` class loads settings from environment variables and YAML files (`config/`).
- **Data Flow:** Data typically flows from `finance_service.data.data_manager` (using `yfinance_provider` or OpenBB), through `indicators`, `strategies`, to `execution`, and finally interacts with `brokers`.
- **API Endpoints:** The `finance_service.app.py` defines Flask REST API endpoints (e.g., `/analyze`, `/portfolio/state`).
- **Logging:** Centralized logging is configured in `finance_service.core.logging.py`.
- **Database:** SQLite databases (`cache.sqlite`, `runs.sqlite`) are used for caching and storing backtest/trade results in `finance_service/storage/`.

## 6. AI/LLM Integration (PicoClaw Framework)

The `AITradeAgent` integrates with an external AI agent framework named "PicoClaw". This integration defines how an LLM can interact with the finance agent's capabilities.

- **PicoClaw Configuration:**
  - `picoclaw_config/picoclaw_integration.yaml`: Defines the overall integration, including services, contexts, tools exposed, routing rules, and approval gate configurations.
  - `picoclaw_config/finance_system_prompt.md`: The system-level instructions given to the LLM when operating in the finance context.
  - `picoclaw_config/finance_tool_policy.md`: Defines the policies and constraints for LLM tool usage.
  - `picoclaw_config/tool_schemas.json`: JSON schemas describing the available tools (e.g., `analyze_symbol`, `execute_trade_proposal`) that the LLM can call.

- **LLM API Keys (Gemini/Others):**
  **This `AITradeAgent` codebase does not directly manage or use specific LLM API keys, such as a "Gemini key."** The interaction with the underlying LLM (e.g., Gemini, OpenAI, etc.) is abstracted and handled by the external PicoClaw framework. API keys for the LLM itself would be configured and managed within the PicoClaw system or its environment, which is external to this repository.

- **Approval Gates:** Trade proposals generated by the LLM (via PicoClaw) can require approval through various channels (Telegram, Slack, or CLI) as configured in `picoclaw_integration.yaml`. These channels use environment variables like `TELEGRAM_BOT_TOKEN` and `SLACK_BOT_TOKEN`.

## 7. Configuration

- **`config/finance.yaml`:** Defines financial parameters like universe of symbols, risk management rules, strategy settings (indicators, entry/exit rules), backtesting parameters, and data fetching configurations.
- **`config/providers.yaml`:** Configures data providers (yfinance, OpenBB, AlphaVantage), caching strategies (SQLite, Redis), and data quality validation rules. It specifies environment variables for provider API keys (e.g., `OPENBB_API_KEY`, `ALPHA_VANTAGE_API_KEY`).
- **`config/schedule.yaml`:** (Not detailed in this analysis, but likely contains scheduling information for automated tasks).

## 8. Naming Conventions and Style Patterns

- **Python (PEP 8):** The codebase largely follows PEP 8 for Python style (snake_case for variables and functions, CapWords for class names).
- **YAML:** Configuration files (`.yaml`) use snake_case keys and often include comments for clarity.
- **Environment Variables:** Environment variables are typically uppercase with underscores (e.g., `OPENBB_API_KEY`).

## 9. Testing Approach

The `tests/` directory contains a comprehensive testing suite.
- **`tests/run_tests.sh`:** Orchestrates the execution of different test phases, including import tests, unit tests, integration tests, end-to-end flow tests, and REST API tests.
- **Pytest:** Used as the primary testing framework. Test files are named `test_*.py`.
- **Test Markers:** `pytest.ini` defines markers like `unit`, `integration`, `asyncio`, `slow` to categorize tests.
- **Testing Phases:** The `run_tests.sh` script breaks down testing into logical phases to ensure different components work in isolation and together.

## 10. Important Gotchas/Non-Obvious Patterns

- **Environment Variables:** Many critical configurations, especially API keys and tokens, are expected to be set as environment variables (e.g., `OPENBB_API_KEY`, `TELEGRAM_BOT_TOKEN`). Refer to `.env.example` for a list of expected variables.
- **Virtual Environment:** Ensure the Python virtual environment is activated before running scripts or tests to manage dependencies correctly.
- **Localhost Communication:** The Streamlit dashboard (`run_dashboard.sh`) expects the finance service to be running on `http://localhost:8801`.
- **PicoClaw Abstraction:** When working on LLM-related behavior, remember that the LLM interaction is mediated by the PicoClaw framework. Changes to prompts, tool definitions, or policies should be made in `picoclaw_config/` files. The core `finance_service` itself is an API consumed by PicoClaw.
- **Docker vs. Local:** Be mindful of the environment. Docker Compose (`docker-compose.yml`) provides a fully containerized setup, while local scripts (`run_finance_service.py`, `run_dashboard.sh`, `start_all.sh`) are for local development.

This guide should provide a solid foundation for agents to understand and effectively contribute to the `AITradeAgent` codebase.