# Testbench: LLM-Generated Generators & Massive Simulation

> **Ydinidea:** LLM ei generoi dataa — LLM generoi **generaattoreita** (Python-koodia) jotka tuottavat rajattomasti realistista dataa. Tämä on 10x nopeampi tapa rakentaa testausinfra.

---

## Paradigman Muutos

```
VANHA TAPA (hidas):
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ Ihminen     │────▶│ Kirjoittaa  │────▶│ Testaa      │
│ suunnittelee│     │ generaattori│     │ debuggaa    │
└─────────────┘     └─────────────┘     └─────────────┘
      │                   │                   │
      └───────────────────┴───────────────────┘
                    VIIKKOJA

UUSI TAPA (nopea):
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ Ihminen     │────▶│ LLM generoi │────▶│ Generaattori│
│ kuvaa       │     │ KOODIN      │     │ tuottaa     │
│ vaatimukset │     │             │     │ ∞ dataa     │
└─────────────┘     └─────────────┘     └─────────────┘
      │                   │                   │
      └───────────────────┴───────────────────┘
                    TUNTEJA
```

---

## 1. Miksi Tämä On Edge

### 1.1 Perinteinen Ongelma

| Tehtävä | Perinteinen aika | Ongelmat |
|---------|------------------|----------|
| Mock server | 2-3 päivää | Formaatit väärin, edge caset puuttuu |
| Data generator | 1-2 päivää | Ei realistinen, kovakoodattu |
| Odds simulator | 1-2 päivää | Ei reagoi tapahtumiin oikein |
| Broker mock | 2-3 päivää | Fill/reject logiikka puuttuu |
| **Yhteensä** | **1-2 viikkoa** | **Silti buginen** |

### 1.2 LLM-Generoidut Generaattorit

| Tehtävä | LLM-aika | Etu |
|---------|----------|-----|
| Mock server | 30 min | Täydellinen formaatti heti |
| Data generator | 30 min | Realistinen, parametrisoitu |
| Odds simulator | 30 min | Reagoi tapahtumiin |
| Broker mock | 30 min | Fill/reject/slippage |
| **Yhteensä** | **2-3 tuntia** | **Toimii heti** |

### 1.3 Miksi Toimii

1. **LLM ymmärtää domainit** — jalkapallo, kertoimet, markkinadynamiikka
2. **LLM osaa formaatit** — JSON, Pydantic, API-vastaukset
3. **LLM generoi KOODIA** — ei dataa, vaan työkaluja
4. **Koodi tuottaa ∞ dataa** — yksi generaattori = miljoonat rivit

---

## 2. Generaattori-Arkkitehtuuri

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    LLM-GENERATED GENERATOR STACK                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  LAYER 1: DATA GENERATORS (LLM writes these)                               │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐            │
│  │ MatchGenerator  │  │ OddsGenerator   │  │ EventGenerator  │            │
│  │                 │  │                 │  │                 │            │
│  │ • Team profiles │  │ • Market model  │  │ • xG model      │            │
│  │ • League styles │  │ • Reaction time │  │ • Event timing  │            │
│  │ • Score patterns│  │ • Volatility    │  │ • Correlations  │            │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘            │
│           │                   │                   │                        │
│           └───────────────────┼───────────────────┘                        │
│                               ▼                                            │
│  LAYER 2: SIMULATION ENGINE                                                │
│  ┌─────────────────────────────────────────────────────────────┐          │
│  │ SimulationOrchestrator                                       │          │
│  │ • Runs generators in sync                                    │          │
│  │ • Maintains match state                                      │          │
│  │ • Feeds Brain API                                            │          │
│  │ • Collects decisions                                         │          │
│  └─────────────────────────────────────────────────────────────┘          │
│                               │                                            │
│                               ▼                                            │
│  LAYER 3: MOCK BROKER                                                      │
│  ┌─────────────────────────────────────────────────────────────┐          │
│  │ MockBroker                                                   │          │
│  │ • Realistic fill/reject                                      │          │
│  │ • Slippage model                                             │          │
│  │ • Latency simulation                                         │          │
│  │ • Order book dynamics                                        │          │
│  └─────────────────────────────────────────────────────────────┘          │
│                               │                                            │
│                               ▼                                            │
│  LAYER 4: ANALYSIS                                                         │
│  ┌─────────────────────────────────────────────────────────────┐          │
│  │ TestbenchAnalyzer                                            │          │
│  │ • P&L calculation                                            │          │
│  │ • CLV measurement                                            │          │
│  │ • Gate statistics                                            │          │
│  │ • Comparison reports                                         │          │
│  └─────────────────────────────────────────────────────────────┘          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. LLM Promptit Generaattoreille

