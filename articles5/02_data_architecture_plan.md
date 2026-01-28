
## 1) LÄHTÖDATA TARKASTI

### 1.1 Pakolliset live-syötteet (minimikelpoinen järjestelmä)

Nämä on “must have”, muuten TPS/EV on helposti illuusio:

**A) Event feed (tapahtumat)**

* Maalit, laukaukset (jaoteltuna: boksista / boksin ulkopuolelta), xG (mieluiten shot-level → aggregoit itse), kulmat, vaaralliset hyökkäykset, kortit, punaiset, vaihdot, VAR, loukkaantumistauot.
* Pakolliset metat: `t_event`, `t_recv`, event-id, source-id.

**B) Live odds feed (book)**

* Markkinat vain rajauksesi mukaisesti: O/U 0.5/1.5/2.5, Next Goal, Double Chance (live).
* Pakolliset metat: `odds_seen`, `t_seen`, mahdollinen `suspend_flag`, `t_suspend`, `odds_fill`, `t_fill`.

**C) Match clock feed (kellotus)**

* Virallinen peliaika, lisäaika, tauko, VAR-pysäytykset.
* Ilman tätä “60–75 min” -ikkunat ja hazardin τ hajoaa.

**D) Quality-of-feed (QoF)**

* Jokaiselle yllä olevalle feedille jatkuva mittari: viive, puuttuvat eventit, jitter.
* Tämä on käytännössä “oikeus lyödä vetoa” -portti.

### 1.2 Ennakkomalli-data (baseline)

* Elo/xG-voimasuhde + konteksti (derby, putoamistaistelu, ruuhka, valmentajapaine).
* Tavoite: vain `base_home`, `base_away` + odotettu ottelutyyppi (tempo/riskitaso) **priorina** live-hazardille.

### 1.3 Data-standardi (yhtenäinen schema)

Tee kaikesta “sama kieli”:

* Yksi match-id kaikille lähteille (mapitus: joukkueet, kickoff, venue).
* Yksi aikastandardi (UTC + oma local), ja aina `t_event` + `t_recv`.
* Jokaiselle datapisteelle: `source`, `confidence`, `latency`.

---

## 2) LÄHDETYYPIT JA REDUNDANSSI

### 2.1 Lähdeluokat (suositus)

1. **Primary event feed** (pääasiallinen TPS/Threat)
2. **Secondary event feed** (ristivarmistus, outage-varmistus)
3. **Primary odds feed** (päätöksenteko)
4. **Execution feed / bet placement receipts** (toteutunut fill on “totuus”)
5. **Clock feed** (mielellään feedistä, ei ruudulta luettu)

Tärkeä periaate:
**Älä koskaan sekoita “televisiohavainnointia” samaan totuuskerrokseen** kuin event feed. TV on vahvistus/heuristiikka, ei state.

### 2.2 Ristivarmistukset (automaattiset)

* Jos Primary feed ilmoittaa punaisen, Secondary ei: **RED_SHIFT lukitaan “pending”** → ei vetoa 30–90 s (tai kun varmistuu).
* Jos odds liikkuu “ilman eventtejä”: kirjaa MMS-komponenttiin “market knows” -varoitus, ja **nosta execution-risk scorea**.

---

## 3) ARKKITEHTUURI (LONGTERM, PROD-KELPOINEN)

### 3.1 Kerrokset (selkeä vastuunjako)

**(1) Ingestion**

* Feed adapterit, normalisointi, deduplikointi, schema-validointi.
* Aikaleimat ja latency-laskenta täällä (ei myöhemmin).

**(2) State Store (totuuskerros)**

* “Current match state”: viimeisin score, minuutti, kortit, TPS-komponentit, rolling-ikkunat (1/5/10 min).
* Kaikki kirjoitetaan myös immutable event logiin (audit trail).

**(3) Feature Engine**

