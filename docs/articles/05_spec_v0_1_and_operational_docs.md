# AI-AVUSTEINEN LIVE-VEDONLYÖNTIJÄRJESTELMÄ (JALKAPALLO) — SPEC

Version: v0.1 (LOCKED SCOPE)
Owner: <YOU>
Last updated: <YYYY-MM-DD>

## 0. Rajaus (LUKITTU)

### 0.1 Lajit
- Valioliiga
- La Liga

### 0.2 Vedot
- LIVE ONLY

### 0.3 Markkinat (LUKITTU)
- Over/Under: 0.5, 1.5, 2.5
- Next Goal
- Double Chance (live)

### 0.4 Panostus ja ottelukohtaiset rajat (LUKITTU)
- Flat stake: S = <STAKE_UNIT>
- Max 1–2 vetoa / ottelu
- Max 1 latentti riski / ottelu
- Default state: NO BET

---

## 1. Määritelmät ja laskennat (NORMATIIVISET)

### 1.1 Aikaleimat ja viive
- t_event = tapahtuma-aika (feedin timestamp)
- t_recv  = vastaanottoaika (järjestelmän kello)
- latency = t_recv - t_event (sekunteina)
- jitter  = latency vaihtelu (p95-p50 tms.)

**Pakollinen:** jokaisella eventillä ja odds-näkymällä on t_event/t_recv (tai t_seen/t_recv).

### 1.2 Bookmakerin implisiittinen todennäköisyys (vig poistettuna)
Desimaalikertoimet o_i:
- q_i = 1 / o_i
- p_book_i = q_i / sum(q_all)

**Pakollinen:** p_book lasketaan aina vig-less muodossa.

### 1.3 Mallin todennäköisyys
- p_model(market, selection, t) = järjestelmän arvio hetkellä t

### 1.4 EV (odotusarvo) desimaalikertoimilla
- EV = p * o - 1
missä p = p_model ja o = odds (seen tai fill)

### 1.5 “Seen vs Fill” -totuus
- odds_seen = kerroin, jolla veto yritetään
- odds_fill = toteutunut hyväksytty kerroin (rahan totuus)

**Pakollinen:** päätöslogiin tallennetaan molemmat.

---

## 2. Data-sopimukset (LIVE)

### 2.1 Pakolliset syötteet (minimi)
A) Event feed:
- goal, shot (box/outside), xG (mieluiten shot-level), corners, dangerous attacks,
  possession(5m), cards, red cards, subs, VAR, stoppages
- metat: event_id, t_event, t_recv, source_id

B) Odds feed:
- OU(0.5/1.5/2.5), Next Goal, DC
- metat: market_id, selection_id, odds_seen, t_seen, t_recv, suspend_flag (jos saatavilla)

C) Match clock:
- minute, stoppage, HT/FT, VAR stoppage (jos saatavilla)
- metat: t_event, t_recv

D) Execution receipts:
- accepted/rejected/canceled, odds_fill, t_fill, stake, bet_id

### 2.2 Redundanssi (suositus mutta ei pakko)
- Secondary event feed ristivarmistukseen
- Jos kriittinen event (maali/punainen/VAR) on ristiriidassa → FREEZE

---

## 3. Tilakone: Match Lifecycle

Tilat:
- PRE (ei vetoja)
- LIVE_ACTIVE (päätökset sallittu, jos gate ok)
- LIVE_FROZEN (päätökset estetty riskin/data-ongelman vuoksi)
- HT (tauko, oletus: FREEZE ellei erikseen avata)
- END

Siirtymät:
- PRE -> LIVE_ACTIVE kun kick-off vahvistuu ja feed-health OK
- LIVE_ACTIVE -> LIVE_FROZEN kun yksikin hard-freeze ehto täyttyy (ks. kohta 8)
- LIVE_FROZEN -> LIVE_ACTIVE kun palautumisehdot täyttyvät ja cooldown ohi
- LIVE_* -> END kun FT

---

## 4. TPS (Todellinen pelitila) — formaali määritelmä

TPS = (Phase, C, T, H, Label)

### 4.1 Phase (bucket)
- P1: 0–15
- P2: 16–45
- P3: 46–60
- P4: 61–75
- P5: 76–90+

