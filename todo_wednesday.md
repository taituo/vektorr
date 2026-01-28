# TODO Wednesday 29.1.2026

## Phase 1: Solidify Data Foundation

### 1. Schema & Data Contract Upgrade (High Priority)
- Odds-schemasta puuttuu `line`, `point`, `is_suspended` -kentät
- Gate 2 (Market Safety) ei toimi ilman `is_suspended`-tietoa
- **Tehtävä:** Päivitä `schemas.py` ja Odds API -adapteri normalisoimaan nämä kentät
 - **Status:** DONE (line/point/is_suspended + QuestDB schema)

### 2. Robust Match Identity System
- Nykyinen team name + kickoff time -sovitus on hauras (Man Utd vs Manchester United)
- **Tehtävä:** Toteuta `match_map`-taulu (Provider ID -> Internal Match ID) tietokantaan
- **Status:** DONE (MatchResolver + match_map ILP)
- **Status:** DONE (TeamMapper normalisointi ennen ID-luontia)
- **Status:** DONE (mappings.yaml laajennettu EPL + La Liga)
- Varmistaa että SportMonks-eventit ja Odds API -kerroindata osuvat oikeaan otteluun

### 3. Ingestion Optimization (Filtering)
- Pollaus hakee liikaa irrelevanttia dataa
- **Tehtävä:** League-filtteröinti provider-adaptereihin (EPL, LaLiga, Serie A jne.)
- Fokus korkealaatuisiin markkinoihin
 - **Status:** SportMonks filtteri DONE; league-IDt vielä täyttämättä

### 4. Storage Performance
- Rivi-kerrallaan kirjoitus QuestDB:hen on tehotonta
- **Tehtävä:** Batch-kirjoitus tai bulk insert
 - **Status:** DONE (write_lines + batch käytössä)

---

## Seuraavat askeleet (uusi rakenne, ei koske MVP-koodia)

### 1. Mapping-workflow
- Match/team/market mapping + täyttötyökalut
 - **Status:** DONE (export/import työkalut), data täyttö puuttuu

### 2. Provider-konfigit
- SportMonks league-IDt
- Odds API sport keys
 - **Status:** Config‑pohja tehty, avaimet + IDt puuttuvat

### 3. Execution-service hardening
- QuestDB-logging
- Mapping-resoluutio stub
 - **Status:** mapping-resoluutio stub DONE, Betfair adapter edelleen stub

---

## Nykytila
- MVP toimii (paper trading, TPS, 5 gatea, lompakko, mock-data)
- Phase 1 scaffolding aloitettu (spine/, brain/, infra/questdb/)
- Git repo alustettu 28.1.2026
