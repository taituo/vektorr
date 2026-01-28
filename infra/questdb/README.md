# QuestDB Init Automation

This directory includes a bootstrap script to apply `schema.sql` after QuestDB is running.

## Option A: One-shot init via Docker Compose

```bash
cd infra/questdb
docker compose up -d
```

`questdb-init` will run once and exit after applying `schema.sql`.

## Option B: Manual init (local)

```bash
cd infra/questdb
./init.sh
```

### Environment variables
- `QDB_HOST` (default: localhost)
- `QDB_PORT` (default: 9000)
- `QDB_SCHEMA` (default: ./schema.sql)
- `QDB_WAIT_TIMEOUT` (default: 60 seconds)