### 4.2 Control (C ∈ [-1, +1])
- -1 = vieras kontrolloi, +1 = koti kontrolloi
Lähteet: possession_5m, territory proxy, dangerous attacks share, field tilt (jos saatavilla)

### 4.3 Threat (T ≥ 0)
- T = w1*live_xG_10m + w2*box_shots_10m + w3*big_chances_10m + w4*setpiece_pressure_10m
Painot = <W1..W4>

### 4.4 Chaos (H ≥ 0)
- kortit, punainen, loukkaantumistauot, setpiece-klusterit, “end-to-end” vaihtelu
- H = <DEFINE_H_FORMULA>

### 4.5 TPS Label (diskreetti)
- LOW: T low AND H low
- PRESS: T high AND |C| high AND H mid
- CHAOS: H high (vaatii tiukemman exec-risk portin)
- SETPIECE: setpiece-klusteri (kulmat/vaparit) + boksikontaktit
- RED_SHIFT: punainen ja 0–<RED_WINDOW_MIN> min sisällä

---

## 5. Mallikerrokset (EI suoraa vetoa ilman gateja)

### 5.1 Staattinen ennakkomalli (EI vetoja)
Input:
- Elo/xG power ratings
- konteksti: derby, relegation, schedule congestion, coach pressure
Output:
- base_home, base_away (maalihazard prior)
- expected match type (tempo/risk prior)

### 5.2 Live-ydinmalli (p_model)
Päivitys: 30–60 s (Core-loop)

Perusmuoto:
- λ_home(t) = base_home * exp( a1*C + a2*T + a3*H + a4*Red + a5*ScoreState + a6*Phase )
- λ_away(t) = base_away * exp( b1*C + b2*T + b3*H + b4*Red + b5*ScoreState + b6*Phase )

Jäljellä oleva aika τ:
- P(goal in τ) = 1 - exp(-(λ_home+λ_away)*τ)

Next Goal (approx):
- P(home next) ≈ (λ_home/(λ_sum)) * P(goal in τ)
- P(away next) ≈ (λ_away/(λ_sum)) * P(goal in τ)
- P(no goal) = exp(-λ_sum*τ) (jos marketissa)

Over/Under:
- Malli arvioi jäljellä olevien maalien jakauman ja yhdistää nykyiseen maalimäärään
- Markkinat rajoitettu: 0.5/1.5/2.5

Double Chance:
- Käytetään vain, jos W/D/L jakauma saatavilla ja kalibroitu; muuten harvinainen/pois.

### 5.3 Meta-/käyttäytymismalli (MMS 0–100)
Komponentit:
A) Odds-vs-event mismatch
B) Reaktioviive (odds change lag vs events)
C) Over/under-reaction (overshoot/mean reversion)
D) Favorite/home bias

MMS = clamp( wA*A + wB*B + wC*C + wD*D, 0..100 )
Kynnys: MMS >= <MMS_MIN>

### 5.4 Execution & Friction Layer (KRIITTINEN)
- Drift, suspend, reject, fill slippage, latency

Exec risk score:
- R_exec = f( suspend_rate_30s, odds_vol_30s, latency, Phase, TPS_label, H )

Kynnys: R_exec <= <R_MAX>

---

## 6. Loopit ja arviointirytmi

### 6.1 Loop A: Fast (1–5 s) — Safety
Tarkkailee:
- feed latency/jitter
- suspend/jitter oddsissa
- reject/slippage spike
Toiminto:
- aseta LIVE_FROZEN, jos yksikin hard-freeze ehto täyttyy

### 6.2 Loop B: Core (30–60 s) — Päätökset
Laskee:
- TPS, p_model, p_book, EV, MMS, R_exec
Arvioi hard gates ja tuottaa päätöksen:
- NO BET / BET_SENT

### 6.3 Loop C: Windows (1/5/10 min) — Trend gates
Ikkunat:
- 1m: impulssi (ΔT, ΔC)
- 5m: trendi (slope, mean)
- 10m: rakenne (mean, disconfirm)

Pakollinen konsensus:
- 1m ja 5m samaan suuntaan
- 10m ei vastakkaissuuntainen (disconfirm)

