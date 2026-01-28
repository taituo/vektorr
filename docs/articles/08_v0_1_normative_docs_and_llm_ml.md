# ARCHITECTURE.md (v0.1)

## 1) Tavoite ja periaatteet

**Tavoite:** live-only päätöskone, joka tuottaa *auditoitavat* NO_BET/BET-päätökset ja suojaa toteutusriskiltä (suspend/slippage/reject/latency).

**Ei-neuvoteltavat periaatteet**

* **NO BET on oletus.**
* **Fill on raha-totuus** (execution receipt).
* **Event feed on pelitilan totuus** (ei TV/kommentaattori).
* **Freeze-first**: kun datan tai toteutuksen laatu heikkenee, järjestelmä jäädyttää mieluummin kuin “pakottaa edgeä”.
* **Determinismi**: sama input + sama config ⇒ sama päätös.
* **LLM ei koskaan triggeröi vetoa.** LLM on vain soft-signal/ops.

---

## 2) Topologia: Hub–Spoke–Frontier

### 2.1 Hub (VPS) – “totuus & raha”

**Vastuut**

* Ingestointi (event/odds/clock), normalisointi, dedupe, aikaleimat/latency
* State store (match lifecycle, rolling windows 1/5/10)
* Feature/TPS (C/T/H + label)
* Mallit (hazard, MMS, exec-risk)
* Decision engine (hard gates + reason_code)
* Execution (two-step commit, receipts, fill gate)
* Observability (metrics, alerts, freeze, stop-edge)
* Replay (paper/live-replay samalla pipelinellä)

### 2.2 Spoke (VPS) – Local LLM “soft-signal”

**Vastuut**

* Tekstin luokittelu → tagit: injury/tactical_shift/intensity + confidence
* Incident-raporttien luonnit (ihmisluettava)
* Selitykset “miksi NO BET” (reason_code + tilannekuva)
  **Rajoite:** ei saa muuttaa match state -totuutta; tuottaa vain *soft_signal* -objektin.

### 2.3 Frontier (Runpod) – offline analyysi

**Vastuut**

* Viikkoraportit, root-cause -klusterointi, ehdotukset config-muutoksiksi
* Laajempi “what changed?” (data vendor drift, market regime)
  **Rajoite:** ei online-käyttöä päätösputkessa.

---

## 3) Komponentit (Hub) ja rajapinnat

### 3.1 Ingest (event/odds/clock)

* Adapterit lähteittäin
* Normalisointi yhteiseen schemaan (DATA_CONTRACTS)
* Deduplikointi: event_id + source_id + timestamp-ikkuna
* QoF-mittarit: latency/jitter/missing

**Output:** NormalizedEvent / NormalizedOddsQuote / NormalizedClockTick

### 3.2 State Store (totuuskerros)

* Match lifecycle: PRE / LIVE_ACTIVE / LIVE_FROZEN / HT / END
* Rolling windows: 1m/5m/10m aggregaatit
* Last-known-good snapshots (palautuminen freeze-tilasta)

**Output:** MatchStateSnapshot (atominen, versioitu)

### 3.3 Feature Engine

* TPS: Phase, C, T, H, Label
* Trend features: slope/mean/z (1/5/10)
* Disconfirm flag (10m vs 1/5m)

**Output:** FeatureSnapshot

### 3.4 Model Layer

* Pre-model → base_home/base_away + prior match type
* Live hazard → p_model per market/selection
* MMS → 0..100 + komponentit
* Exec-risk → R_exec + komponentit

**Output:** ModelSnapshot (p_model/p_book/EV/MMS/R_exec)

### 3.5 Decision Engine (ainoa betin portti)

* Evaluoi gate-ketjun G1..G8 (SPEC)
* Asettaa action: NO_BET/BET_SENT
* Aina reason_code (myös NO_BET; myös “blocked”)

**Output:** DecisionTick (täydellinen audit-rivi)

### 3.6 Execution Engine

* Two-step commit: seen → attempt → receipt(fill/reject/cancel)
* Fill gate: EV_fill ≥ α·EV_seen ja slippage ≤ SLIP_MAX
* Rate limit: max 1–2 vetoa/ottelu, max 1 latent

**Output:** ExecutionReceipt + ExecutionMetrics

### 3.7 Observability / Control Plane

