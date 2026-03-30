"""
Test suite for ExitAgent with enhanced strategic re-analysis capability.
Tests both reactive exits (stop-loss/take-profit) and strategic degradation checks.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime
from dataclasses import asdict

from finance_service.agents.exit_agent import ExitAgent
from finance_service.agents.agent_interface import AgentReport
from finance_service.core.event_bus import Event, Events, get_event_bus


pytest_plugins = ('pytest_asyncio',)


class TestExitAgentBasics:
    """Basic initialization and attribute tests."""
    
    def test_exit_agent_initialization(self):
        """Test ExitAgent initializes with correct properties."""
        config = Mock()
        data_agent = Mock()
        exit_agent = ExitAgent(config, data_agent=data_agent)
        
        assert exit_agent.agent_id == "exit_agent"
        assert exit_agent.data_agent is data_agent
        assert "position" in exit_agent.goal.lower() or "monitor" in exit_agent.goal.lower()
    
    def test_exit_agent_goal(self):
        """Test that ExitAgent has a meaningful goal."""
        agent = ExitAgent(config_engine=Mock())
        assert isinstance(agent.goal, str)
        assert len(agent.goal) > 0


class TestReactiveExits:
    """Test reactive exit detection (stop-loss and take-profit)."""
    
    @pytest.mark.asyncio
    async def test_stop_loss_triggered(self):
        """Test stop-loss exit is triggered when price <= stop_loss."""
        agent = ExitAgent(config_engine=Mock())
        
        positions = [
            {
                "symbol": "NVDA",
                "quantity": 10,
                "current_price": 120.0,
                "stop_loss_price": 125.0,  # Current price below stop-loss
                "take_profit_price": 140.0
            }
        ]
        
        report = await agent.run(positions=positions, perform_strategy_check=False)
        
        assert report.status == "success"
        payload = report.payload or {}
        exits = payload.get("reactive_exits", [])
        assert len(exits) > 0
        assert exits[0]["symbol"] == "NVDA"
        assert "stop loss" in exits[0]["reason"].lower()
    
    @pytest.mark.asyncio
    async def test_take_profit_triggered(self):
        """Test take-profit exit is triggered when price >= take_profit."""
        agent = ExitAgent(config_engine=Mock())
        
        positions = [
            {
                "symbol": "PLTR",
                "quantity": 5,
                "current_price": 140.0,
                "stop_loss_price": 120.0,
                "take_profit_price": 135.0  # Current price above take-profit
            }
        ]
        
        report = await agent.run(positions=positions, perform_strategy_check=False)
        
        assert report.status == "success"
        payload = report.payload or {}
        exits = payload.get("reactive_exits", [])
        assert len(exits) > 0
        assert exits[0]["symbol"] == "PLTR"
        assert "take profit" in exits[0]["reason"].lower()
    
    @pytest.mark.asyncio
    async def test_no_exit_when_price_between_stops(self):
        """Test no exit when price is between stop-loss and take-profit."""
        agent = ExitAgent(config_engine=Mock())
        
        positions = [
            {
                "symbol": "AMD",
                "quantity": 20,
                "current_price": 130.0,
                "stop_loss_price": 120.0,
                "take_profit_price": 140.0  # Price in the middle
            }
        ]
        
        report = await agent.run(positions=positions, perform_strategy_check=False)
        
        assert report.status == "success"
        payload = report.payload or {}
        exits = payload.get("reactive_exits", [])
        assert len(exits) == 0


class TestStrategicDegradation:
    """Test strategic re-analysis for position degradation."""
    
    @pytest.mark.asyncio
    async def test_degradation_detected_high_rsi(self):
        """Test position degradation when RSI becomes overbought."""
        config = Mock()
        data_agent = AsyncMock()
        analysis_agent = AsyncMock()
        
        # Mock data agent response
        data_agent.run.return_value = AgentReport(
            agent_id="data_agent",
            status="success",
            message="Data fetched",
            payload={
                "symbol": "NVDA",
                "dataframe": {"close": [100, 102, 105, 108, 110]}
            }
        )
        
        # Mock analysis agent response with overbought RSI
        analysis_agent.run.return_value = AgentReport(
            agent_id="analysis_agent",
            status="success",
            message="Analysis complete",
            payload={
                "indicators_snapshot": {
                    "rsi": 75.0,  # Overbought
                    "trend": "bullish",
                    "close": 110.0
                }
            }
        )
        
        agent = ExitAgent(
            config_engine=config,
            data_agent=data_agent,
            analysis_agent=analysis_agent
        )
        
        positions = [
            {
                "symbol": "NVDA",
                "quantity": 10,
                "entry_price": 100.0,
                "current_price": 110.0
            }
        ]
        
        report = await agent.run(positions=positions, perform_strategy_check=True)
        
        assert report.status == "success"
        payload = report.payload or {}
        degraded = payload.get("degraded_positions", [])
        assert len(degraded) > 0, f"Expected degradation detected, got: {payload}"
        assert degraded[0]["symbol"] == "NVDA"
        assert degraded[0]["rsi"] > 70
    
    @pytest.mark.asyncio
    async def test_degradation_detected_bearish_trend(self):
        """Test position degradation when trend reverses to bearish."""
        config = Mock()
        data_agent = AsyncMock()
        analysis_agent = AsyncMock()
        
        data_agent.run.return_value = AgentReport(
            agent_id="data_agent",
            status="success",
            message="Data fetched",
            payload={"dataframe": {"close": [120, 118, 115, 112, 110]}}
        )
        
        analysis_agent.run.return_value = AgentReport(
            agent_id="analysis_agent",
            status="success",
            message="Analysis complete",
            payload={
                "indicators_snapshot": {
                    "rsi": 55.0,
                    "trend": "bearish",  # Bearish reversal
                    "close": 110.0
                }
            }
        )
        
        agent = ExitAgent(
            config_engine=config,
            data_agent=data_agent,
            analysis_agent=analysis_agent
        )
        
        positions = [
            {
                "symbol": "TSLA",
                "quantity": 5,
                "entry_price": 120.0,
                "current_price": 110.0
            }
        ]
        
        report = await agent.run(positions=positions, perform_strategy_check=True)
        
        assert report.status == "success"
        payload = report.payload or {}
        degraded = payload.get("degraded_positions", [])
        assert len(degraded) > 0, f"Expected degradation for bearish trend, got: {payload}"
        assert "bearish" in degraded[0]["reason"].lower() or "degraded" in degraded[0]["reason"].lower()
    
    @pytest.mark.asyncio
    async def test_no_degradation_when_healthy(self):
        """Test no degradation when position is still healthy."""
        config = Mock()
        data_agent = AsyncMock()
        analysis_agent = AsyncMock()
        
        data_agent.run.return_value = AgentReport(
            agent_id="data_agent",
            status="success",
            message="Data fetched",
            payload={"dataframe": {"close": [100, 102, 105, 108, 110]}}
        )
        
        analysis_agent.run.return_value = AgentReport(
            agent_id="analysis_agent",
            status="success",
            message="Analysis complete",
            payload={
                "indicators_snapshot": {
                    "rsi": 55.0,  # Healthy RSI
                    "trend": "bullish",  # Bullish trend
                    "close": 110.0
                }
            }
        )
        
        agent = ExitAgent(
            config_engine=config,
            data_agent=data_agent,
            analysis_agent=analysis_agent
        )
        
        positions = [
            {
                "symbol": "AMD",
                "quantity": 15,
                "entry_price": 100.0,
                "current_price": 110.0
            }
        ]
        
        report = await agent.run(positions=positions, perform_strategy_check=True)
        
        assert report.status == "success"
        payload = report.payload or {}
        degraded = payload.get("degraded_positions", [])
        # Should have no degradations for healthy position
        assert len(degraded) == 0, f"Expected no degradation, got: {degraded}"


class TestEmptyAndErrorCases:
    """Test edge cases and error handling."""
    
    @pytest.mark.asyncio
    async def test_no_positions(self):
        """Test handling when no positions are provided."""
        agent = ExitAgent(config_engine=Mock())
        
        report = await agent.run(positions=None)
        
        assert report.status == "error"
        assert "no positions" in report.message.lower()
    
    @pytest.mark.asyncio
    async def test_empty_positions_list(self):
        """Test handling empty positions list."""
        agent = ExitAgent(config_engine=Mock())
        
        report = await agent.run(positions=[])
        
        assert report.status == "success"
        payload = report.payload or {}
        assert payload.get("checked_count") == 0
    
    @pytest.mark.asyncio
    async def test_data_fetch_failure_fallback(self):
        """Test graceful fallback when data fetch fails."""
        config = Mock()
        data_agent = AsyncMock()
        analysis_agent = AsyncMock()
        
        data_agent.run.return_value = AgentReport(
            agent_id="data_agent",
            status="error",
            message="Failed to fetch"
        )
        
        agent = ExitAgent(
            config_engine=config,
            data_agent=data_agent,
            analysis_agent=analysis_agent
        )
        
        positions = [
            {
                "symbol": "TEST",
                "quantity": 1,
                "entry_price": 100.0
            }
        ]
        
        report = await agent.run(positions=positions, perform_strategy_check=True)
        
        # Should complete successfully despite data fetch failure
        assert report.status == "success"


class TestIntegration:
    """Integration tests combining multiple features."""
    
    @pytest.mark.asyncio
    async def test_mixed_exits_and_degradations(self):
        """Test scenario with both reactive exits and degradations."""
        config = Mock()
        data_agent = AsyncMock()
        analysis_agent = AsyncMock()
        
        positions = [
            {
                "symbol": "NVDA",
                "quantity": 10,
                "current_price": 119.0,
                "stop_loss_price": 120.0,  # Reactive exit
                "take_profit_price": 140.0,
                "entry_price": 100.0
            },
            {
                "symbol": "AMD",
                "quantity": 5,
                "current_price": 110.0,
                "stop_loss_price": 100.0,
                "take_profit_price": 130.0,
                "entry_price": 100.0
            }
        ]
        
        # Mock responses for degradation check
        async def mock_data_run(*args, **kwargs):
            return AgentReport(
                agent_id="data_agent",
                status="success",
                message="Data fetched",
                payload={"dataframe": {"close": [100, 102, 105, 108, 110]}}
            )
        
        async def mock_analysis_run(*args, **kwargs):
            # Return overbought for all
            return AgentReport(
                agent_id="analysis_agent",
                status="success",
                message="Analysis complete",
                payload={
                    "indicators_snapshot": {
                        "rsi": 75.0,
                        "trend": "bullish",
                        "close": 110.0
                    }
                }
            )
        
        data_agent.run = mock_data_run
        analysis_agent.run = mock_analysis_run
        
        agent = ExitAgent(
            config_engine=config,
            data_agent=data_agent,
            analysis_agent=analysis_agent
        )
        
        report = await agent.run(positions=positions, perform_strategy_check=True)
        
        assert report.status == "success"
        payload = report.payload or {}
        
        # Should have exits and/or degradations
        exits = payload.get("reactive_exits", [])
        degraded = payload.get("degraded_positions", [])
        
        assert len(exits) + len(degraded) > 0, f"Expected checks to trigger, exits={exits}, degraded={degraded}"


class TestOutputFormat:
    """Test output format and payload structure."""
    
    @pytest.mark.asyncio
    async def test_exit_record_structure(self):
        """Test that exit records have required fields."""
        agent = ExitAgent(config_engine=Mock())
        
        positions = [
            {
                "symbol": "TEST",
                "quantity": 10,
                "current_price": 120.0,
                "stop_loss_price": 125.0,
                "take_profit_price": 140.0
            }
        ]
        
        report = await agent.run(positions=positions, perform_strategy_check=False)
        payload = report.payload or {}
        exits = payload.get("reactive_exits", [])
        
        assert len(exits) > 0
        exit_record = exits[0]
        
        # Check required fields
        assert "symbol" in exit_record
        assert "quantity" in exit_record
        assert "exit_price" in exit_record
        assert "reason" in exit_record
        assert "exit_type" in exit_record
        assert exit_record["exit_type"] == "reactive"
    
    @pytest.mark.asyncio
    async def test_degradation_record_structure(self):
        """Test that degradation records have required fields."""
        config = Mock()
        data_agent = AsyncMock()
        analysis_agent = AsyncMock()
        
        data_agent.run.return_value = AgentReport(
            agent_id="data_agent",
            status="success",
            message="Data fetched",
            payload={"dataframe": {"close": [100, 102, 105, 108]}}
        )
        
        analysis_agent.run.return_value = AgentReport(
            agent_id="analysis_agent",
            status="success",
            message="Analysis complete",
            payload={
                "indicators_snapshot": {
                    "rsi": 80.0,
                    "trend": "bullish",
                    "close": 110.0
                }
            }
        )
        
        agent = ExitAgent(
            config_engine=config,
            data_agent=data_agent,
            analysis_agent=analysis_agent
        )
        
        positions = [
            {
                "symbol": "TEST",
                "quantity": 5,
                "entry_price": 100.0,
                "current_price": 110.0
            }
        ]
        
        report = await agent.run(positions=positions, perform_strategy_check=True)
        payload = report.payload or {}
        degraded = payload.get("degraded_positions", [])
        
        if len(degraded) > 0:
            deg_record = degraded[0]
            # Check required fields
            assert "symbol" in deg_record
            assert "quantity" in deg_record
            assert "entry_price" in deg_record
            assert "current_price" in deg_record
            assert "rsi" in deg_record
            assert "trend" in deg_record
            assert "reason" in deg_record
            assert "recommendation" in deg_record


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# ========== Additional Coverage Tests ==========

class TestReactiveExitExecution:
    """Tests for the execution path within reactive exits."""

    @pytest.mark.asyncio
    async def test_execution_agent_called_on_stop_loss(self):
        """When execution_agent is present, it should auto-execute a SELL on exit trigger."""
        mock_execution = AsyncMock()
        mock_execution.run = AsyncMock(return_value=AgentReport(
            agent_id="execution_agent", status="success",
            message="Executed", payload={"order_id": "123"}
        ))
        agent = ExitAgent(
            config_engine=None,
            data_agent=AsyncMock(),
            execution_agent=mock_execution,
        )
        positions = [{
            "symbol": "AAPL", "quantity": 10,
            "current_price": 90.0, "stop_loss_price": 95.0, "take_profit_price": 200.0
        }]
        report = await agent.run(positions=positions, perform_strategy_check=False)
        assert report.payload["exits_count"] == 1
        mock_execution.run.assert_called_once()
        call_args = mock_execution.run.call_args
        trade = call_args.kwargs["approved_trade_proposal"]
        assert trade["action"] == "SELL"
        assert trade["symbol"] == "AAPL"

    @pytest.mark.asyncio
    async def test_execution_agent_error_does_not_break(self):
        """If execution_agent.run() raises, the exit should still be recorded."""
        mock_execution = AsyncMock()
        mock_execution.run = AsyncMock(side_effect=RuntimeError("Broker connection failed"))
        agent = ExitAgent(
            config_engine=None,
            data_agent=AsyncMock(),
            execution_agent=mock_execution,
        )
        positions = [{
            "symbol": "TSLA", "quantity": 5,
            "current_price": 80.0, "stop_loss_price": 85.0, "take_profit_price": 300.0
        }]
        report = await agent.run(positions=positions, perform_strategy_check=False)
        # Exit should still be recorded even if execution fails
        assert report.payload["exits_count"] == 1
        assert report.payload["reactive_exits"][0]["symbol"] == "TSLA"

    @pytest.mark.asyncio
    async def test_no_execution_agent_logs_warning(self):
        """When execution_agent is None, exits are recorded but not executed."""
        agent = ExitAgent(config_engine=None, data_agent=None, execution_agent=None)
        positions = [{
            "symbol": "GOOG", "quantity": 3,
            "current_price": 50.0, "stop_loss_price": 55.0, "take_profit_price": 200.0
        }]
        report = await agent.run(positions=positions, perform_strategy_check=False)
        assert report.payload["exits_count"] == 1
        assert report.payload["reactive_exits"][0]["symbol"] == "GOOG"


class TestDataAgentPriceFetch:
    """Tests for fetching current_price via DataAgent when not provided."""

    @pytest.mark.asyncio
    async def test_fetches_price_from_data_agent(self):
        """When current_price is None, it should attempt to fetch from data_agent."""
        import pandas as pd
        mock_data = AsyncMock()
        df = pd.DataFrame({"close": [100.0, 95.0, 88.0]})  # last price = 88
        mock_data.run = AsyncMock(return_value=AgentReport(
            agent_id="data_agent", status="success",
            message="ok", payload={"dataframe": df.to_dict()}
        ))
        agent = ExitAgent(config_engine=None, data_agent=mock_data, execution_agent=None)
        positions = [{
            "symbol": "AMD", "quantity": 10,
            "current_price": None,  # force data agent lookup
            "stop_loss_price": 90.0, "take_profit_price": 200.0
        }]
        report = await agent.run(positions=positions, perform_strategy_check=False)
        mock_data.run.assert_called_once()
        # 88.0 < 90.0 → stop-loss triggered
        assert report.payload["exits_count"] == 1
        assert report.payload["reactive_exits"][0]["symbol"] == "AMD"

    @pytest.mark.asyncio
    async def test_skip_position_when_no_price_available(self):
        """When current_price is None and data_agent is also None, skip the position."""
        agent = ExitAgent(config_engine=None, data_agent=None, execution_agent=None)
        positions = [{
            "symbol": "FAKE", "quantity": 10,
            "current_price": None,
            "stop_loss_price": 50.0, "take_profit_price": 200.0
        }]
        report = await agent.run(positions=positions, perform_strategy_check=False)
        # Should skip, not exit (no price to compare)
        assert report.payload["exits_count"] == 0


class TestStrategicEdgeCases:
    """Tests for edge cases in strategic degradation."""

    @pytest.mark.asyncio
    async def test_strategy_check_skipped_without_analysis_agent(self):
        """When perform_strategy_check=True but no analysis_agent, should skip strategic mode."""
        agent = ExitAgent(config_engine=None, data_agent=AsyncMock(), execution_agent=None,
                          analysis_agent=None, strategy_agent=None)
        positions = [{"symbol": "NVDA", "quantity": 10, "current_price": 200.0}]
        report = await agent.run(positions=positions, perform_strategy_check=True)
        assert report.payload["degraded_count"] == 0

    @pytest.mark.asyncio
    async def test_analysis_failure_skips_position(self):
        """When AnalysisAgent returns failure, position is skipped not crashed."""
        mock_data = AsyncMock()
        mock_data.run = AsyncMock(return_value=AgentReport(
            agent_id="data_agent", status="success",
            message="ok", payload={"dataframe": {}}
        ))
        mock_analysis = AsyncMock()
        mock_analysis.run = AsyncMock(return_value=AgentReport(
            agent_id="analysis_agent", status="error",
            message="Failed", payload={}
        ))
        agent = ExitAgent(
            config_engine=None, data_agent=mock_data,
            execution_agent=None, analysis_agent=mock_analysis
        )
        positions = [{
            "symbol": "PLTR", "quantity": 5, "current_price": 30.0,
            "entry_price": 25.0
        }]
        report = await agent.run(positions=positions, perform_strategy_check=True)
        # Analysis failed → position skipped, not degraded
        assert report.payload["degraded_count"] == 0

    @pytest.mark.asyncio
    async def test_position_without_symbol_skipped(self):
        """Position dicts missing 'symbol' key should be gracefully skipped."""
        mock_data = AsyncMock()
        mock_data.run = AsyncMock(return_value=AgentReport(
            agent_id="data_agent", status="success",
            message="ok", payload={}
        ))
        mock_analysis = AsyncMock()
        agent = ExitAgent(
            config_engine=None, data_agent=mock_data,
            execution_agent=None, analysis_agent=mock_analysis
        )
        positions = [
            {"quantity": 10, "current_price": 100.0},  # missing symbol
            {"symbol": None, "quantity": 5, "current_price": 50.0},  # None symbol
        ]
        report = await agent.run(positions=positions, perform_strategy_check=True)
        # Both should be skipped
        assert report.payload["degraded_count"] == 0

    @pytest.mark.asyncio
    async def test_position_degraded_event_emitted(self):
        """When a position is degraded, POSITION_DEGRADED event should be published."""
        mock_data = AsyncMock()
        mock_data.run = AsyncMock(return_value=AgentReport(
            agent_id="data_agent", status="success",
            message="ok", payload={"dataframe": {}}
        ))
        mock_analysis = AsyncMock()
        mock_analysis.run = AsyncMock(return_value=AgentReport(
            agent_id="analysis_agent", status="success",
            message="ok", payload={
                "indicators_snapshot": {"rsi": 80.0, "trend": "bullish", "close": 150.0}
            }
        ))
        agent = ExitAgent(
            config_engine=None, data_agent=mock_data,
            execution_agent=None, analysis_agent=mock_analysis
        )
        # Mock event_bus.publish
        agent.event_bus = AsyncMock()
        agent.event_bus.publish = AsyncMock()

        positions = [{"symbol": "META", "quantity": 8, "entry_price": 100.0, "current_price": 150.0}]
        report = await agent.run(positions=positions, perform_strategy_check=True)
        assert report.payload["degraded_count"] == 1
        # Verify event was published
        agent.event_bus.publish.assert_called()
        published_event = agent.event_bus.publish.call_args[0][0]
        assert published_event.event_type == Events.POSITION_DEGRADED
        assert published_event.data["symbol"] == "META"
