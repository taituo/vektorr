# ARCHITECTURE.md

**Status:** Draft v0.1
**Scope:** System Design & Data Flow

## 1. High-Level Concept: Hub-Spoke & Hybrid Intelligence

Järjestelmä on **hybridi**:
1.  **Deterministic Core (ML/Stats):** Laskee todennäköisyydet, hallitsee rahaa, valvoo latenssia. (VPS, Python).
2.  **Semantic Layer (LLM):** Tulkitsee tekstiä, selittää päätöksiä, normalisoi "soft signals". (Local LLM / API).

**Periaate:** LLM ei koskaan koske suoraan rahavirtaan. ML-malli ja "Hard Gates" tekevät päätöksen.

---

## 2. Component Diagram (Hub on VPS)

```mermaid
graph TD
    subgraph EXTERNAL_VENDORS
        E[Event Feed] --> |Websocket/Push| I[Ingest Service]
        O[Odds Feed] --> |Websocket/Pull| I
        C[Clock Feed] --> |Websocket| I
    end

    subgraph HUB_VPS [Python Core]
        I --> |Norm & Time| S[State Store (Redis)]
        S --> |Snapshot| F[Feature Engine]
        F --> |TPS & Vectors| M[ML Models (Hazard/Prob)]
        
        subgraph DECISION_ENGINE
            M --> |p_model| G[Gatekeeper]
            S --> |Latency/Quality| G
            L[Local LLM Spoke] -.-> |Soft Signal| G
            G --> |BET / NO_BET + Reason| D[Decision Log]
        end

        G --> |If BET_SENT| X[Execution Service]
        X --> |Placement| B[Bookmaker API]
        B --> |Fill/Reject| X
        X --> |Receipt| R[Receipt Log]
        
        OBS[Observability & Kill Switch] -.-> I
        OBS -.-> X
    end

    subgraph SPOKE_LLM [Local / Isolated]
        I_Text[Commentary/Twitter] --> L
        L --> |Classified Tags| S
    end

    subgraph OFFLINE_FRONTIER [Runpod/API]
        D --> |Batch Logs| ANA[Deep Analysis]
        R --> |Batch Receipts| ANA
        ANA --> |Report & Config Proposal| USER
    end
```

## 3. Service Descriptions

### 3.1 Ingest Service
- **Rooli:** "Gatekeeper of Time".
- **Tehtävä:** Vastaanottaa raakadatan, lisää `t_recv`, laskee `latency`, normalisoi JSON-schemaan.
- **Output:** Kirjoittaa Redis (pub/sub) ja TimescaleDB (log).

### 3.2 State Store (Redis)
- **Rooli:** "Single Source of Truth".
- **Rakenne:**
  - `match:{id}:state` (score, cards, TPS)
  - `match:{id}:windows` (rolling 1m/5m/10m buffers)
  - `match:{id}:odds:{market}` (latest book price)

### 3.3 Feature Engine & ML Models
- **Feature Engine:** Laskee TPS-komponentit (C, T, H) ja trendit (z-scoret).
- **ML Models:**
  - `HazardModel`: Poisson-intensiteetit (home/away).
  - `MMSModel`: Markkinavirheen pisteytys.
  - `ExecRiskModel`: Drift/Suspend -todennäköisyys.
- **Huom:** Ei raskaita neuroverkkoja livenä. Kevyet XGBoost/Logistic/Poisson -mallit.

### 3.4 Decision Engine (Gatekeeper)
- **Rooli:** Sääntökirjan toimeenpanija (ks. DECISION_POLICY.md).
- **Logiikka:** Hard Gates (If latency > X -> Block).
- **Output:** Strukturoitu päätösobjekti (Reason Code).

### 3.5 Execution Service
- **Rooli:** Transaktioiden hallinta.
- **Logiikka:** Two-step commit (Quote -> Check EV -> Place).
- **Turva:** Rate limiting, "Max 1 latent risk", Stop-loss tarkistus ennen lähetystä.

