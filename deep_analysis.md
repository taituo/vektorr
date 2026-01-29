================================================================================
                              DEEP_ANALYSIS.MD
================================================================================
# Deep Analysis: Vektorr Arkkitehtuuri, Matematiikka & Kriittiset Puutteet

> **Dokumentin tarkoitus:** Syvällinen tekninen analyysi järjestelmän nykytilasta, matemaattisista malleista, arkkitehtuuripäätöksistä ja kriittisistä aukoista. Tämä on "totuuden dokumentti" — ei markkinointia, vaan raaka analyysi.

---

## 1. Arkkitehtuurin Anatomia

### 1.1 Datavirta (nykyinen)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           VEKTORR PIPELINE                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌───────────┐ │
│  │ DATA SOURCES │───▶│    SPINE     │───▶│   QUESTDB    │───▶│   BRAIN   │ │
│  │              │    │   (Rust)     │    │  (TimeSeries)│    │  (Python) │ │
│  │ SportMonks   │    │              │    │              │    │           │ │
│  │ The Odds API │    │ • Normalize  │    │ • events     │    │ • TPS     │ │
│  │ WebSocket    │    │ • Dedupe     │    │ • odds       │    │ • Gates   │ │
│  │ HTTP Poll    │    │ • ILP Write  │    │ • decisions  │    │ • EV Calc │ │
│  └──────────────┘    │ • Brain Call │    │ • mappings   │    │           │ │
│                      └──────────────┘    └──────────────┘    └─────┬─────┘ │
│                                                                     │       │
│                      ┌──────────────────────────────────────────────▼─────┐ │
│                      │                  EXECUTION                         │ │
│                      │  • Poll decisions from QuestDB                     │ │
│                      │  • Risk checks                                     │ │
│                      │  • Betfair adapter (stub)                          │ │
│                      │  • Audit logging                                   │ │
│                      └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Arkkitehtuurin Vahvuudet

| Komponentti | Päätös | Miksi Oikein |
|-------------|--------|--------------|
| **Spine (Rust)** | Rust ingestor | Muistiturvallinen, nopea, deterministinen. Ei GC-pauseja kriittisellä polulla. |
| **QuestDB** | Time-series DB | ILP-protokolla mahdollistaa >100k writes/s. Append-only = audit trail. |
| **Brain (Python)** | FastAPI service | Nopea iterointi malleihin. Pydantic = tiukat sopimukset. |
| **Separation** | Spine ≠ Brain ≠ Exec | Jokainen komponentti voi kaatua itsenäisesti. Dry-run mahdollinen. |
| **Fail-closed** | NO_BET default | Tuntematon tila = ei vetoa. Turvallinen lähtökohta. |

### 1.3 Arkkitehtuurin Heikkoudet

| Ongelma | Sijainti | Vaikutus | Kriittisyys |
|---------|----------|----------|-------------|
| **Single point of failure** | Brain service | Yksi prosessi, ei failover | 🔴 Korkea |
| **Globaali state** | `brain/service.py` | `state: Dict[str, MatchBuffer]` ei thread-safe | 🟠 Keskitaso |
| **Ei health monitoring** | Koko pipeline | Ei tiedetä jos komponentti kuolee | 🔴 Korkea |
| **Mapping gap** | Spine → Brain | Provider ID → internal ID mapping osittainen | 🟠 Keskitaso |
| **Execution stub** | `betfair_adapter.py` | Ei oikeaa toteutusta | 🟡 Matala (MVP) |

---

## 2. Matemaattinen Analyysi

### 2.1 Poisson-malli (nykyinen)

**Implementaatio (`engine.py`):**
```python
def calculate_probability(self, state, odds, xg_rate):
    tau = max(0.0, (91 - state.minute) / 90.0)
    return 1.0 - math.exp(-xg_rate * tau)
```

**Matemaattinen perusta:**
```
P(≥1 maali aikavälillä τ) = 1 - e^(-λτ)

missä:
  λ = maalien intensiteetti (goals/90min)
  τ = jäljellä oleva peliaika (0-1)
```

**Kriittiset oletukset:**

| Oletus | Todellisuus | Vaikutus |
|--------|-------------|----------|
| λ on vakio | λ vaihtelee minuutin, tilanteen, kokoonpanon mukaan | Alioptimaalinen p_model |
| xG_10m skaalautuu lineaarisesti | xG-intensiteetti ei ole tasainen | Harhainen estimaatti |
| Ei pelitila-adjustia | 0-0 ≠ 2-0 ≠ 1-1 | Menetetty informaatio |

