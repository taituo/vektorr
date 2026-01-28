# FutureSpec: Vektorr v0.2+ (The 8gents Era)

## 1. Executive Summary
Moving from the monolithic MVP, **Vektorr v0.2** implements the "8gents" philosophy: a distributed, agent-native operating system. The system splits concerns between a high-performance, safe core (Rust) and flexible, intelligent agents (Python).

## 2. Architectural Pillars

### A. The Spine (Rust)
*   **Role**: Safety, Routing, State Management.
*   **Technology**: Rust (`tokio`, `actix` or `axum`).
*   **Responsibilities**:
    *   **Market Guardrails**: strict validation of all betting signals. Enforces limits (e.g., "Max $50 exposure per match"). *Code that cannot fail.*
    *   **Event Bus**: High-throughput pub/sub system broadcasting market updates.
    *   **Persistence**: Writes normalized tick data to **QuestDB** (Time-series) and state to **Redis** (Hot).

### B. The Brain (Python 3.11+)
*   **Role**: Intelligence, Strategy, Prediction.
*   **Technology**: Python, `LangChain`/`PydanticAI`, `XGBoost`.
*   **Responsibilities**:
    *   **Quant Agent**: Consumes tick data, runs Poisson/Machine Learning models to output raw probabilities.
    *   **Qual Agent (LLM)**: Consumes textual commentary/social feeds. Uses LLMs (Gemini/Claude) to assess "Vibe" (Momentum, Injury impact, Referee strictness).
    *   **Strategy Agent**: Synthesizes Quant + Qual signals into a `BetProposal` sent to the Spine.

### C. The Limbs (Adapters)
*   **Role**: I/O.
*   **Technology**: Python or Go.
*   **Responsibilities**:
    *   **Ingestors**: Connectors for SportMonks, RapidAPI, 1xBet stream.
    *   **Executors**: API clients for exchanges (Betfair, Pinnacle).

## 3. Technology Stack Decisions

| Component | Choice | Rationale |
| :--- | :--- | :--- |
| **Core Logic** | **Rust** | Memory safety and zero-cost abstractions are critical for the financial/risk module. |
| **Agents** | **Python** | Unmatched ecosystem for AI/ML (PyTorch, LangChain, Pandas). |
| **Time-Series DB** | **QuestDB** | High-performance ingestion for tick data; SQL-compatible. |
| **State DB** | **PostgreSQL** | Relational integrity for user data, wallet ledger, and trade history. |
| **Hot Cache** | **Redis** | Sub-millisecond latency for live match state and deduplication. |
| **LLM** | **Gemini 2.0 / Claude 3** | High context window for analyzing full match commentary logs. |

## 4. Data Architecture

### Data Flow
1.  **Ingest**: `Ingestor` receives raw JSON -> Normalizes to `Protobuf` -> Pushes to **Spine**.
2.  **Route**: **Spine** publishes to `topic.match.{id}`.
3.  **Process**:
    *   **Quant Agent** calculates `WinProb: 0.55`.
    *   **Qual Agent** reads commentary, detects "Home Team Frustration", outputs `Sentiment: -0.2`.
4.  **Decide**: **Strategy Agent** combines `0.55 + (-0.2 adjustment)` -> `FinalProb: 0.53`. Checks edge -> Sends `BetProposal`.
5.  **Validate**: **Spine** checks `RiskLimits`. If PASS -> Sends to `Executor`.

## 5. Migration Plan (MVP -> v0.2)

### Phase 1: The Rust Foundation (The Spine)
*   Create a new Rust project workspace.
*   Define the canonical data types (`Event`, `Market`, `Signal`) using Protobuf/Structs.
*   Implement the "Guardrails" module (Risk checks).

### Phase 2: The Data Pump
*   Deploy **QuestDB** (Docker).
*   Rewrite `MockProvider` as a standalone service pushing to the Rust Spine via ZeroMQ or HTTP.

### Phase 3: The Intelligence Layer
*   Extract `engine.py` logic into a Python microservice.
*   Replace the "TPS Heuristic" with a basic LLM prompt ("Analyze this commentary stream...").

### Phase 4: Integration
*   Connect the Python Brain to the Rust Spine.
*   End-to-end test with paper trading.

## 6. Component Replacement Table

| MVP Component | v0.2 Replacement | Notes |
| :--- | :--- | :--- |
| `main.py` (Loop) | **Rust Orchestrator** | Event-driven, non-blocking. |
| `engine.py` (Logic) | **Python Agent Swarm** | Split into Quant (Math) and Qual (LLM) agents. |
| `wallet.py` (State) | **PostgreSQL Ledger** | ACID transactions, audit trail. |
| `events_log.jsonl` | **QuestDB** | High-speed, queryable history. |

---

# Addendum (2026-01-27): Post-MVP Roadmap Aligned to Retrospec

## 7. MVP+ Milestones (Carry Forward from `retrospec.md`)

### M1: Deterministic Core + Time Coherence (Python-first)
Goal: make simulation trustworthy before scaling.
- Replace random settlement with event- or score-based outcomes.
- Make `mock_provider` stateful (rolling event history) with a single match clock.
- Ensure replay windows are time-sorted and odds are aligned by timestamp.
- Seed randomness for reproducible experiments.

### M2: Data & Storage Hardening
Goal: stop writing analysis-critical data to ad-hoc JSONL only.
- Introduce a normalized schema in Postgres (events, odds, decisions, trades).
- Add a dedicated replay/backtest service reading from DB.
- Move decision logs to append-only tables with `trade_id`.

### M3: Real Ingest + Execution Adapters
Goal: swap mock inputs with real providers.
- Implement provider adapters (SportMonks / Sportradar / exchange API).
- Add rate-limit, dedupe, and clock sync (source time vs recv time).
- Introduce market suspension and line-move guards in the spine.

### M4: Quant Engine v1 (ML Optional)
Goal: upgrade from heuristic xG to calibrated models.
- Baselines: Poisson with priors, team strength, match state.
- Add features: rolling xG/xThreat, possession deltas, cards, scoreline.
- Optional ML: XGBoost / LightGBM trained offline; strict calibration checks.

### M5: Qual/LLM Layer (Optional)
Goal: use LLM only where it adds non-structured signal.
- Inputs: commentary, injury notes, referee bias, weather.
- Output: bounded, explainable adjustments to probability.
- Guardrails: LLM never overrides risk limits or pricing sanity checks.

### M6: Performance Split (Rust Spine + Python Brain)
Goal: keep risk and latency-critical logic in Rust.
- Rust handles routing, rate limits, risk checks, and market guardrails.
- Python runs research and model inference; must be stateless and restartable.
- Define stable protobuf schema between spine and agents.

## 8. Component Swaps (Concrete “What Changes”)
- `mock_provider.py` -> `ingest_service` (real feeds, stateful clock).
- `replay.py` -> `backtest_service` (DB-driven, deterministic).
- `decisions.jsonl` -> `decision_log` table with strict schema.
- `wallet.py` -> `ledger_service` (double-entry accounting).
- `engine.py` -> `strategy_service` (versioned models, A/B gating).

## 9. Tech Decisions (Pragmatic Defaults)
- **Python stays** for MVP+ research and feature engineering.
- **Rust enters** when latency or multi-match concurrency becomes blocking.
- **ML** only after deterministic replay and calibration are stable.
- **LLM** only for qualitative signals; never used for numeric pricing directly.
