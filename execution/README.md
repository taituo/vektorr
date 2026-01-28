# Execution Service (VPS)

This service consumes decisions from QuestDB and executes bets automatically.
Initially runs in **dry-run** mode (no real bets), then upgrades to Betfair API.

## Run (dry-run)

```bash
python3 execution_service.py
```

## Configure
- `EXEC_CONFIG` env var can override the config path.
- Default config: `execution/config.yaml`.

## QuestDB Logging
If `questdb.log_to_questdb=true`, executions are inserted into the `executions` table.

## Mapping requirement (Betfair)
Betfair mode now looks up `market_map` in QuestDB using `market` + `selection` (and line for OU).
If no mapping is found, the decision is skipped with `reason=MAPPING_MISSING`.
