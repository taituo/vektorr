# Spine (Rust Ingestor)

Minimal QuestDB ingestor that pushes `events` and `odds` JSONL into QuestDB via ILP (TCP).

## Run QuestDB

From `infra/questdb`:

```bash
docker compose up -d
```

QuestDB will listen on:
- Web UI: http://localhost:9000
- ILP (TCP): localhost:9009

## Ingest JSONL

From `spine/`:

```bash
cargo run -- \
  --events ../events_log.jsonl \
  --odds ../odds_log.jsonl
```

## Run HTTP Ingest Server

From `spine/`:

```bash
cargo run -- --listen 0.0.0.0:8080
```

With Brain integration:

```bash
cargo run -- --listen 0.0.0.0:8080 --brain-url http://localhost:8090
```

### Example Requests

```bash
curl -X POST http://localhost:8080/event \
  -H 'Content-Type: application/json' \
  -d '{"match_id":"m1","t_event":"2026-01-27T12:00:00Z","t_recv":"2026-01-27T12:00:01Z","type":"SHOT","team":"HOME","xg":0.12}'
```

```bash
curl -X POST http://localhost:8080/odds \
  -H 'Content-Type: application/json' \
  -d '{"match_id":"m1","t_seen":"2026-01-27T12:00:00Z","t_recv":"2026-01-27T12:00:00Z","market":"OU_2.5","selection":"OVER","price":2.05,"is_suspended":false}'
```

## Run HTTP Polling Adapter

Poll JSON arrays from remote endpoints and push into QuestDB.

```bash
cargo run -- \
  --events-url http://localhost:9001/events \
  --odds-url http://localhost:9001/odds \
  --poll-ms 1000 \
  --max-rps 2 \
  --dedup-cap 20000
```

With Brain integration:

```bash
cargo run -- \
  --events-url http://localhost:9001/events \
  --odds-url http://localhost:9001/odds \
  --brain-url http://localhost:8090
```

## Run WebSocket Adapter

The WS adapter expects messages in envelope form:
```json
{"kind":"event","data":{...Event...}}
{"kind":"odds","data":{...Odds...}}
```

Run:
```bash
cargo run -- --ws-url ws://localhost:9002/feed --brain-url http://localhost:8090
```

## Provider Adapters (SportMonks + The Odds API)

### List available sports (The Odds API)
```bash
cargo run -- --odds-api-list-sports --odds-api-key YOUR_KEY
```

### Run both adapters (events + odds)
```bash
cargo run -- \
  --sportmonks-token YOUR_SPORTMONKS_TOKEN \
  --sportmonks-leagues 8,564,72 \
  --odds-api-key YOUR_ODDS_API_KEY \
  --odds-api-sports soccer_epl,soccer_germany_bundesliga \
  --brain-url http://localhost:8090
```

If your feed requires auth:

```bash
cargo run -- \
  --events-url http://localhost:9001/events \
  --bearer-token YOUR_TOKEN \
  --max-backoff-ms 15000
```

## Tables (Auto-Created)

- `events`:
  - tags: `match_id`, `team`, `event_type`
  - fields: `xg`, `latency_ms`
  - timestamp: `t_event`

- `odds`:
  - tags: `match_id`, `market`, `selection`
  - fields: `price`, `is_suspended`, `latency_ms`
  - timestamp: `t_recv`

## QuestDB DDL & Queries

Optional explicit schema and helper queries live in `infra/questdb/`:
- `schema.sql`
- `queries.sql`
 - `init.py` / `init.sh` (automation)
