================================================================================
                              ANTIPATTERNS.MD
================================================================================
# Antipatterns: Vältettävät Virheet & Korjausehdotukset

> **Dokumentin tarkoitus:** Tunnista ja dokumentoi kriittiset virheet, jotka voivat tuhota järjestelmän. Jokainen antipattern sisältää: miksi vaarallinen, miten tunnistaa, miten korjata.

---

## Kategoriat

```
┌─────────────────────────────────────────────────────────────┐
│                    ANTIPATTERN CATEGORIES                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. MATEMATIIKKA & MALLINNUS                               │
│     └── Magic numbers, vakio-λ, vig-virhe                  │
│                                                             │
│  2. EXECUTION & TOTEUTUS                                   │
│     └── Slippage, fill rate, latenssi                      │
│                                                             │
│  3. RISKINHALLINTA                                         │
│     └── Tappioiden jahtaaminen, ei stop-loss               │
│                                                             │
│  4. DATA & VALIDOINTI                                      │
│     └── Lookahead bias, overfitting, survivorship          │
│                                                             │
│  5. PSYKOLOGIA & PROSESSI                                  │
│     └── Override, liian nopea skaalaus                     │
│                                                             │
│  6. TEKNINEN VELKA                                         │
│     └── Duplikaatio, ei testejä                            │
│                                                             │
│  7. MARKKINAKOHTAISET                                      │
│     └── Next Goal CHAOS, price moved                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 1. Matematiikka & Mallinnus

### 1.1 ❌ Magic Numbers Ilman Kalibrointia

**Virhe (nykyinen koodi):**
```python
# engine.py
t_score = threat + (danger_count * 0.05)  # mistä 0.05?

if t_score < 0.2:   # mistä 0.2?
    return "LOW"
if t_score > 0.8:   # mistä 0.8?
    return "PRESS"
```

**Miksi vaarallinen:**
- Ei tiedetä onko optimaalinen
- Ei skaalaudu eri liigat/markkinat
- Overfitting yhteen datasettiin mahdollinen

**Miten tunnistaa:**
```bash
grep -r "0\.[0-9]" brain/ engine.py | grep -v "test"
# Etsi kovakoodattuja desimaaleja
```

**Korjaus:**
```python
# config.yaml
tps:
  danger_weight: 0.05      # KALIBROITU: grid search 2026-02-XX
  low_threshold: 0.20      # KALIBROITU: optimaalinen Sharpe
  high_threshold: 0.80     # KALIBROITU: optimaalinen Sharpe
  calibration_date: "2026-02-15"
  calibration_data_size: 847

# engine.py
t_score = threat + (danger_count * self.config['tps']['danger_weight'])
```

**Checklist:**
- [ ] Jokainen numeerinen vakio on konfiguroitava
- [ ] Jokainen vakio on dokumentoitu (mistä tuli)
- [ ] Grid search on ajettu

---

### 1.2 ❌ Vakio-λ Koko Pelille

**Virhe:**
```python
# engine.py
xg_rate = xg_10m / 10.0 * 9  # olettaa vakio-intensiteetti
```

**Miksi vaarallinen:**
- 80. minuutti ≠ 20. minuutti (intensiteetti nousee)
- Johtotilanne ≠ tasatilanne (motivaatio eri)
- Alivoima ≠ täysi kokoonpano (dynamiikka muuttuu)

**Todellinen data:**
```
Minuutti 1-15:   λ = 0.028 goals/min
Minuutti 16-45:  λ = 0.031 goals/min
Minuutti 46-60:  λ = 0.029 goals/min
Minuutti 61-75:  λ = 0.033 goals/min
Minuutti 76-90:  λ = 0.041 goals/min  ← +47% vs alkupeli
```

**Korjaus:**
```python
def dynamic_lambda(minute, score_state, tps, xg_base):
    # Minuuttiadjusti
    minute_factor = MINUTE_FACTORS.get(minute_bucket(minute), 1.0)
    
    # Tilanne-adjusti
    score_factor = SCORE_FACTORS.get(score_state, 1.0)
    
    # TPS-adjusti
    tps_factor = TPS_FACTORS.get(tps, 1.0)
    
    return xg_base * minute_factor * score_factor * tps_factor
