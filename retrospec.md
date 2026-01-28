# Retrospective & Reverse Engineering: BotBet MVP

## 1. System Analysis (Reverse Engineering)

The current `BotBet` MVP is a synchronous, monolithic Python application designed to simulate a sports betting loop. It operates on a single thread, orchestrating data ingestion, decision logic, and paper trading execution.

### Logic Flow (`main.py`)
1.  **Initialization**: Loads `config.yaml` and initializes `BettingEngine`, `ExecutionStub`, `PaperWallet`, and `MockProvider`.
2.  **The Loop (1-90 mins)**:
    *   **Ingest**: Pulls `events` and `odds` from `MockProvider`.
    *   **Logging**: Appends raw data to `events_log.jsonl` and `odds_log.jsonl`.
    *   **State Update**: Calculates `tps` (Threat Pressure Score) and latency metrics.
    *   **Gating (`engine.evaluate_gates`)**:
        *   Checks Latency (`L_MAX`).
        *   Checks Market Suspension.
        *   Checks Quality (TPS label != "LOW").
        *   Checks Activity (xG > `XG_10M_MIN`).
        *   Checks Value (Poisson EV > `EV_MIN`).
    *   **Execution (`execution.py`)**: If gates pass, simulates order placement with random slippage and rejection probabilities.
    *   **Audit**: Writes decision context to `decisions.jsonl`.
    *   **Blocking**: Uses `time.sleep(0.5)` to throttle the loop.
3.  **Settlement**: At match end, iterates through the wallet's trades and settles them based on the final score.

### Strategy Logic (`engine.py`)
*   **TPS Heuristic**: `threat + (danger_count * 0.05)`. This is a "magic number" formula lacking statistical backing.
*   **Pricing Model**: Naive Poisson distribution `1 - exp(-xg_rate * time_remaining)`. It assumes the last 10 minutes of xG are perfectly predictive of the remaining match, ignoring pre-match priors.

## 2. Anti-Patterns & Technical Debt

### A. Architecture
*   **Monolithic Orchestrator**: `main.py` is a "god object" managing I/O, logic, and control flow.
*   **Blocking I/O**: The core loop blocks on `time.sleep` and file writes. This prevents scaling to multiple concurrent matches.
*   **In-Memory State**: Wallet balance and trade history are stored in RAM (`wallet.py`). A process crash results in total state loss (except for the raw logs).
*   **JSONL as Database**: Using local flat files (`.jsonl`) for state persistence is not ACID-compliant and difficult to query or backup atomically.

### B. Code Quality
*   **Magic Numbers**: Hardcoded values (e.g., `0.05` weight for danger attacks, `0.2` xG threshold) are scattered in the code.
*   **Mock Dependencies**: The system is tightly coupled to `MockProvider`. There is no abstraction layer (Interface/Protocol) for swapping in a real data provider (e.g., SportMonks).
*   **Time Handling**: Mixing `datetime.now()` (server time) with match time leads to potential replay/simulation errors.

### C. Logic
*   **Look-back Inefficiency**: The engine re-calculates xG sums for the "last 10 minutes" every single tick by iterating over raw events. This is computationally wasteful ($O(N)$ per tick).
*   **Deterministic Replay**: The `ExecutionStub` uses `random.random()`, making debugging and regression testing non-deterministic.

## 3. Integration Status
*   **Inputs**: Hardcoded to internal mock generation.
*   **Outputs**: Local filesystem only. No API, no notification system.
*   **ML/AI**: Non-existent. Logic is purely heuristic (if-this-then-that).

## 4. Conclusion
The MVP serves as a functional prototype to validate the *data structures* (`schemas.py`) and the *decision pipeline*, but the *runtime implementation* must be discarded for the production version. The next iteration requires a shift to an event-driven, distributed architecture.

---

# Addendum (2026-01-27): Full Reverse-Engineered Spec

## 5. File Map (Rebuild Blueprint)
This is the minimal file-by-file intent, as if rebuilding from scratch.

### Core Runtime
- `main.py`: Single-threaded match loop (minute 1..90) orchestrating ingest, state, gating, execution, logging, and wallet summary.
- `engine.py`: TPS labeling, Poisson probability, hard gates (latency, market, TPS, xG, EV).
- `execution.py`: Randomized fill/reject + slippage simulation.
- `wallet.py`: In-memory paper wallet; JSONL trade logging; P&L calculation.

### Data + Schema
- `schemas.py`: Pydantic contracts for `Event`, `Odds`, `MatchState`.

### Data Generation + Replay
- `mock_provider.py`: Synthetic event/odds generator for testing live loop.
- `replay.py`: Offline replay of `events_log.jsonl` + `odds_log.jsonl` through the same gate logic.

### Tests
- `tests/test_engine.py`: TPS + gate behavior + Poisson tests.
- `tests/test_execution.py`: Execution stub fill/reject/slippage bounds.
- `tests/test_wallet.py`: Wallet bookkeeping.
- `tests/test_integration.py`: Basic end-to-end sanity.

## 6. Data Contracts (Observed Fields)

### Event
- `match_id`, `t_event`, `t_recv`, `type`, `team`, `xg`, `data`

### Odds
- `match_id`, `t_seen`, `t_recv`, `market`, `selection`, `price`, `is_suspended`

### MatchState
- `match_id`, `minute`, `score`, `tps_label`
- `t_event_latest`, `t_recv_latest`
- `event_latency_p95`, `odds_latency_p95`

## 7. Config & Thresholds (Observed)
- `L_MAX`, `EV_MIN`, `XG_10M_MIN`, `MAX_BETS_PER_MATCH`
- `REJECT_RATE`, `MAX_SLIPPAGE`
- `WALLET_START`, `STAKE`

## 8. Runtime I/O (Logs)
- `events_log.jsonl`: Raw `Event` rows for replay.
- `odds_log.jsonl`: Raw `Odds` snapshots.
- `decisions.jsonl`: Gate outcomes + execution details.
- `trade_log.jsonl`: Wallet events (PENDING, WIN, LOSS, REJECTED).

## 9. Integrations (Current)
- **Input**: Synthetic `mock_provider` only.
- **Output**: Filesystem JSONL only.
- **No APIs**, **no webhooks**, **no database**.

## 10. Defects / Antipatterns (Observed)
1. **Sim time vs real time**: `current_minute` is decoupled from event timestamps (`datetime.now()`), breaking temporal consistency.
2. **Replay window anchor**: `window_events[-1]` assumes sorted events; logs are not guaranteed sorted by time.
3. **Settlement is random**: Outcomes are coin flips, not tied to events or scores.
4. **Odds alignment**: Replay selects odds by index (minute-1) rather than timestamp match.
5. **Trade log duplication**: PENDING and WIN/LOSS are separate JSONL rows without `trade_id`.
6. **Stoppage-time EV zero**: Poisson probability hard-clamped to zero at minute >= 90.
7. **Non-deterministic tests**: Randomness is not seeded; replay/debug is non-reproducible.
8. **Unused metrics**: `odds_latency_p95` is set in live loop but never used for gating.

## 11. Errata (Correction to Earlier Text)
- **Settlement behavior**: The current code **does not** settle at match end based on final score. It settles immediately on fill using a random win rate in both live and replay loops.
