# MVP Gap Analysis: mvp.md vs. Actual Code

## Summary

mvp.md promised a 4-week plan. Implementation covers about 60% of promised features. Below are each gap and its severity.

---

## Features Not Implemented

### 1. Database (SQLite/Postgres)
- **mvp.md:** "SQLite / Postgres, append-only logs"
- **Implementation:** JSONL files (`events_log.jsonl`, `odds_log.jsonl`, `decisions.jsonl`)
- **Severity:** HIGH — no ACID compliance, no query capability, no atomic backup

### 2. Rolling windows (1min, 5min, 10min)
- **mvp.md:** "1 min delta, 5 min mean, 10 min mean"
- **Implementation:** Only 10min xG lookback (O(N) per tick)
- **Severity:** MEDIUM — trend and delta features completely missing

### 3. Extra Features (possession_5m, box_shots_10m)
- **mvp.md:** "live_xG_10m, box_shots_10m, dangerous_attacks_10m, possession_5m, cards/red, score + minute"
- **Implementation:** Only xG and danger_attack count in TPS. box_shots and possession missing.
- **Severity:** MEDIUM — TPS heuristic is poorer than planned

### 4. Dashboard
- **mvp.md:** "Live match panel: minute/score, event latency p95, TPS_label, xG_10m, last decision + reason_code"
- **Implementation:** No dashboard. Console output only.
- **Severity:** LOW — does not affect logic, but complicates monitoring

### 5. Modular Directory Structure
- **mvp.md:** "ingest/, state/, features/, decision/, execution_stub/, replay/, logging/, dashboard/"
- **Implementation:** Flat structure, all .py files in root
- **Severity:** LOW — works for MVP, but scales poorly

### 6. Separate decision.py
- **mvp.md:** "Create `decision.py` containing Gate logic"
- **Implementation:** Decision logic is in `engine.py` (`evaluate_gates`)
- **Severity:** LOW — functionally same, only naming difference

### 7. Trend (Rising/Falling)
- **mvp.md:** "trend (rising / falling)" in TPS output
- **Implementation:** No rolling deltas, no trend calculation
- **Severity:** MEDIUM — cannot see pressure direction, only current value

### 8. Market Suspension - Gate Missing as Independent
- **mvp.md:** "Market Suspended == True → NO BET" as a separate hard gate
- **Implementation:** Checked in `engine.evaluate_gates`, but `MockProvider` does not generate suspension situations realistically
- **Severity:** LOW — gate is in code, but untested

### 9. Slippage Penalty in Backtest
- **mvp.md:** "Automatically deduct 0.05 from every odd"
- **Implementation:** `ExecutionStub` uses `random.uniform` based slippage, not fixed 0.05 penalty
- **Severity:** LOW — implementation is actually more realistic than plan

### 10. Real Data Adapter
- **mvp.md:** "Ingest adapter for your chosen data API"
- **Implementation:** Only `MockProvider` generating random data. No real API connection.
- **Severity:** CRITICAL — System is completely useless without real data.

### 11. Architecture (Blocking vs. Non-blocking)
- **mvp.md:** "One Python process per role" (Ingest, Decision, etc.)
- **Implementation:** One monolithic `main.py` loop that blocks with `time.sleep(0.5)` call.
- **Severity:** HIGH — Does not scale to multiple matches, prevents role separation.

### 12. Replay Determinism
- **mvp.md:** "Replay works with the same decision code as live" (implicitly deterministic)
- **Implementation:** `ExecutionStub` uses `random.random()` function, making replay non-deterministic.
- **Severity:** MEDIUM — Complicates regression testing and optimization.

---

## Implemented Features ✓

| Feature | Status |
|---|---|
| Event + odds ingest | ⚠️ (Mock Only, no Real) |
| Latency measurement (p95) | ✓ |
| TPS calculation (LOW/MID/PRESS/CHAOS) | ✓ |
| Gate logic (latency, quality, EV, limits) | ✓ |
| Poisson EV model | ✓ |
| Execution stub (fill/reject/slippage) | ✓ |
| Paper wallet + settlement | ✓ |
| Audit log (decisions.jsonl) | ✓ |
| Replay (replay.py) | ✓ |
| Reason codes | ✓ |
| config.yaml thresholds | ✓ |
| Pydantic schemas | ✓ |

---

## Priority Order for Fixes

1. **SQLite Migration** — JSONL → SQLite. Enables queries and atomic storage.
2. **Rolling windows** — 1min/5min/10min windows with incremental calculation (O(1) per tick).
3. **Extra features to TPS** — include box_shots, possession.
4. **Trend** — delta to previous window.
5. **Dashboard** — Streamlit minimum.
6. **Directory Structure** — refactor into modules.

---

# Addendum (2026-01-27): Clarifications / Changes

## Changes to Observations
1. **Market Suspension - Gate**: Gate is implemented and `MockProvider` sets `is_suspended` randomly (~5%). Not a missing gate but *realism and test coverage*. Severity remains low, but classification "missing" is too strong.
2. **Score Not Updating**: `score` is hardcoded `"0-0"` and does not change, even though mvp.md promises "score + minute". This is a gap affecting analysis and potential models.
3. **Replay Not Reliable**: Replay exists, but event windowing and odds timing alignment are unstable (order/timing). Therefore "Replay ✓" is only partially true.
4. **Execution Receipts vs. Outcome**: Decision log does record execution, but *settlement is random* and does not follow events. This makes audit value weaker than MVP spec spirit.