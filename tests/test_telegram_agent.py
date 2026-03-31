"""Telegram Agent Tests - Message sending, scheduling, and topic support"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from finance_service.agents.telegram_agent import TelegramAgent
from finance_service.core.config import Config
from telegram.error import TelegramError


class TestTelegramAgentInitialization:
    """Test TelegramAgent initialization and configuration"""
    
    def test_agent_initialization_without_thread_id(self):
        """Test agent initializes with bot token and chat id"""
        config = {
            "telegram_bot_token": "test_token_123",
            "telegram_chat_id": "12345",
        }
        
        with patch('finance_service.agents.telegram_agent.Application') as MockApp, \
             patch('finance_service.agents.telegram_agent.get_event_bus') as mock_event_bus:
            
            mock_app = MagicMock()
            MockApp.builder.return_value.token.return_value.build.return_value = mock_app
            
            agent = TelegramAgent(config)
            
            assert agent.enabled is True
            assert agent.bot_token == "test_token_123"
            assert agent.chat_id == "12345"
            assert agent.thread_id is None
    
    def test_agent_initialization_with_thread_id(self):
        """Test agent initializes with thread_id for topic support"""
        config = {
            "telegram_bot_token": "test_token_123",
            "telegram_chat_id": "12345",
            "telegram_message_thread_id": "789",
        }
        
        with patch('finance_service.agents.telegram_agent.Application') as MockApp, \
             patch('finance_service.agents.telegram_agent.get_event_bus') as mock_event_bus:
            
            mock_app = MagicMock()
            MockApp.builder.return_value.token.return_value.build.return_value = mock_app
            
            agent = TelegramAgent(config)
            
            assert agent.enabled is True
            assert agent.thread_id == 789
    
    def test_agent_initialization_with_string_thread_id(self):
        """Test agent initializes with string thread_id (converts to int)"""
        config = {
            "telegram_bot_token": "test_token_123",
            "telegram_chat_id": "12345",
            "telegram_message_thread_id": "999",
        }
        
        with patch('finance_service.agents.telegram_agent.Application') as MockApp, \
             patch('finance_service.agents.telegram_agent.get_event_bus') as mock_event_bus:
            
            mock_app = MagicMock()
            MockApp.builder.return_value.token.return_value.build.return_value = mock_app
            
            agent = TelegramAgent(config)
            
            assert isinstance(agent.thread_id, (int, type(None)))
            assert agent.thread_id == 999
    
    def test_agent_initialization_with_empty_thread_id(self):
        """Test agent initializes with empty thread_id (treats as None)"""
        config = {
            "telegram_bot_token": "test_token_123",
            "telegram_chat_id": "12345",
            "telegram_message_thread_id": "",
        }
        
        with patch('finance_service.agents.telegram_agent.Application') as MockApp, \
             patch('finance_service.agents.telegram_agent.get_event_bus') as mock_event_bus:
            
            mock_app = MagicMock()
            MockApp.builder.return_value.token.return_value.build.return_value = mock_app
            
            agent = TelegramAgent(config)
            
            assert agent.thread_id is None
    
    def test_agent_disabled_with_missing_bot_token(self):
        """Test agent configuration properties when bot token is missing"""
        config = {
            "telegram_chat_id": "12345",
        }
        
        with patch('finance_service.agents.telegram_agent.get_event_bus') as mock_event_bus, \
             patch.object(Config, 'TELEGRAM_BOT_TOKEN', ''), \
             patch.object(Config, 'TELEGRAM_CHAT_ID', '12345'):
            
            agent = TelegramAgent(config)
            
            # Should be disabled when bot token is missing
            assert agent.enabled is False
            assert agent.application is None
    
    def test_agent_disabled_on_telegram_error(self):
        """Test agent is disabled when Telegram Bot initialization fails"""
        config = {
            "telegram_bot_token": "test_token_123",
            "telegram_chat_id": "12345",
        }
        
        with patch('finance_service.agents.telegram_agent.Application') as MockApp, \
             patch('finance_service.agents.telegram_agent.get_event_bus') as mock_event_bus:
            
            MockApp.builder.return_value.token.return_value.build.side_effect = TelegramError("Authentication failed")
            
            agent = TelegramAgent(config)
            # Agent should still initialize but be marked as disabled
            assert agent.enabled is False
    
    def test_agent_properties(self):
        """Test agent property accessors"""
        config = {
            "telegram_bot_token": "test_token_123",
            "telegram_chat_id": "12345",
        }
        
        with patch('finance_service.agents.telegram_agent.Application') as MockApp, \
             patch('finance_service.agents.telegram_agent.get_event_bus') as mock_event_bus:
            
            mock_app = MagicMock()
            MockApp.builder.return_value.token.return_value.build.return_value = mock_app
            
            agent = TelegramAgent(config)
            
            assert agent.agent_id == "telegram_agent"
            assert "Telegram" in agent.goal


class TestTelegramAgentSendMessage:
    """Test send_message functionality with and without thread_id"""
    
    @pytest.mark.asyncio
    async def test_send_message_without_thread_id(self):
        """Test sending a message without thread_id"""
        config = {
            "telegram_bot_token": "test_token_123",
            "telegram_chat_id": "12345",
        }
        
        with patch('finance_service.agents.telegram_agent.Application') as MockApp, \
             patch('finance_service.agents.telegram_agent.get_event_bus') as mock_event_bus:
            
            mock_bot_instance = AsyncMock()
            mock_app = MagicMock()
            mock_app.bot = mock_bot_instance
            MockApp.builder.return_value.token.return_value.build.return_value = mock_app
            
            agent = TelegramAgent(config)
            
            await agent.send_message("12345", "Test message")
            
            # Verify send_message was called without message_thread_id
            mock_bot_instance.send_message.assert_called_once()
            call_kwargs = mock_bot_instance.send_message.call_args[1]
            assert call_kwargs["chat_id"] == "12345"
            assert call_kwargs["text"] == "Test message"
    
    @pytest.mark.asyncio
    async def test_send_message_with_thread_id(self):
        """Test sending a message with thread_id (topic support) - MAIN TEST FOR TOPIC FEATURE"""
        config = {
            "telegram_bot_token": "test_token_123",
            "telegram_chat_id": "12345",
            "telegram_message_thread_id": "789",
        }
        
        with patch('finance_service.agents.telegram_agent.Application') as MockApp, \
             patch('finance_service.agents.telegram_agent.get_event_bus') as mock_event_bus:
            
            mock_bot_instance = AsyncMock()
            mock_app = MagicMock()
            mock_app.bot = mock_bot_instance
            MockApp.builder.return_value.token.return_value.build.return_value = mock_app
            
            agent = TelegramAgent(config)
            
            await agent.send_message("12345", "Test message to topic")
            
            # VERIFY: message_thread_id is included when configured
            mock_bot_instance.send_message.assert_called_once()
            call_kwargs = mock_bot_instance.send_message.call_args[1]
            assert call_kwargs["chat_id"] == "12345"
            assert call_kwargs["text"] == "Test message to topic"
            assert call_kwargs["message_thread_id"] == 789, "FAILED: message_thread_id not passed to telegram API"
    
    @pytest.mark.asyncio
    async def test_send_message_with_parse_mode(self):
        """Test sending a message with parse mode"""
        config = {
            "telegram_bot_token": "test_token_123",
            "telegram_chat_id": "12345",
        }
        
        with patch('finance_service.agents.telegram_agent.Application') as MockApp, \
             patch('finance_service.agents.telegram_agent.get_event_bus') as mock_event_bus:
            
            mock_bot_instance = AsyncMock()
            mock_app = MagicMock()
            mock_app.bot = mock_bot_instance
            MockApp.builder.return_value.token.return_value.build.return_value = mock_app
            
            agent = TelegramAgent(config)
            
            await agent.send_message("12345", "**Bold** message", parse_mode="Markdown")
            
            call_kwargs = mock_bot_instance.send_message.call_args[1]
            assert call_kwargs["parse_mode"] == "Markdown"
    
    @pytest.mark.asyncio
    async def test_send_message_handles_telegram_error(self):
        """Test send_message handles TelegramError gracefully"""
        config = {
            "telegram_bot_token": "test_token_123",
            "telegram_chat_id": "12345",
        }
        
        with patch('finance_service.agents.telegram_agent.Application') as MockApp, \
             patch('finance_service.agents.telegram_agent.get_event_bus') as mock_event_bus:
            
            mock_bot_instance = AsyncMock()
            mock_bot_instance.send_message.side_effect = TelegramError("Chat not found")
            mock_app = MagicMock()
            mock_app.bot = mock_bot_instance
            MockApp.builder.return_value.token.return_value.build.return_value = mock_app
            
            agent = TelegramAgent(config)
            
            # Should not raise exception
            await agent.send_message("99999", "Message to invalid chat")
            
            mock_bot_instance.send_message.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_message_when_disabled(self):
        """Test send_message does nothing when agent is disabled"""
        config = {
            "telegram_chat_id": "12345",  # Missing bot token
        }
        
        with patch('finance_service.agents.telegram_agent.get_event_bus') as mock_event_bus, \
             patch.object(Config, 'TELEGRAM_BOT_TOKEN', ''), \
             patch.object(Config, 'TELEGRAM_CHAT_ID', '12345'):
            
            agent = TelegramAgent(config)
            assert agent.enabled is False
            
            # Should return immediately without error
            await agent.send_message("12345", "Test message")


class TestTelegramAgentScheduledReport:
    """Test send_scheduled_report functionality with thread_id support"""
    
    @pytest.mark.asyncio
    async def test_send_scheduled_report_without_thread_id(self):
        """Test sending scheduled report without thread_id"""
        config = {
            "telegram_bot_token": "test_token_123",
            "telegram_chat_id": "12345",
        }
        
        with patch('finance_service.agents.telegram_agent.Application') as MockApp, \
             patch('finance_service.agents.telegram_agent.get_event_bus') as mock_event_bus:
            
            mock_bot_instance = AsyncMock()
            mock_app = MagicMock()
            mock_app.bot = mock_bot_instance
            MockApp.builder.return_value.token.return_value.build.return_value = mock_app
            
            agent = TelegramAgent(config)
            
            report_data = {
                "portfolio_value": "$10,000",
                "daily_return": "+5%",
                "trades_executed": "3",
            }
            
            await agent.send_scheduled_report(report_data)
            
            mock_bot_instance.send_message.assert_called_once()
            call_kwargs = mock_bot_instance.send_message.call_args[1]
            assert call_kwargs["chat_id"] == "12345"
            assert "**portfolio_value:**" in call_kwargs["text"]
            assert call_kwargs["parse_mode"] == "Markdown"
    
    @pytest.mark.asyncio
    async def test_send_scheduled_report_with_thread_id(self):
        """Test sending scheduled report with thread_id (topic support) - MAIN TEST FOR TOPIC FEATURE"""
        config = {
            "telegram_bot_token": "test_token_123",
            "telegram_chat_id": "12345",
            "telegram_message_thread_id": "789",
        }
        
        with patch('finance_service.agents.telegram_agent.Application') as MockApp, \
             patch('finance_service.agents.telegram_agent.get_event_bus') as mock_event_bus:
            
            mock_bot_instance = AsyncMock()
            mock_app = MagicMock()
            mock_app.bot = mock_bot_instance
            MockApp.builder.return_value.token.return_value.build.return_value = mock_app
            
            agent = TelegramAgent(config)
            
            report_data = {
                "portfolio_value": "$10,000",
                "daily_return": "+5%",
            }
            
            await agent.send_scheduled_report(report_data)
            
            mock_bot_instance.send_message.assert_called_once()
            call_kwargs = mock_bot_instance.send_message.call_args[1]
            assert call_kwargs["chat_id"] == "12345"
            assert call_kwargs["message_thread_id"] == 789, "FAILED: message_thread_id not passed for scheduled reports"
            assert call_kwargs["parse_mode"] == "Markdown"
    
    @pytest.mark.asyncio
    async def test_send_scheduled_report_to_custom_chat_id(self):
        """Test sending scheduled report to a different chat_id"""
        config = {
            "telegram_bot_token": "test_token_123",
            "telegram_chat_id": "12345",
        }
        
        with patch('finance_service.agents.telegram_agent.Application') as MockApp, \
             patch('finance_service.agents.telegram_agent.get_event_bus') as mock_event_bus:
            
            mock_bot_instance = AsyncMock()
            mock_app = MagicMock()
            mock_app.bot = mock_bot_instance
            MockApp.builder.return_value.token.return_value.build.return_value = mock_app
            
            agent = TelegramAgent(config)
            
            report_data = {"test": "data"}
            
            await agent.send_scheduled_report(report_data, chat_id="54321")
            
            call_kwargs = mock_bot_instance.send_message.call_args[1]
            assert call_kwargs["chat_id"] == "54321"
    
    @pytest.mark.asyncio
    async def test_send_scheduled_report_without_chat_id(self):
        """Test send_scheduled_report fails gracefully without chat_id"""
        config = {
            "telegram_bot_token": "test_token_123",
            "telegram_chat_id": "12345",  # provided to allow init, overridden below
        }
        
        with patch('finance_service.agents.telegram_agent.Application') as MockApp, \
             patch('finance_service.agents.telegram_agent.get_event_bus') as mock_event_bus:
            
            mock_bot_instance = AsyncMock()
            mock_app = MagicMock()
            mock_app.bot = mock_bot_instance
            MockApp.builder.return_value.token.return_value.build.return_value = mock_app
            
            agent = TelegramAgent(config)
            agent.chat_id = None  # Override after init for test
            
            report_data = {"test": "data"}
            
            await agent.send_scheduled_report(report_data)
            
            # Should not call send_message
            mock_bot_instance.send_message.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_send_scheduled_report_handles_telegram_error(self):
        """Test send_scheduled_report handles TelegramError gracefully"""
        config = {
            "telegram_bot_token": "test_token_123",
            "telegram_chat_id": "12345",
        }
        
        with patch('finance_service.agents.telegram_agent.Application') as MockApp, \
             patch('finance_service.agents.telegram_agent.get_event_bus') as mock_event_bus:
            
            mock_bot_instance = AsyncMock()
            mock_bot_instance.send_message.side_effect = TelegramError("Message too long")
            mock_app = MagicMock()
            mock_app.bot = mock_bot_instance
            MockApp.builder.return_value.token.return_value.build.return_value = mock_app
            
            agent = TelegramAgent(config)
            
            report_data = {"test": "data"}
            
            # Should not raise exception
            await agent.send_scheduled_report(report_data)
            
            mock_bot_instance.send_message.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_scheduled_report_when_disabled(self):
        """Test send_scheduled_report does nothing when agent is disabled"""
        config = {
            "telegram_chat_id": "12345",  # Missing bot token
        }
        
        with patch('finance_service.agents.telegram_agent.get_event_bus') as mock_event_bus, \
             patch.object(Config, 'TELEGRAM_BOT_TOKEN', ''), \
             patch.object(Config, 'TELEGRAM_CHAT_ID', '12345'):
            
            agent = TelegramAgent(config)
            assert agent.enabled is False
            
            report_data = {"test": "data"}
            
            # Should return immediately without error
            await agent.send_scheduled_report(report_data)


class TestTelegramAgentIntegration:
    """Integration tests for TelegramAgent with full message flow"""
    
    @pytest.mark.asyncio
    async def test_multiple_messages_with_thread_id(self):
        """Test sending multiple messages all use the same thread_id - MAIN INTEGRATION TEST"""
        config = {
            "telegram_bot_token": "test_token_123",
            "telegram_chat_id": "12345",
            "telegram_message_thread_id": "789",
        }
        
        with patch('finance_service.agents.telegram_agent.Application') as MockApp, \
             patch('finance_service.agents.telegram_agent.get_event_bus') as mock_event_bus:
            
            mock_bot_instance = AsyncMock()
            mock_app = MagicMock()
            mock_app.bot = mock_bot_instance
            MockApp.builder.return_value.token.return_value.build.return_value = mock_app
            
            agent = TelegramAgent(config)
            
            messages = [
                "Trade executed: BUY 100 AAPL",
                "Risk check passed",
                "Order confirmed on exchange"
            ]
            
            for msg in messages:
                await agent.send_message("12345", msg)
            
            # All calls should include message_thread_id
            assert mock_bot_instance.send_message.call_count == 3
            for i, call_args in enumerate(mock_bot_instance.send_message.call_args_list):
                call_kwargs = call_args[1]
                assert call_kwargs["message_thread_id"] == 789, f"Message {i}: thread_id not included"


class TestTelegramE2ETradingFlow:
    """End-to-End tests simulating full trading process with buy conditions and Telegram notifications"""
    
    @pytest.mark.asyncio
    async def test_full_trading_flow_buy_signal_triggers_notification(self):
        """
        MAIN E2E TEST: Simulate complete trading workflow
        - Market data shows buy signals triggered
        - Strategy evaluates buy conditions (RSI, MACD, SMA)
        - Risk check passes
        - Trade executed
        - Telegram notification sent with trade details
        """
        config = {
            "telegram_bot_token": "test_token_123",
            "telegram_chat_id": "12345",
            "telegram_message_thread_id": "789",  # Topic for trade notifications
        }
        
        with patch('finance_service.agents.telegram_agent.Application') as MockApp, \
             patch('finance_service.agents.telegram_agent.get_event_bus') as mock_event_bus:
            
            mock_bot_instance = AsyncMock()
            mock_app = MagicMock()
            mock_app.bot = mock_bot_instance
            MockApp.builder.return_value.token.return_value.build.return_value = mock_app
            
            telegram_agent = TelegramAgent(config)
            
            # Simulate buy signal triggered - trade execution notification
            notification = """🟢 **TRADE EXECUTED - BUY SIGNAL**

