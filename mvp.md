Olet aivan oikeassa. Vuonna 2026 **AI-avusteinen koodaus (Cursor, Claude-agentit, Devin-tyyppiset autonomiset koodarit)** muuttaa pelikentän täysin. Se, mikä vuonna 2022 oli 1 000 tunnin urakka senior-tiimille, on nyt taitavan "AI-orkestroijan" käsissä viikkojen, ei kuukausien, projekti.

Jos katsomme tätä spesifikaatiota vuoden 2026 linssin läpi, tässä on syy, miksi sanot "Done" – ja missä ne todelliset haasteet nykyään piilevät:

### 1. Mikä on nyt "Helppoa" (AI hoitaa):
*   **Rust-ytimen generointi:** Voit syöttää `DATA_CONTRACTS.md` ja `SPEC.md` agentille ja sanoa: *"Rakenna tästä ultranopea Rust-moottori, joka käsittelee nämä WebSocket-feedit ja laskee nämä Poisson-arvot."* AI kirjoittaa muistiturvallisen ja tehokkaan koodin puolestasi.
*   **Dashboardit ja orkestraatio:** Streamlit- tai React-dashboardin pystyttäminen Hubin päälle on AI:lle iltapäivätyö.
*   **Boilerplate ja API-integraatiot:** Eri bookkereiden ja datatoimittajien monimutkaiset JSON-rakenteet AI mapittaa sekunneissa.

### 2. Mikä on edelleen vaikeaa (Ihmisen ja lompakon vastuulla):
Vaikka koodi syntyy napin painalluksella, nämä kolme asiaa erottavat edelleen voittajat häviäjistä vuonna 2026:

*   **Datalähteiden "Likainen työ":** AI ei voi ostaa puolestasi niitä kalleimpia ja nopeimpia datafeedejä. Se ei myöskään voi fyysisesti testata, onko jonkun tietyn toimittajan "Live xG" oikeasti luotettava vai manipuloitu.
*   **Kissa ja hiiri -leikki (Account management):** Vedonlyöntisivustojen AI-pohjaiset bottitunnistimet ovat vuonna 2026 todella pelottavia. Järjestelmän rakentaminen on helppoa, mutta sen pitäminen "tutkan alla" vaatii ihmisen oveluutta (tai todella monimutkaisia stealth-toteutuksia).
*   **Mallin kalibrointi:** AI kirjoittaa matemaattisen mallin, mutta se ei välttämättä huomaa, jos malli on "ylioppinut" (overfit) historialliseen dataan. Tarvitset edelleen ymmärrystä siitä, *miksi* joku malli toimii.

### 3. Järjestelmän "Päävastustaja" 2026
Vuonna 2026 et kilpaile enää ihmisvedonlyöjiä vastaan. Kilpailet **bookkerien omia AI-malleja vastaan**, jotka säätävät kertoimia millisekunneissa.
*   Tuo speksissä mainittu **Audio-triggeri** (maalin "kuuleminen" yleisön äänestä) on vuonna 2026 se todellinen *edge*, koska se on fyysinen datapiste, jota pelkkä tilasto-API ei heti näe.

### Miten etenet?
Jos aiot oikeasti toteuttaa tämän AI:n avulla, järjestys on tämä:
1.  **Arkkitehtuuri ensin:** Kopioi nuo speksit agentillesi.
2.  **Simulation first:** Anna AI:n rakentaa tuo `REPLAY.md`:n mukainen testausympäristö. Älä lyö euroakaan sisään ennen kuin olet ajanut 1000 peliä historiadataa läpi AI:n generoimalla koodilla.
3.  **Rust hot-path:** Käytä AI:ta kirjoittamaan nimenomaan se Rust-osa, jotta vältät Pythonin hitauden.

**Summa summarum:** Tekninen toteutus on "Done". Nyt kyse on enää siitä, onko sinulla pääsy tarpeeksi nopeaan dataan ja onko mallisi fiksumpi kuin vastapuolen miljoona dollaria maksanut algoritmi.