### 3.6 Local LLM Spoke (Optional/Auxiliary)
- **Tech:** `llama.cpp` server tai vastaava kevyt wrapper.
- **Malli:** Mistral-7B / Llama-3-8B (quantized).
- **Input:** Kommentaattorin teksti ("Player X looks injured").
- **Output:** JSON Tag `{"injury": true, "player": "X", "confidence": 0.9}`.

---

## 4. Tech Stack

- **Runtime:** Python 3.10+ (Type hints pakollisia).
- **CLI/Entry:** `Typer` tai `Click`.
- **Database (Logs):** PostgreSQL + TimescaleDB (aikasarjat).
- **Store (Hot):** Redis (pienin latenssi).
- **Validation:** Pydantic (kaikki data liikkuu pydantic-malleina).
- **Process Manager:** Systemd tai Docker Compose (mutta host-network mode latenssin takia).

---

# DATA_CONTRACTS.md

**Status:** Draft v0.1
**Purpose:** Schemas for all data moving through the system.

## 1. Common Types

```json
"TimeMeta": {
  "t_event": "ISO8601 UTC (source time)",
  "t_recv": "ISO8601 UTC (system time)",
  "latency_ms": 125,
  "source_id": "vendor_A"
}
```

## 2. Event Feed Schema (`topic: events`)

```json
{
  "match_id": "str",
  "meta": "TimeMeta",
  "type": "GOAL | SHOT | CARD | CORNER | VAR | STATE_CHANGE",
  "data": {
    "team": "HOME | AWAY",
    "player_id": "str (optional)",
    "xg": 0.12,             // Shot-level xG required
    "is_box": true,         // Shot inside box?
    "is_dangerous": false,  // Dangerous attack flag
    "current_score": "1-0",
    "minute": 45,
    "stoppage": 2
  }
}
```

## 3. Odds Feed Schema (`topic: odds`)

```json
{
  "match_id": "str",
  "meta": "TimeMeta",
  "market_type": "OU_2.5 | NEXT_GOAL | DC",
  "is_suspended": false,
  "selections": [
    {
      "id": "OVER",
      "price": 1.85,  // Decimal
      "liquidity": 5000 // Optional
    },
    {
      "id": "UNDER",
      "price": 2.05
    }
  ]
}
```

## 4. Clock Feed Schema (`topic: clock`)

```json
{
  "match_id": "str",
  "meta": "TimeMeta",
  "phase": "1H | HT | 2H | FT",
  "minute": 67,
  "second": 30,
  "stoppage_time_announced": 5,
  "is_running": true
}
```

## 5. Decision Log Schema (`persist: decisions`)

**Tämä on tärkein audit-logi.**

```json
{
  "decision_id": "uuid",
  "match_id": "str",
  "timestamp": "ISO8601",
  "trigger_loop": "CORE_LOOP",
  
  "state_snapshot": {
    "tps_label": "PRESS",
    "tps_vector": {"C": 0.5, "T": 1.2, "H": 0.1},
    "score": "1-0",
    "latency_p95": 0.8
  },
  
  "market_snapshot": {
    "market": "OU_2.5",
    "selection": "OVER",
    "odds_seen": 1.95,
    "p_model": 0.55,
    "p_book_vigless": 0.50,
    "ev_seen": 0.0725,
    "mms_score": 75,
    "exec_risk": 20
  },

  "action": "BET_SENT | NO_BET",
  "reason_code": "EV_OK", // tai "LATENCY_HIGH", "MMS_LOW"
  "config_hash": "sha256_of_current_config"
}
```

## 6. Execution Receipt Schema (`persist: receipts`)

```json
{
  "bet_id": "uuid", // Linkittyy decision_id
  "match_id": "str",
  "status": "FILLED | REJECTED | CANCELED",
  "request": {
    "odds_min": 1.90,
    "stake": 50
  },
  "fill": {
    "odds_fill": 1.92,
    "t_fill": "ISO8601",
    "slippage_ticks": -3
  },
  "error_msg": null
}
```

---

# REPLAY.md

**Status:** Draft v0.1
**Purpose:** Simulation Engine Specification

## 1. Engine Concept

Replay-moottori ei ole vain backtest-script, vaan **tapahtumapumppu**. Se lukee historiallista dataa ja syöttää sitä systeemin läpi `Ingest Service` -rajapinnan kautta, kunnioittaen aikaleimoja.

