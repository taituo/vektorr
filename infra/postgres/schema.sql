-- Postgres schema for mapping + execution (optional)

CREATE TABLE IF NOT EXISTS match_map (
  id BIGSERIAL PRIMARY KEY,
  provider TEXT NOT NULL,
  provider_match_id TEXT NOT NULL,
  match_id TEXT NOT NULL,
  kickoff TIMESTAMPTZ,
  home TEXT,
  away TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS match_map_provider_idx
  ON match_map(provider, provider_match_id);

CREATE TABLE IF NOT EXISTS team_map (
  id BIGSERIAL PRIMARY KEY,
  provider TEXT NOT NULL,
  provider_team_id TEXT NOT NULL,
  team_name TEXT,
  team_canonical TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS team_map_provider_idx
  ON team_map(provider, provider_team_id);

CREATE TABLE IF NOT EXISTS market_map (
  id BIGSERIAL PRIMARY KEY,
  provider TEXT NOT NULL,
  provider_market_id TEXT NOT NULL,
  market TEXT NOT NULL,
  selection TEXT NOT NULL,
  line DOUBLE PRECISION,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS market_map_provider_idx
  ON market_map(provider, provider_market_id, selection, line);

CREATE TABLE IF NOT EXISTS manual_trades (
  id BIGSERIAL PRIMARY KEY,
  match_id TEXT NOT NULL,
  market TEXT,
  selection TEXT NOT NULL,
  price DOUBLE PRECISION,
  stake DOUBLE PRECISION,
  note TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);