```

---

### 1.3 ❌ Vig-korjauksen Unohtaminen

**Virhe:**
```python
p_book = 1 / odds  # VÄÄRIN - sisältää vigin
```

**Miksi vaarallinen:**
- Vertaat omaa p:tä väärään baseline
- Yliarviot edgen systemaattisesti
- Tyypillinen vig: 5-8% (2-way market)

**Esimerkki:**
```
Odds: Home 2.10, Away 1.85
Raw probs: 47.6% + 54.1% = 101.7% (vig = 1.7%)

Oikeat implied probs:
  Home: 47.6% / 101.7% = 46.8%
  Away: 54.1% / 101.7% = 53.2%
```

**Korjaus:**
```python
def remove_vig(odds_list):
    """Remove vig from odds to get true implied probabilities."""
    raw_probs = [1/o for o in odds_list]
    total = sum(raw_probs)
    return [p/total for p in raw_probs]

# Käyttö
p_book_true = remove_vig([odds_home, odds_away])[0]
edge = p_model - p_book_true  # Oikea edge
```

---

### 1.4 ❌ Osumatarkkuus Ainoana Mittarina

**Virhe:**
```
"Malli osuu 55% ajasta → toimii!"
```

**Miksi vaarallinen:**
- Eri kertoimet = eri breakeven
- 55% @ 1.80 = tappiollinen (breakeven 55.6%)
- 45% @ 2.50 = voitollinen (breakeven 40%)

**Oikeat mittarit:**
| Mittari | Kaava | Käyttö |
|---------|-------|--------|
| ROI | (voitot - panokset) / panokset | Absoluuttinen tuotto |
| CLV | (entry_odds / close_odds) - 1 | Edge todiste |
| Brier | Σ(p - outcome)² / N | Kalibraatio |
| Sharpe | mean(returns) / std(returns) | Risk-adjusted |

**Korjaus:**
```python
def comprehensive_metrics(bets):
    return {
        'roi': calculate_roi(bets),
        'clv_mean': calculate_mean_clv(bets),
        'brier': calculate_brier(bets),
        'sharpe': calculate_sharpe(bets),
        'hit_rate': calculate_hit_rate(bets),  # vain referenssi
    }
```

---

## 2. Execution & Toteutus

### 2.1 ❌ Slippagen Ignorointi

**Virhe:**
```python
ev = p * odds_seen - 1  # olettaa saat tämän hinnan
```

**Miksi vaarallinen:**
- Live-markkinoilla 1-5 tikkiä slippage normaali
- CHAOS-tilanteissa 10+ tikkiä
- Koko edge voi kadota

**Todellinen data:**
```
Normaali tilanne:  E[slippage] = 0.02 (2 tikkiä)
PRESS:             E[slippage] = 0.04 (4 tikkiä)
CHAOS:             E[slippage] = 0.08 (8 tikkiä)
Punainen kortti:   E[slippage] = 0.15 (15 tikkiä)
```

**Korjaus:**
```python
def calculate_effective_ev(p_model, odds_seen, market_state):
    expected_slippage = slippage_model.predict(market_state)
    odds_expected = odds_seen - expected_slippage
    return p_model * odds_expected - 1
```

---

### 2.2 ❌ Fill Raten Unohtaminen

**Virhe:**
```
"Löysin +EV tilanteen!" → veto hylätään 40% ajasta
```

**Miksi vaarallinen:**
- Efektiivinen EV = P(fill) × EV
- Jos fill rate 60%, EV puolittuu
- Opportunity cost menetetyistä vedoista

**Korjaus:**
```python
def effective_ev_with_fill(p_model, odds, fill_rate):
    ev_if_filled = p_model * odds - 1
    opportunity_cost = 0.01  # menetetty aika
    return fill_rate * ev_if_filled - (1 - fill_rate) * opportunity_cost
```

---

### 2.3 ❌ Latenssin Aliarviointi

**Virhe:**
```
"3 sekunnin viive on ok"
```

**Miksi vaarallinen:**
- Live-markkinoilla 3s = ikuisuus
- Odds voi liikkua 5-10 tikkiä
- Suspend voi tulla

**Latenssin vaikutus:**
```
Latenssi    P(suspend)    E[slippage]
< 1s        5%            0.01
1-2s        10%           0.02
2-3s        20%           0.04
3-5s        35%           0.08
> 5s        50%           0.15
```

**Korjaus:**
```python
# Tiukemmat rajat eri tilanteille
LATENCY_LIMITS = {
    'LOW': 4.0,      # rauhallinen peli
    'MID': 3.0,      # normaali
    'PRESS': 2.0,    # korkea paine
    'CHAOS': 1.5,    # kriittinen
}

