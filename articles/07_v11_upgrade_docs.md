Alla päivitetyt, **Institutional Grade** -dokumentit.

# ARCHITECTURE.md (v11.0 - RUST HYBRID)

```mermaid
graph TD
    subgraph "SENSORS (The Eyes & Ears)"
        F1[Fast Feed A] --> |UDP| R[RUST CORE]
        F2[Fast Feed B] --> |UDP| R
        AUDIO[Audio Stream Processor] --> |Crowd Noise Trigger| R
        OB[Exchange Order Book] --> |L2 Data| R
    end

    subgraph "RUST CORE (The Brain - <1ms)"
        R --> |1. Normalize| ARB[Feed Arbiter]
        ARB --> |Synthetic Truth| STATE[State Engine]
        STATE --> |Vector| HAZARD[Hazard Model (Compiled)]
        OB --> |OFI Signal| HAZARD
        
        HAZARD --> |Probabilities| GATES[Hard Gates]
        GATES --> |Signal| EXEC[Smart Router]
        
        EXEC --> |Fix/API| BROKER[Asian Broker / Exchange]
        BROKER --> |Fill| EXEC
    end

    subgraph "PYTHON CONTROL PLANE (The Ops)"
        STATE -.-> |Shared Memory / gRPC| PY[Python Orchestrator]
        PY --> DB[TimescaleDB]
        PY --> DASH[Grafana / Streamlit]
        
        LLM[Local LLM Spoke] --> |Soft Signals| PY
        PY -.-> |Update Weights| HAZARD
    end
```

### Key Changes:
1.  **Ingest & Decision on Rustissa:** Pythonin GC (Garbage Collection) ei voi enää pysäyttää prosessia kriittisellä hetkellä.
2.  **Audio Trigger:** Järjestelmä "kuulee" maalin ennen kuin bookkeri näkee sen datassa.
3.  **Shared Memory:** Python lukee Rustin tilaa suoraan muistista ilman hidasta serialisointia.

---

# SPEC.md (v11.0 - LISÄYKSET)

Lisätään "Secret Sauce" -osiot.

## 2.3 Audio & Visual Acceleration (AVA)
- **Input:** Low-latency audio stream (radio/webradio/low-res video).
- **Detection:**
  - `RMS_Amplitude` > Threshold (Crowd Roar).
  - `Whistle_Signature` match (Tuomarin vihellys).
- **Latency Advantage:** Tyypillisesti 500ms – 3000ms etu datafeediin nähden.
- **Action:** Jos AVA triggeröityy -> **HARD FREEZE** välittömästi (estää huonot vedot) TAI **SNIPE** (jos strategia sallii "front-running").

## 5.5 Market Microstructure Model (OFI)
- **Input:** Level 2 Order Book (Exchange).
- **Laskenta:** `OFI(t) = Volume_Best_Bid * (P_Bid_t - P_Bid_t-1) ...`
- **Sääntö:** Jos `OFI_10s` on voimakkaasti negatiivinen (markkina myy), älä osta "Over" -vetoa vaikka xG-malli huutaa ostoa. Markkina näkee jotain mitä sinä et (esim. pelaaja makaa maassa).

## 7. Execution Algorithms (Smart Routing)
Ei enää simppeliä "bet placementia".
- **Algo A: "Sniper"** (Käytetään kun Edge on valtava/lyhytaikainen): Market Order / Aggressive Limit.
- **Algo B: "Pegged Maker"** (Käytetään normaalitilassa): Aseta limit order = Best Bid + 1 tick. Odota filliä. Jos hinta karkaa > 2 tickiä -> Cancel or Chase.
- **Routing:** Tarkista likviditeetti: Betfair vs. Broker. Valitse reitti, jossa `slippage + commission` on pienin.

---

# REPLAY.md (v11.0 - MICROSECOND REALISM)

Jotta 11/10 taso saavutetaan, simulaation pitää olla brutaali.

## 2.1 The "Packet Loss" Simulation
Normaalissa replay'ssa data on täydellistä. 11/10 replayssa:
- Pudota satunnaisesti 1-5% UDP-paketeista.
- Sekoita pakettien järjestys (out-of-order delivery).
- Testaa, pystyykö **Feed Arbiter** rakentamaan totuuden tästä kaaoksesta.

## 2.2 The "Front-Running" Bot Simulation
Markkinalla on muita botteja.
- Simuloi tilanne, jossa joku toinen syö likviditeetin 5ms ennen sinua.
- Laske "Fill Probability" funktiona latenssista:
  `P(Fill) = exp(-k * latency_diff_to_competitor)`
- Tämä pakottaa optimoimaan Rust-koodin nopeutta.

---

# RUNBOOK.md (v11.0 - OPS WAR ROOM)

## 2. Live Operations: " The Cockpit"

Dashboradissa ei ole enää vain numeroita, siinä on **Signaalit**.

**Panel: "Latency Delta"**
- Näyttää reaaliajassa erotuksen: `My_Audio_Trigger_Time` vs `Bookie_Suspend_Time`.
- Jos tämä luku on positiivinen (esim. +1500ms), teet rahaa. Jos se on negatiivinen, olet hidas.

**Panel: "Market Pressure"**
- Visualisoi OFI:n (Order Flow Imbalance). Näet "paineen" kertoimien alla.

**Protocol: "Server Isolation"**
- Aja kriittinen Rust Core **dedicated CPU coreilla** (`taskset -c 1-3 ...`).
- Estä käyttöjärjestelmän keskeytykset näiltä ytimiltä.
- Verkko: Käytä kernel-bypass ajureita (esim. DPDK) jos mahdollista, tai vähintään optimoitua verkkopinoa.

---

# YHTEENVETO: MIKSI TÄMÄ ON 11/10?

Tämä speksi ei enää luota onneen tai pelkkään tilastomatematiikkaan. Se hyökkää markkinan fysikaalisia rajoitteita vastaan.

1.  **Nopeus:** Rust + Audio Trigger = Olet nopeampi kuin bookkerin feed-provider.
2.  **Informaatio:** OFI + Order Book = Näet mihin "smart money" liikkuu ennen kuin hinta muuttuu.
3.  **Toteutus:** Smart Routing + Broker API = Et jää jumiin limiitteihin ja minimoit kulut.

**Tämä on hedge fund -tason järjestelmä.** Vaatimuslistalle lisätään:
*   **Kieli:** Rust (pakollinen).
*   **Rauta:** Dedikoitu palvelin lähellä Lontoon/Aasian data-keskuksia (cross-connects jos mahdollista).
*   **Budjetti:** Data maksaa. Brokerit vaativat pääomaa.

Jos rakennat tämän, et pelaa enää samaa peliä muiden kanssa. Sinä olet talo.

Alla neljä dokumenttia samalla “normatiivisella” tarkkuudella kuin SPEC/METRICS/DASHBOARD: **ARCHITECTURE.md, DATA_CONTRACTS.md, REPLAY.md, RUNBOOK.md** (ei koodia; schemat esitetty kenttälistoina + taulukoina). Lopussa selkeä vastaus **LLM vs ML?**.

---