* Metrics (METRICS.md), dashboard (DASHBOARD.md)
* Alertit → freeze/cooldown/stop-edge
* Manual kill switch, safe mode

---

## 4) Prosessit: PRE / LIVE / POST

### PRE

* Pre-model ajot
* Source health-check
* MatchConfig snapshot (immutable per day)

### LIVE

* Ingest → State → Features → Models → Decisions (30–60s core)
* Fast safety loop (1–5s): freeze triggers
* Execution vain gatejen läpi

### POST

* Reconcile (tulokset, receipts)
* CLV, calibration, failure modes
* Weekly report + config change proposals (ei auto-apply)

---

## 5) Versiointi ja determinismi

* Kaikki kynnysarvot “config_version hash”
* DecisionTick sisältää: config_hash + data_source_versions
* Replay vaatii identtiset versiot determinismitestiin (T10)

---

# DATA_CONTRACTS.md (v0.1)

## 0) Yleiset säännöt (pakolliset)

* Kaikilla riveillä: `match_id`, `source_id`, `t_event` (tai `t_seen`), `t_recv`
* Aikaleimat: UTC ISO-8601
* Viive: `latency_sec = t_recv - t_event` (tai t_seen)
* Kaikilla objekteilla: `schema_version`
* “Truth layers”:

  * Event/Clock: pelitila-totuus
  * Receipt: raha-totuus
  * OddsQuote: markkina-havainto (ei totuus, vaan havainto)

---

## 1) Identiteetit ja mapitus

### 1.1 match_id (hubin master-id)

Kentät (MatchIdentity):

* match_id (string, unique)
* league (enum: EPL, LALIGA)
* kickoff_utc (datetime)
* home_team_id, away_team_id (string)
* home_team_name, away_team_name (string)
* venue_id (optional)
* mapping_confidence (0..1)
* source_match_ids[] (list: vendor-specific ids)

**Sääntö:** ilman varmaa match-id mapitusta → match jäädytetään (NOT_LIVE_ACTIVE / FEED_MISMATCH_CRITICAL).

---

## 2) Event feed: NormalizedEvent

### 2.1 Yleiskentät

* schema_version
* event_id (string; dedupe key yhdessä source_id:n kanssa)
* match_id
* source_id
* t_event (datetime)
* t_recv (datetime)
* latency_sec (float)
* period (enum: 1H, 2H)
* minute (int)
* stoppage_minute (int, optional)
* team_side (enum: HOME, AWAY, NONE)
* player_id (optional)
* event_type (enum; alla)
* confidence (0..1)
* raw_ref (optional pointer/id alkuperäiseen)

### 2.2 event_type ja pakolliset lisäkentät

**GOAL**

* assist_player_id (optional)
* is_own_goal (bool)
* is_penalty (bool)
* score_home (int), score_away (int)

**SHOT**

* shot_id (string)
* xg (float, optional mutta suositus)
* shot_location (enum: BOX, OUTSIDE, SIX_YARD, UNKNOWN)
* situation (enum: OPEN_PLAY, SET_PIECE, COUNTER, PENALTY, UNKNOWN)
* outcome (enum: ON_TARGET, OFF_TARGET, BLOCKED, GOAL)
* is_big_chance (bool, optional)

**CORNER / FREE_KICK (ATTACKING)**

* setpiece_id
* into_box (bool, optional)
* followup_shot_id (optional)

**DANGEROUS_ATTACK (AGGREGATE)**

* value (int) tai delta (int)
* window_hint (optional)

**POSSESSION_SNAPSHOT**

* possession_home_pct (0..100)
* window (enum: LAST_5M)

**CARD**

* card_color (enum: YELLOW, SECOND_YELLOW, RED)
* player_id
* reason (optional)

**SUBSTITUTION**

* player_out_id, player_in_id
* tactical_hint (optional)

**VAR**

* var_state (enum: CHECKING, OVERTURNED, CONFIRMED)
* related_event_id (optional)

**STOPPAGE**

* reason (enum: INJURY, VAR, CROWD, OTHER)
* duration_sec (optional)

### 2.3 Dedupe ja järjestys

* Event järjestysprimääri: t_event, sekundääri: t_recv
* Dedupe: (source_id, event_id) tai fallback: (type, minute, team_side, player_id, xg±epsilon)

---

## 3) Odds feed: NormalizedOddsQuote

### 3.1 Yleiskentät

