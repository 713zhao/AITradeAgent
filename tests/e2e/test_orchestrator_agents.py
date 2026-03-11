import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
import pandas as pd
import json

from finance_service.app import MainOrchestratorAgent, initialize_orchestrator, flask_response_queues
from finance_service.core.event_bus import Event, Events, get_event_bus
from finance_service.core.config import Config
from finance_service.agents.agent_interface import AgentReport

# Mock data for yfinance provider
MOCK_OHLCV_DATA = {
    "open": [100.0, 101.0, 102.0, 103.0, 104.0],
    "high": [101.0, 102.0, 103.0, 104.0, 105.0],
    "low": [99.0, 100.0, 101.0, 102.0, 103.0],
    "close": [100.5, 101.5, 102.5, 103.5, 104.5],
    "volume": [100000, 110000, 120000, 130000, 140000],
}
MOCK_DF = pd.DataFrame(MOCK_OHLCV_DATA, index=pd.to_datetime(pd.date_range(end=datetime.now(), periods=5, freq='D')))\
.rename_axis('Date')\
.reset_index()\
.to_dict(orient='records')


@pytest.fixture(autouse=True)
async def setup_event_bus():
    # Ensure event bus is clean for each test
    event_bus = await get_event_bus()
    event_bus.clear_listeners()
    return event_bus

@pytest.fixture
async def mocked_orchestrator():
    # Mock Config for agents during initialization
    with patch('finance_service.core.config.Config.load_config') as mock_load_config, \
         patch('finance_service.agents.data_agent.YfinanceProvider') as MockYfinanceProvider, \
         patch('finance_service.agents.data_agent.DataCache') as MockDataCache, \
         patch('finance_service.agents.market_scanner_agent.MarketScannerAgent.run') as mock_market_scanner_run, \
         patch('finance_service.agents.news_agent.NewsAgent.run') as mock_news_agent_run, \
         patch('finance_service.agents.analysis_agent.AnalysisAgent.run') as mock_analysis_agent_run, \
         patch('finance_service.agents.strategy_agent.StrategyAgent.run') as mock_strategy_agent_run, \
         patch('finance_service.agents.risk_agent.RiskAgent.run') as mock_risk_agent_run, \
         patch('finance_service.agents.execution_agent.ExecutionAgent.run') as mock_execution_agent_run, \
         patch('finance_service.agents.learning_agent.LearningAgent.run') as mock_learning_agent_run, \
         patch('finance_service.agents.telegram_agent.TelegramAgent.send_message') as mock_telegram_send_message, \
         patch('finance_service.agents.telegram_agent.TelegramAgent.send_scheduled_report') as mock_telegram_send_scheduled_report, \
         patch('finance_service.agents.portfolio_agent.TradeRepository') as MockTradeRepository, \
         patch('finance_service.agents.portfolio_agent.EquityCalculator') as MockEquityCalculator:
        
        # Configure mock config values
        mock_load_config.return_value = {
            "telegram_agent": {"telegram_bot_token": "mock_token", "telegram_chat_id": "12345"},
            "scheduler_agent": {},
            "market_scanner": {},
            "data_agent": {},
            "news_agent": {},
            "analysis_agent": {},
            "strategy_agent": {},
            "risk_agent": {},
            "execution_agent": {},
            "learning_agent": {},
            "portfolio_agent": {"initial_cash": 100000.0}
        }

        # Mock market scanner to return some symbols
        mock_market_scanner_run.return_value = AgentReport(agent_id="market_scanner_agent", status="success", message="Scanned", payload={"symbols": ["AAPL", "MSFT"]})

        # Mock data agent to return mock DataFrame
        MockYfinanceProvider.return_value.fetch_ohlcv.return_value = pd.DataFrame(MOCK_OHLCV_DATA)
        MockDataCache.return_value.retrieve.return_value = None
        MockDataCache.return_value.store.return_value = True

        # Mock news agent
        mock_news_agent_run.return_value = AgentReport(agent_id="news_agent", status="success", message="News fetched", payload={"symbol": "AAPL", "news_count": 1, "sentiment": {"AAPL": {"overall_sentiment": 0.8}}, "catalysts": {}}))

        # Mock analysis agent
        mock_analysis_agent_run.return_value = AgentReport(agent_id="analysis_agent", status="success", message="Analysis complete", payload={"symbol": "AAPL", "timestamp": datetime.now().isoformat(), "indicators": {"rsi": {"value": 70.0}}})

        # Mock strategy agent
        mock_strategy_agent_run.return_value = AgentReport(agent_id="strategy_agent", status="success", message="Trade proposal", payload={"proposals": [{"symbol": "AAPL", "action": "BUY", "confidence": 0.9}]}))

        # Mock risk agent
        mock_risk_agent_run.return_value = AgentReport(agent_id="risk_agent", status="success", message="Risk check complete", payload={"trade_proposal": {"symbol": "AAPL", "action": "BUY"}, "risk_check_result": {"approval_required": False}}))

        # Mock execution agent
        mock_execution_agent_run.return_value = AgentReport(agent_id="execution_agent", status="success", message="Trade executed", payload={"trade_id": "TRADE_123", "symbol": "AAPL", "side": "BUY", "quantity": 10, "price": 100.0}))

        # Mock learning agent
        mock_learning_agent_run.return_value = AgentReport(agent_id="learning_agent", status="success", message="Learning complete", payload={}))

        # Mock portfolio agent
        mock_get_portfolio = MagicMock()
        mock_get_portfolio.return_value.model_dump.return_value = {
            "initial_cash": 100000.0, "current_cash": 99000.0, "total_equity": 101000.0, "position_count": 1
        }
        mock_get_equity_metrics = MagicMock(return_value={
            "initial_cash": 100000.0, "current_cash": 99000.0, "total_equity": 101000.0,
            "total_pnl": 1000.0, "total_return_pct": 1.0, "position_count": 1
        })
        MockTradeRepository.return_value.calculate_portfolio = mock_get_portfolio
        MockEquityCalculator.return_value.get_equity_metrics = mock_get_equity_metrics
        MockTradeRepository.return_value.get_positions.return_value = [MagicMock(model_dump=lambda: {"symbol": "AAPL", "quantity": 10, "avg_cost": 100.0, "current_price": 101.0})]

        mock_portfolio_agent_run = AsyncMock()
        mock_portfolio_agent_run.side_effect = [
            AgentReport(agent_id="portfolio_agent", status="success", message="Trade processed", payload={}),
            AgentReport(agent_id="portfolio_agent", status="success", message="Portfolio state retrieved", payload={
                "overview": {"initial_cash": 100000.0, "current_cash": 99000.0, "total_equity": 101000.0, "position_count": 1},
                "positions": [{"symbol": "AAPL", "quantity": 10, "avg_cost": 100.0, "current_price": 101.0}],
                "trades": [],
                "equity_metrics": {
                    "initial_cash": 100000.0, "current_cash": 99000.0, "gross_position_value": 1010.0,
                    "net_position_value": 1010.0, "total_equity": 101000.0, "total_pnl": 1000.0,
                    "total_return_pct": 1.0, "unrealized_pnl": 100.0, "realized_pnl": 900.0,
                    "drawdown_pct": 0.0, "position_count": 1, "trade_count": 1, "win_rate": 100.0
                },
                "last_updated": datetime.utcnow().isoformat()
            })
        ]

        with patch('finance_service.agents.portfolio_agent.PortfolioAgent.run', new=mock_portfolio_agent_run):
            orchestrator = await initialize_orchestrator()
            orchestrator.data_agent.provider = MockYfinanceProvider.return_value
            orchestrator.data_agent.cache = MockDataCache.return_value
            yield orchestrator

