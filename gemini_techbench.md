# Gemini Techbench: Botbet Simulation & Integration Suite

Tämä dokumentti kuvaa Botbet-projektille rakennetun uuden sukupolven testaus- ja simulointi-infrastruktuurin.

## 1. Arkkitehtuuri: "Generators, not Data"

Toisin kuin perinteinen testaus, joka perustuu kovakoodattuihin JSON-tiedostoihin, tämä Techbench käyttää **generaattoreita** (Python-koodia), jotka simuloivat todellisuutta dynaamisesti.

### Keskeiset komponentit (`tools/generators/`):
- **`EventGenerator`**: Luo realistisia ottelutapahtumia (SHOT, GOAL, CARD) perustuen joukkueprofiileihin (`team_profiles.py`).
- **`OddsGenerator`**: Simuloi kertoimien liikkeitä, jotka reagoivat pelin tapahtumiin viiveellä.
- **`MockBroker`**: Simuloi vedonvälittäjän käyttäytymistä (fill-rate, slippage, latenssi).
- **`ChaosInjector`**: Injektoi "mustia joutsenia" (VAR-peruutukset, useat punaiset kortit), joilla testataan algoritmin kestävyyttä.

## 2. Analyysi- ja optimointityökalut

Järjestelmä mahdollistaa massiivisen datan prosessoinnin ja strategian hiomisen:

- **`testbench_runner.py`**: Ajaa täysiä otteluita (90 min) sekunnin murto-osissa. Kerää audit-logia jokaisesta portista (Gate Rejection Stats).
- **`sweep_params.py`**: Ajaa rinnakkain kymmeniä eri konfiguraatioita (esim. eri EV_MIN rajat) ja raportoi parhaan ROI:n tuottavat asetukset.
- **`analyze_results.py`**: Laskee voittoprosentit, keskimääräiset kertoimet ja analysoi porttien toimivuutta.

## 3. Universal Converters

Järjestelmä on valmis skaalautumaan uusiin datalähteisiin:
- **`UniversalConverter`**: Tunnistaa automaattisesti syötetyn datan lähteen (esim. SportMonks tai The Odds API).
- **Mappauskoodi**: Eristetty konverttereihin, mikä tekee uusien API-integraatioiden lisäämisestä tunnin työn päivien sijaan.

## 4. Käyttöohjeet

### Simulaation ajaminen:
```bash
export PYTHONPATH=$PYTHONPATH:.
python3 tools/testbench_runner.py
```

### Parametrien optimointi (Sweep):
```bash
python3 tools/sweep_params.py
```

### Tulosten analysointi:
```bash
python3 tools/analyze_results.py
```

## 5. Nykyinen tila

Testbench on täysin toiminnallinen ja vahvistettu 100+ ottelun simulaatioilla. Se on paljastanut strategian herkkyyden kertoimien nousulle ja auttanut asettamaan turvarajat (`ODDS_MAX`).

---
*Techbench valmisteltu: 2026-01-28*