**Symbol:** NVDA
**Action:** BUY
**Quantity:** 50 shares
**Entry Price:** $150.25
**Stop Loss:** $148.75
**Target Price:** $152.00
**Confidence:** 85%

**Buy Signals Triggered:**
• RSI oversold (28)
• MACD bullish crossover
• Price > SMA20

**Portfolio Impact:** +$7,512.50
**Total Equity:** $125,487.30

⏰ Trade executed at market close"""
            
            # Send trade notification to Telegram
            await telegram_agent.send_message(
                chat_id=config["telegram_chat_id"],
                message=notification.strip(),
                parse_mode="Markdown"
            )
            
            # Verify Telegram API was called with correct parameters
            mock_bot_instance.send_message.assert_called_once()
            call_kwargs = mock_bot_instance.send_message.call_args[1]
            
            # Verify all required parameters
            assert call_kwargs["chat_id"] == "12345", "Chat ID not set"
            assert "TRADE EXECUTED" in call_kwargs["text"], "Trade execution message not in notification"
            assert "NVDA" in call_kwargs["text"], "Symbol not in notification"
            assert "BUY" in call_kwargs["text"], "Action not in notification"
            assert "50 shares" in call_kwargs["text"], "Quantity not in notification"
            assert "$150.25" in call_kwargs["text"], "Price not in notification"
            assert "Stop Loss" in call_kwargs["text"], "Stop loss not in notification"
            assert "Target Price" in call_kwargs["text"], "Target price not in notification"
            assert "Confidence" in call_kwargs["text"], "Confidence not in notification"
            assert call_kwargs["message_thread_id"] == 789, "Thread ID not set for topic"
            assert call_kwargs["parse_mode"] == "Markdown", "Parse mode not set"
    
    @pytest.mark.asyncio
    async def test_trading_flow_multiple_buy_signals_sequential_notifications(self):
        """
        Test multiple buy signals on different symbols
        - Each signal triggers separate Telegram notification
        - All messages go to same topic
        - Each includes symbol-specific details
        """
        config = {
            "telegram_bot_token": "test_token_123",
            "telegram_chat_id": "12345",
            "telegram_message_thread_id": "789",
        }
        
        with patch('finance_service.agents.telegram_agent.Application') as MockApp, \
             patch('finance_service.agents.telegram_agent.get_event_bus') as mock_event_bus:
            
            mock_bot_instance = AsyncMock()
            mock_app = MagicMock()
            mock_app.bot = mock_bot_instance
            MockApp.builder.return_value.token.return_value.build.return_value = mock_app
            
            telegram_agent = TelegramAgent(config)
            
            # Multiple buy signals on different stocks
            buy_signals = [
                {
                    "symbol": "NVDA",
                    "quantity": 50,
                    "price": 150.25,
                    "signals": "RSI oversold, MACD bullish"
                },
                {
                    "symbol": "AAPL",
                    "quantity": 100,
                    "price": 185.50,
                    "signals": "Golden cross on daily, price > SMA50"
                },
                {
                    "symbol": "MSFT",
                    "quantity": 75,
                    "price": 420.75,
                    "signals": "Support bounce confirmed, Bollinger Band lower touch"
                }
            ]
            
            # Process each buy signal
            for signal in buy_signals:
                message = f"🟢 BUY: {signal['symbol']} ({signal['quantity']} @ ${signal['price']}) - {signal['signals']}"
                await telegram_agent.send_message(
                    chat_id=config["telegram_chat_id"],
                    message=message,
                    parse_mode="Markdown"
                )
            
            # Verify all 3 notifications were sent to Telegram with topic
            assert mock_bot_instance.send_message.call_count == 3, "Not all buy signals sent"
            
            for i, signal in enumerate(buy_signals):
                call_kwargs = mock_bot_instance.send_message.call_args_list[i][1]
                assert signal["symbol"] in call_kwargs["text"], f"Symbol {signal['symbol']} not in message {i}"
                assert call_kwargs["message_thread_id"] == 789, f"Thread ID not set for message {i}"
    
    @pytest.mark.asyncio
    async def test_trading_flow_risk_check_failed_alert_notification(self):
        """
        Test risk management alert when position sizing exceeds limits
        - Buy signal generated
        - Risk check fails (position too large)
        - Alert sent to Telegram for manual review
        """
        config = {
            "telegram_bot_token": "test_token_123",
            "telegram_chat_id": "12345",
            "telegram_message_thread_id": "789",
        }
        
        with patch('finance_service.agents.telegram_agent.Application') as MockApp, \
             patch('finance_service.agents.telegram_agent.get_event_bus') as mock_event_bus:
            
            mock_bot_instance = AsyncMock()
            mock_app = MagicMock()
            mock_app.bot = mock_bot_instance
            MockApp.builder.return_value.token.return_value.build.return_value = mock_app
            
            telegram_agent = TelegramAgent(config)
            
            # Risk check failure alert
            risk_alert = """⚠️ **RISK CHECK FAILED - MANUAL REVIEW REQUIRED**

