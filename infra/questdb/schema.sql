-- QuestDB schema (optional). ILP can auto-create tables, but explicit DDL is recommended.

CREATE TABLE IF NOT EXISTS events (
  timestamp TIMESTAMP,
  match_id SYMBOL,
  team SYMBOL,
  event_type SYMBOL,
  xg DOUBLE,
  latency_ms LONG
) TIMESTAMP(timestamp) PARTITION BY DAY;

CREATE TABLE IF NOT EXISTS odds (
  timestamp TIMESTAMP,
  match_id SYMBOL,
  market SYMBOL,
  selection SYMBOL,
  price DOUBLE,
  is_suspended LONG,
  latency_ms LONG
) TIMESTAMP(timestamp) PARTITION BY DAY;

CREATE TABLE IF NOT EXISTS decisions (
  timestamp TIMESTAMP,
  match_id SYMBOL,
  reason SYMBOL,
  tps_label SYMBOL,
  market SYMBOL,
  selection SYMBOL,
  can_bet LONG,
  xg_10m DOUBLE,
  latency_p95 DOUBLE,
  odds_price DOUBLE,
  minute INT
) TIMESTAMP(timestamp) PARTITION BY DAY;

-- Mapping tables (provider -> canonical)
CREATE TABLE IF NOT EXISTS match_map (
  timestamp TIMESTAMP,
  provider SYMBOL,
  provider_match_id SYMBOL,
  match_id SYMBOL,
  kickoff TIMESTAMP,
  home SYMBOL,
  away SYMBOL
) TIMESTAMP(timestamp) PARTITION BY DAY;

CREATE TABLE IF NOT EXISTS team_map (
  timestamp TIMESTAMP,
  provider SYMBOL,
  provider_team_id SYMBOL,
  team_name SYMBOL,
  team_canonical SYMBOL
) TIMESTAMP(timestamp) PARTITION BY DAY;

CREATE TABLE IF NOT EXISTS market_map (
  timestamp TIMESTAMP,
  provider SYMBOL,
  provider_market_id SYMBOL,
  market SYMBOL,
  selection SYMBOL,
  line DOUBLE
) TIMESTAMP(timestamp) PARTITION BY DAY;

-- Manual execution log (optional)
CREATE TABLE IF NOT EXISTS manual_trades (
  timestamp TIMESTAMP,
  match_id SYMBOL,
  market SYMBOL,
  selection SYMBOL,
  price DOUBLE,
  stake DOUBLE,
  note SYMBOL
) TIMESTAMP(timestamp) PARTITION BY DAY;

CREATE TABLE IF NOT EXISTS executions (
  timestamp TIMESTAMP,
  match_id SYMBOL,
  market SYMBOL,
  selection SYMBOL,
  odds_price DOUBLE,
  status SYMBOL,
  reason SYMBOL
) TIMESTAMP(timestamp) PARTITION BY DAY;
