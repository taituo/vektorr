# Thematic backlog

Open engineering work grouped by theme. Each item should appear under **one** theme; link dependencies explicitly (`blocked by: …`).

**Planning stack**

| Layer | Document |
| ------- | ---------- |
| Strategy (phases, exit gates) | [roadmap.md](../../roadmap.md) |
| Thematic backlog (this file) | Ongoing priorities |
| Sprint slice | Optional `docs/planning/sprint-YYYY-MM-DD.md` using [sprint-TEMPLATE.md](sprint-TEMPLATE.md) |

**Suggested sequencing** (adjust if data quality risks outweigh integration):

1. Integration smoke — Compose or prod-like path: poller / Rust Spine → Brain → QuestDB; document env vars.
2. Data parity — Single `engine` / `schemas` story (root vs `brain/`); staging matches Docker behavior.
3. Orchestration — Replace placeholder loop in `orchestrator.py` with a real driver (queue, subscription, or poll).
4. Execution — Paper → shadow with real adapters behind flags; reconciliation and idempotent placement.
5. Model hardening — Execution-risk fitting, calibration milestones per roadmap Phase 0–1.

---

## Integration

End-to-end operation with credentials and runtime wiring.

- [ ] Validate Docker Compose path (or equivalent): Brain + QuestDB + `provider-poller` / Spine with **real API keys**.
- [ ] Document required environment variables and a minimal smoke checklist (health endpoints, one decision written).
- [ ] Observability: logs/metrics/alerts aligned with production expectations.

**Blocked-by notes:** README operational row **Integration** stays Pending until this theme has a repeatable smoke run.

---

## Orchestration

Glue beyond individual services.

- [ ] `orchestrator.py` main loop today sleeps after `start()` — replace with a production-appropriate driver (event stream consumer, scheduled poll, or HTTP callback handler).
- [ ] Define how live match batches reach `Orchestrator.process_match` (contract + failure modes).

---

## Execution

Real brokerage path vs stubs.

- [ ] `execution/betfair_adapter.py`: implement login / session lifecycle (`TODO` in source).
- [ ] `execution/betfair_adapter.py`: implement place-order path (`TODO` in source).
- [ ] Reconciliation: fills vs intents; idempotent placement; QuestDB execution logging hardened beyond dry-run where needed.

---

## Data contract parity

Feeds, IDs, and Brain inputs consistent across Spine and Brain.

**Residual gaps** (from legacy `todo.md` / sprint snapshot — superseded DONE items removed):

- [ ] Confirm SportMonks ↔ Odds API alignment per match (`match_map` / resolver); fill mapping **data** where tooling exists but tables are empty (see `mapping/`, export/import tools).
- [ ] Provider richness: SportMonks events often lack xG/score/period in adapters — tighten heuristics or enrich contract when APIs allow.
- [ ] Odds API: verify `line` / `point` / `is_suspended` / in-play handling end-to-end for targeted markets.
- [ ] Provider polling still may fetch broad lists — dedup relied upon; tune league filters (SportMonks league IDs populated).
- [ ] Brain `minute` / `score`: coarse inference vs official match clock — improve when feed supports it.
- [ ] Anti-pattern cleanup: keep decision logic vs mapping boundaries explicit (single ownership per concern).

**Inputs needed from operators**

- SportMonks league IDs (EPL, La Liga, Serie A, Bundesliga, Ligue 1 + Nordics as desired).
- The Odds API sport keys from provider listing:  
  `cargo run --manifest-path spine/Cargo.toml -- --odds-api-list-sports --odds-api-key YOUR_KEY`

---

## Models / calibration

- [ ] `brain/models/execution_risk.py`: replace placeholder calibration with fitted parameters where appropriate (`TODO` in module).
- [ ] Tie calibration dashboards / CLV pipelines to roadmap Phase 0 exit criteria ([roadmap.md](../../roadmap.md)).

---

## References

- Operational snapshot: [README.md](../../README.md)
- Archived sprint snapshot (do not extend): [todo_wednesday.md](../../todo_wednesday.md)