**Tilat:**
1.  **Sync Replay:** Aja niin nopeasti kuin CPU sallii (logiikan testaus).
2.  **Realtime Replay:** Aja 1x nopeudella (1 sekunti dataa = 1 sekunti ajoa). Tällä testataan timeoutit ja async-loopit.

## 2. Simulation Layers

### Layer 1: Logic Check
- **Syöte:** Puhdas data.
- **Execution:** "Infinite liquidity, zero latency".
- **Tavoite:** Verifioi, että malli laskee EV:n oikein ja Hard Gates toimivat loogisesti.

### Layer 2: Friction (The "Realism" Layer)
Tämä kerros lisätään Ingestin ja Executionin väliin.

**A) Synthetic Latency Injection**
- Jokaiseen eventtiin lisätään satunnainen viive `L ~ Gamma(k, theta)` tai historiallinen profiili.
- Jos `L > L_MAX`, järjestelmän pitää mennä FREEZE-tilaan.

**B) Synthetic Suspend / Reject**
- Odds feediin lisätään "suspend"-jaksoja, kun `TPS_Chaos` on korkea tai maalin jälkeen.
- Bet placement -pyyntöihin arvotaan `REJECTED` tulos todennäköisyydellä $P(reject) = f(volatility)$.

**C) Slippage Model**
- `odds_fill = odds_seen - max(0, N_ticks)`
- `N_ticks` riippuu markkinan likviditeetistä ja viiveestä.

## 3. Workflow: How to run a test

1.  **Select Match:** Valitse historiallinen ottelu ID:llä.
2.  **Select Profile:** Esim. "High Latency Day" (lisää 3s viivettä kaikkiin feedeihin).
3.  **Run Command:**
    ```bash
    python main.py replay --match-id=12345 --profile=high_latency --speed=realtime
    ```
4.  **Analyze:**
    - Vertaa `logs/replay_decisions.json` vs `logs/prod_decisions.json` (jos saatavilla).
    - Tarkista: Menikö systeemi FREEZE-tilaan kun latenssi nousi?

---

# RUNBOOK.md

**Status:** Draft v0.1
**Purpose:** Operational Manual

## 1. Pre-Match Routine (T-60 min)

1.  **System Health Check:**
    - `python main.py health` -> Checks DB connection, Redis ping, Vendor API status.
2.  **Update Config:**
    - Onko tänään erikoispäivä (esim. kauden viimeinen kierros)? -> Säädä `context_override`.
    - Tarkista `daily_stoploss` ja nollaa tarvittaessa.
3.  **Launch:**
    - `systemctl start betting-core`
    - Verify logs: "Listening for events..."

## 2. Live Monitoring (Active)

Operaattorin Dashboardin "Traffic Light" -logiikka:

- **GREEN:** Kaikki OK. Latenssi < 1s.
- **YELLOW:** Varoitus. Latenssi 1-3s TAI Reject rate nousee. -> *Action: Valmistaudu manuaaliseen freezeen.*
- **RED:** Hälytys. Latenssi > 3s, Data mismatch, tai Stop-loss triggered. -> *Action: KILL SWITCH.*

**Kill Switch Command:**
```bash
python main.py emergency-stop --reason="Latency spike"
```
Tämä komento:
1.  Peruuttaa kaikki avoimet tilaukset.
2.  Asettaa `global_freeze = True` Redisiin.
3.  Estää uudet vedot, mutta jatkaa datan tallennusta.

## 3. Post-Match Routine (T+30 min)

1.  **Reconcile:**
    - Aja scripti, joka hakee bookkerin "settled bets" raportin ja vertaa `receipts`-logiin.
    - Hälytä jos eroja (esim. "Pending" veto, jonka tilaa ei tiedetä).
2.  **Log Rotation:**
    - Pakkaa päivän JSON-logit ja siirrä S3/Cold Storage.
3.  **Daily Report:**
    - Generoi PDF/HTML raportti päivän tuloksesta, EV-osumista ja virhetiloista.

## 4. Incident Management