### 3.1 Event Generator Prompt

```
Kirjoita Python-luokka EventGenerator joka:

1. Generoi jalkapallo-ottelun tapahtumat minuutti minuutilta
2. Parametrit:
   - home_strength (0-100)
   - away_strength (0-100) 
   - match_tempo: 'low' | 'normal' | 'high'
   - chaos_factor (0-1)

3. Tapahtumatyypit: SHOT, DANGER_ATTACK, GOAL, CARD, RED_CARD
4. xG-arvot realistisia (SHOT: 0.02-0.8)
5. Tapahtumien tiheys vaihtelee:
   - Alkupeli: harvempi
   - Loppupeli: tiheämpi jos tasapeli
   - Maalin jälkeen: hetkellinen piikki

6. Output: List[Event] jossa Event on Pydantic-malli:
   - minute: int
   - type: str
   - team: 'HOME' | 'AWAY'
   - xg: float
   - t_event: datetime
   - t_recv: datetime (+ random latency 0.5-3s)

7. Käytä numpy/random, ei ulkoisia API-kutsuja
8. Sisällytä docstringit ja type hints
```

### 3.2 Odds Generator Prompt

```
Kirjoita Python-luokka OddsGenerator joka:

1. Simuloi live-kertoimien liikkeitä
2. Reagoi tapahtumiin realistisesti:
   - GOAL: iso liike (0.3-0.8 riippuen minuutista)
   - DANGER_ATTACK: pieni liike (0.01-0.03)
   - RED_CARD: keskisuuri (0.1-0.3)

3. Parametrit:
   - initial_odds: dict (over_2.5, under_2.5, etc)
   - volatility: float (0-1)
   - market_efficiency: float (0-1, kuinka nopeasti reagoi)

4. Suspend-logiikka:
   - GOAL: suspend 3-8s
   - Vaarallinen tilanne: suspend 0.5-2s
   - Satunnainen suspend: 1% todennäköisyys

5. Output per tick:
   - price: float
   - is_suspended: bool
   - spread: float (back-lay ero)
   - t_seen: datetime

6. Sisällytä mean reversion (kertoimet palautuvat "oikeaan" hintaan)
```

### 3.3 Mock Broker Prompt

```
Kirjoita Python-luokka MockBroker joka:

1. Simuloi Betfair-tyyppinen exchange
2. place_order(match_id, side, price, stake) -> FillResult

3. Fill-logiikka:
   - Base fill rate: 85%
   - Jos hinta liikkunut >2%: -20% fill rate
   - Jos stake >€50: -15% fill rate
   - Jos suspended: 0% fill rate
   - Jos CHAOS-tilanne: -25% fill rate

4. Slippage-malli:
   - Base: 1-2 tikkiä
   - Volatility kerroin
   - Stake size kerroin
   - Minute kerroin (loppupeli = enemmän)

5. Latenssi:
   - Mean: 150ms
   - Std: 50ms
   - Occasional spike: 5% todennäköisyys 500ms+

6. Tallenna kaikki:
   - fills: List[Fill]
   - rejects: List[Reject]
   - slippage_stats: dict

7. Metodit:
   - place_order()
   - update_market_state()
   - get_statistics()
```

---

## 4. Historiallisen Datan Remix

### 4.1 Konsepti

```
┌─────────────────────────────────────────────────────────────────┐
│                    HISTORICAL DATA REMIX                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  OIKEA DATA              REMIX                 SYNTEETTINEN     │
│  ┌─────────┐            ┌─────────┐           ┌─────────┐      │
│  │ EPL     │            │ Shuffle │           │ "Uusi"  │      │
│  │ 2024-25 │ ────────▶  │ Mutate  │ ───────▶  │ kausi   │      │
│  │ 380     │            │ Combine │           │ 380     │      │
│  │ ottelua │            │         │           │ ottelua │      │
│  └─────────┘            └─────────┘           └─────────┘      │
│                                                                 │
│  REMIX OPERAATIOT:                                             │
│  • Vaihda joukkueet (Arsenal vs Liverpool → Chelsea vs Spurs)  │
│  • Muuta tulosta (2-1 → 2-2, lisää yksi maali)                 │
│  • Siirrä tapahtumia (maali 45' → 88')                         │
│  • Yhdistä otteluita (1. puoliaika A + 2. puoliaika B)         │
│  • Lisää kohinaa (xG ±10%, ajoitus ±2min)                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Remix Generator Prompt

```
Kirjoita Python-luokka HistoricalRemixer joka:

1. Lataa oikean ottelun data (events, odds)
2. Remix-operaatiot:
   - swap_teams(): vaihda koti/vieras
   - shift_time(minutes): siirrä kaikkia tapahtumia
   - add_goal(minute, team): lisää maali
   - remove_goal(minute): poista maali
   - add_noise(xg_std, time_std): lisää satunnaisuutta
   - change_tempo(factor): nopeuta/hidasta tapahtumia

3. Combine-operaatiot:
   - merge_halves(match_a, match_b): yhdistä puoliajat
   - splice_period(match_a, match_b, start, end): yhdistä jaksoja

4. Validointi:
   - Tapahtumat aikajärjestyksessä
   - xG-summat realistisia
   - Maalit vastaavat GOAL-tapahtumia

5. Output: sama formaatti kuin alkuperäinen data
```

---

## 5. Testbench Workflow

### 5.1 Generaattorien Luonti (kerran)

```bash
# 1. Generoi EventGenerator
llm generate \
    --prompt prompts/event_generator.md \
    --output tools/generators/event_generator.py \
    --validate

# 2. Generoi OddsGenerator  
llm generate \
    --prompt prompts/odds_generator.md \
    --output tools/generators/odds_generator.py \
    --validate

# 3. Generoi MockBroker
llm generate \
    --prompt prompts/mock_broker.md \
    --output tools/generators/mock_broker.py \
    --validate

# 4. Generoi HistoricalRemixer
llm generate \
    --prompt prompts/historical_remixer.md \
    --output tools/generators/historical_remixer.py \
    --validate
```

### 5.2 Massiivinen Simulaatio (toistuvasti)

```bash
# Generoi 10,000 ottelua (kestää ~10 min)
python tools/testbench_runner.py \
    --mode synthetic \
    --matches 10000 \
    --leagues "EPL,LaLiga,UCL" \
    --output data/synthetic_10k.jsonl

# Tai remix historiallisesta
python tools/testbench_runner.py \
    --mode remix \
    --source data/historical_epl_2024.jsonl \
    --remix-count 5000 \
    --output data/remixed_5k.jsonl
```

### 5.3 Sokkotestaus

```bash
# Brain ei tiedä että data on synteettistä
python tools/blind_test.py \
    --brain-url http://localhost:8090 \
    --data data/synthetic_10k.jsonl \
    --broker-mode realistic \
    --output results/blind_test_001.json
```

### 5.4 Analyysi

```bash
python tools/analyze_results.py \
    --input results/blind_test_001.json \
    --compare-to results/real_data_baseline.json \
    --report results/comparison_report.md
```

---

## 6. Generaattori-Kirjasto

### 6.1 Valmiit Generaattorit (LLM-generoituja)

```
tools/generators/
├── event_generator.py      # Ottelutapahtumat
├── odds_generator.py       # Kertoimien liikkeet
├── mock_broker.py          # Exchange-simulaatio
├── historical_remixer.py   # Historiadata remix
├── team_profiles.py        # Joukkuekohtaiset parametrit
├── league_styles.py        # Liigakohtaiset tyylit
├── chaos_injector.py       # Edge case -generaattori
└── latency_simulator.py    # Verkkoviive-simulaatio
```

### 6.2 Joukkueprofiilit (generoitu)

```python
# tools/generators/team_profiles.py

TEAM_PROFILES = {
    'Manchester City': {
        'strength': 92,
        'style': 'possession',
        'xg_per_90': 2.4,
        'xga_per_90': 0.8,
        'tempo': 'high',
        'late_goals_tendency': 0.7,  # usein maaleja loppupelissä
    },
    'Burnley': {
        'strength': 58,
        'style': 'direct',
        'xg_per_90': 1.1,
        'xga_per_90': 1.6,
        'tempo': 'low',
        'late_goals_tendency': 0.4,
    },
    # ... 500+ joukkuetta
}
```

### 6.3 Liigaprofiilit (generoitu)

```python
# tools/generators/league_styles.py