**Korjausehdotus — Dynaaminen λ(t):**
```python
def dynamic_lambda(minute, score_state, tps, control_5m, red_card):
    """
    λ(t) = λ_base × exp(Σ βᵢ × featureᵢ)
    
    Kertoimet kalibroitava historiadata-analyysillä.
    """
    base = xg_10m / 10.0 * 9  # nykyinen
    
    # Minuuttiadjusti (75+ min = korkeampi intensiteetti)
    minute_factor = 1.0 + 0.3 * max(0, (minute - 60) / 30)
    
    # Tilanne-adjusti
    score_factor = {
        'trailing': 1.3,   # häviöllä oleva hyökkää
        'drawing': 1.0,
        'leading': 0.7,    # johdossa oleva puolustaa
    }.get(score_state, 1.0)
    
    # TPS-adjusti
    tps_factor = {'LOW': 0.5, 'MID': 1.0, 'PRESS': 1.5, 'CHAOS': 1.8}.get(tps, 1.0)
    
    # Punainen kortti
    red_factor = 1.4 if red_card else 1.0
    
    return base * minute_factor * score_factor * tps_factor * red_factor
```

### 2.2 TPS (Threat Pressure Score)

**Nykyinen implementaatio:**
```python
def calculate_tps(self, events):
    threat = sum(e.xg for e in events if e.type == "SHOT")
    danger_count = len([e for e in events if e.type == "DANGER_ATTACK"])
    card_count = len([e for e in events if e.type == "CARD"])
    
    if card_count >= 1 or (both_teams >= 2 and danger_count >= 4):
        return "CHAOS"
    
    t_score = threat + (danger_count * 0.05)  # ← MAGIC NUMBER
    
    if t_score < 0.2:   # ← MAGIC NUMBER
        return "LOW"
    if t_score > 0.8:   # ← MAGIC NUMBER
        return "PRESS"
    return "MID"
```

**Ongelmat:**

| Ongelma | Koodi | Vaikutus |
|---------|-------|----------|
| Magic numbers | `0.05`, `0.2`, `0.8` | Ei kalibroitu, ei perustetta |
| Ei normalisointia | `t_score` absoluuttinen | Eri ottelut, eri baseline |
| Kategorinen output | `LOW/MID/PRESS/CHAOS` | Menettää jatkuvan informaation |
| Ei aikaikkunan painotusta | Kaikki 10min tapahtumat samanarvoisia | Viimeisin 2min ≠ 8min sitten |

**Korjausehdotus — Kalibroitu TPS:**
```python
def calculate_tps_v2(events, match_baseline=None):
    """
    Z-score normalisoitu TPS + aikaikkunan painotus.
    """
    if not events:
        return 0.0, "LOW"
    
    now = max(e.t_event for e in events)
    
    # Aikaikkunan painotus (eksponentiaalinen decay)
    def time_weight(event):
        age_minutes = (now - event.t_event).total_seconds() / 60
        return math.exp(-0.2 * age_minutes)  # λ=0.2 → 5min half-life
    
    weighted_xg = sum(e.xg * time_weight(e) for e in events if e.type == "SHOT")
    weighted_danger = sum(time_weight(e) for e in events if e.type == "DANGER_ATTACK")
    
    raw_score = weighted_xg + weighted_danger * 0.05
    
    # Z-score normalisointi (jos baseline saatavilla)
    if match_baseline:
        z_score = (raw_score - match_baseline.mean) / match_baseline.std
    else:
        z_score = raw_score  # fallback
    
    # Jatkuva arvo + kategorinen label
    if z_score < -0.5:
        label = "LOW"
    elif z_score > 1.5:
        label = "PRESS"
    elif has_chaos_indicators(events):
        label = "CHAOS"
    else:
        label = "MID"
    
    return z_score, label
```

### 2.3 EV-laskenta

**Nykyinen:**
```python
ev = (p_model * odds.price) - 1
```

**Puutteet:**

| Puute | Vaikutus | Korjaus |
|-------|----------|---------|
| Ei vig-korjausta | Vertaa väärään baseline | `p_book = remove_vig(odds)` |
| Ei execution friction | Yliarvioitu EV | `ev_eff = p_fill × ev - (1-p_fill) × opp_cost` |
| Ei slippage-mallia | Todellinen hinta ≠ nähty hinta | `odds_expected = odds_seen - E[slippage]` |