def check_latency_gate(latency, tps):
    limit = LATENCY_LIMITS.get(tps, 3.0)
    return latency <= limit
```

---

## 3. Riskinhallinta

### 3.1 ❌ Tappioiden Jahtaaminen

**Virhe:**
```
"Olen -5 yksikköä, nostetaan panosta"
```

**Miksi vaarallinen:**
- Klassinen gambler's fallacy
- Varianssi ei "korjaannu"
- Johtaa ruin-riskiin eksponentiaalisesti

**Korjaus:**
```python
class StakeManager:
    def get_stake(self, bankroll, recent_pnl):
        # KOSKAAN ei nosta panosta tappioiden jälkeen
        base_stake = bankroll * self.kelly_fraction
        
        # Voi LASKEA panosta drawdownin aikana
        if recent_pnl < -0.05 * bankroll:
            return base_stake * 0.5  # puolita
        
        return base_stake
```

---

### 3.2 ❌ Liian Monta Vetoa Per Ottelu

**Virhe:**
```
"Löysin 4 hyvää tilannetta samasta pelistä"
```

**Miksi vaarallinen:**
- Korreloituneet vedot
- Yksi maali voi tappaa kaikki
- Efektiivinen varianssi räjähtää

**Korjaus:**
```python
# config.yaml
limits:
  max_bets_per_match: 1      # LUKITTU
  max_latent_risk_per_match: 1
  
# engine.py
def check_match_limit(match_id, existing_bets):
    match_bets = [b for b in existing_bets if b.match_id == match_id]
    return len(match_bets) < config['limits']['max_bets_per_match']
```

---

### 3.3 ❌ Ei Stop-Loss Mekanismia

**Virhe:**
```
"Malli on hyvä, jatketaan vaikka -20%"
```

**Miksi vaarallinen:**
- Malli voi olla rikki
- Markkinat muuttuvat
- Ruin risk kasvaa eksponentiaalisesti

**Korjaus:**
```python
class RiskManager:
    STOP_LOSS = {
        'daily': -0.05,      # -5% päivässä
        'weekly': -0.10,     # -10% viikossa
        'drawdown': -0.15,   # -15% huipusta
    }
    
    def check_limits(self, metrics):
        for limit_type, threshold in self.STOP_LOSS.items():
            if metrics[limit_type] < threshold:
                self.freeze_system(reason=f"STOP_LOSS_{limit_type.upper()}")
                self.notify_human(urgent=True)
                return False
        return True
```

---

## 4. Data & Validointi

### 4.1 ❌ Lookahead Bias Backtestissä

**Virhe:**
```python
# Käytetään tulevaisuuden dataa päätöksessä
if match_result == "home_win":  # tiedät tämän vasta lopussa!
    ...
```

**Miksi vaarallinen:**
- Backtest näyttää liian hyvältä
- Live-tulokset pettävät
- Vaikea havaita

**Miten tunnistaa:**
```python
def check_lookahead(decision_time, data_used):
    for data_point in data_used:
        if data_point.timestamp > decision_time:
            raise LookaheadError(f"Using future data: {data_point}")
```

**Korjaus:**
```python
def replay_decision(events, odds, decision_time):
    # Käytä VAIN dataa joka oli saatavilla decision_time:ssa
    available_events = [e for e in events if e.t_recv <= decision_time]
    available_odds = [o for o in odds if o.t_recv <= decision_time]
    
    return engine.decide(available_events, available_odds[-1])
```

---

### 4.2 ❌ Survivorship Bias

**Virhe:**
```
"Testasin strategiaa EPL:ssä, toimii!"
```

**Miksi vaarallinen:**
- EPL on likvidein → helpoin
- Muut liigat voivat käyttäytyä eri tavalla
- Valitsit "voittajan" jälkikäteen

**Korjaus:**
```python
def validate_across_leagues(strategy, leagues):
    results = {}
    for league in leagues:
        data = load_league_data(league)
        metrics = backtest(strategy, data)
        results[league] = metrics
    
    # Tarkista konsistenssi
    rois = [r['roi'] for r in results.values()]
    if max(rois) - min(rois) > 0.10:
        print("WARNING: Large variance across leagues")
    
    return results