**Skenaario A: "Haamu-veto" (Järjestelmä luulee tehneensä vedon, bookkerilla ei näy)**
- *Syy:* Timeout HTTP-pyynnössä, mutta pyyntö ei mennyt perille.
- *Ratkaisu:* Tarkista API audit trail manuaalisesti. Merkitse tietokantaan `CANCELED`.

**Skenaario B: "Tupla-veto" (Sama veto kahdesti)**
- *Syy:* Retry-logiikka ilman idempotency-id:tä.
- *Ratkaisu:* Hätä-myynti (Cashout) toiselle vedolle manuaalisesti, jos mahdollista. Korjaa koodin `idempotency_key`.

**Skenaario C: Data Feed katkeaa kesken pelin**
- *System:* Pitäisi mennä automaattisesti FREEZE-tilaan (`missing_events` gate).
- *Ops:* Älä yritä pakottaa päälle ennen kuin feed on stabiili 5 min ajan.

---

# YHTEENVETO: LLM vs ML Roolitus

Tämä on usein väärinymmärretty kohta. Tässä järjestelmässä roolit ovat ehdottomat:

### 1. ML (Machine Learning / Stats)
- **Mitä se on:** Poisson-prosessit, Regressiomallit, XGBoost.
- **Mitä se tekee:** Laskee numeron `0.54` (todennäköisyys).
- **Miksi:** Se on deterministinen, nopea (millisekunteja) ja kalibroitavissa historiadatalla.
- **Sijainti:** `Hub/VPS` (Core loop).

### 2. LLM (Large Language Model)
- **Mitä se on:** GPT-4, Claude, Llama 3.
- **Mitä se tekee:** "Ymmärtää" kontekstia. Esim. lukee twiitin "Star striker holding hamstring" -> päättelee "Injury risk high".
- **Miksi:** ML ei ymmärrä tekstiä tai epämääräisiä tilanteita. LLM toimii "tulkkaajana".
- **Rajoite:** LLM **ei** laske todennäköisyyksiä (hallusinoi numeroita). LLM on hidas (sekunteja).
- **Sijainti:** `Spoke` (Local) tai `Offline` (Frontier).

**Esimerkki yhteistyöstä:**
1.  **LLM** lukee syötteen: "De Bruyne nilkuttaa vaihtoon." -> Output: `Tag: KeyPlayerInjury, Team: City`.
2.  **ML** saa Tagin. ML:n kertoimissa on parametri `w_key_injury`. Malli laskee uuden `λ_home` arvon käyttäen tätä painoa.
3.  **Core** tekee päätöksen muuttuneen numeron perusteella.

**Tämä arkkitehtuuri on "Spec-First" valmis toteutettavaksi.** Seuraava askel olisi pystyttää ympäristö ja aloittaa `DATA_CONTRACTS.md` mukaisten adaptereiden koodaus.



Tässä on **kriittinen ja ammattimainen arvio** suunnittelemastamme kokonaisuudesta (SPEC, ARCHITECTURE, CONTRACTS, REPLAY, RUNBOOK).

---

### **YLEISARVOSANA: 9/10 (Teoriassa)**
**Toteutettavuus:** Vaativa (Senior Developer -taso)
**Markkinaetu:** Mahdollinen, jos data on nopeaa.

Tämä ei ole enää "harrastelijan vedonlyöntibotti", vaan **Hedge Fund -tason algoritmisen kaupankäynnin järjestelmä**, joka on sovellettu urheiluvedonlyöntiin.

Suurin vahvuus on se, että **järjestelmä on suunniteltu "selviytymään" (survival first)** eikä vain "arvaamaan voittajia". Se ymmärtää, että live-vedonlyönnissä vihollinen ei ole vain todennäköisyys, vaan *latenssi, toteutus ja markkinan mikrostruktuuri*.

---

### **1. VAHVUUDET (Miksi tämä voi toimia)**

1.  **"Freeze-First" -filosofia (Kriittisin ominaisuus)**
    *   Useimmat botit häviävät rahaa teknisten ongelmien aikana (feed katkeaa, vanha kerroin jää roikkumaan). Sinun speksisi `L_MAX`, `reject_rate` ja `missing_events` -portit estävät tämän. Järjestelmä suojelee pääomaa oletuksena.