LEAGUE_PROFILES = {
    'Premier League': {
        'avg_goals': 2.8,
        'tempo': 'high',
        'card_frequency': 'medium',
        'var_usage': 'high',
        'home_advantage': 1.15,
    },
    'La Liga': {
        'avg_goals': 2.5,
        'tempo': 'medium',
        'card_frequency': 'high',
        'var_usage': 'high',
        'home_advantage': 1.20,
    },
    'Champions League': {
        'avg_goals': 2.9,
        'tempo': 'very_high',
        'card_frequency': 'medium',
        'var_usage': 'high',
        'home_advantage': 1.10,
    },
}
```

---

## 7. Edge Case Generator

### 7.1 Chaos Injector Prompt

```
Kirjoita Python-luokka ChaosInjector joka:

1. Generoi harvinaisia mutta tärkeitä tilanteita:
   - 5+ maalia ottelussa
   - 3 punaista korttia
   - Maali 90+5 minuutilla
   - VAR-peruutus (maali → ei maali)
   - Keskeytys (sää, floodlight failure)

2. Parametrit:
   - chaos_level: 'mild' | 'medium' | 'extreme'
   - target_scenario: str (optional, specific scenario)

3. Injektoi olemassa olevaan otteluun:
   - inject_late_drama(match, num_goals)
   - inject_red_card_chaos(match)
   - inject_var_drama(match)
   - inject_suspension(match, duration_minutes)

4. Käyttö: testaa miten Brain käsittelee edge caseja
```

---

## 8. Formaattien Yhteensopivuus

### 8.1 Validaatiokerros

```python
# tools/validators/format_validator.py

class FormatValidator:
    """
    Varmistaa että generoitu data vastaa oikeaa dataa.
    """
    
    def __init__(self, reference_data_path: str):
        self.reference = self._load_reference(reference_data_path)
    
    def validate_event(self, event: dict) -> ValidationResult:
        """Vertaa generoitua eventtiä oikeaan."""
        
    def validate_odds(self, odds: dict) -> ValidationResult:
        """Vertaa generoituja kertoimia oikeisiin."""
        
    def validate_match(self, match: dict) -> ValidationResult:
        """Kokonaisvalidointi."""
        
    def generate_compatibility_report(self) -> str:
        """Raportti formaattien yhteensopivuudesta."""
```

### 8.2 Auto-Fix

```python
class FormatAutoFixer:
    """
    Korjaa pienet formaattivirheet automaattisesti.
    """
    
    def fix_timestamps(self, data: dict) -> dict:
        """Korjaa aikaleima-formaatit."""
        
    def fix_field_names(self, data: dict) -> dict:
        """Korjaa kenttänimet (camelCase → snake_case)."""
        
    def fix_types(self, data: dict) -> dict:
        """Korjaa tyypit (str → float, etc)."""
```

---

## 9. Käyttöesimerkit

### 9.1 Nopea Testi (5 min)

```bash
# Generoi 100 ottelua, testaa Brain
python tools/quick_test.py --matches 100
```

### 9.2 Kattava Validointi (1h)

```bash
# 10,000 ottelua, kaikki liigat, edge caset
python tools/full_validation.py \
    --matches 10000 \
    --include-chaos \
    --include-remix \
    --parallel 8
```

### 9.3 A/B Parametritesti (30 min)

```bash
# Vertaa kahta konfiguraatiota
python tools/ab_test.py \
    --config-a config_v1.yaml \
    --config-b config_v2.yaml \
    --matches 5000
```

### 9.4 Regressiotesti (10 min)

```bash
# Varmista että muutokset eivät riko mitään
python tools/regression_test.py \
    --baseline results/baseline.json \
    --current results/current.json
```

---

## 10. Yhteenveto: Miksi Tämä On 10x

| Aspekti | Perinteinen | LLM-Generaattorit |
|---------|-------------|-------------------|
| **Aika** | 1-2 viikkoa | 2-3 tuntia |
| **Formaatit** | Manuaalinen debug | Oikein heti |
| **Edge caset** | Unohdetaan | Sisäänrakennettu |
| **Ylläpito** | Jatkuva työ | Regeneroi tarvittaessa |
| **Datamäärä** | Rajallinen | Rajaton |
| **Realistisuus** | Vaihtelee | Korkea (domain knowledge) |

**Avain:** LLM ei ole data-generaattori — LLM on **työkalu-generaattori**. Yksi hyvä generaattori tuottaa miljoonat datarivit.

---

## 11. Universal Data Converters

### 11.1 Ongelma (perinteinen)

```
SportMonks API     ──┐
The Odds API       ──┼──▶  ERI FORMAATIT  ──▶  Manuaalinen mapping  ──▶  VIIKKOJA
BetsAPI            ──┤                         per provider
Betfair Stream     ──┤                         bugit, edge caset
Historical CSV     ──┘                         ylläpito helvetti
```

### 11.2 Ratkaisu: LLM-Generated Converters

```
SportMonks API     ──┐
The Odds API       ──┤     LLM generoi          UNIFIED FORMAT
BetsAPI            ──┼──▶  KONVERTTERIT   ──▶   (Vektorr internal)
Betfair Stream     ──┤     per provider         
Historical CSV     ──┘     ~30 min / provider   TUNTEJA, EI VIIKKOJA
```

### 11.3 Converter Generator Prompt

```
Tässä on esimerkki SportMonks API -vastauksesta:
{raw_response}