* schema_version
* quote_id (string; dedupe)
* match_id
* source_id
* t_seen (datetime)  ← “markkina nähty”
* t_recv (datetime)
* latency_sec
* market_type (enum: OU, NEXT_GOAL, DOUBLE_CHANCE)
* market_line (float, only for OU: 0.5/1.5/2.5)
* selection (enum riippuen marketista)
* odds_decimal (float)
* suspend_flag (bool, optional)
* liquidity_hint (optional)
* raw_ref (optional)

### 3.2 selection enumit

**OU**

* OVER
* UNDER

**NEXT_GOAL**

* HOME_NEXT
* AWAY_NEXT
* NO_GOAL (jos tarjolla)

**DOUBLE_CHANCE**

* HOME_OR_DRAW (1X)
* AWAY_OR_DRAW (X2)
* HOME_OR_AWAY (12)

### 3.3 Vigless laskenta (normatiivinen)

* OddsQuote ei sisällä p_bookia; p_book lasketaan Decision/Model -kerroksessa samalla quote-timestampilla.

---

## 4) Clock feed: NormalizedClockTick

Kentät:

* schema_version
* match_id
* source_id
* t_event
* t_recv
* latency_sec
* state (enum: PRE, LIVE, HT, END)
* minute (int)
* period (1H/2H)
* stoppage_minute (int, optional)
* is_running (bool, optional)

**Sääntö:** Core-loop käyttää clock-tickin minuutteja τ-laskentaan; jos clock epäluotettava → ODDS/EV päätökset jäädytetään.

---

## 5) Execution receipts: NormalizedExecutionReceipt (raha-totuus)

Kentät:

* schema_version
* bet_id (string)
* match_id
* t_sent (datetime)
* t_ack (datetime, optional)
* t_fill (datetime, optional)
* market_type, market_line (if OU), selection
* stake (float)
* odds_seen (float)
* odds_fill (float, optional)
* status (enum: FILLED, REJECTED, CANCELED, PARTIAL)
* reject_reason (optional)
* slippage (odds_seen - odds_fill, optional)
* ev_seen (float)
* ev_fill (float, optional)
* retention (ev_fill/ev_seen, optional)

---

## 6) DecisionTick (audit: myös NO BET)

Kentät:

* schema_version
* tick_id
* match_id
* t_tick (datetime)
* lifecycle_state (LIVE_ACTIVE/FROZEN/…)
* score_home, score_away, minute, phase_bucket
* TPS: C, T, H, label
* windows: T_slope_1m, T_slope_5m, T_mean_10m, disconfirm_flag, quality_flags
* latencies: event_p50/p95, odds_p50/p95, jitter
* market_candidate (market_type/line/selection) (optional; jos ei edes ehdokasta, merkitse NONE)
* odds_seen (optional), p_book (optional), p_model (optional), EV_seen (optional)
* MMS_total + components (optional)
* R_exec + components (optional)
* action (NO_BET / BET_SENT)
* reason_code (required always)
* config_hash (required)

---

# REPLAY.md (v0.1)

## 1) Replayn tarkoitus

Replay on “tuotanto ilman rahaa”, jolla varmistetaan:

* determinismi (T10)
* freeze-first käyttäytyminen stressissä
* execution-mallin realismi (slippage/suspend/reject)
* edge-mittarit (CLV/calibration) ilman tuotantoriskiä

---

## 2) Replay-tilat ja syötteet

### 2.1 Syötteet (pakolliset)

* NormalizedEvent (aikajärjestyksessä)
* NormalizedOddsQuote (aikajärjestyksessä)
* NormalizedClockTick (aikajärjestyksessä)
* (Valinnainen) historiallinen ExecutionReceipt – jos saat “attempt vs fill” datan; muuten simuloidaan.

### 2.2 Ajan simulointi

* Replay time = virtuaalikello, joka käy `t_event`-järjestyksessä
* `t_recv` generoidaan:

  * joko historiasta (jos tallessa)
  * tai latency-profiililla (p50/p95 + jitter), erikseen event/odds/clock

**Normi:** replayssä pitää pystyä ajamaan usealla latency-profiililla sama ottelu.

---

## 3) Execution-simulaattori (pakollinen realismi)

### 3.1 Mallinnettavat ilmiöt

* **Suspend**: markkina sulkeutuu tapahtumien ympärillä
* **Slippage**: odds_fill huononee suhteessa odds_seen
* **Reject**: veto hylätään (rate spikes)
* **Delay**: ack/fill viive

