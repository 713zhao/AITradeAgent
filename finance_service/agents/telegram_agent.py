"""Telegram Agent - Handles Telegram commands and sends reports (PTB v22 compatible)."""
import asyncio
import logging
from typing import Dict, Any, Optional
from telegram import Bot
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.event_bus import Event, Events, get_event_bus
from finance_service.core.config import Config

logger = logging.getLogger(__name__)

class TelegramAgent(Agent):
    """Telegram Agent - Provides Telegram interface and scheduled reports."""

    @property
    def agent_id(self) -> str:
        return "telegram_agent"

    @property
    def goal(self) -> str:
        return "Provide a Telegram interface for interacting with the trading system and delivering scheduled reports."

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.event_bus = get_event_bus()
        self.bot_token = config.get("telegram_bot_token", Config.TELEGRAM_BOT_TOKEN)
        self.chat_id = config.get("telegram_chat_id", Config.TELEGRAM_CHAT_ID)

        raw_thread_id = config.get("telegram_message_thread_id", Config.TELEGRAM_MESSAGE_THREAD_ID)
        self.thread_id = int(str(raw_thread_id).strip()) if raw_thread_id is not None and str(raw_thread_id).strip() != "" else None

        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram Agent not fully configured (missing token or chat ID). Disabling.")
            self.enabled = False
            self.application = None
            self.bot = None
        else:
            self.enabled = True
            try:
                # Build Application
                self.application = Application.builder().token(self.bot_token).build()
                self.bot = self.application.bot

                # Register command handlers
                self.application.add_handler(CommandHandler("start", self._start_command))
                self.application.add_handler(CommandHandler("status", self._status_command))
                self.application.add_handler(CommandHandler("portfolio", self._portfolio_command))
                # Add more handlers as needed

            except Exception as e:
                logger.error(f"Failed to initialize Telegram Bot: {e}")
                self.enabled = False
                self.application = None
                self.bot = None

    async def run(self):
        """Start Telegram bot polling without blocking the running asyncio event loop.

        python-telegram-bot v20+ provides run_polling() which internally calls
        loop.run_until_complete() — incompatible with an already-running loop
        (e.g. Hypercorn). We use the lower-level coroutines instead:
        initialize → updater.start_polling → application.start, then hold
        until the application signals it should stop.
        """
        if not self.enabled or not self.application:
            logger.info("Telegram Agent is disabled or not properly initialized.")
            return
        logger.info(f"{self.agent_id} starting polling (non-blocking mode).")
        try:
            await self.application.initialize()
            await self.application.updater.start_polling(drop_pending_updates=True)
            await self.application.start()
            logger.info(f"{self.agent_id} polling started successfully.")
            # Keep running as long as the updater is polling
            while self.application.updater.running:
                await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"{self.agent_id} polling error: {e}")
        finally:
            try:
                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
            except Exception:
                pass
            logger.info(f"{self.agent_id} polling stopped.")

    async def send_message(self, chat_id: str, message: str, parse_mode: Optional[str] = None):
        if not self.enabled or not self.bot:
            return
        try:
            kwargs = {"chat_id": chat_id, "text": message}
            if parse_mode:
                kwargs["parse_mode"] = parse_mode
            if self.thread_id is not None:
                kwargs["message_thread_id"] = self.thread_id
            await self.bot.send_message(**kwargs)
            logger.info(f"Message sent to chat ID: {chat_id}")
        except TelegramError as e:
            logger.error(f"Failed to send message to {chat_id}: {e}")

    async def _start_command(self, update: Any, context: ContextTypes.DEFAULT_TYPE):
        if not self.enabled:
            return
        chat_id = update.effective_chat.id
        user = update.effective_user.mention_html()
        logger.info(f"Telegram Agent received /start command from {user} ({chat_id})")
        await self.send_message(chat_id, f"Hello {user}! I am your AI Trade Agent. How can I assist you?", parse_mode="HTML")

    async def _status_command(self, update: Any, context: ContextTypes.DEFAULT_TYPE):
        if not self.enabled:
            return
        chat_id = update.effective_chat.id
        logger.info(f"Telegram Agent received /status command from chat_id: {chat_id}")
        await self.event_bus.publish(Event(event_type=Events.GET_SYSTEM_STATUS, data={"chat_id": chat_id}))
        await self.send_message(chat_id, "Fetching system status...")

    async def _portfolio_command(self, update: Any, context: ContextTypes.DEFAULT_TYPE):
        if not self.enabled:
            return
        chat_id = update.effective_chat.id
        logger.info(f"Telegram Agent received /portfolio command from chat_id: {chat_id}")
        await self.event_bus.publish(Event(event_type=Events.GET_PORTFOLIO_STATE, data={"chat_id": chat_id}))
        await self.send_message(chat_id, "Fetching portfolio state...")

    async def send_pre_execution_notification(
        self,
        symbol: str,
        action: str,
        quantity: float,
        target_price,
        stop_loss_price,
        confidence: float,
        rationale,
        indicators_snapshot=None,
        news_sentiment=None,
        news_catalysts=None,
        chat_id=None,
        company_name: str = None,
        portfolio_cash: float = None,
        portfolio_equity: float = None,
    ):
        """Send a Telegram notification before a trade is executed, with full technical detail."""
        if not self.enabled or not self.bot:
            return
        target_chat_id = chat_id if chat_id else self.chat_id
        if not target_chat_id:
            return

        action_emoji = "🟢 BUY" if action == "BUY" else "🔴 SELL"
        yf_symbol = symbol.replace(".", "-") if "." in symbol else symbol
        link = f"https://finance.yahoo.com/quote/{yf_symbol}"

        price_str = f"${target_price:.4f}" if target_price else "market"
        conf_str = f"{confidence * 100:.1f}%"

        # Build stop-loss line with ATR context
        if stop_loss_price and target_price:
            sl_pct = ((stop_loss_price - target_price) / target_price) * 100
            stop_str = f"${stop_loss_price:.4f} ({sl_pct:+.1f}%)"
        elif stop_loss_price:
            stop_str = f"${stop_loss_price:.4f}"
        else:
            stop_str = "N/A"

        # ── Technical Indicators ──────────────────────────────────────────
        tech_lines = []
        if indicators_snapshot is not None:
            snap = indicators_snapshot
            ind = getattr(snap, "indicators", {})
            current_price = getattr(snap, "current_price", None) or target_price

            def _v(key):
                r = ind.get(key)
                return r.value if r else None

            def _meta(key):
                r = ind.get(key)
                return (r.metadata or {}) if r else {}

            def _sig(key):
                r = ind.get(key)
                if r is None:
                    return ""
                sig = r.signal
                sig_val = sig.value if hasattr(sig, "value") else str(sig)
                return sig_val

            # RSI
            rsi_val = _v("rsi")
            if rsi_val is not None:
                rsi_sig = _sig("rsi")
                rsi_icon = "✅" if rsi_val < 35 else ("⚠️" if rsi_val > 70 else "–")
                tech_lines.append(f"  • RSI (14): {rsi_val:.1f} — {rsi_sig} {rsi_icon}")

            # MACD
            macd_val = _v("macd")
            macd_meta = _meta("macd")
            if macd_val is not None:
                signal_line = macd_meta.get("signal_line")
                histogram = macd_meta.get("histogram")
                hist_icon = "📈" if histogram and histogram > 0 else ("📉" if histogram else "")
                hist_str = f" | Hist: {histogram:+.4f} {hist_icon}" if histogram is not None else ""
                sig_str = f" | Signal: {signal_line:.4f}" if signal_line is not None else ""
                tech_lines.append(f"  • MACD: {macd_val:.4f}{sig_str}{hist_str}")

            # SMA 20 / 50 / 200
            for period, key in [(20, "sma_20"), (50, "sma_50"), (200, "sma_200")]:
                sma_val = _v(key)
                if sma_val is not None and current_price:
                    diff_pct = ((current_price - sma_val) / sma_val) * 100
                    icon = "✅" if diff_pct > 0 else "⚠️"
                    tech_lines.append(f"  • SMA{period}: ${sma_val:.4f} → Price {diff_pct:+.1f}% {icon}")

            # ATR
            atr_val = _v("atr")
            if atr_val is not None and current_price:
                atr_pct = (atr_val / current_price) * 100
                stop_atr = stop_loss_price
                atr_note = f" (stop = {2}×ATR = ${stop_atr:.4f})" if stop_atr else ""
                tech_lines.append(f"  • ATR (14): ${atr_val:.4f} ({atr_pct:.1f}% of price){atr_note}")

            # Stochastic
            stoch_val = _v("stoch")
            stoch_meta = _meta("stoch")
            if stoch_val is not None:
                d_pct = stoch_meta.get("d_percent")
                stoch_icon = "✅" if stoch_val < 20 else ("⚠️" if stoch_val > 80 else "–")
                d_str = f" / %D: {d_pct:.1f}" if d_pct is not None else ""
                stoch_sig = _sig("stoch")
                tech_lines.append(f"  • Stoch %K: {stoch_val:.1f}{d_str} — {stoch_sig} {stoch_icon}")

            # Bollinger Bands
            bb_meta = _meta("bb")
            if bb_meta:
                bb_upper = bb_meta.get("upper")
                bb_lower = bb_meta.get("lower")
                if bb_upper and bb_lower and current_price:
                    bb_width = bb_upper - bb_lower
                    bb_pos_pct = ((current_price - bb_lower) / bb_width * 100) if bb_width else None
                    if bb_pos_pct is not None:
                        pos_str = f"{bb_pos_pct:.0f}% from lower"
                        bb_icon = "✅" if bb_pos_pct < 20 else ("⚠️" if bb_pos_pct > 80 else "–")
                        tech_lines.append(f"  • BB: ${bb_lower:.4f}–${bb_upper:.4f} | {pos_str} {bb_icon}")

            # Regime Score
            regime_val = _v("regime_score")
            if regime_val is not None:
                regime_sig = _sig("regime_score")
                tech_lines.append(f"  • Regime Score: {regime_val:.2f} — {regime_sig}")

        # ── News ─────────────────────────────────────────────────────────
        news_lines = []
        if news_sentiment is not None:
            sent_icon = "📈" if news_sentiment >= 0.3 else ("📉" if news_sentiment <= -0.3 else "➡️")
            sent_label = "Bullish" if news_sentiment >= 0.3 else ("Bearish" if news_sentiment <= -0.3 else "Neutral")
            news_lines.append(f"  {sent_icon} Sentiment: {sent_label} ({news_sentiment:+.2f})")
        if news_catalysts:
            cats = ", ".join(news_catalysts[:3])
            news_lines.append(f"  🗞 Catalysts: {cats}")

        # ── Entry Rationale ───────────────────────────────────────────────
        reasons = "\n".join(f"  • {r}" for r in rationale) if rationale else "  • N/A"

        # ── Assemble message ─────────────────────────────────────────────
        # Company name display
        name_str = f" — {company_name}" if company_name and company_name != symbol else ""
        # Portfolio context
        portfolio_line = None
        if portfolio_equity is not None:
            if portfolio_cash is not None:
                pos_val = portfolio_equity - portfolio_cash
                portfolio_line = f"  Cash: ${portfolio_cash:,.2f}  |  Positions: ${pos_val:,.2f}  |  Equity: ${portfolio_equity:,.2f}"
            else:
                portfolio_line = f"  Equity: ${portfolio_equity:,.2f}"

        lines = [
            f"⚡ *Trade About to Execute*",
            "",
            f"*Symbol:* [{symbol}]({link}){name_str}",
            f"*Action:* {action_emoji}",
            f"*Quantity:* {quantity:.4f} shares",
            f"*Entry Price:* {price_str}",
            f"*Stop Loss:* {stop_str}",
            f"*Confidence:* {conf_str}",
        ]
        if portfolio_line:
            lines += [f"*Portfolio:* {portfolio_line}"]

        if tech_lines:
            lines += ["", "📊 *Technical Indicators:*"] + tech_lines

        if news_lines:
            lines += ["", "📰 *News:*"] + news_lines

        lines += ["", "📋 *Reason to Buy:*", reasons]

        message = "\n".join(lines)

        try:
            kwargs = {
                "chat_id": target_chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            }
            if self.thread_id is not None:
                kwargs["message_thread_id"] = self.thread_id
            await self.bot.send_message(**kwargs)
            logger.info(f"Pre-execution notification sent for {symbol} {action}")
        except TelegramError as e:
            logger.error(f"Failed to send pre-execution notification: {e}")

    async def send_scheduled_report(self, report_data: Dict[str, Any], chat_id: Optional[str] = None):
        if not self.enabled or not self.bot:
            return
        target_chat_id = chat_id if chat_id else self.chat_id
        if not target_chat_id:
            logger.error("Cannot send scheduled report: No chat_id provided or configured.")
            return

        message_text = f"**Daily Report**\n\n"
        for key, value in report_data.items():
            message_text += f"**{key}:** {value}\n"

        try:
            kwargs = {"chat_id": target_chat_id, "text": message_text, "parse_mode": "Markdown"}
            if self.thread_id is not None:
                kwargs["message_thread_id"] = self.thread_id
            await self.bot.send_message(**kwargs)
            logger.info(f"Scheduled report sent to chat ID: {target_chat_id}")
        except TelegramError as e:
            logger.error(f"Failed to send scheduled report to {target_chat_id}: {e}")