**Oletko jo valinnut, millä kielellä/stackilla aloitat agentin kanssa?** Jos haluat, voimme purkaa tuon "Two-step commit" -logiikan sellaiseen muotoon, että voit syöttää sen suoraan koodaus-AI:lle.
---

Selvä. Tässä on **oikeasti rakennettava, vitsi-proof MVP build plan**.
Ei HFT-puhetta, ei Rustia, ei Runpodia. Tämä on se versio, jonka **yksi ihminen voi rakentaa** ja joka todistaa nopeasti onko edgeä vai ei.

---

# 🎯 MVP BUILD PLAN — LIVE-ONLY (REALISTINEN)

## MVP:n tavoite (1 lause)

> **Rakentaa järjestelmä, joka osaa luotettavasti sanoa NO BET 95 % ajasta ja lyödä harvat vedot vain silloin, kun data + toteutus + hinta ovat oikeasti kunnossa.**

Jos tämä ei toimi → koko projekti tapetaan ajoissa.

---

# 🧱 MVP: MITÄ RAKENNETAAN (JA MITÄ EI)

## MVP:SSÄ ON

* LIVE data ingest (event + odds)
* match state + rolling ikkunat
* **NO BET / BET decision engine**
* execution receipts (vaikka et vielä lyö oikeaa vetoa)
* replay (paper trading)
* audit log + reason_code
* 1 dashboard

## MVP:SSÄ EI OLE

❌ Rust
❌ LLM
❌ Twitter / kommentaattori
❌ Audio trigger
❌ Order book / OFI
❌ Multi-agent
❌ Runpod

Kaikki nämä ovat **Phase 2+**.

---

# 🗺️ ARKKITEHTUURI (MVP)

**Yksi VPS, yksi Python-prosessi per rooli**

```
ingest/
  ├── events
  ├── odds
state/
features/
decision/
execution_stub/
replay/
logging/
dashboard/
```

Tietokanta:

* **SQLite / Postgres** (ei Redis MVP:ssä)
* append-only logit

---

# 🧩 MVP KOMPONENTIT (4 kpl)

---

## 1️⃣ INGEST + STATE (viikko 1)

### Mitä tehdään

* Event feed adapteri
* Odds feed adapteri
* Kellon/minuutin ylläpito
* Latency-mittaus

### Tallennetaan jokaisesta tickistä

* t_event
* t_recv
* latency
* raw payload
* match_id

### Output

* `match_state.json` (in-memory)
* `events_log.jsonl`
* `odds_log.jsonl`

### DONE kun

* näet live-ottelussa:

  * event latency p95
  * odds latency p95
* data tulee **luotettavasti koko ottelun ajan**

⚠️ **Jos latency > 3–5s suurimman osan ajasta → projekti kannattaa lopettaa tähän.**

---

## 2️⃣ FEATURE + TPS (viikko 1–2)

### MVP-TPS (pidä helppona)

**Laske vain nämä:**

* live_xG_10m
* box_shots_10m
* dangerous_attacks_10m
* possession_5m
* cards/red
* score + minute

### TPS label (MVP-versio)

```
LOW      = xG_10m < X AND box_shots < Y
PRESS    = xG_10m >= X AND box_shots >= Y
CHAOS    = cards/red OR high attacks both sides
```

Ei hienosäätöä vielä.

### Rolling windows

* 1 min delta
* 5 min mean
* 10 min mean

### DONE kun

* pystyt tulostamaan ottelusta:

  * TPS_label
  * xG_10m
  * trendi (nousee / laskee)

---

## 3️⃣ DECISION ENGINE (viikko 2)

### Tässä MVP:n ydin

**Yksi funktio:**

```
decide(state, features, odds) -> NO_BET | BET
```

### MVP Hard Gates (vain nämä!)

1. **Latency**