---

## 7. Päätöspolitiikka (HARD GATES) — AINOA tie bettiin

Veto voidaan lähettää vain, jos KAIKKI ehdot täyttyvät:

G1) Match state:
- lifecycle == LIVE_ACTIVE

G2) Latency gate:
- latency_p95 <= <L_MAX_SEC> (event feed)
- odds_latency_p95 <= <O_MAX_SEC>

G3) TPS gate:
- TPS_label != LOW
- Quality gate: (live_xG_10m >= <XG10_MIN> OR box_shots_10m >= <BOX10_MIN>)

G4) Trend gate:
- sign(T_slope_1m) == sign(T_slope_5m)
- T_5m_mean >= <T5_MIN>
- Disconfirm: NOT(10m signal clearly opposite)

G5) Market gate:
- MMS >= <MMS_MIN>
- Price moved gate: abs(odds_move_ticks_? ) <= <MOVE_MAX> (jos määritelty)
- EV_seen >= <EV_MIN>

G6) Exec-risk gate:
- R_exec <= <R_MAX>

G7) Stake/limits gate:
- bets_in_match < 2
- latent_risk_in_match < 1 (ks. 7.1)

G8) Two-step commit (fill gate):
- jos betti hyväksytään:
  - EV_fill >= <ALPHA> * EV_seen
  - odds_fill >= odds_seen - <SLIP_MAX>
- muuten: cancel / treat as rejected (policy in EXECUTION_POLICY)

Default: NO BET

### 7.1 Latent risk -luokitus
- High latent: Next Goal
- Medium latent: OU 2.5
- Low latent: OU 0.5 myöhään (80+), jos määritelty

Sääntö:
- Jos Next Goal placed -> ei enää vetoja samaan otteluun (suositus: HARD)
- Muuten: max 1 medium/high latent per match

---

## 8. Freeze, cooldown, stop-edge (RISKIKURI)

### 8.1 Hard-freeze ehdot (välitön)
- event_latency_p95 > <L_MAX_SEC>
- missing_critical_events_rate > <MISS_MAX>
- odds_suspend_rate_30s > <SUSP_MAX>
- reject_rate_last_N > <REJ_MAX>
- critical event feed mismatch (goal/red/VAR) primary vs secondary

### 8.2 Palautuminen (unfreeze)
- kaikki freeze-metriikat alle rajan yhtäjaksoisesti <RECOVERY_WINDOW>
- cooldown <COOLDOWN_MIN> suoritettu

### 8.3 Päiväkohtainen stop-loss
- daily_pnl <= -<STOPLOSS_UNITS>*S -> FREEZE loppupäiväksi

### 8.4 Stop-edge (mallijäädytys)
- rolling ROI (50–100 bets) < -<ROI_FREEZE_PCT> -> FREEZE + POST-analyysi pakollinen
- rolling CLV < 0 (N bets) -> FREEZE + analyysi

---

## 9. Logging & Audit (Pakollinen, myös NO BET)

### 9.1 Decision log (jokainen Core-loop arvio)
- match_id, league, teams, minute, score
- TPS: Phase, C, T, H, Label
- windows: 1m/5m/10m metrics
- latencies: event p50/p95, odds p50/p95
- market snapshot: market_type, selection, odds_seen, p_book, p_model, EV_seen
- MMS total + components
- R_exec
- action: NO_BET / BET_SENT
- reason_code (jos NO_BET tai jos estettiin)
- config_version hash

### 9.2 Execution log (vain jos BET_SENT)
- bet_id, t_sent, odds_seen, stake
- result: FILLED/REJECTED/CANCELED
- odds_fill, t_fill, EV_fill, slippage
- fill_gate_pass boolean
- final_outcome (POST)

---

## 10. Validointi (viikoittain)

Pakolliset:
- Calibration: p_model bins vs realized
- CLV: live-CLV määritelmän mukaan (ks. REPLAY.md)
- Execution KPIs: fill, slippage, reject, suspend at attempt
- Failure mode -jakauma reason_code -tasolla

---

## 11. Simulointi (ennen rahaa)