### 3.2 Parametrit (configurable)

* suspend_rate_by_market, suspend_duration_dist
* slippage_dist_by_market_and_phase (esim. p50/p95 ticks)
* reject_rate_base + spike_rules (esim. “high chaos”)
* fill_delay_dist

### 3.3 Pass/fail-kytkentä fill gateen

* Fill gate arvioidaan *täsmälleen* kuten prodissa (EV retention, SLIP_MAX)
* “Huono fill” pitää johtaa CANCELED/REJECTED/FILL_GATE_FAILED -lokitukseen, ei hiljaiseen hyväksyntään.

---

## 4) CLV-määritelmä (live-ympäristöön sopiva)

Koska “closing line” liveessä on liukuva, määrittele yksi **vakio**:

**CLV_anchor = odds_same_market_selection at (t_sent + Δt)**, missä:

* Δt = <CLV_DELAY_SEC> (esim. 120s) TAI
* “stabiloitunut” = ensimmäinen quote, jossa suspend_flag==false ja odds pysyy ±X ticks vähintään Y sekuntia

**CLV metric:**

* clv_ticks = odds_seen - clv_anchor (tai odds-implied p)
* clv_positive_rate = % vedoista joilla clv_ticks > 0

---

## 5) Test matrix (viitataan SPEC v0.1)

Käytä samaa T1–T10 -matriisia jonka jo määrittelit, plus nämä tuotantokriittiset lisät:

### T11: Clock drift / stoppage stress

**Setup:** clock-feed viivästyy tai stoppage-aika puuttuu.
**Pass:** FREEZE tai ODDS_LATENCY_HIGH/NOT_LIVE_ACTIVE; ei EV-päätöksiä väärällä τ:lla.

### T12: Feed outage (primary down)

**Setup:** primary event feed katkeaa X minuutiksi.
**Pass:** FREEZE + reason_code MISSING_EVENTS; palautuu vain recovery-ikkunan jälkeen.

### T13: Secondary mismatch false positive

**Setup:** secondary antaa virheellisen “punaisen”.
**Pass:** pending/freeze, mutta ei pysyvää tilakontaminaatiota; palaa LIVE_ACTIVE kun ristiriita poistuu.

---

## 6) Replay “Definition of Done”

Replay kelpaa go-live porttiin vasta kun:

* Determinismi: T10 pass 100%
* Audit: decision ticks 100% (ei aukkoja)
* Freeze-first: T2/T3/T4 pass
* Execution realism: T8 pass (fill gate suojaa)
* Limits: T9 pass
* Ei “silent failures”: kaikki estot näkyvät reason_codena

---

# RUNBOOK.md (v0.1)

## 1) Operointifilosofia

* Operointi on ensisijaisesti **riskin hallintaa**, ei “bettaamisen maksimoimista”.
* Kun epävarmuus kasvaa (data/toteutus), järjestelmä **jäädyttää**.

---

## 2) Päivittäinen rutiini (ennen ensimmäistä ottelua)

### 2.1 Pre-flight checklist (pakollinen)

1. **Config lukitus**

* Varmista prod-config hash (päivän immutable)
* Safe mode OFF (ellei tarkoituksella)

2. **Feed health**

* Event latency p95 < L_MAX
* Odds latency p95 < O_MAX
* Missing events rate ~0 (edelliset ottelut)
* Clock tickit tulevat säännöllisesti

3. **Execution sanity**

* Testi “dry-run” (jos mahdollista): yhteys, auth, kuittivirta
* Viimeisimmän päivän reject/slippage ei ole poikkeava

4. **Dashboards auki**

* Live Ops, Execution Health, Data Vendor Health, Alerts Console

**Jos mikä tahansa epäonnistuu:** SAFE_MODE tai MANUAL_FREEZE ennen kickoffia.

---

## 3) Live-operointi (ottelun aikana)

### 3.1 Normaali tila: LIVE_ACTIVE

* Seuraa: lifecycle + viimeisin reason_code
* Tarkista: latency p95, suspend rate, reject rate, TPS label
* Betit syntyvät autonomisesti gatejen kautta

### 3.2 Freeze-tilat ja toiminta

**HARD FREEZE triggeröityy automaattisesti**, kun:

* latency p95 > raja
* feed mismatch critical
* reject spike
* suspend spike