```

---

### 4.3 ❌ Overfitting Historiaan

**Virhe:**
```
"Optimoin parametrit kunnes ROI oli +15%"
```

**Miksi vaarallinen:**
- Löysit satunnaista kohinaa
- Ei yleisty tulevaisuuteen
- Mitä enemmän parametreja, sitä pahempi

**Tunnistus:**
```python
def detect_overfitting(train_metrics, test_metrics):
    gap = train_metrics['roi'] - test_metrics['roi']
    if gap > 0.05:  # > 5% ero
        print(f"WARNING: Possible overfitting. Gap: {gap:.2%}")
        return True
    return False
```

**Korjaus:**
```python
def cross_validate_time_series(data, strategy, n_splits=5):
    """Time-based cross-validation (ei random split!)"""
    results = []
    
    for i in range(n_splits):
        train_end = len(data) * (i + 1) // (n_splits + 1)
        test_end = len(data) * (i + 2) // (n_splits + 1)
        
        train = data[:train_end]
        test = data[train_end:test_end]
        
        strategy.fit(train)
        metrics = strategy.evaluate(test)
        results.append(metrics)
    
    return aggregate_results(results)
```

---

## 5. Psykologia & Prosessi

### 5.1 ❌ "Tiedän Paremmin" -Override

**Virhe:**
```
Malli sanoo NO BET, mutta "tuntuu hyvältä"
```

**Miksi vaarallinen:**
- Ihmisen bias > mallin objektiivisuus
- Ei voi mitata "tunteen" edgeä
- Tuhoaa koko systeemin pointin

**Korjaus:**
```python
class DecisionLogger:
    def log_override(self, model_decision, human_decision, reason):
        """
        Jos haluat overriden, tee siitä oma signaali.
        Mittaa override-vetojen ROI erikseen.
        """
        self.overrides.append({
            'model': model_decision,
            'human': human_decision,
            'reason': reason,
            'timestamp': datetime.now()
        })
    
    def override_performance(self):
        """Näytä miten overridet ovat performoineet."""
        return calculate_roi(self.overrides)
```

---

### 5.2 ❌ Liian Nopea Skaalaus

**Virhe:**
```
"50 vetoa, +8% ROI → nostetaan panokset 10x"
```

**Miksi vaarallinen:**
- 50 vetoa = tilastollisesti merkityksetön
- Varianssi voi olla 100% selitys
- Ruin risk skaalautuu

**Tarvittava otoskoko:**
```
Edge    Tarvittava N (95% CI)
2%      2500 vetoa
3%      1100 vetoa
5%      400 vetoa
10%     100 vetoa
```

**Korjaus:**
```python
def can_scale_up(bets, current_stake):
    if len(bets) < 500:
        return False, "Insufficient sample size"
    
    roi_ci = calculate_confidence_interval(bets)
    if roi_ci['lower'] <= 0:
        return False, "ROI CI includes zero"
    
    clv_mean = calculate_mean_clv(bets)
    if clv_mean <= 0:
        return False, "CLV not positive"
    
    return True, "OK to scale (max 2x)"
```

---

### 5.3 ❌ Ei Dokumentointia

**Virhe:**
```
"Muutin jotain, nyt toimii paremmin"
```

**Miksi vaarallinen:**
- Et tiedä mikä muutos auttoi
- Et voi toistaa
- Et voi debugata kun menee rikki

**Korjaus:**
```yaml
# CHANGELOG.md
## 2026-01-28
- Changed EV_MIN from 0.05 to 0.04
- Reason: Grid search showed better Sharpe at 0.04
- Data: 847 matches, 1203 decisions
- Before: Sharpe 1.21, ROI 3.2%
- After: Sharpe 1.42, ROI 4.1%
- Commit: abc123
```

---

## 6. Tekninen Velka

### 6.1 ❌ Duplikoitu Logiikka

**Virhe (nykyinen koodi):**
```python
# engine.py
def calculate_tps(events): ...

# brain/engine.py  
def calculate_tps(events): ...  # sama koodi!
```

**Miksi vaarallinen:**
- Muutokset pitää tehdä kahdesti
- Divergenssi ajan myötä
- Bugit vaikea jäljittää

**Korjaus:**
```python
# brain/core/tps.py (yksi totuuden lähde)
def calculate_tps(events): ...

# engine.py
from brain.core.tps import calculate_tps