- Live-replay samalla pipelinellä (ingest -> state -> features -> decision -> execution-sim)
- Stressitestit (ks. REPLAY.md test matrix)
- Go-live vain, jos pass-kriteerit täyttyvät

---

## 12. Muutoshallinta (Governance)

- Kynnykset ja painot configissa, versionhallittu
- Muutokset vain POST/Weekly -prosessissa
- Tuotantopäivän aikana config immutable (ellei kill switch -> safe mode)


# REASON_CODE Vocabulary (v0.1)

## Data & Latency
- LATENCY_HIGH: event-latency yli rajan
- ODDS_LATENCY_HIGH: odds-latency yli rajan
- JITTER_HIGH: latency jitter yli rajan
- MISSING_EVENTS: missing/puuttuvat eventit tai kriittinen aukko
- FEED_MISMATCH_CRITICAL: primary vs secondary ristiriita (goal/red/VAR)

## Match lifecycle / State
- NOT_LIVE_ACTIVE: ei LIVE_ACTIVE-tilassa (PRE/HT/END/FROZEN)
- TPS_LOW: TPS_label == LOW
- QUALITY_LOW: laatuportti ei täyty (xG/box shots minimi)

## Trend / Disconfirmation
- TREND_MISMATCH: 1m ja 5m eivät samaan suuntaan
- DISCONFIRM_10M: 10m rakenne vastakkainen / piikki ilman rakennetta
- SPIKE_ONLY: havaittu vain 1m piikki ilman tukea

## Market / Edge
- MMS_LOW: Market Mispricing Score alle rajan
- EV_LOW: EV_seen alle rajan
- PRICE_MOVED: hinta liikkunut liikaa (myöhästytty edge)
- MARKET_KNOWS: odds liikkuu ilman eventtiä (varoitus -> estää vedon)

## Execution / Friction
- EXEC_RISK_HIGH: R_exec yli rajan
- SUSPEND_RISK: suspend-riski liian korkea
- REJECT_SPIKE: reject rate liian korkea (cooldown)
- SLIPPAGE_TOO_HIGH_EXPECTED: odotettu slippage liian suuri
- FILL_GATE_FAILED: EV_fill tai slippage-ehto ei täyttynyt

## Limits / Discipline
- MATCH_BET_LIMIT: max 2 vetoa/ottelu täynnä
- LATENT_LIMIT: latentti riski jo käytetty
- DAILY_STOPLOSS: päivän stop-loss täynnä
- STOP_EDGE_TRIGGER: rolling ROI/CLV triggeröi jäädytyksen
- COOLDOWN_ACTIVE: cooldown käynnissä

## Manual / Ops
- MANUAL_FREEZE: operaattori freeze
- SAFE_MODE: safe mode estää kyseisen markkinan


# REPLAY Test Matrix (v0.1)

## Yleiset määritelmät
- Replay käyttää samaa decision pipelineä kuin prod.
- Execution-simulaatio mallintaa: suspend, slippage, reject (syntetisoitu tai historiasta).
- Pass/fail mitataan sekä "bet outcomes" että "system behavior" (freeze-first).

---

## T1: Baseline replay (normaalit olosuhteet)
**Goal:** Pipeline tuottaa päätökset deterministisesti ja lokittaa kaiken.
**Setup:** latency p95 < L_MAX, suspend low, slippage normaalitaso.
**Pass:**
- 100% decision ticks logattu (NO_BET mukaan)
- 100% bets: receipt-log (filled/rejected/canceled)
- reason_code ei ole tyhjä NO_BET tapauksissa
**Fail:**
- puuttuva audit trail tai epädeterministinen päätös samalla datalla

---

## T2: Slow event feed day
**Goal:** Järjestelmä jäädyttää eikä yritä väkisin.
**Setup:** event latency p95 = L_MAX + (1..N)s, jitter korkea.
**Pass:**
- LIVE_FROZEN aktivoituu < 1 Core-loop sisällä rajan ylityksestä
- bet attempt count = 0 freeze-tilassa
**Fail:**
- vetoja lähtee vaikka latency-gate rikki

---