**Oikea EV-kaava:**
```python
def calculate_effective_ev(p_model, odds_seen, execution_model):
    """
    EV_eff = P(fill) × [p_model × E[odds_fill] - 1] - (1 - P(fill)) × opportunity_cost
    """
    p_fill = execution_model.predict_fill_rate(odds_seen, market_state)
    expected_slippage = execution_model.predict_slippage(odds_seen, volatility)
    odds_expected = odds_seen - expected_slippage
    
    ev_if_filled = p_model * odds_expected - 1
    opportunity_cost = 0.01  # menetetty aika/tilaisuus
    
    return p_fill * ev_if_filled - (1 - p_fill) * opportunity_cost
```

---

## 3. Gate-logiikan Analyysi

### 3.1 Nykyiset Portit

```python
# engine.py - evaluate_gates()

GATE 1: LATENCY_HIGH      if event_latency_p95 > L_MAX (3.0s)
GATE 2: MARKET_SUSPENDED  if odds.is_suspended
GATE 3: QUALITY_LOW       if tps_label == "LOW"
GATE 4: QUALITY_LOW       if xg_10m < XG_10M_MIN (0.2)
GATE 5: EV_LOW            if ev < EV_MIN (0.05)
```

### 3.2 Puuttuvat Portit

| Gate | Tarkoitus | Miksi Kriittinen |
|------|-----------|------------------|
| **EXEC_RISK** | Mallinna P(fill), slippage | Ilman tätä EV on harhainen |
| **DISCONFIRM** | 10min vs 1min trendi | Estää "vanhan signaalin" vedon |
| **PRICE_MOVED** | Odds jo liikkunut | Edge hinnoiteltu pois |
| **MMS** | Market Mispricing Score | Tunnista anomaliat |
| **MATCH_LIMIT** | Max 1 latentti riski/ottelu | Korrelaatioriski |
| **DAILY_LIMIT** | Stop-loss | Ruin-suoja |

**Ehdotettu gate-hierarkia:**
```
┌─────────────────────────────────────────────────────────────┐
│                    GATE HIERARCHY                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  TIER 1: HARD KILL (välitön hylkäys)                       │
│  ├── LATENCY_HIGH (>3s)                                    │
│  ├── MARKET_SUSPENDED                                       │
│  ├── DAILY_STOP_LOSS_HIT                                   │
│  └── SYSTEM_FREEZE                                          │
│                                                             │
│  TIER 2: QUALITY (signaalin laatu)                         │
│  ├── TPS_LOW                                                │
│  ├── XG_INSUFFICIENT                                        │
│  ├── DISCONFIRM_ACTIVE (trendi kääntynyt)                  │
│  └── DATA_STALE (>30s vanha)                               │
│                                                             │
│  TIER 3: VALUE (onko edge)                                 │
│  ├── EV_LOW (<5%)                                          │
│  ├── PRICE_MOVED (>3 tikkiä)                               │
│  └── MMS_LOW (markkina ei mispriced)                       │
│                                                             │
│  TIER 4: EXECUTION (toteutusriski)                         │
│  ├── EXEC_RISK_HIGH (P(fill) < 60%)                        │
│  ├── SLIPPAGE_EXPECTED_HIGH                                │
│  └── VOLATILITY_EXTREME                                     │
│                                                             │
│  TIER 5: PORTFOLIO (kokonaisriski)                         │
│  ├── MATCH_LIMIT_REACHED                                   │
│  ├── EXPOSURE_LIMIT                                         │
│  └── CORRELATION_RISK                                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Kalibraatio-ongelma

### 4.1 Nykytila: Ei Validointia

**Kriittinen puute:** Järjestelmä ei mittaa omaa tarkkuuttaan.

| Mittari | Tila | Vaikutus |
|---------|------|----------|
| Brier Score | Ei implementoitu | Ei tiedetä mallin tarkkuutta |
| Calibration | Ei implementoitu | Ei tiedetä onko p=0.6 → 60% |
| CLV | Ei implementoitu | Ei tiedetä onko edge todellinen |
| Log Loss | Ei implementoitu | Ei voi vertailla malleja |

### 4.2 Parametrit Ilman Perustetta

| Parametri | Arvo | Perustelu | Ongelma |
|-----------|------|-----------|---------|
| `L_MAX` | 3.0s | "Tuntuu järkevältä" | Ei dataa |
| `XG_10M_MIN` | 0.2 | "Riittävä aktiivisuus" | Ei kalibroitu |
| `EV_MIN` | 0.05 | "5% edge" | Ei huomioi execution |
| TPS kynnykset | 0.2/0.8 | "Intuitio" | Magic numbers |

### 4.3 Kalibraatioputki (tarvitaan)

```python
class CalibrationPipeline:
    """
    Jatkuva kalibraatio ja validointi.
    """
    
    def __init__(self, history_db):
        self.history = history_db
    
    def calculate_brier_score(self, predictions, outcomes):
        """
        Brier = (1/N) × Σ(p_i - o_i)²
        Pienempi = parempi. 0 = täydellinen.
        """
        return sum((p - o)**2 for p, o in zip(predictions, outcomes)) / len(predictions)
    
    def calibration_plot_data(self, predictions, outcomes, bins=10):
        """
        Ryhmittele ennusteet bineihin, laske toteutunut % per bin.
        """
        bin_edges = [i/bins for i in range(bins+1)]
        results = []
        
        for i in range(bins):
            low, high = bin_edges[i], bin_edges[i+1]
            mask = [(low <= p < high) for p in predictions]
            bin_preds = [p for p, m in zip(predictions, mask) if m]
            bin_outs = [o for o, m in zip(outcomes, mask) if m]
            
            if bin_preds:
                results.append({
                    'bin_center': (low + high) / 2,
                    'mean_predicted': sum(bin_preds) / len(bin_preds),
                    'actual_rate': sum(bin_outs) / len(bin_outs),
                    'count': len(bin_preds)
                })
        
        return results
    
    def calculate_clv(self, entry_odds, closing_odds):
        """
        CLV = (entry_odds / closing_odds) - 1
        
        Positiivinen CLV = lyöty ennen markkinaa.
        """
        return (entry_odds / closing_odds) - 1
    
    def rolling_metrics(self, window=100):
        """
        Viimeisen N vedon metriikat.
        """
        recent = self.history.get_recent_bets(window)
        return {
            'roi': self.calculate_roi(recent),
            'clv_mean': self.calculate_mean_clv(recent),
            'brier': self.calculate_brier_score(
                [b.p_model for b in recent],
                [b.won for b in recent]
            ),
            'sharpe': self.calculate_sharpe(recent),
        }