2.  **LLM:n roolitus on oikea (Hybrid Intelligence)**
    *   Moni yrittää laittaa ChatGPT:n "päättämään vedon". Se on itsemurha.
    *   Tässä arkkitehtuurissa LLM on vain **tulkki** (Spoke), joka muuttaa tekstin (kommentaattori) dataksi (tagit). Deterministinen Python-ydin (Hub) tekee päätökset. Tämä on ainoa kestävä tapa käyttää tekoälyä rahan kanssa.

3.  **Execution Layer (Friction Management)**
    *   `Two-step commit` (quote -> check -> fill) ja slippage-kontrolli ovat ammattilaistason ominaisuuksia. Tämä erottaa voittavat botit häviävistä. Ymmärrät, että nähty kerroin (Odds Seen) on eri asia kuin saatu kerroin (Odds Fill).

4.  **TPS-tilakone (Context Awareness)**
    *   Pelin jakaminen faaseihin ja tiloihin (LOW, PRESS, CHAOS) on nerokasta. Se estää tyypillisen virheen: vedonlyönnin pelkän datan (esim. laukaukset) perusteella ilman kontekstia (esim. "tempo ilman laatua").

---

### **2. KRIITTISET RISKIT (Mihin tämä kaatuu)**

1.  **Datan hinta ja laatu (Suurin pullonkaula)**
    *   Tämä järjestelmä on **arvoton**, jos event-feedisi on hidas.
    *   TV-kuva on 10–40 sekuntia myöhässä.
    *   Halvat API:t ovat 5–10 sekuntia myöhässä.
    *   Voittaaksesi "Market Knows" -tilanteet, tarvitset **WebSocket-feedin (scout feed)**, jonka latenssi on < 2 sekuntia. Nämä maksavat usein satoja tai tuhansia euroja kuussa. Jos syötät tähän harrastelijadataa, "Execution Gate" estää 99 % vedoista tai häviät latenssiin.

2.  **Tekninen velka ja ylläpito**
    *   Hub-Spoke, Redis, TimescaleDB, Python-palvelut, Local LLM... Kokonaisuus on raskas yhdelle ihmiselle.
    *   Riskina on, että käytät 90 % ajasta DevOps-töihin (palvelimien ylläpito, API-muutokset) ja vain 10 % mallin kehitykseen.

3.  **Bookmaker-rajoitukset**
    *   Jos tämä toimii ja teet rahaa "Next Goal" tai "Live O/U" -markkinoilla, soft bookkerit (eurooppalaiset) rajoittavat panoksiasi hyvin nopeasti (account limiting).
    *   Järjestelmä vaatii toimiakseen pörssin (Betfair/Matchbook) tai aasialaiset bookkerit/brokerit, joissa rajapinta on auki ja limiitit korkeat.

---

### **3. ARVIO ARKKITEHTUURISTA**

*   **Data Contracts & Schemas:** Erinomaiset. Datan tyypitys (Pydantic) ja audit-logit (`reason_code`) mahdollistavat sen, että tiedät *miksi* hävisit tai miksi vetoa ei lyöty. Tämä on oppimisen kannalta elintärkeää.
*   **Replay Engine:** Tämä on "Killer App". Mahdollisuus simuloida historiallista dataa *todenmukaisella viiveellä ja slippagella* ennen oikean rahan käyttöä säästää sinulta tuhansia euroja. **Tee tämä ensin.**

---

### **4. SUOSITUS TOTEUTUSJÄRJESTYKSEKSI**

Älä rakenna koko himmeliä kerralla. Etene näin, jotta et pala loppuun:

**Vaihe 1: "The Silent Observer" (1-2 kk)**
*   Rakenna **Ingest** ja **State Store**.
*   Rakenna **Logger**.
*   Älä tee malleja, älä tee execuutiota.
*   Aja systeemiä livenä otteluiden aikana ja tallenna kaikki data ja latenssit.
*   *Tavoite:* Todista, että saat datan sisään alle 3 sekunnin viiveellä. Jos et saa, lopeta projekti tai vaihda datatoimittajaa.