## T3: Slow odds feed day
**Goal:** estää stale pricing.
**Setup:** odds_latency p95 > O_MAX.
**Pass:**
- NO_BET reason_code = ODDS_LATENCY_HIGH
- ei bettejä vaikka p_model näyttäisi EV:tä
**Fail:**
- bettejä lähtee stale odds -tilassa

---

## T4: High suspend day
**Goal:** exec-risk gate toimii.
**Setup:** suspend_rate_30s > SUSP_MAX monissa jaksoissa.
**Pass:**
- R_exec ylittää rajan ja estää vedot (EXEC_RISK_HIGH / SUSPEND_RISK)
- cooldown toimii reject-spikeissä
**Fail:**
- korkea reject/slippage ilman automaattista estoa

---

## T5: Red card window test (90–300s)
**Goal:** RED_SHIFT-ikkuna toimii, mutta ei ennen vahvistusta.
**Setup:** punainen, primary/secondary vahvistus viiveellä.
**Pass:**
- ennen vahvistusta: FREEZE tai NO_BET (FEED_MISMATCH_CRITICAL / pending)
- vahvistuksen jälkeen: päätökset sallittuja vain, jos MMS+EV+exec-risk ok
**Fail:**
- veto ennen vahvistusta tai ilman gateja

---

## T6: “Tempo ilman laatua” (false pressure)
**Goal:** quality gate estää.
**Setup:** dangerous attacks ↑, mutta xG/box shots matalat.
**Pass:** NO_BET (QUALITY_LOW / TPS_LOW)
**Fail:** OU/NextGoal vetoja ilman laatumittareita

---

## T7: Odds move without events (market knows)
**Goal:** varoitus estää tai nostaa riskin.
**Setup:** odds drift merkittävä ilman eventeja.
**Pass:**
- MARKET_KNOWS reason_code tai MMS/exec-risk estää vedon
- incident kirjautuu
**Fail:**
- vetoja lähtee “sokeasti” tähän

---

## T8: Slippage stress (fill deterioration)
**Goal:** two-step commit suojaa.
**Setup:** odds_fill usein heikompi kuin odds_seen (slip > SLIP_MAX).
**Pass:**
- FILL_GATE_FAILED kasvaa, mutta PnL-suojaus toimii (ei “huonoja fillejä” läpi)
- avg EV retention >= ALPHA_TARGET (simuloitu)
**Fail:**
- järjestelmä hyväksyy järjestelmällisesti huonot fillit

---

## T9: Limits & latent risk enforcement
**Goal:** ottelurajat pitävät.
**Setup:** generoidaan useita signaaleja samaan otteluun.
**Pass:**
- max 2 bet attempts / match
- max 1 latent risk / match
**Fail:** rajoja rikotaan

---

## T10: Determinism & reproducibility
**Goal:** sama input -> sama output.
**Setup:** replay ajetaan kahdesti samalla datalla ja configilla.
**Pass:** 100% identtiset päätökset + reason_code + bet attempts
**Fail:** eroavaisuuksia ilman selitystä (nondeterminismi)


# Project Stub (V0)

## What this is
Live-only football betting system for:
- EPL, La Liga
- Markets: OU(0.5/1.5/2.5), Next Goal, Double Chance
- Flat stake, strict risk discipline, freeze-first

## Docs (source of truth)
- SPEC.md (policy + gates; locked scope)
- ARCHITECTURE.md (hub-spoke services + dataflow)
- DATA_CONTRACTS.md (schemas for events/odds/clock/receipts)
- DECISION_POLICY.md (decision tree + reason_code mapping)
- EXECUTION_POLICY.md (two-step commit + fill gate)
- METRICS.md (KPI definitions + alert thresholds)
- DASHBOARD.md (views + panels + drill-down)
- REPLAY.md (replay engine + test matrix)
- RUNBOOK.md (ops routines + incident handling)

## Non-negotiables
- NO BET is default
- Everything is logged (including NO BET)
- Fill is money-truth; feed is game-truth
- LLM never triggers bets

## Environments
- VPS = hub (deterministic + execution + audit)
- Local LLM on VPS = soft-signal classifier only
- Frontier model (Runpod) = offline reports only

## Milestones
1) Data + Audit trail
2) Freeze-first controls + dashboards
3) Replay engine + stress tests
4) Micro-stake rollout (execution KPI first)

