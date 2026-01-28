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
