# Vektorr

Real-time, live-only betting decision engine with deterministic, fail-closed logic.
Phase 1 focuses on data reliability and mapping; MVP paper trading remains intact.

## Vision (short)
- Live-only decisioning with strict safety gates and auditability.
- Deterministic pipeline: same inputs -> same outputs.
- ML/statistics drive decisions; LLM is limited to weak-signal context tags only.
- Risk-first operation: "NO BET" is the default.

## Technical highlights (from master spec)
- Fail-closed: NO BET default, freeze-first behavior under uncertainty.
- Hard gates: latency, data quality, disconfirm, MMS, exec-risk, EV retention.
- Exec-risk model: suspend/slippage/reject/latency drive the freeze gate.
- Full audit trail: every decision logged (including NO BET) with reason_code.
- Determinism + replay: same data -> same decision, mandatory replay validation.
- Latent risk rule: max 1 latent risk per match (Next Goal is high-latent).

## Locked scope (current)
- Leagues: EPL, La Liga.
- Markets: Over/Under 0.5/1.5/2.5, Next Goal, Double Chance (live only).
- Staking: flat stake, max 1-2 bets per match, max 1 latent risk per match.

## Architecture
Data (APIs) -> SPINE (Rust ingestor) -> QuestDB -> BRAIN (Python) -> EXECUTION

## Environment tiers (environment_spec.yaml)
- Tier 0: Local dev + mock data (Docker QuestDB, mock server, dry-run).
- Tier 1: Paper trading with official APIs (SportMonks + The Odds API).
- Tier 1B: Data hoarding (BetsAPI) for large historical sets (planned).
- Tier 2: Micro live execution (Matchbook/Betfair; adapter is stub today).
- Tier 4: Asian broker aggregator (planned).

## Why these tech choices (aligned with environment_spec.yaml)
- QuestDB + ILP: high-throughput time-series ingest, easy local/VPS Docker use.
- Rust Spine: low-latency ingest + strict data contracts + deterministic mapping.
- Python Brain: fast iteration for models + gates while keeping determinism.
- Mapping tables + CSV tools: stable provider-ID resolution across feeds.
- Execution separated: allows dry-run, safety gating, and staged rollout by tier.

## Status
Done:
- MVP paper trading: TPS + 5 hard gates, wallet, mock-data, TUI dashboard.
- Spine adapters: JSONL, HTTP poll, WebSocket, SportMonks + The Odds API.
- QuestDB infra + schema + ILP writes (batch).
- Mapping infra: TeamMapper, MatchResolver, CSV tools.
- Brain service (FastAPI) + decision logic.

Open:
- Provider config (league IDs + API keys).
- Mapping CSV population (match/team/market).
- Betfair adapter implementation (currently stub).
- Risk controls (liability/Kelly/exposure), execution hardening.
- Production features (auth, rate limiting, graceful shutdown).

## Key docs
- `currentfuturespec.md`: current scope and constraints.
- `delta_vision.md`: gaps between vision and master spec.
- `all.md`: master spec (long).
- `mvp.md`: MVP history (kept as-is).

## Layout
- `spine/`: Rust ingest + providers + mapping.
- `brain/`: Python decision service.
- `execution/`: execution service + Betfair stub.
- `infra/questdb/`: QuestDB setup.
- `mapping/`: CSV mapping workflow and tools.
- `docs/`: archived long-form docs and articles.

## Quick start
See module READMEs:
- `spine/README.md`
- `brain/README.md`
- `execution/README.md`
- `infra/questdb/README.md`