```
if event_latency_p95 > 3s → NO_BET
```

2. **TPS**

```
if TPS == LOW → NO_BET
```

3. **Quality**

```
if xG_10m < X AND box_shots_10m < Y → NO_BET
```

4. **Simple EV**

```
p_model = heuristic (esim. 1 - exp(-xG_rate * tau))
p_book = 1 / odds
if p_model * odds < 1.05 → NO_BET
```

5. **Limits**

```
if bets_in_match >= 1 → NO_BET
```

### Reason codes (pakollinen)

* LATENCY_HIGH
* TPS_LOW
* QUALITY_LOW
* EV_LOW
* MATCH_LIMIT
* BET_OK

### Output (aina!)

```
decision_log.jsonl
```

### DONE kun

* näet ottelun jälkeen:

  * 200–400 NO_BET
  * 1–3 BET_OK signaalia
* jokaisella rivillä on **reason_code**

---

## 4️⃣ EXECUTION STUB + REPLAY (viikko 3)

### Execution Stub

Et lyö vielä oikeaa vetoa.

Simuloit:

* fill
* reject
* slippage

Esim:

```
if random() < 0.2 → REJECT
else fill_odds = odds_seen - random_slip
```

### Replay

* Aja historiallinen ottelu
* Syötä eventit & odds aikajärjestyksessä
* Katso:

  * milloin järjestelmä olisi lyönyt
  * olisiko veto ollut hyvä vai huono

### Mittarit MVP:ssä

* kuinka usein BET syntyy
* kuinka usein EV katoaa slippageen
* kuinka usein latency estää vedon

### DONE kun

* replay toimii **samalla päätöskoodilla kuin live**
* voit ajaa 10–20 ottelua putkeen

---

# 📊 MVP DASHBOARD (minimi)

Yksi näkymä riittää:

**Live match panel**

* minute / score
* event latency p95
* TPS_label
* xG_10m
* last decision + reason_code

Jos tämä ei ole selkeä → olet rakentanut liikaa.

---

# ⏱️ AIKATAULU (REALISTINEN)

| Viikko | Mitä             |
| ------ | ---------------- |
| 1      | ingest + latency |
| 2      | TPS + decision   |
| 3      | replay + stub    |
| 4      | paper trading    |

**4 viikkoa = tiedät onko järkeä jatkaa.**

---

# 🚦 MVP GO / NO-GO KRITEERIT

## GO jos:

* latency p95 < 3s suurimman osan ajasta
* järjestelmä löytää **harvoja mutta järkeviä** bettejä
* replay ei romahda slippageen
* NO_BET on default

## NO-GO jos:

* latency vaihtelee villisti
* EV katoaa executionissa
* järjestelmä “haluaa lyödä koko ajan”
* et pysty selittämään jälkikäteen miksi veto syntyi

---

# 🔑 Totuus, joka tekee tästä ei-vitsin

**MVP:n tarkoitus ei ole voittaa rahaa.
MVP:n tarkoitus on todistaa, että ET häviä typerästi.**

Kun tämä MVP on valmis, kaikki “11/10” jutut ovat **optioita**, eivät haaveita.

Jos haluat seuraavaksi:

* **konkreettisen folder-rakenteen**
* **päiväkohtaisen TODO-listan**
* tai **täysin minimal SPEC.md (2 sivua)**

sano mikä, niin jatketaan.


Vuonna 2026 MVP:n (Minimum Viable Product) rakentaminen tälle järjestelmälle tarkoittaa **"Paper Trading" -moottoria**. Emme koske oikeaan rahaan vielä, vaan rakennamme päätöksentekoketjun, joka todistaa edun.

Tässä on MVP:n tekninen blueprint, jonka voit kopioida suoraan AI-koodarillesi (esim. Cursor/Claude/Devin).

---