```

---

## 5. Execution-matematiikka

### 5.1 Slippage-malli (puuttuu)

**Todellisuus live-markkinoilla:**
- Normaali: 1-3 tikkiä slippage
- CHAOS/punainen kortti: 5-15 tikkiä
- Suspend-riski: 10-30% tilanteesta riippuen

**Ehdotettu malli:**
```python
class SlippageModel:
    """
    E[slippage] = f(volatility, latency, market_depth, minute, chaos_index)
    """
    
    def predict(self, market_state):
        base_slippage = 0.02  # 2 tikkiä baseline
        
        # Volatiliteetti-kerroin
        vol_factor = 1.0 + market_state.volatility * 2.0
        
        # Minuutti-kerroin (loppupeli = enemmän slippagea)
        minute_factor = 1.0 + max(0, (market_state.minute - 70) / 20) * 0.5
        
        # CHAOS-kerroin
        chaos_factor = {'LOW': 1.0, 'MID': 1.2, 'PRESS': 1.5, 'CHAOS': 2.5}[market_state.tps]
        
        return base_slippage * vol_factor * minute_factor * chaos_factor
```

### 5.2 Fill Rate -malli (puuttuu)

```python
class FillRateModel:
    """
    P(fill) = g(odds_movement, suspend_risk, stake_size, latency)
    """
    
    def predict(self, order_context):
        base_fill = 0.85  # 85% baseline
        
        # Odds-liike viimeisen 30s aikana
        if order_context.odds_moved > 0.05:
            base_fill -= 0.20  # -20% jos hinta liikkunut
        
        # Suspend-riski
        suspend_risk = self.estimate_suspend_risk(order_context)
        base_fill -= suspend_risk * 0.30
        
        # Stake-koko (isompi = vaikeampi täyttää)
        if order_context.stake > 50:
            base_fill -= 0.10
        
        return max(0.1, min(0.95, base_fill))
```

---

## 6. Tilastollinen Analyysi

### 6.1 Varianssi ja Otoskoko

**Live-vedonlyönnin realiteetit:**
- Tyypillinen edge: 2-5%
- Varianssi: KORKEA (yksittäiset vedot)
- Tarvittava otoskoko merkitsevyyteen: 500-2000 vetoa

**Kelly-kaava (ei implementoitu):**
```
f* = (p × b - q) / b

missä:
  f* = optimaalinen panososuus
  p = voittotodennäköisyys
  b = odds - 1
  q = 1 - p
