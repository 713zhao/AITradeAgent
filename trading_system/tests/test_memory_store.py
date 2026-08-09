import pytest

from trading_system.memory.store import MemoryStore


def _store(tmp_path):
    return MemoryStore(str(tmp_path / "memory.sqlite"))


def test_log_and_recent_decisions(tmp_path):
    store = _store(tmp_path)
    store.log_decision("AAPL", "BUY", 0.8, 0.1, "trend up", "llm_strategy")
    store.log_decision("AAPL", "HOLD", 0.5, 0.0, "no signal", "llm_strategy")
    recent = store.recent_decisions("AAPL", limit=5)
    assert len(recent) == 2
    assert recent[0].action == "HOLD"  # most recent first


def test_win_rate_summary_with_no_history(tmp_path):
    store = _store(tmp_path)
    summary = store.win_rate_summary("AAPL")
    assert "No resolved trade history" in summary


def test_backfill_outcome_attaches_to_latest_executed_buy(tmp_path):
    store = _store(tmp_path)
    decision_id = store.log_decision("AAPL", "BUY", 0.8, 0.1, "trend up", "llm_strategy")
    store.mark_executed(decision_id)
    store.backfill_outcome_for_symbol("AAPL", 123.45)

    recent = store.recent_decisions("AAPL", limit=1)
    assert recent[0].outcome_pnl == pytest.approx(123.45)
    assert "1/1 profitable" in store.win_rate_summary("AAPL")


def test_backfill_ignores_unexecuted_decisions(tmp_path):
    store = _store(tmp_path)
    store.log_decision("AAPL", "BUY", 0.8, 0.1, "trend up", "llm_strategy")  # never executed
    store.backfill_outcome_for_symbol("AAPL", 50.0)
    recent = store.recent_decisions("AAPL", limit=1)
    assert recent[0].outcome_pnl is None


def test_lessons_round_trip(tmp_path):
    store = _store(tmp_path)
    store.add_lesson("Avoid chasing RSI > 75 buys", scope="global")
    store.add_lesson("SMA50 breaks are a reliable exit", scope="global")
    lessons = store.recent_lessons(scope="global", limit=5)
    assert len(lessons) == 2
    assert lessons[0] == "SMA50 breaks are a reliable exit"  # most recent first


def test_cooldown_persists_across_store_instances(tmp_path):
    db_path = str(tmp_path / "memory.sqlite")
    store1 = MemoryStore(db_path)
    from datetime import datetime, timedelta, timezone
    until = datetime.now(timezone.utc) + timedelta(minutes=30)
    store1.set_cooldown("AAPL", until)

    store2 = MemoryStore(db_path)
    recovered = store2.cooldown_until("AAPL")
    assert recovered is not None
    assert abs((recovered - until).total_seconds()) < 1


def test_unresolved_decisions_since_only_returns_resolved(tmp_path):
    store = _store(tmp_path)
    id1 = store.log_decision("AAPL", "BUY", 0.8, 0.1, "x", "llm_strategy")
    store.mark_executed(id1)
    id2 = store.log_decision("MSFT", "BUY", 0.7, 0.1, "y", "llm_strategy")
    store.mark_executed(id2)

    assert store.unresolved_decisions_since(0) == []

    store.backfill_outcome_for_symbol("AAPL", 10.0)
    resolved = store.unresolved_decisions_since(0)
    assert len(resolved) == 1
    assert resolved[0].symbol == "AAPL"