### MVP:n Tavoite
1.  **Datan sisäänluku:** Simuloi tai lue live-feediä.
2.  **TPS-laskenta:** Määritä pelitila (LOW/PRESS/CHAOS).
3.  **Gate-logiikka:** Estä huonot vedot (Latency/Quality).
4.  **Audit-logi:** Kirjaa jokainen "NO BET" ja "SIMULATED BET" perusteluineen.

---

### 1. Hakemistorakenne (MVP)
```text
/bet-system-mvp
├── config.yaml          # Kynnysarvot (L_MAX, EV_MIN, jne.)
├── main.py              # Core loop
├── engine.py            # TPS & Decision logic
├── schemas.py           # Pydantic-sopimukset (DATA_CONTRACTS)
└── mock_provider.py     # Simuloi live-dataa testaukseen
```

### 2. Sydän: `schemas.py`
Määritellään data, jotta AI tietää tarkalleen, mitä käsitellään.

```python
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List

class Event(BaseModel):
    match_id: str
    t_event: datetime
    t_recv: datetime
    type: str  # SHOT, GOAL, DANGER_ATTACK
    team: str  # HOME, AWAY
    xg: float = 0.0

class Odds(BaseModel):
    match_id: str
    t_seen: datetime
    market: str
    selection: str
    price: float
    is_suspended: bool
```

### 3. Logiikka: `engine.py`
Tämä on se osa, joka erottaa "vitsin" ammattilaistyökalusta.

```python
import numpy as np

class BettingEngine:
    def __init__(self, config):
        self.config = config

    def calculate_tps(self, events: List[Event]):
        # MVP: Threat on xG:n ja vaarallisten hyökkäysten summa viimeiseltä 10 minuutilla
        threat = sum(e.xg for e in events if e.type == "SHOT")
        danger_count = len([e for e in events if e.type == "DANGER_ATTACK"])
        
        t_score = threat + (danger_count * 0.05)
        
        if t_score < 0.2: return "LOW"
        if t_score > 0.8: return "PRESS"
        return "MID"

    def evaluate_gates(self, state, odds):
        latency = (state['t_recv'] - state['t_event']).total_seconds()
        
        # GATE 1: Latenssi
        if latency > self.config['L_MAX']:
            return False, "LATENCY_HIGH"
            
        # GATE 2: Pelitila
        if state['tps'] == "LOW":
            return False, "QUALITY_LOW"
            
        # GATE 3: EV (Yksinkertaistettu MVP-malli)
        # Lasketaan mallin todennäköisyys p_model (tässä placeholder)
        p_model = 0.60 
        ev = (p_model * odds.price) - 1
        
        if ev < self.config['EV_MIN']:
            return False, "EV_LOW"
            
        return True, "BET_READY"
```

### 4. Päätiedosto: `main.py` (The Loop)
Tämä pyörittää järjestelmää.

```python
import time
import yaml
from engine import BettingEngine
from mock_provider import get_mock_data

def run_mvp():
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)
        
    engine = BettingEngine(config)
    
    print("MVP käynnistetty - Paper Trading Mode...")
    
    while True:
        # 1. Hae data (Live tai Mock)
        events, odds = get_mock_data()
        
        # 2. Päivitä tilannekuva
        tps = engine.calculate_tps(events)
        state = {
            'tps': tps,
            't_event': events[-1].t_event if events else datetime.now(),
            't_recv': datetime.now()
        }
        
        # 3. Päätöksenteko
        can_bet, reason = engine.evaluate_gates(state, odds)
        
        # 4. Audit-loki (TÄRKEIN OSA)
        timestamp = datetime.now().strftime("%H:%M:%S")
        if can_bet:
            print(f"[{timestamp}] 🎯 VETO: {odds.selection} @ {odds.price} | TPS: {tps} | EV: OK")
        else:
            # Tulostetaan vain jos kyseessä ei ole LOW-pelitila (melun vähentämiseksi)
            if reason != "QUALITY_LOW":
                print(f"[{timestamp}] 🚫 SKIP: {reason} | TPS: {tps}")
        
        time.sleep(1) # Core loop 1s välein

if __name__ == "__main__":
    run_mvp()
```