**Operaattorin toimet (järjestyksessä)**

1. Vahvista syy dashboardista (Data vs Execution)
2. Tarkista onko kyse yksittäisestä ottelusta vai globaalista
3. Jos globaali: pidä freeze päällä, älä “pakota palautusta”
4. Kirjaa incident: aika, syy, vaikutus (auto)

### 3.3 Manual kill switch (MANUAL_FREEZE)

Käytä kun:

* näet selkeän vendor/outage-tilan ennen kuin alert ehtii
* execution alkaa hylätä järjestelmällisesti
* odds liikkuu “ilman eventtejä” laajasti (MARKET_KNOWS -tilanne)

### 3.4 Safe mode

Safe mode on rajoitettu operointitila:

* estää valitut markkinat (esim. Next Goal OFF)
* alentaa max bets/match (esim. 1)
* tiukentaa EV_MIN tai MMS_MIN (valinnainen)

---

## 4) Incident-luokat ja vaste

### A) Data incident

Oireet:

* LATENCY_HIGH, MISSING_EVENTS, FEED_MISMATCH_CRITICAL
  Vaste:
* freeze
* vendor health -tarkistus
* replay myöhemmin kyseisellä latency-profiililla

### B) Execution incident

Oireet:

* REJECT_SPIKE, retention romahtaa, SLIPPAGE p95 > raja
  Vaste:
* freeze + cooldown
* safe mode (pois Next Goal / CHAOS-tilat)
* tarkista bookin rajoitteet / API / throttling

### C) Model incident (edge health)

Oireet:

* CLV < 0 pitkään, calibration drift
  Vaste:
* STOP_EDGE_TRIGGER → freeze
* POST: analyysi + config/malli muutos vasta viikkoprosessissa

---

## 5) Päivän lopetus (POST)

1. Reconcile: kaikki receipts + tulokset
2. Raportti:

* ROI, CLV, calibration summary
* execution KPI:t
* top reason_codes

3. Päätös:

* pysyykö config samana
* tarvitaanko vendor/ops fix
* tarvitaanko mallin kalibrointi

---

## 6) Muutoshallinta (käytännön sääntö)

* **Ei muutoksia kesken päivän**, paitsi:

  * MANUAL_FREEZE / SAFE_MODE
* Kaikki muutokset:

  * PR/Change request
  * perustelu + odotettu vaikutus
  * replay T1–T10 (min) ennen prodia

---

# LLM vs ML? OR LLM? (selkeä linja)

**Online-live-bettingissä: käytä ML (tai deterministinen tilastomalli) päätöksiin, LLM vain apurooleihin.**

## Miksi ML/tilastomalli päätöksiin

* **Kalibroitavuus**: p_model pitää olla mitattavasti kalibroitu (Brier, reliability bins).
* **Determinismi ja auditointi**: sama data → sama p, sama veto/ei-veto.
* **Nopeus ja robustius**: 30–60s core-loop ei saa riippua “tekstin tulkinnan” epävakaudesta.
* **Riskin hallinta**: exec-risk ja freeze-logiikka ovat paremmin “kovina sääntöinä”.

## Missä LLM on paras (ja turvallinen)

* Soft-signal: kommentaattori/Twitter/uutinen → *tagi* (injury/tactical_shift) + confidence
* Ops: incident-raportit, “miksi NO BET” selitykset, failure-mode -klusterointi
* Offline: viikkoraportit, speksin kehitysehdotukset (frontier)

## Yksi lauseen sääntö

* **ML laskee todennäköisyydet ja tekee gate-päätökset. LLM selittää, luokittelee ja auttaa operoimaan.**

Jos haluat, voin seuraavaksi kirjoittaa vielä **DECISION_POLICY.md** ja **EXECUTION_POLICY.md** samaan tyyliin (ne ovat käytännössä “käyttöohje” Decision/Execution -komponenteille), mutta yllä olevilla neljällä saat jo koko järjestelmän “buildable + operoitava” -tasolle.


Tämän arkkitehtuurin (Hub + Spoke) toteuttamiseen tarvitaan VPS, joka priorisoi **yhden säikeen suorituskykyä (clock speed)** ja **muistin nopeutta**, koska live-vedonlyönnissä viive (latency) on suurin vihollinen.

Tässä suositukset kolmessa eri kategoriassa.

---