* Rakentaa TPS: C/T/H + labelit (LOW/PRESS/CHAOS/SETPIECE/RED_SHIFT).
* Laskee window-metriikat: slope/mean/zscore.

**(4) Models**

* Ennakkomalli (priorit)
* Live-hazard (päättäjä)
* Meta/MMS (markkinavirhe + viive)
* Execution & Friction (drift/suspend/fill)

**(5) Decision Engine (Hard gates)**

* Ainoa paikka, jossa “BET/NO BET” syntyy.
* Antaa myös `reason_code` aina.

**(6) Execution**

* Vetojen lähetys, kuittaukset, peruutukset, fill-kontrolli (EV_fill ≥ α * EV_seen).
* Reititys ja throttling: max 1–2 vetoa/ottelu, max 1 latentti riski.

**(7) Observability & Risk Control**

* Dashboardit, hälytykset, stop-edge, cooldownit.

**(8) Learning & Research**

* Offline analytiikka, simulointi, kalibrointi, CLV, drifti, lähdevertailut.

### 3.2 “Totuusperiaate”

* **Toteutunut fill** on ainoa raha-totuus.
* **Event feed** on ainoa pelitilan totuus.
* Kaikki muu (kommentaattori/LLM/Twitter) on “soft signal” eikä saa yksin muuttaa tilaa.

---

## 4) LOOPIT JA PÄIVITYSNOPEUDET (MÄÄRÄT)

### 4.1 Kolme rinnakkaista loopia (kuten rungossasi), mutta selkeällä rytmillä

**Loop A: Fast (1s–5s) – Execution Safety**

* Tarkkailee: suspend, odds jitter, fill/Reject, feed-latency.
* Päätös: “allow trading” / “freeze”.

**Loop B: Core (30–60s) – TPS & p_model**

* Päivittää TPS, hazardit, p_model jokaiselle markkinalle.
* Tämä on “pääpäivitys” vedonlyöntipäätöksille.

**Loop C: Windows (1/5/10 min) – Trend gates**

* Ikkunat päivittyy jatkuvasti, mutta gate-ehto arvioidaan Core-loopissa.
* Käytännössä: Core-loop käyttää valmiiksi laskettuja 1/5/10 -metriikoita.

### 4.2 Match lifecycle -tilat

* PRE (ei vetoja) → LIVE_ACTIVE → LIVE_FROZEN (riskikynnys) → HT (tauko) → LIVE_ACTIVE → END.
* Freeze ei ole virhe, vaan normaali tila.

---

## 5) SEURANTA JA VALVONTA (PROD-LEVEL)

### 5.1 Pakolliset KPI:t (päivittäin + rolling)

**Data**

* Event-latency (p50/p95), odds-latency (p50/p95), clock drift, missing events rate.
* Feed uptime, jitter.

**Execution**

* Fill rate, reject rate, avg slippage, slippage distribution, suspend frequency bet-attempt hetkellä.
* “Seen→Fill EV retention”: kuinka usein EV_fill ≥ α * EV_seen.

**Edge**

* ROI rolling 50/100, mutta myös **CLV rolling** (live-tyyli: esim. 60–180 s myöhemmin).
* Calibration (p_model binning vs toteutuma).

### 5.2 Hälytykset (automaattiset stopit)

* Latency p95 > L_max → FREEZE kaikki.
* Reject rate > r% viimeisen N yrityksen aikana → cooldown.
* CLV < 0 jatkuvasti + execution kunnossa → malliongelma → jäädytys ja analyysi.
* “Odds moves without events” -piikit → lähdeongelma tai markkina tietää → risk score ylös.

---

## 6) KIELIMALLIT (PAIKALLISET? FRONTIER?) — VAIN OIKEASSA ROOLISSA

### 6.1 Missä LLM on järkevä (ja turvallinen)

**A) Soft signal -normalisointi**

* Kommentaattoriteksti → strukturoitu “intensity / injury / tactical shift” -tagi (whitelist-lähteet).
* Twitter/uutisvirta → loukkaantumis- ja lineup-muutosten poiminta, mutta vain “pending → confirmed” -polulla.