### 5. Config: `config.yaml`
```yaml
L_MAX: 3.0          # Max latenssi sekunteina
EV_MIN: 0.05        # 5% odotusarvo minimi
BOX_SHOTS_MIN: 2    # Minimi laukaukset boksista (10 min)
STAKE: 10           # Flat stake (simulaatiossa)
```

---

### Miten tästä eteenpäin? (AI-ohjeet sinulle)

1.  **Kopioi yllä olevat rakenteet** koodaus-AI:llesi.
2.  **Käsky:** *"Toteuta `mock_provider.py`, joka simuloi Valioliigan ottelun tapahtumavirtaa: xG-arvoja, kulmapotkuja ja kertoimien vaihtelua. Varmista, että latenssi kasvaa satunnaisesti testatakseni LATENCY_HIGH -gatea."*
3.  **Käsky:** *"Lisää `logger.py`, joka tallentaa jokaisen päätöksen CSV-tiedostoon, jotta voimme analysoida ne myöhemmin Excelissä."*
4.  **Käsky:** *"Rakenna yksinkertainen Poisson-laskin hazard-malliksi, joka käyttää ottelun alkukertoimia baseline-arvona."*

### Miksi tämä MVP on 11/10 alku?
Se ei yritä lyödä vetoa. Se yrittää **hylätä vetoja**. Jos saat tämän toimimaan niin, että se hylkää "roskan" ja poimii vain ne hetket, jolloin paine on kova (PRESS) ja kertoimet eivät ole vielä reagoineet, olet voittanut 90 % muista vedonlyöjistä. 

**Oletko valmis ajamaan ensimmäisen simulaation?**

Tämä on erinomainen suunnanmuutos. Vuonna 2026 suurin virhe on "ylirakentaa" infraa ennen kuin on todistettu, että algoritmi löytää rahaa.

Tässä on **MVP Build Plan**, joka on riisuttu kaikesta turhasta. Se keskittyy vain yhteen asiaan: **Päätöksenteon laatuun.**

---

# 🚀 MVP: "THE TRUTH MACHINE" (4 viikon suunnitelma)

Tämä MVP ei lyö oikeaa rahaa. Se on "Paper Trading" -robotti, joka pyörii yhdellä Python-skriptillä ja todistaa, pystytkö voittamaan markkinan slippagen ja latenssin jälkeen.

## 🛠️ Tekninen Valinta (MVP)
*   **Kieli:** Python 3.11+ (Kehitysnopeus > Suorituskyky tässä vaiheessa).
*   **Tietokanta:** SQLite (Yksi tiedosto, nolla säätöä).
*   **AI-työkalu:** Cursor tai Claude-3.5-Sonnet agenttimoodissa.

---

## 📅 VIIKKO 1: Data Ingest & Latency Audit
*Tavoite: Saada data sisään ja nähdä, kuinka hidas olet oikeasti.*

1.  **Ingestor:** Kirjoita adapteri valitsemallesi data-API:lle (esim. Sportradar, BetsAPI tai vastaava).
2.  **Latency Monitor:** Tallenna jokaisesta viestistä kaksi aikaleimaa:
    *   `t_event`: Milloin tapahtuma tapahtui kentällä (API-kenttä).
    *   `t_recv`: Milloin koodisi vastaanotti tiedon.
3.  **Audit Log:** Tallenna kaikki raaka-data SQLiteen.
4.  **Check:** Jos `t_recv - t_event` on jatkuvasti > 5 sekuntia, tiedät jo nyt, että live-arbitraasi on mahdotonta.

## 📅 VIIKKO 2: TPS (Threat Pressure Score) Engine
*Tavoite: Muuttaa datavirta "pelitilaksi".*

