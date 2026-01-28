# Data Provider Compatibility Spec

This document defines the minimum compatibility requirements for any real data provider (SportMonks, BetsAPI, etc.).
The goal is to ensure Spine can ingest with low latency and Brain can evaluate gates deterministically.

## 1. Required Feeds

### A) Events Feed (live match events)
**Must provide:**
- `match_id` (stable ID)
- `t_event` (timestamp when event occurred on field)
- `t_recv` (timestamp when provider delivered event; if absent, Spine will set)
- `type` (SHOT, GOAL, DANGER_ATTACK, CORNER, CARD, etc.)
- `team` (HOME/AWAY)
- `xg` (float, can be 0.0 if not available)

**Optional but strongly recommended:**
- `period` (1H/2H/ET)
- `score` (home/away at event time)
- `player_id`, `assist_id`

### B) Odds Feed (live market snapshots or deltas)
**Must provide:**
- `match_id`
- `t_seen` (timestamp when odds were published)
- `t_recv`
- `market` (e.g. OU_2.5)
- `selection` (e.g. OVER, UNDER)
- `price` (decimal odds)
- `is_suspended` (boolean or equivalent)

**Optional:**
- `line` / `handicap` (numeric)
- `bookmaker_id`

## 2. Update Frequency & Latency
- Events should arrive within **<3s p95** (go/no-go gate).
- Odds should arrive within **<3s p95** for live edges.
- If provider cannot meet this, the system must default to **NO_BET**.

## 3. Delivery Semantics
- **Ordering:** events and odds must be orderable by `t_event` / `t_seen`.
- **Idempotency:** duplicates are allowed; Spine will dedup.
- **Completeness:** both feeds must cover the full 90+ minutes.

## 4. API Interface (Compatibility Modes)

### Mode 1: HTTP Polling (supported)
- Endpoint returns JSON array of `Event` or `Odds`.
- Supports `?since=<RFC3339>` for incremental polling.
- Example:
  - `GET /events?since=2026-01-27T12:00:00Z`
  - `GET /odds?since=2026-01-27T12:00:00Z`

### Mode 2: WebSocket Streaming (supported)
- Messages in envelope format:
  ```json
  {"kind":"event","data":{...Event...}}
  {"kind":"odds","data":{...Odds...}}
  ```
- Must allow reconnection without full state reset.

### Mode 3: Push HTTP (optional)
- Provider posts to Spine `/event` and `/odds` endpoints.

## 5. Mapping Requirements (Provider → Canonical)
- Provider must map event types into canonical set.
- Team must be normalized to HOME/AWAY.
- Any proprietary fields must be captured into `data` (if used later).

## 6. Validation Checklist (Before Go‑Live)
- [ ] `t_event` and `t_seen` are present and monotonic per match.
- [ ] Event latency p95 < 3s on at least 50+ matches.
- [ ] Odds latency p95 < 3s on at least 50+ matches.
- [ ] Suspension flag is reliable (no phantom liquidity).
- [ ] Match IDs consistent across events and odds.
- [ ] Market names map to canonical strings (`OU_2.5`, `NEXT_GOAL`, etc.).

## 7. Failure Modes (Must Handle)
- Missing fields → drop event, log error, continue.
- Out-of-order timestamps → accept, but note ordering issues.
- Feed gaps > 10s → mark match as NO_BET.
- Provider throttling → auto-backoff in Spine.

## 8. Provider Decision Matrix
- If provider cannot supply `t_event` or `t_seen`: **reject**.
- If provider cannot deliver `is_suspended`: **reject** (live-only use-case).
- If provider cannot meet latency targets: **use only for offline research**.
