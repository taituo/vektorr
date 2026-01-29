# Vektorr: Survival-First Betting Engine

Vektorr is a deterministic, fail-closed decision engine for live-only sports markets. It is not designed to gamble; it is designed to reject noise. **NO BET** is the default state.

## 1. Core Constraints (Non-Negotiable)
- **Deterministic:** Same input data must result in the exact same decision. Replay is mandatory.
- **Fail-Closed:** Under any uncertainty (latency spike, feed mismatch, market suspension), the system freezes.
- **Hard Gates:** Every signal must pass five layers of verification (Latency, Data Quality, Disconfirm, MMS, Execution Risk).
- **Auditability:** Every decision—and every rejection—is logged with a unique `reason_code`.

## 2. Technical Architecture
The system is split to separate ingest concerns from decision logic:
- **SPINE (Rust):** Low-latency ingestion and ILP batch-writing to QuestDB. Enforces strict data contracts.
- **BRAIN (Python):** Threat Pressure Scoring (TPS) and ML-driven probability modeling.
- **QUESTDB:** High-throughput time-series storage for all events, odds, and decisions.
- **EXECUTION:** Staged rollout logic from Paper to Target stakes with non-overrideable kill switches.

## 3. Current Scope
- **Leagues:** EPL, La Liga only.
- **Markets:** Over/Under (0.5 - 2.5), Next Goal, Double Chance.
- **Rules:** Max 1–2 bets per match. Max 1 latent risk per match.

## 4. Operational Readiness
| Phase | Status | Reality |
| :--- | :--- | :--- |
| **P0: Validation** | ✅ DONE | Math proven. Brier scores locked. |
| **P1: Calibration** | ✅ DONE | Params set by grid search, not intuition. |
| **P2: ML Models** | ✅ DONE | Dynamic lambda and TPS velocity active. |
| **P3: Autonomy** | ⚠️ 90% | LearningAgent active; shared state refined. |
| **P4: Execution** | ✅ DONE | KillSwitch and StagedRollout implemented. |
| **P5: Ingest** | ⚠️ 80% | Real-world API integration ready; keys pending. |

## 5. Directory Structure
- `/spine`: Rust ingestor. High-performance, zero-garbage.
- `/brain`: Decision logic and ML models.
- `/execution`: Safety systems and execution adapters.
- `/infra`: Dockerized QuestDB and telemetry.
- `/tools`: Backtesting, parameter sweeps, and mapping utilities.

## 6. Development Discipline
1. **Never** assume a library is available.
2. **Never** ignore a latency spike.
3. **Never** deploy without a successful replay of the last 1000 decisions.
4. **NO BET** is a successful outcome.