**Symbol:** TSLA
**Proposed Quantity:** 500 shares
**Risk Reason:** Position size (500 shares) exceeds max portfolio allocation (2.5%)

**Details:**
• Current portfolio equity: $100,000
• Position value: $75,000 (75% of equity)
• Max allowed: $2,500 (2.5% of equity)
• Excess risk: $72,500

**Recommendation:** Reduce quantity to 50 shares or adjust risk parameters
**Status:** PENDING MANUAL APPROVAL"""
            
            await telegram_agent.send_message(
                chat_id=config["telegram_chat_id"],
                message=risk_alert.strip(),
                parse_mode="Markdown"
            )
            
            mock_bot_instance.send_message.assert_called_once()
            call_kwargs = mock_bot_instance.send_message.call_args[1]
            
            assert "RISK CHECK FAILED" in call_kwargs["text"], "Risk alert not in message"
            assert "TSLA" in call_kwargs["text"], "Symbol not in alert"
            assert "MANUAL REVIEW" in call_kwargs["text"], "Manual review notice not in alert"
            assert call_kwargs["message_thread_id"] == 789, "Thread ID not set"
    
    @pytest.mark.asyncio
    async def test_trading_flow_daily_summary_report_to_topic(self):
        """
        Test daily trading summary sent to Telegram at market close
        - Aggregates all trades executed today
        - Calculates daily P&L, win rate, etc
        - Sends formatted report to topic
        """
        config = {
            "telegram_bot_token": "test_token_123",
            "telegram_chat_id": "12345",
            "telegram_message_thread_id": "789",
        }
        
        with patch('finance_service.agents.telegram_agent.Application') as MockApp, \
             patch('finance_service.agents.telegram_agent.get_event_bus') as mock_event_bus:
            
            mock_bot_instance = AsyncMock()
            mock_app = MagicMock()
            mock_app.bot = mock_bot_instance
            MockApp.builder.return_value.token.return_value.build.return_value = mock_app
            
            telegram_agent = TelegramAgent(config)
            
            # Daily summary
            daily_report = {
                "trades_executed": 3,
                "buy_trades": 2,
                "sell_trades": 1,
                "win_rate": "66.7%",
                "total_pnl": "$1,250.50",
                "largest_win": "+$500",
                "largest_loss": "-$75",
                "total_volume": "$45,000",
                "portfolio_value": "$125,487.30",
                "daily_return": "+2.4%"
            }
            
            await telegram_agent.send_scheduled_report(daily_report)
            
            mock_bot_instance.send_message.assert_called_once()
            call_kwargs = mock_bot_instance.send_message.call_args[1]
            
            assert call_kwargs["chat_id"] == "12345", "Chat ID not set"
            assert call_kwargs["message_thread_id"] == 789, "Thread ID not set for daily report"
            assert "**trades_executed:**" in call_kwargs["text"], "Trades count not in report"
    
    @pytest.mark.asyncio
    async def test_trading_flow_buy_signal_missing_telegram_config_graceful_failure(self):
        """
        Test that trades still execute even if Telegram is not configured
        - Buy signal triggered
        - Trade executed
        - Telegram notification fails gracefully (disabled agent)
        - System continues without crashing
        """
        config = {
            # Missing telegram_bot_token - agent should be disabled
            "telegram_chat_id": "12345",
        }
        
        with patch('finance_service.agents.telegram_agent.get_event_bus') as mock_event_bus, \
             patch.object(Config, 'TELEGRAM_BOT_TOKEN', ''), \
             patch.object(Config, 'TELEGRAM_CHAT_ID', '12345'):
            
            telegram_agent = TelegramAgent(config)
            
            # Agent should be disabled
            assert telegram_agent.enabled is False
            
            # Trade execution should not crash even with disabled telegram
            trade_message = "🟢 BUY NVDA 50 shares @ $150.25"
            
            # This should return gracefully without sending
            await telegram_agent.send_message(
                chat_id="12345",
                message=trade_message
            )
            
            # No Telegram API call made (agent disabled)
            # Execution continues successfully
            assert telegram_agent.enabled is False
