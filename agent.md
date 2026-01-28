# BotBet – Agent & Codebase Guide

Live-vedonlyönnin päätösmoottori. Paper trading MVP + Phase 1 tuotantoinfra.

## Arkkitehtuuri

```
┌─────────────────────────────────────────────────────────┐
│  DATA SOURCES                                           │
│  SportMonks API · The Odds API · WebSocket · HTTP poll  │
└───────────────┬─────────────────────────────────────────┘
                │
        ┌───────▼───────┐
        │  SPINE (Rust)  │  Ingestor: normalisoi, deduplikoi, kirjoittaa
        │  spine/src/    │  QuestDB:hen ILP:llä + kutsuu Brain HTTP API:a
        └───────┬───────┘
                │
       ┌────────▼────────┐
       │  BRAIN (Python)  │  Päätöslogiikka: TPS + 5 hard gatea
       │  brain/          │  FastAPI-palvelu (port 8090)
       └────────┬────────┘
                │
       ┌────────▼────────┐
       │  EXECUTION       │  Betfair-adapteri (stub), dry-run, manual log
       │  execution/      │  Pollaa QuestDB:stä päätöksiä
       └────────┬────────┘
                │
        ┌───────▼───────┐
        │  QUESTDB        │  Aikasarjatietokanta (Docker)
        │  infra/questdb/ │  events, odds, decisions, mappings
        └───────────────┘
```

## Hakemistorakenne

```
├── main.py              # MVP entry point – 90min paper trading simulaatio
├── engine.py            # TPS-laskenta + gate-evaluointi (MVP)
├── schemas.py           # Pydantic: Event, Odds, MatchState
├── wallet.py            # PaperWallet + Trade-dataclass, P&L
├── execution.py         # ExecutionStub (fill/reject/slippage simulointi)
├── mock_provider.py     # Synteettinen otteludata testeihin
├── monitor.py           # Textual TUI dashboard (8 ottelua, account bar)
├── replay.py            # Backtesting: replay JSONL -> gate-analyysi
├── brain_api.py         # FastAPI päätöspalvelu (MVP-versio)
├── config.yaml          # Kynnysarvot (L_MAX, EV_MIN, XG_10M_MIN jne.)
├── mappings.yaml        # Team/league-nimien normalisointi (Pohjoismaat)
│
├── brain/               # Eriytetty päätösmoduuli (Phase 1)
│   ├── service.py       #   FastAPI + MatchBuffer + cleanup + manual bet
│   ├── engine.py        #   TPS + gates (kopio root engine.py:stä)
│   ├── schemas.py       #   Data contracts (kopio)
│   ├── mapping.py       #   EntityMapper – lataa mappings.yaml
│   └── execution_adapter.py  # ABC + ManualExecutionAdapter + StubAdapter
│
├── spine/               # Rust-ingestor (Phase 1)
│   ├── provider_config.example.yaml  # Provider-asetusten pohja (leagues/sports/keys)
│   ├── src/main.rs      #   CLI: --listen, --ws-url, --events-url, provider flags
│   ├── src/types.rs     #   Event, Odds structs (serde)
│   ├── src/ilp.rs       #   ILP-serialisointi (events, odds, decisions)
│   ├── src/questdb.rs   #   TCP-yhteys QuestDB ILP:hen (port 9009)
│   ├── src/brain.rs     #   BrainClient – HTTP POST /event, /odds
│   ├── src/match_id.rs  #   canonical_match_id(home, away, date)
│   ├── src/mapping.rs   #   provider_id -> match_id + TeamMapper (mappings.yaml)
│   ├── src/polling.rs   #   Deduper + backoff + rate limiting
│   ├── src/source/      #   jsonl.rs, http_poll.rs, ws.rs
│   └── src/providers/   #   sportmonks.rs, odds_api.rs
│
├── execution/           # Execution-palvelu (Phase 1)
│   ├── execution_service.py  # Pollaa QuestDB decisions -> execute
│   ├── betfair_adapter.py    # Betfair stub (ei toteutettu)
│   └── config.yaml           # QuestDB, risk, betfair -asetukset
│
├── infra/questdb/       # Tietokantainfra
│   ├── docker-compose.yml    # QuestDB + init-palvelu
│   ├── schema.sql            # events, odds(line/point), decisions, match_map, team_map
│   └── init.py               # Ajaa schema.sql QuestDB:hen
│
├── mapping/             # CSV-pohjat provider-mappingille (tyhjät)
│   ├── match_map.csv
│   ├── team_map.csv
│   └── market_map.csv
│
├── tools/               # Mapping-CSV workflow
│   ├── load_mapping.py      # CSV -> QuestDB
│   └── export_mapping.py    # QuestDB -> CSV
│
├── tests/
│   ├── test_engine.py        # TPS, gates, todennäköisyys (150+ riviä)
│   ├── test_wallet.py        # Trade, settle, summary
│   ├── test_execution.py     # Fill/reject/slippage
│   └── test_integration.py   # MockProvider + Engine roundtrip
│
├── docs/                # Docs + arkistoidut specs
│   ├── articles/        # Siirretyt spec-luonnokset
│   └── archive/         # Vanha futurespec ym.
├── legacy/              # Arkistoitu vanha koodi
│
├── mvp.md               # Pääspesifikaatio (~97KB)
├── after_mvp.md         # Mitä rakennettiin MVP:n jälkeen
├── futurespec.md        # Phase 2+ roadmap
├── currentfuturespec.md # Current spec (aligned to all.md)
├── delta_vision.md      # Gap analysis (futurespec vs all.md)
├── todo_wednesday.md    # Aktiivinen tehtävälista
└── .gitignore
```

