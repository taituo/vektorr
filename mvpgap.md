# MVP Gap Analysis: mvp.md vs. toteutunut koodi

## Yhteenveto

mvp.md lupasi 4 viikon suunnitelman. Toteutus kattaa noin 60 % luvatuista ominaisuuksista. Alla jokainen puute ja sen vakavuus.

---

## Toteuttamatta jääneet ominaisuudet

### 1. Tietokanta (SQLite/Postgres)
- **mvp.md:** "SQLite / Postgres, append-only logit"
- **Toteutus:** JSONL-tiedostot (`events_log.jsonl`, `odds_log.jsonl`, `decisions.jsonl`)
- **Vakavuus:** KORKEA — ei ACID-yhteensopivuutta, ei kyselymahdollisuutta, ei atomista backupia

### 2. Rolling windows (1min, 5min, 10min)
- **mvp.md:** "1 min delta, 5 min mean, 10 min mean"
- **Toteutus:** Vain 10min xG-lookback (O(N) per tick)
- **Vakavuus:** KESKITASO — trendi- ja deltaominaisuudet puuttuvat kokonaan

### 3. Lisäfeaturet (possession_5m, box_shots_10m)
- **mvp.md:** "live_xG_10m, box_shots_10m, dangerous_attacks_10m, possession_5m, cards/red, score + minute"
- **Toteutus:** Vain xG ja danger_attack -määrä TPS:ssä. box_shots ja possession puuttuvat.
- **Vakavuus:** KESKITASO — TPS-heuristiikka on köyhempi kuin suunniteltu

### 4. Dashboard
- **mvp.md:** "Live match panel: minute/score, event latency p95, TPS_label, xG_10m, last decision + reason_code"
- **Toteutus:** Ei dashboardia. Vain konsolituloste.
- **Vakavuus:** MATALA — ei vaikuta logiikkaan, mutta vaikeuttaa seurantaa

### 5. Modulaarinen hakemistorakenne
- **mvp.md:** "ingest/, state/, features/, decision/, execution_stub/, replay/, logging/, dashboard/"
- **Toteutus:** Flat-rakenne, kaikki .py-tiedostot juurihakemistossa
- **Vakavuus:** MATALA — toimii MVP:ssä, mutta skaalautuu huonosti

### 6. Erillinen decision.py
- **mvp.md:** "Luo `decision.py`, jossa on Gate-logiikka"
- **Toteutus:** Päätöslogiikka on `engine.py`:ssä (`evaluate_gates`)
- **Vakavuus:** MATALA — toiminnallisesti sama, vain nimeämisero

### 7. Trendi (nousee/laskee)
- **mvp.md:** "trendi (nousee / laskee)" TPS-outputissa
- **Toteutus:** Ei rolling-deltoja, ei trendilaskentaa
- **Vakavuus:** KESKITASO — ei näe paineen suuntaa, vain nykyarvon

### 8. Market Suspension -gate puuttuu itsenäisenä
- **mvp.md:** "Market Suspended == True → NO BET" erillisenä hard gatena
- **Toteutus:** Tarkistetaan `engine.evaluate_gates`:ssa, mutta `MockProvider` ei generoi suspensiotilanteita realistisesti
- **Vakavuus:** MATALA — gate on koodissa, mutta testaamaton

### 9. Slippage penalty backtestissä
- **mvp.md:** "Vähennä jokaisesta kertoimesta automaattisesti 0.05"
- **Toteutus:** `ExecutionStub` käyttää `random.uniform` -pohjaista slippagea, ei kiinteää 0.05-penaltia
- **Vakavuus:** MATALA — toteutus on itse asiassa realistisempi kuin suunnitelma

### 10. Oikea Data-adapteri
- **mvp.md:** "Ingest adapteri valitsemallesi data-API:lle"
- **Toteutus:** Vain `MockProvider`, joka generoi satunnaista dataa. Oikeaa API-yhteyttä ei ole.
- **Vakavuus:** KRIITTINEN — Järjestelmä on täysin hyödytön ilman oikeaa dataa.

### 11. Arkkitehtuuri (Blocking vs. Non-blocking)
- **mvp.md:** "Yksi Python-prosessi per rooli" (Ingest, Decision, jne.)
- **Toteutus:** Yksi monoliittinen `main.py` looppi, joka blokkaa `time.sleep(0.5)` -kutsulla.
- **Vakavuus:** KORKEA — Ei skaalaudu useaan otteluun, estää roolien eriytymisen.

### 12. Replay-determinismi
- **mvp.md:** "Replay toimii samalla päätöskoodilla kuin live" (implisiittisesti deterministinen)
- **Toteutus:** `ExecutionStub` käyttää `random.random()` -funktiota, mikä tekee replaysta ei-deterministisen.
- **Vakavuus:** KESKITASO — Vaikeuttaa regressiotestausta ja optimointia.

---

## Toteutetut ominaisuudet ✓

| Ominaisuus | Tila |
|---|---|
| Event + odds ingest | ⚠️ (Vain Mock, ei Real) |
| Latency-mittaus (p95) | ✓ |
| TPS-laskenta (LOW/MID/PRESS/CHAOS) | ✓ |
| Gate-logiikka (latency, quality, EV, limits) | ✓ |
| Poisson EV-malli | ✓ |
| Execution stub (fill/reject/slippage) | ✓ |
| Paper wallet + settlement | ✓ |
| Audit log (decisions.jsonl) | ✓ |
| Replay (replay.py) | ✓ |
| Reason codes | ✓ |
| config.yaml kynnysarvot | ✓ |
| Pydantic-skeemit | ✓ |

---

## Prioriteettijärjestys korjauksille

1. **SQLite-migraatio** — JSONL → SQLite. Mahdollistaa kyselyt ja atomisen talletuksen.
2. **Rolling windows** — 1min/5min/10min ikkunat inkrementaalisella laskennalla (O(1) per tick).
3. **Lisäfeaturet TPS:ään** — box_shots, possession mukaan.
4. **Trendi** — delta edelliseen ikkunaan.
5. **Dashboard** — Streamlit-minimi.
6. **Hakemistorakenne** — refaktoroi moduuleihin.

---

# Addendum (2026-01-27): Täsmennykset / muutokset

## Muutokset havaintoihin
1. **Market Suspension -gate**: Gate on toteutettu ja `MockProvider` asettaa `is_suspended` satunnaisesti (~5%). Kyse ei ole puuttuvasta gatesta vaan *realismista ja testikattavuudesta*. Vakavuus pysyy matalana, mutta luokitus “puuttuu” on liian vahva.
2. **Score ei päivity**: `score` on kovakoodattu `"0-0"` eikä muutu, vaikka mvp.md lupaa “score + minute”. Tämä on puute, joka vaikuttaa analyysiin ja mahdollisiin malleihin.
3. **Replay ei ole luotettava**: Replay on olemassa, mutta tapahtumaikkunointi ja oddsien aikakohdistus ovat epävakaita (järjestys/ajastus). Siksi “Replay ✓” on vain osittain tosi.
4. **Execution receipts vs. outcome**: Päätösloki kyllä tallentaa executionin, mutta *settlement on satunnainen* eikä seuraa eventtejä. Tämä tekee audit-arvosta heikomman kuin MVP-spesin henki.