Tässä on Vektorr internal Event schema:
{target_schema}

Kirjoita Python-funktio `convert_sportmonks_event(raw: dict) -> Event`
joka konvertoi SportMonks-formaatin Vektorr-formaattiin.

Huomioi:
- Kenttänimet (camelCase → snake_case)
- Aikaleima-formaatit (ISO → datetime)
- Enum-arvot (SportMonks type → Vektorr type)
- Puuttuvat kentät (default-arvot)
- Edge caset (null-arvot, tyhjät listat)

Sisällytä:
- Type hints
- Docstring
- Unit test esimerkit
```

### 11.4 Converter Library

```
tools/converters/
├── sportmonks_converter.py    # LLM-generoitu
├── odds_api_converter.py      # LLM-generoitu
├── betsapi_converter.py       # LLM-generoitu
├── betfair_converter.py       # LLM-generoitu
├── flashscore_converter.py    # LLM-generoitu
├── csv_converter.py           # LLM-generoitu
└── universal_converter.py     # Auto-detect + route
```

### 11.5 Universal Converter

```python
# tools/converters/universal_converter.py

class UniversalConverter:
    """
    Auto-detect source format, route to correct converter.
    """
    
    CONVERTERS = {
        'sportmonks': SportMonksConverter,
        'odds_api': OddsApiConverter,
        'betsapi': BetsApiConverter,
        'betfair': BetfairConverter,
        'csv': CSVConverter,
    }
    
    def convert(self, data: dict, source: str = None) -> Event | Odds:
        if source is None:
            source = self._detect_source(data)
        
        converter = self.CONVERTERS[source]()
        return converter.convert(data)
    
    def _detect_source(self, data: dict) -> str:
        """Tunnista lähde datan rakenteesta."""
        if 'sport_event_status' in data:
            return 'sportmonks'
        if 'bookmakers' in data:
            return 'odds_api'
        # ...
```

### 11.6 Miksi Tämä Toimii

| Perinteinen | LLM Converters |
|-------------|----------------|
| 2-3 päivää / provider | 30 min / provider |
| Manuaalinen debug | Toimii heti |
| Edge caset unohtuu | LLM näkee esimerkeistä |
| Ylläpito jatkuvaa | Regeneroi kun API muuttuu |
| Yksi ihminen pullonkaula | Rinnakkainen generointi |

### 11.7 Workflow: Uusi Datalähde

```bash
# 1. Hae esimerkki-response
curl "https://new-api.com/events" > samples/new_api_sample.json

# 2. Generoi converter
llm generate \
    --prompt prompts/converter_template.md \
    --sample samples/new_api_sample.json \
    --target schemas/event.py \
    --output tools/converters/new_api_converter.py

# 3. Validoi
python tools/validate_converter.py \
    --converter new_api_converter \
    --samples samples/new_api_*.json

# 4. Done. Uusi datalähde käytössä.
```

### 11.8 Bonus: Schema Evolution

Kun internal schema muuttuu:

```bash
# Regeneroi KAIKKI converterit uudelle schemalle
for provider in sportmonks odds_api betsapi betfair; do
    llm regenerate \
        --converter tools/converters/${provider}_converter.py \
        --new-schema schemas/event_v2.py
done
```

**Ei manuaalista työtä. LLM hoitaa.**

---

## 12. Seuraavat Askeleet

1. **Tänään:** Generoi `event_generator.py` LLM:llä
2. **Huomenna:** Generoi `odds_generator.py` ja `mock_broker.py`
3. **Viikon sisällä:** Aja ensimmäinen 1000 ottelun sokkotesti
4. **2 viikon sisällä:** Täysi testbench toiminnassa

---

*Dokumentti päivitetty: 2026-01-28*
*Versio: 2.0 — LLM generates generators, not data*