## Päätöslogiikka (engine.py)

### TPS (Threat Pressure Score)
Luokittelee ottelutilanteen neljään tasoon:
- **LOW** – vähän tapahtumia, matala xG
- **MID** – kohtuullinen aktiivisuus
- **PRESS** – korkea xG-summa tai paljon vaarallisia hyökkäyksiä
- **CHAOS** – punainen kortti TAI molemmat joukkueet + 4+ vaarallista hyökkäystä

### 5 Hard Gatea (kaikki pitää läpäistä)
1. **Latency** – event latency p95 ≤ L_MAX (3.0s)
2. **Market Safety** – `is_suspended == false`
3. **Quality** – TPS ei LOW
4. **xG Minimum** – viimeisen 10min xG ≥ XG_10M_MIN (0.2)
5. **Expected Value** – `(p_model × price) - 1 ≥ EV_MIN` (0.05)

Todennäköisyysmalli: Poisson `p = 1 - exp(-xg_rate × tau)`, tau = jäljellä oleva peliaika.

## Konfiguaatio (config.yaml)

| Avain | Oletus | Kuvaus |
|-------|--------|--------|
| L_MAX | 3.0 | Latenssin yläraja (s) |
| EV_MIN | 0.05 | Minimi EV (5%) |
| XG_10M_MIN | 0.2 | Minimi xG / 10min |
| MAX_BETS_PER_MATCH | 1 | Vedot per ottelu |
| REJECT_RATE | 0.20 | Simuloidun hylkäyksen todennäköisyys |
| MAX_SLIPPAGE | 0.10 | Maksimihinnan liukuma |
| WALLET_START | 1000.0 | Aloitussaldo |
| STAKE | 10.0 | Kiinteä panos |

## Data Flow

```
Provider API
  → Spine (Rust): normalisoi, deduplikoi, ILP-kirjoitus
    → QuestDB: events, odds taulut
    → Brain (Python): /event, /odds endpointit
      → Engine: TPS + gates → DecisionResponse
        → decisions.jsonl + QuestDB decisions -taulu
          → Execution: pollaa decisions → execute → trade_log
```

## Käynnistys

```bash
# MVP (paper trading, mock data)
python main.py

# Brain API
uvicorn brain.service:app --port 8090

# QuestDB
cd infra/questdb && docker compose up -d

# Spine (esimerkkejä)
cd spine && cargo run -- --listen 0.0.0.0:8080 --qdb-host localhost
cargo run -- --sportmonks-token XXX --sportmonks-leagues 271,501
cargo run -- --odds-api-key XXX --odds-api-sports soccer_epl
cargo run -- --provider-config provider_config.yaml --brain-url http://localhost:8090

# Monitor TUI
python monitor.py

# Replay/backtest
python replay.py events_log.jsonl odds_log.jsonl
```

## Testit

```bash
pytest tests/ -v
python test_integration.py  # E2E: käynnistää brain_api:n subprosessina
```

## Tunnetut rajoitukset

- Vain OU_2.5 OVER -markkina tuettu
- Poisson-malli yksinkertaistettu (ei pelaajatason dataa)
- brain_api.py: globaali state ei thread-safe
- Betfair-adapteri on stub (ei toteutettu)
- Mapping-CSV workflow on olemassa, mutta CSV:t pitää yhä täyttää
- Provider-konfigi on pohjana; league-IDt ja API-avaimet puuttuvat
- Execution käyttää market_mapia vain market+selection -tasolla (selection_id puuttuu)
- TeamMapper (mappings.yaml) kattaa vain osan liigoista
- Ei liability-seurantaa tai cross-match exposure -rajoituksia
- Flat staking (ei Kelly-kriteeritä)

## Aktiiviset prioriteetit (todo_wednesday.md)

1. **Schema upgrade** – `line`, `point`, `is_suspended` kentät (done)
2. **Match identity** – provider ID → internal match ID + TeamMapper (done)
3. **League filtering** – SportMonks filtteri done; league-IDt vielä täyttämättä
4. **Batch writes** – QuestDB batch insert (done)
5. **Mapping workflow** – CSV import/export tools (done), data täyttö puuttuu
6. **Provider configs** – config‑pohja tehty, avaimet + IDt puuttuvat
7. **Execution hardening** – QuestDB‑logging ok, mapping‑resoluutio vielä stub