**B) Operator copilotti**

* Selittää miksi “NO BET” (reason_code + TPS + MMS + exec risk).
* Tuottaa “post-mortem” -yhteenvetoja ja etsii toistuvia failure modeja (esim. “liikaa vetoja CHAOS-tilassa, slippage tappaa”).

**C) Data quality triage**

* Kun lähteet ristiriidassa: LLM voi kirjoittaa ihmislukuisen incident-raportin, ei päätä vetoa.

### 6.2 Missä LLM EI saa olla

* Ei koskaan “triggeröi vetoa”.
* Ei koskaan korvaa event feediä (ei TV-havainnointia malliin).
* Ei koskaan arvioi todennäköisyyksiä suoraan (“tuntuu että maali tulee”).

### 6.3 Local vs Frontier – käytännön jako

**Paikallinen LLM**

* Halpa, nopea, yksityinen: tekstin luokittelu, tagitus, operator-raportit.
* Parempi “always-on” pipelineen.

**Frontier LLM**

* Käytä vain harvempiin, kalliimpiin tehtäviin: viikkoraporttien analyysi, poikkeamien juurisyyt, sääntökirjan iterointi.

---

## 7) KONTROLLI: RISKIKURI JA “GOVERNANCE”

### 7.1 Sääntökirja versionhallintaan

* Kaikki kynnysarvot (L_max, MMS_min, EV_min, α, R_max, stop-loss) ovat “config”, jolla on versiohistoria.
* Jokainen muutos: syy, odotettu vaikutus, päivä.

### 7.2 Ihmisen kontrolli (operointi)

* “Kill switch” (manual freeze).
* “Safe mode” (vain yksi markkina kerrallaan, esim. vain O/U 0.5).
* Päiväkohtainen stop-loss + tilt-lock (execution-ongelmiin perustuva, ei tunteeseen).

### 7.3 Audit trail

* Jokaisesta päätöksestä (myös NO BET): snapshot + reason_code.
* Tämä mahdollistaa oikean validoinnin ja estää “muistiharhan”.

---

## 8) SIMULOINTI ETUKÄTEEN (ENNEN RAHAA)

Tämä on se osa, joka tekee tästä “professional longterm” eikä kokeilua.

### 8.1 Paper trading -simulaatio (live-replay)

* Aja historialliset ottelut “ikään kuin livenä”:

  * syötä eventit ja oddsit aikajärjestyksessä,
  * pakota latency/jitter -profiileja (realistinen p95),
  * simuloi suspendeja ja slippagea.
* Tulokset ilman execution-mallia ovat arvottomia → slippage/suspend täytyy olla mukana.

### 8.2 Execution-stressitestit

* “Worst-case day”: korkea jitter + paljon suspendeja.
* “Red card day”: paljon RED_SHIFT -tiloja.
* “Slow odds feed”: odds viive 3–8s.
  Tavoite: järjestelmä oppii **jäädyttämään** eikä “pakottamaan vetoja”.

### 8.3 Overfit-suojat

* Erottele:

  * kalibrointi- ja kynnysoptimointi (offline),
  * ja “lukittu tuotantokonfiguraatio” (online).
* Käytä walk-forward -validointia: kuukausi kerrallaan.

### 8.4 Go-live -portaat

1. 0€ paper
2. Mikropanos (tavoite: execution KPI:t kuntoon, ei ROI)
3. Flat stake normaaliksi vasta kun:

   * fill rate ja slippage stabiilit
   * CLV ≥ 0 useassa jaksossa
   * ei data-incidenttejä

---

## 9) PITKÄJÄNTEINEN KEHITYS (ROADMAP)

### 0–4 viikkoa: “Data & Control”

* Lähteet, schema, state store, reason_code, dashboard, freeze-automatiikka.
* Tavoite: järjestelmä osaa olla **NO BET** luotettavasti.

