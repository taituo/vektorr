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