```

**Miksi flat stake MVP:ssä:**
- Kelly vaatii tarkan p-estimaatin
- Yliarvioidulla p:llä Kelly tuhoaa
- Flat stake = turvallinen kunnes malli kalibroitu

### 6.2 Ruin-riski

```python
def calculate_ruin_probability(edge, variance, bankroll_units, target_units=0):
    """
    P(ruin) ≈ ((1-edge)/(1+edge))^(bankroll_units)
    
    Yksinkertaistettu kaava; todellisuudessa monimutkaisempi.
    """
    if edge <= 0:
        return 1.0  # Negatiivinen edge = varma ruin
    
    ratio = (1 - edge) / (1 + edge)
    return ratio ** bankroll_units
```

### 6.3 Confidence Intervals

**Nykyinen ongelma:** Ei raportoida epävarmuutta.

```python
def roi_confidence_interval(bets, confidence=0.95):
    """
    ROI:n luottamusväli bootstrap-menetelmällä.
    """
    n_bootstrap = 1000
    roi_samples = []
    
    for _ in range(n_bootstrap):
        sample = random.choices(bets, k=len(bets))
        roi = sum(b.pnl for b in sample) / sum(b.stake for b in sample)
        roi_samples.append(roi)
    
    roi_samples.sort()
    lower_idx = int((1 - confidence) / 2 * n_bootstrap)
    upper_idx = int((1 + confidence) / 2 * n_bootstrap)
    
    return {
        'mean': sum(roi_samples) / len(roi_samples),
        'lower': roi_samples[lower_idx],
        'upper': roi_samples[upper_idx],
        'confidence': confidence
    }
```

---

## 7. Kriittisten Puutteiden Yhteenveto

### 7.1 Prioriteettijärjestys

| # | Puute | Vaikutus | Korjauksen Vaativuus | Prioriteetti |
|---|-------|----------|---------------------|--------------|
| 1 | **Ei kalibrointia** | Ei tiedetä toimiiko malli | Keskitaso | 🔴 KRIITTINEN |
| 2 | **Ei CLV-mittausta** | Ei tiedetä onko edge todellinen | Matala | 🔴 KRIITTINEN |
| 3 | **Vakio-λ** | Alioptimaalinen p_model | Keskitaso | 🟠 KORKEA |
| 4 | **Ei execution risk** | Yliarvioitu EV | Korkea | 🟠 KORKEA |
| 5 | **Magic numbers** | Ei optimaaliset kynnykset | Keskitaso | 🟠 KORKEA |
| 6 | **Ei health monitoring** | Ei tiedetä jos järjestelmä rikki | Matala | 🟠 KORKEA |
| 7 | **Single Brain instance** | Ei failover | Keskitaso | 🟡 KESKITASO |
| 8 | **Ei ML** | Menetetty potentiaali | Korkea | 🟡 KESKITASO |
| 9 | **Flat stake** | Suboptimaalinen kasvu | Matala | 🟡 KESKITASO |

### 7.2 Välittömät Toimenpiteet

```
VIIKKO 1-2:
├── Implementoi Brier score + calibration plot
├── Lisää CLV-mittaus (tallenna closing odds)
├── Lisää health endpoint + alerting
└── Dokumentoi parametrien perusteet

VIIKKO 3-4:
├── Grid search parametreille (backtest)
├── Implementoi execution risk gate
├── Lisää disconfirmation gate
└── Testaa dynaaminen λ(t)
```

---

## 8. Johtopäätökset

### 8.1 Arkkitehtuuri: ✅ Hyvä Pohja

Spine → QuestDB → Brain → Execution -putki on oikein suunniteltu:
- Rust kriittisellä polulla
- Time-series DB audit trailille
- Python nopeaan iterointiin
- Separation of concerns

### 8.2 Matematiikka: ⚠️ Vaatii Työtä

- Poisson-malli on OK lähtökohta, mutta vakio-λ on liian yksinkertainen
- TPS-logiikka toimii, mutta magic numbers pitää kalibroida
- EV-laskenta ei huomioi execution frictionia

### 8.3 Validointi: 🔴 Kriittinen Puute

- Ei kalibraatiometriikoita
- Ei CLV-mittausta
- Ei tiedetä toimiiko järjestelmä oikeasti

### 8.4 Seuraava Askel

**Ennen yhtään oikeaa euroa:**
1. Implementoi kalibraatioputki
2. Aja 500+ paper trade -vetoa
3. Validoi CLV > 0 ja ROI > 0 (95% CI)
4. Kalibroi parametrit grid searchilla

**Vasta sitten:** Tier 2 (micro live).

---

*Dokumentti päivitetty: 2026-01-28*
*Versio: 2.0 — Korkea ambitiotaso*
