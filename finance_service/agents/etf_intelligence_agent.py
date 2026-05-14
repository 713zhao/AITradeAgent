"""Layer 4 ETF Intelligence Agent.

Provides four core capabilities:
  1. run_daily_snapshot()     — Fetch and store price/metrics for 200+ ETFs
  2. run_sector_rotation_analysis() — AI-driven weekly top-sector ETF picks
  3. run_hedge_analysis()     — Detect portfolio concentration and suggest hedges
  4. run_correlation_scan()   — Find low-corr ETFs to improve diversification
"""
import asyncio
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.ml.etf_models import (
    ETFRecommendation,
    ETFSnapshot,
    insert_etf_recommendation,
    insert_etf_snapshot,
    query_etf_snapshot_history,
    query_etf_snapshots,
)
from finance_service.ml.etf_universe import (
    CORRELATION_SCAN_SYMBOLS,
    HEDGE_ETF_SYMBOLS,
    get_etf_by_category,
    get_etf_metadata,
    get_sector_etfs,
)
from finance_service.storage.database import get_portfolio_db

logger = logging.getLogger(__name__)

_BATCH_SIZE = 50
_GEMINI_MODEL = "gemini-2.5-pro-exp-05-21"


class ETFIntelligenceAgent(Agent):
    """Layer 4: AI-driven ETF Monitoring & Recommendations."""

    @property
    def agent_id(self) -> str:
        return "etf_intelligence_agent"

    @property
    def goal(self) -> str:
        return "Monitor 200+ ETFs daily; deliver AI-powered sector rotation, hedge, and correlation recommendations via Gemini and Telegram."

    def __init__(self, config_engine):
        self.config_engine = config_engine
        self.telegram_agent = None
        self.hedge_threshold: float = float(
            config_engine.get("finance", "etf_intelligence/hedge_threshold", default=0.50)
        )
        self.gemini_client = None
        self._init_gemini_client()

    # ── Agent interface ────────────────────────────────────────────────────────

    async def run(self, payload: Dict = None) -> AgentReport:
        count = await self.run_daily_snapshot()
        return AgentReport(
            agent_id=self.agent_id,
            status="success",
            message=f"ETF snapshot complete: {count} symbols saved",
            payload={"snapshot_count": count},
        )

    # ── Public async API ───────────────────────────────────────────────────────

    async def run_daily_snapshot(self, symbols_override: Optional[List[str]] = None) -> int:
        """Fetch and store ETF metrics. Returns number of symbols saved."""
        from finance_service.ml.etf_universe import get_all_etf_symbols
        symbols = symbols_override or get_all_etf_symbols()
        db = self._get_db()
        total_saved = 0
        for i in range(0, len(symbols), _BATCH_SIZE):
            batch = symbols[i : i + _BATCH_SIZE]
            try:
                snapshots = await asyncio.to_thread(self._fetch_etf_batch_sync, batch)
                for snap in snapshots:
                    if insert_etf_snapshot(db, snap):
                        total_saved += 1
            except Exception as exc:
                logger.error(f"ETF snapshot batch error ({batch[:3]}...): {exc}")
        logger.info(f"ETF snapshot: saved {total_saved}/{len(symbols)} symbols")
        return total_saved

    async def run_sector_rotation_analysis(self) -> List[ETFRecommendation]:
        """Weekly: identify best sector ETFs using Layer 2 patterns + Gemini."""
        try:
            db = self._get_db()
            today = datetime.utcnow().strftime("%Y-%m-%d")
            sector_syms = [s for syms in get_sector_etfs().values() for s in syms]
            snapshots = query_etf_snapshots(db, sector_syms, today)

            layer2_summary = self._load_layer2_summary(db)
            snapshot_table = self._format_snapshot_table(snapshots)
            prompt_tmpl = self._load_prompt("etf_sector_rotation")
            prompt = prompt_tmpl.replace("{LAYER2_PATTERN_SUMMARY}", layer2_summary)
            prompt = prompt.replace("{ETF_SNAPSHOT_TABLE}", snapshot_table)
            prompt = prompt.replace("{MARKET_CONTEXT}", f"Date: {today}")

            llm_text = await self._call_gemini_for_etf(prompt)
            recs = self._parse_etf_recommendations(llm_text, "sector_rotation", today, snapshots)

            for rec in recs:
                insert_etf_recommendation(db, rec)

            if recs and self.telegram_agent:
                msg = self._format_sector_rotation_message(recs)
                await self.telegram_agent.send_message(msg)

            return recs
        except Exception as exc:
            logger.error(f"Sector rotation analysis failed: {exc}")
            return []

    async def run_hedge_analysis(self) -> List[ETFRecommendation]:
        """Daily: if sector concentration > threshold, suggest hedge ETFs."""
        try:
            positions = self._get_portfolio_positions()
            if not positions:
                return []

            sector_weights = self._calculate_sector_weights(positions)
            if not sector_weights:
                return []

            max_weight = max(sector_weights.values())
            if max_weight <= self.hedge_threshold:
                return []

            db = self._get_db()
            today = datetime.utcnow().strftime("%Y-%m-%d")
            snapshots = query_etf_snapshots(db, HEDGE_ETF_SYMBOLS, today)

            prompt_tmpl = self._load_prompt("etf_hedge_analysis")
            prompt = prompt_tmpl.replace("{PORTFOLIO_SECTOR_WEIGHTS}", self._format_sector_weights(sector_weights))
            prompt = prompt.replace("{HEDGE_ETF_METRICS}", self._format_snapshot_table(snapshots))
            prompt = prompt.replace("{CONCENTRATION_THRESHOLD}", f"{self.hedge_threshold:.0%}")

            llm_text = await self._call_gemini_for_etf(prompt)
            recs = self._parse_etf_recommendations(llm_text, "hedge", today, snapshots)

            for rec in recs:
                insert_etf_recommendation(db, rec)

            if recs and self.telegram_agent:
                msg = self._format_hedge_message(recs, sector_weights)
                await self.telegram_agent.send_message(msg)

            return recs
        except Exception as exc:
            logger.error(f"Hedge analysis failed: {exc}")
            return []

    async def run_correlation_scan(self, symbols_override: Optional[List[str]] = None) -> List[ETFRecommendation]:
        """Weekly: find ETFs with low correlation to portfolio for diversification."""
        try:
            symbols = symbols_override or CORRELATION_SCAN_SYMBOLS
            portfolio_returns = self._get_portfolio_return_history()
            if not portfolio_returns:
                return []

            db = self._get_db()
            today = datetime.utcnow().strftime("%Y-%m-%d")

            corr_table_rows = []
            for sym in symbols:
                history = query_etf_snapshot_history(db, sym, days=60)
                if len(history) < 5:
                    continue
                prices = [h["price"] for h in history if h.get("price", 0) > 0]
                if len(prices) < 5:
                    continue
                etf_returns = self._prices_to_returns(prices)
                corr = self._pearson_correlation(portfolio_returns, etf_returns)
                meta = get_etf_metadata(sym)
                corr_table_rows.append(
                    f"| {sym} | {meta['sector']} | {corr:+.3f} | {prices[-1]:.2f} |"
                )

            if not corr_table_rows:
                return []

            corr_table = "| Symbol | Sector | Corr | Price |\n|--------|--------|------|-------|\n" + "\n".join(corr_table_rows)
            prompt_tmpl = self._load_prompt("etf_correlation_scan")
            prompt = prompt_tmpl.replace("{PORTFOLIO_RETURN_SUMMARY}", f"Portfolio daily returns: {len(portfolio_returns)} data points")
            prompt = prompt.replace("{ETF_CORRELATION_TABLE}", corr_table)

            llm_text = await self._call_gemini_for_etf(prompt)
            recs = self._parse_etf_recommendations(llm_text, "correlation", today, [])

            for rec in recs:
                insert_etf_recommendation(db, rec)

            if recs and self.telegram_agent:
                msg = self._format_correlation_message(recs)
                await self.telegram_agent.send_message(msg)

            return recs
        except Exception as exc:
            logger.error(f"Correlation scan failed: {exc}")
            return []

    # ── Private helpers ────────────────────────────────────────────────────────

    def _init_gemini_client(self):
        api_key = os.getenv("GOOGLE_API_KEY", "")
        if api_key:
            try:
                import google.generativeai as genai
                self.gemini_client = genai.Client(api_key=api_key)
            except ImportError:
                pass

    def _get_db(self):
        return get_portfolio_db()

    def _get_portfolio_positions(self) -> List[Dict]:
        try:
            db = self._get_db()
            cursor = db.connection.execute(
                "SELECT symbol, current_value FROM positions WHERE status='open'"
            )
            return [dict(row) for row in cursor.fetchall()]
        except Exception:
            return []

    def _get_portfolio_return_history(self) -> List[float]:
        try:
            db = self._get_db()
            cursor = db.connection.execute(
                """SELECT daily_return FROM portfolio_snapshots
                   ORDER BY snapshot_date DESC LIMIT 60"""
            )
            rows = [row[0] for row in cursor.fetchall() if row[0] is not None]
            return list(reversed(rows))
        except Exception:
            return []

    def _fetch_etf_batch_sync(self, symbols: List[str]) -> List[ETFSnapshot]:
        import yfinance as yf
        snapshots = []
        today = datetime.utcnow().strftime("%Y-%m-%d")
        try:
            df = yf.download(symbols, period="60d", group_by="ticker",
                             auto_adjust=True, progress=False, threads=True)
            if df.empty:
                return []
            for sym in symbols:
                try:
                    close = df["Close"][sym].dropna() if len(symbols) > 1 else df["Close"].dropna()
                    vol = df["Volume"][sym].dropna() if len(symbols) > 1 else df["Volume"].dropna()
                    if len(close) < 2:
                        continue
                    price = float(close.iloc[-1])
                    volume = int(vol.iloc[-1]) if len(vol) > 0 else 0
                    momentum_20d = float((close.iloc[-1] / close.iloc[-21]) - 1) if len(close) >= 21 else 0.0
                    volatility_20d = float(close.pct_change().rolling(20).std().iloc[-1]) if len(close) >= 20 else 0.0
                    info = {}
                    try:
                        info = yf.Ticker(sym).info or {}
                    except Exception:
                        pass
                    meta = get_etf_metadata(sym)
                    snap = ETFSnapshot(
                        etf_symbol=sym, date=today, price=price, volume=volume,
                        momentum_20d=momentum_20d, volatility_20d=volatility_20d,
                        ytd_return=float(info.get("ytdReturn", 0) or 0),
                        dividend_yield=float(info.get("trailingAnnualDividendYield", 0) or 0),
                        aum=float(info.get("totalAssets", 0) or 0),
                        sector=meta["sector"], asset_class=meta["asset_class"],
                    )
                    snapshots.append(snap)
                except Exception as e:
                    logger.debug(f"ETF fetch skip {sym}: {e}")
        except Exception as e:
            logger.error(f"yfinance batch download failed: {e}")
        return snapshots

    async def _call_gemini_for_etf(self, prompt: str, timeout: float = 30.0) -> str:
        if not self.gemini_client:
            return ""
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self.gemini_client.models.generate_content,
                    model=_GEMINI_MODEL,
                    contents=prompt,
                ),
                timeout=timeout,
            )
            return response.text or ""
        except Exception as exc:
            logger.error(f"Gemini ETF call failed: {exc}")
            return ""

    def _parse_json_response(self, text: str) -> List[Dict]:
        if not text:
            return []
        try:
            return json.loads(text)
        except Exception:
            pass
        # Try to extract JSON array from surrounding prose
        m = re.search(r'\[.*?\]', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
        # Try single object
        m = re.search(r'\{.*?\}', text, re.DOTALL)
        if m:
            try:
                return [json.loads(m.group())]
            except Exception:
                pass
        return []

    def _parse_etf_recommendations(
        self, llm_text: str, rec_type: str, date: str, snapshots: List[Dict],
    ) -> List[ETFRecommendation]:
        items = self._parse_json_response(llm_text)
        recs = []
        snap_by_sym = {s["etf_symbol"]: s for s in snapshots}
        for item in items[:5]:
            try:
                sym = str(item.get("symbol", item.get("etf_symbol", ""))).upper()
                if not sym:
                    continue
                snap = snap_by_sym.get(sym, {})
                rec = ETFRecommendation(
                    recommendation_date=date,
                    etf_symbol=sym,
                    recommendation_type=rec_type,
                    confidence=float(item.get("confidence", 0)),
                    reason=str(item.get("reason", "")),
                    sector=str(item.get("sector", snap.get("sector", "Unknown"))),
                    correlation_to_portfolio=float(item.get("correlation", 0)),
                    suggested_allocation_pct=float(item.get("allocation_pct", item.get("weight_pct", 0))),
                    win_probability_estimate=float(item.get("win_probability", 0)),
                    llm_response=item,
                )
                recs.append(rec)
            except Exception as e:
                logger.debug(f"Skipping rec item {item}: {e}")
        return recs

    def _calculate_sector_weights(self, positions: List[Dict]) -> Dict[str, float]:
        total = sum(float(p.get("current_value", 0)) for p in positions)
        if total <= 0:
            return {}
        sector_vals: Dict[str, float] = {}
        for p in positions:
            meta = get_etf_metadata(str(p.get("symbol", "")))
            sector = meta["sector"]
            sector_vals[sector] = sector_vals.get(sector, 0) + float(p.get("current_value", 0))
        return {s: v / total for s, v in sector_vals.items()}

    def _prices_to_returns(self, prices: List[float]) -> List[float]:
        if len(prices) < 2:
            return []
        return [(prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))]

    def _pearson_correlation(self, a: List[float], b: List[float]) -> float:
        n = min(len(a), len(b))
        if n < 3:
            return 0.0
        a, b = a[-n:], b[-n:]
        try:
            import numpy as np
            corr = np.corrcoef(a, b)[0, 1]
            return float(corr) if not np.isnan(corr) else 0.0
        except Exception:
            return 0.0

    def _load_layer2_summary(self, db) -> str:
        try:
            cursor = db.connection.execute(
                """SELECT pattern_name, win_rate, avg_return, pattern_count
                   FROM trade_analysis_layer2
                   WHERE analysis_date >= date('now', '-30 days')
                   ORDER BY win_rate DESC LIMIT 10"""
            )
            rows = cursor.fetchall()
            if not rows:
                return "No Layer 2 pattern data available."
            lines = ["Pattern | Win Rate | Avg Return | Count"]
            for r in rows:
                lines.append(f"{r[0]} | {r[1]:.1%} | {r[2]:.2%} | {r[3]}")
            return "\n".join(lines)
        except Exception:
            return "Layer 2 data unavailable."

    def _load_prompt(self, template_name: str) -> str:
        prompt_path = Path(__file__).parent.parent / "prompts" / f"{template_name}.md"
        if prompt_path.exists():
            return prompt_path.read_text()
        return f"Analyze ETF data and return JSON recommendations for {template_name}."

    def _format_snapshot_table(self, snapshots: List[Dict]) -> str:
        if not snapshots:
            return "No snapshot data available."
        header = "| Symbol | Sector | Price | Mom20d | Vol20d | YTD | AUM(B) |"
        sep    = "|--------|--------|-------|--------|--------|-----|--------|"
        rows = []
        for s in snapshots:
            rows.append(
                f"| {s.get('etf_symbol','')} "
                f"| {s.get('sector','')[:12]} "
                f"| {s.get('price',0):.2f} "
                f"| {s.get('momentum_20d',0):+.1%} "
                f"| {s.get('volatility_20d',0):.2%} "
                f"| {s.get('ytd_return',0):+.1%} "
                f"| {s.get('aum',0)/1e9:.1f} |"
            )
        return "\n".join([header, sep] + rows)

    def _format_sector_weights(self, weights: Dict[str, float]) -> str:
        if not weights:
            return "No sector data available."
        return "\n".join(
            f"  {sector}: {pct:.0%}" for sector, pct in sorted(weights.items(), key=lambda x: -x[1])
        )

    def _format_sector_rotation_message(self, recs: List[ETFRecommendation]) -> str:
        lines = ["📊 *Layer 4 — Sector Rotation Picks*\n"]
        for i, rec in enumerate(recs, 1):
            conf_pct = f"{rec.confidence:.0%}" if rec.confidence <= 1 else f"{rec.confidence:.1f}"
            lines.append(
                f"{i}. *{rec.etf_symbol}* ({rec.sector})\n"
                f"   Confidence: {conf_pct}  Alloc: {rec.suggested_allocation_pct:.0f}%\n"
                f"   {rec.reason}"
            )
        return "\n".join(lines)

    def _format_hedge_message(self, recs: List[ETFRecommendation], sector_weights: Dict[str, float]) -> str:
        top_sector = max(sector_weights, key=sector_weights.get) if sector_weights else "Unknown"
        top_pct = sector_weights.get(top_sector, 0)
        lines = [
            f"🛡️ *Layer 4 — Hedge Alert*",
            f"Portfolio concentration: {top_sector} {top_pct:.0%}\n",
        ]
        for i, rec in enumerate(recs, 1):
            lines.append(
                f"{i}. *{rec.etf_symbol}* ({rec.sector})\n"
                f"   Alloc: {rec.suggested_allocation_pct:.0f}%  Conf: {rec.confidence:.0%}\n"
                f"   {rec.reason}"
            )
        return "\n".join(lines)

    def _format_correlation_message(self, recs: List[ETFRecommendation]) -> str:
        lines = ["🔗 *Layer 4 — Diversification Scan*\n"]
        for i, rec in enumerate(recs, 1):
            lines.append(
                f"{i}. *{rec.etf_symbol}* corr={rec.correlation_to_portfolio:+.2f}\n"
                f"   Alloc: {rec.suggested_allocation_pct:.0f}%  Conf: {rec.confidence:.0%}\n"
                f"   {rec.reason}"
            )
        return "\n".join(lines)