### 1. Minimisuositus (Kehitys & Testaus)
Tämä riittää Hubin ajamiseen ja kevyen paikallisen LLM:n (esim. Llama-3 8B 4-bit quant) käyttöön, mutta LLM-vastausajat ovat hitaampia (2–5 sekuntia).

*   **CPU:** 4 vCPU (mieluiten dedikoituja, ei jaettuja)
*   **RAM:** 8 GB
*   **Levy:** 50 GB NVMe SSD (loggaus vaatii nopeutta)
*   **Verkko:** 1 Gbps
*   **Sijainti:** Frankfurt tai Lontoo (lähellä suurimpia data-vendoreita)
*   **Arvioitu hinta:** 20–30 € / kk
*   **Esimerkki:** Hetzner **CPX31** (tai dedikoitu **CCX13**).

---

### 2. Ammattilaissuositus (Tuotanto – "The Hub")
Tämä on optimoitu matalaan latenssiin ja rinnakkaiseen prosessointiin (Ingest, State, Model, Execution rullaavat omilla säikeillään ilman kilpailua).

*   **CPU:** 8 vCPU (Dedikoidut ytimet, esim. AMD EPYC tai Intel Xeon Gold)
*   **RAM:** 16 GB (Redis ja TimescaleDB vaativat tilaa datan kasvaessa)
*   **Levy:** 100 GB NVMe SSD
*   **Verkko:** 1 Gbps+ dedikoitu kaista
*   **Sijainti:** Frankfurt (Hetzner/Vultr) tai Lontoo (AWS/Vultr)
*   **Arvioitu hinta:** 50–80 € / kk
*   **Esimerkki:** Hetzner **CCX33** (Dedikoitu CPU on kriittinen, jotta "Fast Loop" ei jäädy käyttöjärjestelmän muiden prosessien takia).

---

### 3. LLM-erikoistus (The "Power Spoke")
Jos haluat, että paikallinen LLM analysoi tekstivirtaa reaaliajassa (< 1s viiveellä), CPU ei riitä. Tällöin sinulla on kaksi vaihtoehtoa:

**A) GPU-pohjainen VPS (Kallis)**
*   Esim. Vultr tai Lambda Labs GPU-instanssi (A10 tai L40).
*   Hinta: 150–300 € / kk.

**B) Hybrid-malli (Suositus)**
*   **Hub:** Hetzner CCX33 (Ammattilaissuositus yllä).
*   **Spoke:** Käytä LLM-tehtäviin **Runpodia** tai **Together AI**:n APIa.
*   Tämä säästää rahaa ja pitää Hubin resurssit puhtaana laskennasta.

---

### Tekninen perustelu valinnoille

1.  **Dedikoidut ytimet (Dedicated vCPU):** Live-vedonlyönnissä "micro-stutters" (jaetun prosessorin aiheuttamat lyhyet pysähdykset) voivat aiheuttaa sen, että `odds_seen` on jo vanhentunut, kun veto lähtee. Dedikoitu CPU takaa, että prosessi saa laskentatehon heti.
2.  **RAM & Redis:** Koko `Match State` pidetään Rediksessä (RAM). Mitä nopeampi muisti, sitä nopeammin Feature Engine laskee trendit (slope, mean).
3.  **Verkon sijainti:**
    *   Valitse **Frankfurt**, jos käytät eurooppalaisia datatoimittajia (esim. Sportradar, LSports).
    *   Valitse **Lontoo**, jos pääasiallinen markkinasi on Betfair Exchange.
    *   *Ping-ero Frankfurt vs. Helsinki voi olla 30-50ms. Se on live-markkinassa valtava ero.*

### Palveluntarjoaja-suositukset

1.  **Hetzner (Saksa):** Paras hinta-laatusuhde. **CCX-sarja** (Dedicated AMD EPYC) on erinomainen Hubille.
2.  **Vultr (Globaali):** Erittäin hyvät **High Frequency** -instanssit ja helppo lisätä GPU-node tarvittaessa.
3.  **DigitalOcean:** "Premium Optimized Droplets" toimivat hyvin, mutta Hetzner on usein nopeampi samassa hintaluokassa.

**Suositeltu aloitus:** Hetzner **CCX23** (4 Dedikoitua CPU:ta, 16GB RAM) Frankfurtissa. Se on tarpeeksi vahva pyörittämään Hubin ja Spoken (CPU-LLM:llä) vakaasti.