# Metrics & Alerts (v0.1)

## 1) Data Quality
### Event latency
- event_latency_p50 / p95 (seconds)
Alert:
- p95 > L_MAX_SEC => HARD FREEZE

### Odds latency
- odds_latency_p50 / p95
Alert:
- p95 > O_MAX_SEC => HARD FREEZE

### Missing events
- missing_events_rate (per match or per 10 min)
- critical_missing (goal/red/VAR)
Alert:
- critical_missing OR mismatch => HARD FREEZE

### Jitter
- event_jitter = p95 - p50
Alert:
- jitter > J_MAX => FREEZE

## 2) Execution
### Fill rate
- filled / (sent)
Alert:
- fill_rate < F_MIN over last N => cooldown / investigate

### Reject rate
- rejected / sent (rolling N)
Alert:
- reject_rate > REJ_MAX => HARD FREEZE + cooldown

### Slippage
- slip = odds_seen - odds_fill (or ticks)
- avg_slip, p95_slip
Alert:
- p95_slip > SLIP_MAX => tighten exec gate / freeze if persistent

### EV retention
- retention = EV_fill / EV_seen
Alert:
- retention_p50 < ALPHA over last N => freeze and inspect

### Suspend at attempt
- suspend_rate_30s at bet attempt
Alert:
- > SUSP_MAX => exec-risk up; may freeze if persistent

## 3) Edge Health
### ROI rolling
- ROI_50, ROI_100
Alert:
- ROI_100 < -ROI_FREEZE_PCT => STOP_EDGE_TRIGGER => freeze

### CLV rolling
- CLV_50, CLV_100 (definition in REPLAY.md)
Alert:
- CLV_100 < 0 => freeze and calibrate

### Calibration error
- Brier score / reliability bins
Alert:
- calibration drift > CAL_MAX => investigate model

## 4) System Behavior
### Freeze rate
- % time in LIVE_FROZEN
Alert:
- too high => data/vendor issue or thresholds too strict

### Decision tick completeness
- decision_ticks_logged / expected
Alert:
- < 100% => FAIL (audit broken)


# Dashboard Spec (v0.1)

## View A: Live Operations (per match)
Panels:
1) Lifecycle state (LIVE_ACTIVE/FROZEN) + last reason_code
2) Latency: event p50/p95, odds p50/p95 (sparkline)
3) TPS: Label + C/T/H (current + last 10 min)
4) Windows: 1m/5m/10m trend arrows + disconfirm flag
5) Market snapshot:
   - odds_seen, p_book, p_model, EV_seen
   - MMS total + top component
6) Exec panel:
   - R_exec
   - suspend flag (current/last 30s)
   - last bet result (filled/rejected) + slippage

Drill-down:
- click bet -> show receipts, EV_seen vs EV_fill, retention, timestamps

## View B: Execution Health (global)
Panels:
- Fill rate (rolling)
- Reject rate (rolling)
- Slippage distribution (hist)
- EV retention distribution
- Suspend at attempt trend
- “Top reason_codes (NO_BET + BLOCK)” distribution

## View C: Edge Health (weekly)
Panels:
- ROI_50/100 trend
- CLV_50/100 trend
- Calibration reliability plot summary (bins table)
- Market-by-market performance (OU vs NextGoal vs DC)

## View D: Data Vendor Health
Panels:
- Uptime per feed
- Missing events (critical vs non-critical)
- Latency heatmap by league/time
- Feed mismatch incidents list

## Alerts Console
- Active alerts (freeze triggers)
- Incident timeline
- Operator actions (manual freeze/safe mode toggles)


Kirjoita myös ARCHITECTURE.md + DATA_CONTRACTS.md + REPLAY.md + RUNBOOK.md samalla tarkkuudella (ei koodia, mutta täsmälliset schemat ja operointipolut).

LLM vs ML? OR LLM?


Tässä on loput kriittiset dokumentit (**ARCHITECTURE.md**, **DATA_CONTRACTS.md**, **REPLAY.md**, **RUNBOOK.md**) samalla tarkkuudella. Lopussa lyhyt selvennys "LLM vs ML" -roolituksesta tässä arkkitehtuurissa.

---
