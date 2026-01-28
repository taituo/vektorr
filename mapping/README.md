# Mapping Files

These CSVs are used to bridge provider IDs to canonical IDs.
Populate them before enabling automated execution.

## Files
- `match_map.csv`: provider match → canonical match
- `team_map.csv`: provider team → canonical team
- `market_map.csv`: provider market → canonical market/selection

## Example flow
1) Export current mapping rows from QuestDB (optional)
2) Normalize names (home/away)
3) Fill CSVs
4) Load into QuestDB using `tools/load_mapping.py`

## Tools

Export (QuestDB -> CSV):
```bash
python3 tools/export_mapping.py match_map mapping/match_map.csv
python3 tools/export_mapping.py team_map mapping/team_map.csv
python3 tools/export_mapping.py market_map mapping/market_map.csv
```

Import (CSV -> QuestDB):
```bash
python3 tools/load_mapping.py match_map mapping/match_map.csv
python3 tools/load_mapping.py team_map mapping/team_map.csv
python3 tools/load_mapping.py market_map mapping/market_map.csv
```

Notes:
- `match_map.kickoff` accepts ISO time or epoch millis on import.
- `match_map.seen` is optional (use `1` if you want to mark as active).
- Set `QDB_HOST` / `QDB_PORT` env vars if QuestDB is not on localhost:9000.