### 1–3 kuukautta: “Edge realism”

* MMS ja execution-risk mallinnus kuntoon.
* CLV + kalibrointi rutiiniksi.

### 3–6 kuukautta: “Stability”

* 500 vetoa -vaatimus järkevä, mutta edellytä samalla:

  * tasainen execution,
  * ei heikkoa data-latenssia,
  * sääntökirjan muutokset harvoin ja hallitusti.

---

## 10) MINIMI “DEFINITION OF DONE”

Järjestelmä on oikeasti valmis vasta kun nämä toteutuu:

* **Täysi audit trail** (myös NO BET)
* **Hard gates** (latency, laatu, disconfirm, MMS, execution risk, EV_seen→EV_fill)
* **Observability** (latency + execution + CLV + calibration)
* **Paper replay** sisältäen suspend/slippage
* LLM vain soft-signal / operator -roolissa

---

Jos haluat, voin seuraavaksi tiivistää tästä **yhden sivun operointikäsikirjan** (päivärutiini, hälytysrajat, freeze/rollback-prosessi) ja toisen sivun **data- ja lähdevaatimuslistan** (checklist muodossa).

PYTHON;LOCAL LLM;RUNPOD,CLI-WRAPPER;CLAUDE-CODE CLI WRAPPER; SUBPRPCESS;,HUB-SPOKE;VPS; ARKKITEHTUUTRI; SPEC.MD,AGENT VS AGENTS;DATALÄHTEET;LIVE;POST;PRE;TOTEUTA;SPEC.MD JA MUUT

Alla on **toteutussuunnitelma + tiedostorakenne (SPEC.md + muut)** sellaisena, että voit oikeasti rakentaa tämän **Pythonilla**, käyttää **local LLM:ää** (VPS:llä) ja tarvittaessa **frontier-mallia Runpodissa**, sekä ajaa “agentit” **hub–spoke** -mallilla. Ei koodia, vain selkeä speksi ja arkkitehtuuri.

---

# 1) Korkean tason arkkitehtuuri: Hub–Spoke (VPS) + Frontier (Runpod)

## 1.1 Hub (VPS) = “totuus ja raha”

**VPS hoitaa kaiken, mikä on:**

* determinististä, auditointikelpoista, jatkuvaa
* “raha-totuus” (fill, reject, slippage)
* riskikuri ja hard gates

**Hub-palvelut (prosessit/servicet):**

