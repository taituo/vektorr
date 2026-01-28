# TODO Wednesday 29.1.2026

## Phase 1: Solidify Data Foundation

### 1. Schema & Data Contract Upgrade (High Priority)
- Odds-schemasta puuttuu `line`, `point`, `is_suspended` -kentät
- Gate 2 (Market Safety) ei toimi ilman `is_suspended`-tietoa
- **Tehtävä:** Päivitä `schemas.py` ja Odds API -adapteri normalisoimaan nämä kentät

### 2. Robust Match Identity System
- Nykyinen team name + kickoff time -sovitus on hauras (Man Utd vs Manchester United)
- **Tehtävä:** Toteuta `match_map`-taulu (Provider ID -> Internal Match ID) tietokantaan
- **Tehtävä:** Päivitä `spine/src/mapping.rs` käyttämään `TeamMapper`-logiikkaa (normalisointi ennen ID-luontia)
- **Tehtävä:** Täydennä `mappings.yaml` Valioliigan ja La Ligan joukkue-variaatioilla
- Varmistaa että SportMonks-eventit ja Odds API -kerroindata osuvat oikeaan otteluun

### 3. Ingestion Optimization (Filtering)
- Pollaus hakee liikaa irrelevanttia dataa
- **Tehtävä:** League-filtteröinti provider-adaptereihin (EPL, LaLiga, Serie A jne.)
- Fokus korkealaatuisiin markkinoihin

### 4. Storage Performance
- Rivi-kerrallaan kirjoitus QuestDB:hen on tehotonta
- **Tehtävä:** Batch-kirjoitus tai bulk insert

---

## Seuraavat askeleet (uusi rakenne, ei koske MVP-koodia)

### 1. Mapping-workflow
- Match/team/market mapping + täyttötyökalut

### 2. Provider-konfigit
- SportMonks league-IDt
- Odds API sport keys

### 3. Execution-service hardening
- QuestDB-logging
- Mapping-resoluutio stub

---

## Nykytila
- MVP toimii (paper trading, TPS, 5 gatea, lompakko, mock-data)
- Phase 1 scaffolding aloitettu (spine/, brain/, infra/questdb/)
- Git repo alustettu 28.1.2026
