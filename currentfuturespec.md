# currentfuturespec.md

Updated, concise future spec aligned with `all.md`.

Last updated: 2026-01-28

---

## 0) Locked scope (do not change casually)

- Leagues: EPL, La Liga.
- Bets: LIVE ONLY.
- Markets: Over/Under 0.5/1.5/2.5, Next Goal, Double Chance (live only).
- Staking: flat stake, max 1–2 bets per match, max 1 latent risk per match,
  NO BET is default state.

---

## 1) Core philosophy

Survival first. The system fails closed. Hard gates block bets on uncertainty.
Decisions must be deterministic: same inputs -> same outputs, even at scale.

---

## 2) Role of AI (strict boundaries)

Phase 1 (now): ML/statistics drive the decisions. LLM can code, summarize, and
produce weak-signal context tags only. It does not trigger bets.

Phase 2 (next): LLM runs as a sidecar that summarizes live context (injuries,
rumors, lineup changes) into tags. Tags are advisory metadata only.

Phase 3 (future): Constrained autonomy inside a Rust sandbox. Hard limits on
latency, stake, and stop‑loss are non-overrideable.

LLM never replaces ML/statistics for probabilistic decisioning, and it never
changes thresholds automatically without explicit human config changes.

---

## 3) Architecture (as built)

Spine (Rust):
- Ingests events/odds, normalizes, dedups, writes ILP to QuestDB.
- Match mapping via match_map + team normalization (mappings.yaml).

Brain (Python):
- Runs TPS + 5 hard gates.
- Stateless HTTP API for decisioning.

Execution:
- Dry‑run executor + Betfair stub.
- Market mapping via market_map (QuestDB).

QuestDB:
- Time‑series store for events/odds/decisions/executions + mapping tables.

---

## 4) Data contracts (normative)

All events and odds must include t_event/t_recv or t_seen/t_recv timestamps.
EV uses vig‑less probabilities. Decision logs store both seen and fill prices.
Determinism is required: the decision pipeline must be reproducible.

---

## 5) Loop cadence and lifecycle

- Loop A (1–5s): safety checks, latency, suspensions.
- Loop B (30–60s): core decisioning.
- Loop C (1/5/10 min): rolling windows and trend gates.

Match lifecycle: PRE -> LIVE_ACTIVE -> POST, with freeze/unfreeze states.

---

## 6) Governance and risk controls

Hard freeze on latency spikes or feed mismatch. Stop‑loss enforced. All rule
changes are versioned. Audit logs include NO BET decisions.

---

## 7) Validation and replay

Replay is mandatory before real money. Determinism is required. Use the test
matrix from `all.md` (slow feed days, suspend spikes, slippage stress, etc.).

---

## 8) Next concrete steps (implementation)

1) Connect real data feeds (SportMonks + Odds API).
2) Populate mapping CSVs (match/team/market) and load into QuestDB.
3) Wire execution mapping to real Betfair IDs.
4) Add observability: KPI dashboard + alerting.
5) Harden replay pipeline for deterministic end‑to‑end tests.

---

## 9) Operator focus (personal)

Coding is mostly handled by automation/agents. The main human focus is on
mathematics, modeling, and learning the odds/betting domain.