1. **ingest/**: event/odds/clock adapterit + normalisointi
2. **state/**: match state store + rolling windows
3. **feature/**: TPS (C/T/H + label) + 1/5/10-min signaalit
4. **models/**: hazard + p_model + MMS + exec-risk
5. **decision/**: hard gates → BET/NO BET + reason_code
6. **execution/**: bet placement + receipts + fill-check (EV_fill ≥ α·EV_seen)
7. **observability/**: metriikat, dashboard, hälytykset, stop-edge
8. **replay/**: paper/live-replay simulaatio samoilla komponenteilla

**Tärkein periaate:** Hub ei koskaan tarvitse LLM:ää päättämään vetoa.

## 1.2 Spoke (VPS) = “local LLM -apupalvelut”

Local LLM tekee vain:

* tekstin luokittelua (kommentaattori/uutis/twiitti → tagit)
* incident-raportteja
* selityksiä (miksi NO BET)

Spoke antaa Hubille vain **soft-signal** -objektin, jossa on `confidence` ja `source`.

## 1.3 Frontier (Runpod) = “harvinainen raskas analyysi”

Runpodia käytetään:

* viikkoraporttien tiivistys + root cause -luokittelu
* sääntökirjan iteroinnin ehdotukset
* “what changed?” -analyysi (ei online päätöksiä)

---

# 2) Agent vs Agents (mitä kannattaa oikeasti tehdä)

## 2.1 Yksi “Agent” online-päätöksessä (suositus)

Online-vedossa **yksi päätöksentekijä** (Decision Engine) = paras:

* vähiten nondeterminismiä
* helpoin auditoida ja freeze/rollbackata
* nopein

## 2.2 “Agents” offline- ja ops-puolella (hyödyllinen)

Moni-agentti sopii:

* datan laadun analyysiin (Data QA Agent)
* execution-problemien luokitteluun (Exec QA Agent)
* mallin kalibroinnin raportointiin (Model QA Agent)
* “Spec change advisor” (muutosehdotukset configiin)

Eli: **moniagentti = analyysi ja operointi**, ei live-bet trigger.

---

# 3) Prosessimalli: PRE / LIVE / POST (selkeä toimitusketju)

## 3.1 PRE (ennen ottelua)

* Ennakkomalli tuottaa: `base_home/base_away`, “odotettu ottelutyyppi”
* Lähteiden health-check: event-feed, odds-feed, clock-feed
* Ottelun “watchlist”-rajaukset (liigat/markkinat lukittu)

Output: **MatchConfig snapshot** (versioitu)

## 3.2 LIVE (ottelun aikana)

* Ingest (tapahtumat + odds + kello)
* State store päivittää “totuus”
* Feature engine päivittää TPS + window-signaalit
* Core-loop (30–60s): hazard → p_model → p_book (vig-less) → MMS → exec-risk → gates
* Execution lähettää vain jos fill-kriteeri täyttyy
* Observability hälyttää, jäädyttää, cooldown

Output: **BetDecisionLog** + **ExecutionReceiptLog**

## 3.3 POST (ottelun jälkeen)

* Reconcile: täsmäytä vedot, fillit, lopputulos
* CLV (live-tyyli): vertaa esim. 60–180s myöhemmin tai “stabiloitunut odds”
* Calibration + binning
* Failure modes: “miksi hävisimme?” (malli vs execution vs data)

Output: **Weekly report** + “config change proposals” (ei automaattista muutosta)

---

# 4) Python toteutus: prosessit, wrapperit, subprocess ja CLI

## 4.1 Ydinajatus: kaikki on ajettavissa CLI:nä

Jokainen komponentti on:

* ajettavissa palveluna (daemon)
* ajettavissa testissä (one-shot)
* ajettavissa replay-simulaatiossa

Tämä tekee “paper replay”stä saman kuin tuotanto.

## 4.2 CLI-wrapperit (Claude Code CLI wrapper / vastaava)

Käyttöidea:

* **LLM-wrapper** on vain yksi binääri/skripti, joka:

  * ottaa JSON-in → palauttaa JSON-out
  * lokittaa prompt/version/hash
  * timeouttaa ja failaa turvallisesti

Hub kutsuu wrapperia vain:

* soft-signaalin luokitteluun
* raporttien generointiin

**subprocess**-malli on ok, kunhan:

* timeouts ovat tiukat (online: sekunteja)
* output schema validoidaan (pydantic tms.)
* fallback on “no signal” (ei koskaan “panic bet”)

## 4.3 Runpod-integraatio (frontier)

Sama wrapper-rajapinta, mutta “remote provider”.

* Online polussa: **ei pakollinen**
* Offline: batch-ajot (päivittäin/viikoittain)

---

# 5) Data-lähteet: “tyypit” + live-vaatimukset (ei toimittajalistaa)

## 5.1 Lähdetyypit (minimi)

* **Event feed** (shot/xG, cards, set pieces, subs, VAR, stoppages)
* **Odds feed** (3 markkinaa rajauksesi mukaan)
* **Clock feed** (minute + stoppage + HT/FT)
* **Execution receipts** (seen/fill/reject/cancel)

## 5.2 Pakolliset tekniset vaatimukset lähteille

* Tapahtumilla: `t_event` + event_id + dedupe
* Oddsilla: `t_seen`, suspend flags jos saatavilla
* Kaikesta: latency/jitter mittarit
* “source reliability score” (havaittu missing rate)

---

# 6) Kontrolli ja turvallisuus: “freeze-first” tuotantofilosofia

## 6.1 Freeze-käytännöt (hard)

Freeze, jos:

* latency p95 > L_max
* odds jitter/suspend räjähtää
* reject rate nousee
* feedit ristiriidassa kriittisessä eventissä (punainen, maali, VAR)

## 6.2 Rollback ja config governance

* Kaikki kynnykset ovat **config-versioituja**
* Muutokset vain POST/Weekly -prosessissa
* Tuotannossa “lukittu config” (immutable per päivä)

---

# 7) Simulointi etukäteen: Live-replay on pakko rakentaa “ensimmäisenä”

## 7.1 Replay-moottori (sama pipeline)

Replay syöttää:

* eventit ja oddsit aikajärjestyksessä
* keinotekoiset latency/jitter/suspend-profiilit

Tavoite:

* mitata fill-ongelmat ja slippage ennen rahaa
* testata RED_SHIFT-ikkunat (90–300s) realistisesti

## 7.2 Testikategoriat (pakolliset)

* “Slow feed day”
* “Red card day”
* “High suspend day”
* “Odds move without events day”

---

# 8) Repo + tiedostot: SPEC.md ja muut (suoraan käyttökelpoinen runko)

## 8.1 Pakollinen dokumentaatio (root)

* **SPEC.md** (järjestelmän totuus: rajaus, hard gates, loopit, riskikuri)
* **ARCHITECTURE.md** (hub–spoke, prosessit, datavirrat)
* **DATA_CONTRACTS.md** (schema: event/odds/clock/receipts + versionointi)
* **DECISION_POLICY.md** (gates + reason_code lista + latent risk -säännöt)
* **EXECUTION_POLICY.md** (two-step commit, EV retention α, slippage, suspend)
* **OBSERVABILITY.md** (KPI:t, hälytysrajat, stop-edge)
* **REPLAY.md** (paper replay -speksi + stressitestit)
* **RUNBOOK.md** (operointi: päivärutiinit, incident-prosessi, kill switch)
* **CHANGELOG.md** (config muutokset ja syyt)
* **SECURITY.md** (avaimet, secrets, access, audit)

## 8.2 Config-rakenne

* `config/prod.yaml` (lukittu päivän ajaksi)
* `config/thresholds.yaml` (L_max, MMS_min, EV_min, α, R_max jne.)
* `config/sources.yaml` (feedien prioriteetit, reliability)
* `config/markets.yaml` (rajatut markkinat + parametrit)

## 8.3 Logging ja audit

* `schemas/*.json` (päätöslogi ja receipt-logi)
* `logs/` (append-only)
* `reports/weekly/` (autogeneroidut raportit)

---

# 9) “SPEC.md” sisältörunko (täsmäotsikot)

Tämä on se dokumentti, jota “ei rikota”.

1. Rajaus (lukittu)
2. Määritelmät (t_event/t_recv/latency, p_book vigless, EV)
3. TPS-formalismi (C/T/H + labelit)
4. Loopit (Fast/Core/Windows)
5. Markkinasäännöt (O/U, Next Goal, DC)
6. Hard gates (latency, quality, disconfirm, MMS, exec risk, EV retention)
7. Execution (two-step commit, cancel rules, suspend rules)
8. Riskikuri (flat stake, latent risk, stop-loss, freeze/cooldown)
9. Logging schema + reason_codes (NO BET mukaan)
10. Validointi (CLV, calibration, execution KPI)
11. Simulointi (replay + stressitestit)
12. Muutoshallinta (config versionointi, rollout/rollback)

---

TEE  **valmiin SPEC.md -tekstin** (täysin kirjoitettuna, kynnysarvot placeholdereina) + **reason_code -sanaston** + **replay test matrixin** (mitä testataan ja millä “pass/fail” -ehdoilla).

STUB.MD

METRICS

DASHBOARD

