# Brain (Python)

This is the extracted decision engine (the only code carried forward from the MVP).

## Contents
- `engine.py`: TPS + gate logic
- `schemas.py`: Pydantic contracts used by the engine

## Notes
- The Brain is intentionally stateless.
- It will be wired to the Spine via a message bus in later phases.

## Run the Brain HTTP Service

```bash
cd brain
python -m pip install -r requirements.txt
uvicorn service:app --host 0.0.0.0 --port 8090
```

### State Controls

```bash
export BRAIN_STATE_TTL_MINUTES=120
export BRAIN_MAX_MATCHES=200
```

### Example

```bash
curl -X POST http://localhost:8090/event \
  -H 'Content-Type: application/json' \
  -d '{"match_id":"m1","t_event":"2026-01-27T12:00:00Z","t_recv":"2026-01-27T12:00:01Z","type":"SHOT","team":"HOME","xg":0.12}'
```

## Manual Bet Logging

If you place bets manually, you can log them for audit/analysis:

```bash
curl -X POST http://localhost:8090/manual_bet \
  -H 'Content-Type: application/json' \
  -d '{"match_id":"m1","selection":"OVER","price":2.05,"stake":10,"market":"OU_2.5","note":"manual"}'
```

Logs are written to `manual_trades.jsonl` by default (override via `BRAIN_MANUAL_LOG_PATH`).