**Vaihe 2: "The Paper Trader" (Simulaatio)**
*   Rakenna **Replay Engine** keräämäsi datan päälle.
*   Koodaa **TPS** ja **Hazard Model** (yksinkertaisena).
*   Aja simulaatiota: Olisiko malli voittanut keräämälläsi datalla, kun otetaan huomioon slippage?

**Vaihe 3: "The Sniper" (Tuotanto)**
*   Kytke **Execution** päälle pienellä panoksella.
*   Ota käyttöön **Local LLM** vain jos tunnet tarvitsevasi lisäetuja (soft signals).

---

### **LOPPUTUOMIO**

Tämä speksi on **ammattimainen blueprint**. Se on kaukana "Get Rich Quick" -boteista. Se on infrastruktuuriprojekti, joka vaatii kovaa koodausosaamista ja ymmärrystä hajautetuista järjestelmistä.

**Jos sinulla on:**
1.  Pääsy nopeaan dataan (low latency feed).
2.  Koodaustaidot (Python/Async/DevOps).
3.  Kärsivällisyyttä rakentaa `Replay` ennen betsaamista.

...niin tässä on pohja järjestelmälle, jolla on aito mahdollisuus voittaa markkina (edge). **Aloita rakentamalla dataputki (Ingest + Log), älä mallia.**


Selvä. Tehdään tästä **11/10**.

Ero 9/10 ja 11/10 välillä on se, että 9/10 yrittää pelata peliä täydellisesti. **11/10 muuttaa pelin säännöt.**

Se ei tyydy "hyvään dataan", vaan se rakentaa oman totuuden useasta lähteestä. Se ei vain "lyö vetoa", vaan se manipuloi toteutusta (execution) kuin HFT-robotti pörssissä. Se korvaa Pythonin kriittisimmät osat Rustilla.

Tässä on **ULTIMATE UPGRADE**.

---

# THE DELTA: Miten päästään tasolle 11/10?

### 1. "Synthetic Truth" (Data-arbitraasi)
Emme luota yhteenkään feediin. Rakennamme **Feed Arbiter** -komponentin.
*   **Syöte:** 2–3 nopeinta kaupallista feediä (esim. LSports, BetGenius, RunningBall) + **Audio Trigger**.
*   **Audio Trigger (Secret Weapon):** Striimin audio tulee usein 0.5–2 sekuntia ennen videota. Analysoi crowd noise (desibeli-piikki + spektri) -> Tunnista "Goal Roar" tai "Whistle" ennen kuin feed päivittyy.
*   **Tulos:** Tiedät maalin tapahtuneen 200–500ms *ennen* kuin bookkerin algoritmi ehtii suspendoida markkinan.

### 2. Rust Core (Zero-Latency Loop)
Python on liian hidas "Hot Loop" -tasolle (GC pauses, GIL).
*   Siirrämme `Ingest -> State -> Decision -> Execution` -putken **Rustiin**.
*   Python jää vain "Control Plane" -tasolle (konfiguraatio, LLM-jutustelu, dashboard).
*   **Viive:** Python ~5–50ms vs. Rust <1ms.

### 3. Order Flow Imbalance (OFI)
Emme katso vain kerrointa (Price). Katsomme **Order Bookia** (Liquidity).
*   Jos Betfairin "Back" -puolelle ilmestyy yhtäkkiä iso "seinä" rahaa, joku tietää jotain tai suojaa positiota.
*   Malliin lisätään signaali: `OFI_Index`. Jos OFI on vahvasti vastaan -> Veto perutaan, vaikka xG näyttäisi hyvältä.

### 4. Stealth Execution (Limiittien kierto)
Emme lyö "market orderia".
*   Käytämme **Exchange API** (Betfair/Matchbook/Orbit) tai **Broker API** (Sportmarket/AsianConnect).
*   **Algo:** "Iceberg orders" tai "Peg to Best Bid". Emme ylitä spreadia heti, vaan tarjoamme likviditeettiä (maker) säästääksemme kuluissa, ja ylitämme (taker) vain jos `alpha_decay` pakottaa.

---