1.  **Rolling Windows:** Laske viimeisen 5 ja 10 minuutin trendit:
    *   Vaaralliset hyökkäykset / minuutti.
    *   Laukaukset (box vs. outside).
    *   Kulmapotkut.
2.  **TPS-luokittelija:** Tee yksinkertainen sääntöpohjainen logiikka:
    *   `LOW`: Peli keskialueella, ei vaaraa.
    *   `PRESS`: Hyökkäävä joukkue hallitsee, xG nousee.
    *   `CHAOS`: Kortteja, kulmapotkuja, peli auki.
3.  **Output:** Skripti tulostaa konsoliin reaaliajassa: `"MIN 62: [HOME PRESS] - xG_10m: 0.45"`.

## 📅 VIIKKO 3: Decision Engine & Gates
*Tavoite: Sanoa "EI" 99 % ajasta.*

1.  **Hard Gates:** Kirjoita funktio, joka hylkää vedon jos:
    *   `Latency > 3.0s` (Olet jo myöhässä).
    *   `Market Suspended == True` (Bookkeri sulki jo kohteen).
    *   `TPS != PRESS` (Ei tarpeeksi painetta maaliin).
2.  **Simple EV:** Vertaa mallisi todennäköisyyttä (esim. Poisson-laskin) bookkerin kertoimeen.
    *   `if (p_model * odds) > 1.05: return "BET_OK"`
3.  **Reason Codes:** Joka ikisestä "NO BET" -päätöksestä on jäätävä syy lokiin (esim. `FAIL_GATE_LATENCY`).

## 📅 VIIKKO 4: Backtest & Paper Trade
*Tavoite: Todistaa "Edge".*

1.  **Simulation Loop:** Aja viikon 1 ja 2 aikana kertynyt data moottorin läpi.
2.  **Virtual Wallet:** Aloita 1000 € virtuaalikassalla.
3.  **Slippage Penalty:** Vähennä jokaisesta kertoimesta automaattisesti 0.05 (esim. 2.10 -> 2.05) simuloidaksesi viivettä ja hinnanmuutosta.
4.  **Loppuraportti:** Katso montako "BET_OK" signaalia syntyi ja mikä oli niiden osumatarkkuus suhteessa kertoimiin.

---

# 🤖 Ohjeet AI-Agentille (Kopioi tämä)

Syötä tämä Cursorille tai vastaavalle, kun aloitat:

> "Olemme rakentamassa Live-vedonlyönnin MVP:tä. Arkkitehtuuri on Python-pohjainen ja painottaa auditointia.
> 
> Tehtävä 1: Luo `schemas.py`, jossa on Pydantic-mallit `MatchState`, `Event` ja `Odds` -luokille.
> Tehtävä 2: Luo `engine.py`, jossa on `calculate_tps(events)` -funktio. Se laskee painearvon (0.0 - 1.0) perustuen viimeisen 10 minuutin tapahtumiin.
> Tehtävä 3: Luo `decision.py`, jossa on 'Gate-logiikka'. Jos latenssi on yli 3 sekuntia tai TPS on alle 0.7, palauta `False` ja syykoodi.
> 
> Tärkeintä on, että jokainen tapahtuma ja päätös tallennetaan SQLite-tietokantaan myöhempää analyysia varten."

---

# 🚦 Milloin tiedät, että MVP on onnistunut?

**MVP on valmis, kun sinulla on Excel-taulukko, joka näyttää:**
1.  Olisimme lyöneet 50 vetoa viime viikolla.
2.  70 % hylättiin latenssin takia (mikä on rehellistä).
3.  Ne 15 vetoa, jotka menivät läpi, tuottivat +4 % palautuksen (ROI) jopa slippagen jälkeen.

**Jos ROI on miinuksella paperilla, älä koodaa Rustia. Muuta mallia.**

Haluatko, että kirjoitan sinulle suoraan tuon `decision.py`:n logiikan, jolla voit aloittaa?


