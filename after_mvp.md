# After MVP — Phase 1 Bootstrap (2026-01-27)

This document captures what was done after the MVP and what should happen next.

## What was done (summary)
- Wrote a project conclusion report in `codex_conclude.md`.
- Appended reverse-engineering addendum to `retrospec.md`.
- Appended post-MVP roadmap addendum to `articles/futurespec.md`.
- Appended a clarification addendum to `mvpgap.md` (no further edits requested after that).
- Created a new clean “Phase 1” structure with QuestDB + Rust ingestor + extracted Python brain.

## New structure added
```
infra/questdb/
  docker-compose.yml
spine/
  Cargo.toml
  README.md
  src/
    main.rs
    questdb.rs
    types.rs
    source/
      jsonl.rs
      mod.rs
brain/
  engine.py
  schemas.py
  README.md
  requirements.txt
```

## Why this matches FutureSpec Phase 1
- **Database**: QuestDB provisioned via Docker (no SQLite in Python).
- **Ingestor**: Rust ingestor (`spine/`) that pushes data into QuestDB via ILP (TCP).
- **Brain**: MVP logic preserved by extracting `engine.py` + `schemas.py` into `brain/`.
- **MVP code**: left as-is, treated as disposable reference.

## How to run (quickstart)
1) Start QuestDB
```
cd infra/questdb
docker compose up -d
```

2) Ingest JSONL into QuestDB
```
cd spine
cargo run -- --events ../events_log.jsonl --odds ../odds_log.jsonl
```

QuestDB UI should be at http://localhost:9000

## Next steps (choose one path)
1) **Real ingest adapter (Rust)**
   - Replace JSONL input with an HTTP/WebSocket ingestor.
   - Add clock sync and dedup in the ingestor.

2) **Brain service wrapper (Python)**
   - Expose `brain/engine.py` as a small HTTP or CLI service.
   - Define a minimal request/response schema for `MatchState + Events + Odds`.

3) **QuestDB schema hardening**
   - Add explicit DDL and retention policies.
   - Create basic queries for latency p95 and TPS summaries.

4) **Deterministic replay rework (optional)**
   - Build a new replay that reads from QuestDB, not JSONL.
   - Ensure time alignment between events and odds.

---

## Update (2026-01-27): Rust HTTP Ingest Mode
- Added `--listen` mode to the Spine ingestor to accept HTTP POSTs.
- Endpoints: `POST /event`, `POST /odds`, `GET /health`.
- Updated `spine/README.md` with usage examples.

## Update (2026-01-27): HTTP Polling Adapter
- Added `--events-url` / `--odds-url` polling mode in Spine.
- Supports bearer token and configurable poll/timeout.
- Intended as first “real” adapter for external feeds.
 - Added dedup cache, rate-limiting (`--max-rps`), and backoff controls.

## Update (2026-01-27): Spine ↔ Brain Integration (Push)
- Added Brain HTTP client in Spine (`--brain-url`).
- Spine forwards events/odds to Brain and writes `decisions` back to QuestDB.
- Brain now exposes FastAPI service with `/event` and `/odds`.

## Update (2026-01-27): WebSocket Adapter
- Added `--ws-url` for streaming ingestion (envelope: `{kind,data}`).
- Optional bearer token and reconnect interval.

## Update (2026-01-27): Brain Consolidation
- Canonical Brain is `brain/service.py` (stateless decision service).
- MVP-era `brain_api.py` and its integration script moved to `legacy/`.

## Update (2026-01-27): QuestDB Schema + Queries
- Added `infra/questdb/schema.sql` (explicit table definitions).
- Added `infra/questdb/queries.sql` (latency + decision monitoring).

## Update (2026-01-27): Brain State Management
- Added TTL and max‑match cap via `BRAIN_STATE_TTL_MINUTES` and `BRAIN_MAX_MATCHES`.

## Update (2026-01-27): QuestDB Init Automation
- Added `infra/questdb/init.py` and `init.sh`.
- Added `questdb-init` service in docker-compose for one-shot schema bootstrap.

## Update (2026-01-27): Provider Adapters
- Added SportMonks live events adapter (livescores + events).
- Added The Odds API adapter for odds (totals + h2h).
- Added CLI helper to list available Odds API sports.

## Update (2026-01-27): Mapping + Manual Execution
- Added mapping tables to QuestDB schema (`match_map`, `team_map`, `market_map`).
- Added Postgres schema for mapping (optional) under `infra/postgres/`.
- Added manual execution adapter + `/manual_bet` endpoint in Brain.

## Update (2026-01-27): Execution Service Skeleton
- Added `execution/` service that polls QuestDB decisions and logs execution (dry-run).
- Added Betfair adapter skeleton (`execution/betfair_adapter.py`).
 - Added QuestDB execution log table + optional insert in execution service.
 - Added mapping loader (`tools/load_mapping.py`) and CSV templates under `mapping/`.