class TestEndToEndAgentWorkflow:

    @pytest.mark.asyncio
    async def test_full_trading_workflow(self, mocked_orchestrator, setup_event_bus):
        event_bus = setup_event_bus
        orchestrator = mocked_orchestrator

        # Simulate initial market scan trigger
        await event_bus.publish(Event(event_type=Events.MARKET_SCAN_TRIGGER))
        await asyncio.sleep(0.1) # Allow tasks to propagate

        # Verify market scanner and data agent were called (mocks are already configured to return success reports)
        orchestrator.market_scanner_agent.run.assert_called_once()
        orchestrator.data_agent.run.assert_called_with(symbol="AAPL", interval="1d") # First symbol from mock_market_scanner_run
        # The data_agent.run is mocked, so we need to ensure the subsequent calls in orchestrator's handler are made
        # which means analysis_agent.run and news_agent.run should be called.
        
        # Need to manually trigger data_fetch_complete event for the workflow to continue,
        # as the DataAgent mock doesn't actually publish it.
        await event_bus.publish(Event(event_type=Events.DATA_FETCH_COMPLETE, data={"symbol": "AAPL", "interval": "1d", "dataframe": MOCK_DF}))
        await asyncio.sleep(0.1)

        orchestrator.news_agent.run.assert_called_with(symbol="AAPL")
        orchestrator.analysis_agent.run.assert_called_with(data_payload=MOCK_DF, symbol="AAPL")

        # Now simulate both news and analysis complete to trigger strategy agent
        await event_bus.publish(Event(event_type=Events.NEWS_FETCH_COMPLETE, data={"symbol": "AAPL", "news_count": 1, "sentiment": {"AAPL": {"overall_sentiment": 0.8}}, "catalysts": {}}))
        await event_bus.publish(Event(event_type=Events.ANALYSIS_COMPLETE, data={"symbol": "AAPL", "timestamp": datetime.now().isoformat(), "indicators": {"rsi": {"value": 70.0}}, "current_price": 104.5})) # Added current_price
        await asyncio.sleep(0.1)

        orchestrator.strategy_agent.run.assert_called_once()
        orchestrator.risk_agent.run.assert_called_once()
        orchestrator.execution_agent.run.assert_called_once()
        orchestrator.portfolio_agent.run.assert_called() # Called for trade execution
        orchestrator.learning_agent.run.assert_called_once()

        print("Full trading workflow test passed.")

    @pytest.mark.asyncio
    async def test_flask_portfolio_state_endpoint(self, mocked_orchestrator, setup_event_bus):
        orchestrator = mocked_orchestrator
        event_bus = setup_event_bus
        
        from finance_service.app import app
        client = app.test_client()

        request_id = "flask_test_request_1"
        flask_response_queues[request_id] = asyncio.Queue()

        response = await client.get(f"/portfolio/state?request_id={request_id}") # Pass request_id via query param for simplicity in test
        assert response.status_code == 200
        assert "Portfolio state request sent" in response.json["message"]

        # The orchestrator should have received the GET_PORTFOLIO_STATE event and put a report in the queue
        await asyncio.sleep(0.1)
        orchestrator.portfolio_agent.run.assert_called_with(event_type=Events.GET_PORTFOLIO_STATE, payload={})
        
        # Verify the final response
        # The Flask handler now waits on the queue, so we need to ensure the mock puts data into it.
        # This is implicitly handled by the mocked_orchestrator's mock_portfolio_agent_run side_effect.

        # Since the Flask endpoint now waits, we need to ensure the response queue gets populated.
        # This is already set up in the mocked_orchestrator fixture for the second call to portfolio_agent.run.
        # We need to explicitly get the response from the queue in the test if we are not testing the live app loop.
        # However, the current Flask app code directly calls portfolio_agent.run and *then* tries to get from queue.
        # Let's adjust the Flask endpoint to pass the request_id to the event, and then handle in orchestrator.
        
        # We need to manually put an item into the queue to simulate the orchestrator responding
        # For simplicity, let's just assert on the message initially and assume the orchestrator correctly publishes.
        # The actual /portfolio/state route in app.py now awaits on the queue.
        # To properly test this, we need to mock the `initialize_orchestrator` to return our `mocked_orchestrator`
        # and ensure the `handle_get_portfolio_state` pushes to the queue.

        # Re-mock initialize_orchestrator for Flask tests, as it needs to return our mocked_orchestrator
        with patch('finance_service.app.initialize_orchestrator') as mock_init_orchestrator:
            mock_init_orchestrator.return_value = orchestrator
            # Now, simulate a Flask request that expects a response from the queue
            request_id = "flask_test_request_2"
            flask_response_queues[request_id] = asyncio.Queue()
            
            # Manually trigger the event that the Flask endpoint would trigger, but ensure it uses the request_id
            await event_bus.publish(Event(event_type=Events.GET_PORTFOLIO_STATE, data={"chat_id": "flask_request", "request_id": request_id}))
            await asyncio.sleep(0.1) # Give time for event to be handled

            # The orchestrator's handler for GET_PORTFOLIO_STATE should have put a report into flask_response_queues[request_id]
            response_report = await flask_response_queues[request_id].get()
            assert response_report.status == "success"
            assert response_report.payload["equity_metrics"]["total_equity"] == 101000.0
        
        print("Flask /portfolio/state endpoint test passed.")

    @pytest.mark.asyncio
    async def test_telegram_system_status_command(self, mocked_orchestrator, setup_event_bus):
        orchestrator = mocked_orchestrator
        event_bus = setup_event_bus

        # Simulate Telegram /status command
        mock_chat_id = "telegram_chat_123"
        await event_bus.publish(Event(event_type=Events.GET_SYSTEM_STATUS, data={"chat_id": mock_chat_id}))
        await asyncio.sleep(0.1) # Allow orchestrator to handle

        # Verify TelegramAgent.send_message was called with the status report
        orchestrator.telegram_agent.send_message.assert_called_with(
            chat_id=mock_chat_id,
            message=f"System Status Report:\\n```json\\n{json.dumps({\n                \"orchestrator\": \"running\",\n                \"market_scanner\": \"idle\",\n                \"data_agent\": \"ready\",\n                \"news_agent\": \"ready\",\n                \"analysis_agent\": \"ready\",\n                \"strategy_agent\": \"ready\",\n                \"risk_agent\": \"ready\",\n                \"execution_agent\": \"ready\",\n                \"learning_agent\": \"ready\",\n                \"portfolio_agent\": \"ready\",\n                \"scheduler_agent\": \"running\",\n                \"last_scan\": datetime.utcnow().isoformat()[:-7] + 'Z', # Adjust for potential timezone differences in mock\n                \"active_tasks\": MagicMock()\n            }, indent=2)}\\n```",
            parse_mode=None
        )
        print("Telegram /status command test passed.")

    @pytest.mark.asyncio
    async def test_daily_report_trigger(self, mocked_orchestrator, setup_event_bus):
        orchestrator = mocked_orchestrator
        event_bus = setup_event_bus

        # Simulate daily report trigger from scheduler
        await event_bus.publish(Event(event_type=Events.DAILY_REPORT_TRIGGER))
        await asyncio.sleep(0.1) # Allow orchestrator to handle

        # Verify portfolio agent was called to get state
        orchestrator.portfolio_agent.run.assert_called_with(event_type=Events.GET_PORTFOLIO_STATE, payload={})
        
        # Verify TelegramAgent.send_scheduled_report was called with the report data
        orchestrator.telegram_agent.send_scheduled_report.assert_called_once()
        args, kwargs = orchestrator.telegram_agent.send_scheduled_report.call_args
        
        assert "report_data" in kwargs
        report_data = kwargs["report_data"]
        assert report_data["total_equity"] == 101000.0
        assert report_data["total_pnl"] == 1000.0

        print("Daily report trigger test passed.")

    @pytest.mark.asyncio
    async def test_flask_get_quote_endpoint(self, mocked_orchestrator):
        orchestrator = mocked_orchestrator
        from finance_service.app import app
        client = app.test_client()

        # Mock the data_agent.run to return a successful report with DataFrame payload
        orchestrator.data_agent.run = AsyncMock(return_value=AgentReport(
            agent_id="data_agent",
            status="success",
            message="Data fetched",
            payload={
                "symbol": "AAPL",
                "interval": "1d",
                "dataframe": MOCK_DF # Return the mock DataFrame dict
            }
        ))

        response = await client.get("/quote/AAPL")
        assert response.status_code == 200
        json_data = response.json
        assert json_data["symbol"] == "AAPL"
        assert json_data["close"] == 104.5 # Latest close price from MOCK_OHLCV_DATA

        print("Flask /quote/<symbol> endpoint test passed.")

    @pytest.mark.asyncio
    async def test_flask_propose_trade_endpoint(self, mocked_orchestrator):
        orchestrator = mocked_orchestrator
        from finance_service.app import app
        client = app.test_client()

        # The mocked_orchestrator already has mock_strategy_agent_run configured
        response = await client.post("/portfolio/propose", json={"symbol": "AAPL"})
        assert response.status_code == 200
        json_data = response.json
        assert "proposals" in json_data
        assert len(json_data["proposals"]) > 0
        assert json_data["proposals"][0]["symbol"] == "AAPL"
        assert json_data["proposals"][0]["action"] == "BUY"

        orchestrator.strategy_agent.run.assert_called_once()
        print("Flask /portfolio/propose endpoint test passed.")

    @pytest.mark.asyncio
    async def test_flask_execute_trade_endpoint(self, mocked_orchestrator, setup_event_bus):
        orchestrator = mocked_orchestrator
        event_bus = setup_event_bus
        from finance_service.app import app
        client = app.test_client()

        trade_proposal_mock = {"symbol": "AAPL", "action": "BUY", "quantity": 10, "price": 100.0, "trade_id": "TEST_EXEC_1"}

        request_id = "flask_test_request_execute_1"
        flask_response_queues[request_id] = asyncio.Queue()

        response = await client.post("/portfolio/execute", json={"trade_proposal": trade_proposal_mock, "request_id": request_id})
        assert response.status_code == 200
        json_data = response.json
        assert json_data["status"] == "success"
        assert json_data["payload"]["trade_id"] == "TRADE_123" # From mock_execution_agent_run

        orchestrator.execution_agent.run.assert_called_once()
        orchestrator.portfolio_agent.run.assert_called() # Should have been called during handle_trade_executed
        orchestrator.learning_agent.run.assert_called_once()

        print("Flask /portfolio/execute endpoint test passed.")