# brain/engine.py
from brain.core.tps import calculate_tps
```

---

### 6.2 ❌ Ei Testejä Kriittiselle Logiikalle

**Virhe:**
```
# Ei yksikkötestejä EV-laskennalle
```

**Miksi vaarallinen:**
- Regressiot jäävät huomaamatta
- Refaktorointi pelottavaa
- Bugit päätyvät tuotantoon

**Korjaus:**
```python
# tests/test_engine.py
class TestEVCalculation:
    def test_positive_ev(self):
        ev = calculate_ev(p_model=0.6, odds=2.0)
        assert ev == 0.2  # 60% * 2.0 - 1 = 0.2
    
    def test_negative_ev(self):
        ev = calculate_ev(p_model=0.4, odds=2.0)
        assert ev == -0.2
    
    def test_edge_cases(self):
        assert calculate_ev(0, 2.0) == -1.0
        assert calculate_ev(1.0, 2.0) == 1.0
```

---

## 7. Markkinakohtaiset

### 7.1 ❌ Next Goal CHAOS-tilanteessa

**Virhe:**
```
"Molemmat hyökkää, lyödään Next Goal"
```

**Miksi vaarallinen:**
- Korkea varianssi
- Suspend-riski maksimi
- Slippage pahin mahdollinen

**Korjaus:**
```python
def next_goal_allowed(tps, control_ratio):
    # Next Goal vain kun yksi joukkue dominoi
    if tps == "CHAOS":
        return False, "CHAOS_NO_NEXT_GOAL"
    
    if control_ratio < 0.6:  # ei selkeää dominointia
        return False, "NO_CLEAR_DOMINANCE"
    
    return True, "OK"
```

---

### 7.2 ❌ Over/Under Kun Hinta Jo Liikkunut

**Virhe:**
```
"Over 2.5 näyttää hyvältä" (hinta tippunut 2.10 → 1.70)
```

**Miksi vaarallinen:**
- Edge on jo hinnoiteltu
- Olet myöhässä
- CLV negatiivinen

**Korjaus:**
```python
def check_price_movement(current_odds, odds_5min_ago):
    movement = (current_odds - odds_5min_ago) / odds_5min_ago
    
    if abs(movement) > 0.10:  # > 10% liike
        return False, "PRICE_MOVED_TOO_MUCH"
    
    return True, "OK"
```

---

## Yhteenveto: Top 10 Tappajaa

| # | Antipattern | Kategoria | Vaikutus | Prioriteetti |
|---|-------------|-----------|----------|--------------|
| 1 | Ei kalibrointia | Matematiikka | Ei tiedetä toimiiko | 🔴 KRIITTINEN |
| 2 | Slippagen ignorointi | Execution | Edge katoaa | 🔴 KRIITTINEN |
| 3 | Overfitting | Data | Live pettää | 🔴 KRIITTINEN |
| 4 | Tappioiden jahtaaminen | Riski | Ruin | 🔴 KRIITTINEN |
| 5 | Liian nopea skaalaus | Psykologia | Varianssi tappaa | 🔴 KRIITTINEN |
| 6 | Ei stop-loss | Riski | Ruin | 🟠 KORKEA |
| 7 | Vakio-λ | Matematiikka | Alioptimaalinen | 🟠 KORKEA |
| 8 | Fill rate ignorointi | Execution | Harhainen EV | 🟠 KORKEA |
| 9 | Lookahead bias | Data | Väärä backtest | 🟠 KORKEA |
| 10 | Override | Psykologia | Systeemin tuho | 🟡 KESKITASO |

---

## Checklist Ennen Jokaista Muutosta

```
□ Onko tämä kalibroitu datalla?
□ Onko out-of-sample testattu?
□ Huomioiko execution friction?
□ Onko dokumentoitu (miksi, milloin, data)?
□ Onko testit?
□ Onko train/test gap < 20%?
□ Onko CLV positiivinen?
```

---

## Checklist Ennen Jokaista Vetoa (Live)

```
□ Latenssi < raja?
□ Markkina ei suspended?
□ TPS ei LOW?
□ EV > minimi (execution huomioitu)?
□ Match limit ei täynnä?
□ Daily limit ei täynnä?
□ Hinta ei liikkunut > 10%?
```

---

*Dokumentti päivitetty: 2026-01-28*
*Versio: 2.0 — Korkea ambitiotaso*
