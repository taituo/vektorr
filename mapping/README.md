# Mapping Files

These CSVs are used to bridge provider IDs to canonical IDs.
Populate them before enabling automated execution.

## Files
- `match_map.csv`: provider match → canonical match
- `team_map.csv`: provider team → canonical team
- `market_map.csv`: provider market → canonical market/selection

## Example flow
1) Export provider IDs (SportMonks / Odds API)
2) Normalize names (home/away)
3) Fill CSVs
4) Load into QuestDB using `tools/load_mapping.py`
