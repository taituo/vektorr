# 🚀 VEKTORR: IMPROVEMENT ROADMAP (POST-MVP)

Tämä dokumentti listaa kriittiset tekniset ja matemaattiset parannukset, joilla järjestelmästä tehdään tuotantokelpoinen.

## 1. DATA & INGEST (The Spine)
*   **WebSocket Migration:** Siirry HTTP Pollingista WebSokettiin kaikissa mahdollisissa feedeissä (esim. Betfair Stream API). Latenssi putoaa < 100ms.
*   **Shadow Logging:** Tallenna *kaikki* raaka-JSON-viestit S3-bucket-tyyppiseen hitaaseen tallennukseen. Jos bugin syytä etsitään viikon päästä, tarvitset raakadataa.
*   **Multi-Provider Consensus:** Jos SportMonks sanoo "Maali" mutta Betfairin kertoimet eivät liiku, luota kertoimiin (fail-closed).

## 2. BRAIN & MODELS (The Engine)
*   **Dynamic Decay:** Muuta 10 minuutin liukuva ikkuna painotetuksi. 1 minuutti sitten tapahtunut laukaus on 5x tärkeämpi kuin 9 minuuttia sitten tapahtunut.
*   **Pressure Velocity (TPS_V):** Älä katso vain TPS-arvoa, vaan sen muutosnopeutta. Nopea nousu 0.2 -> 0.8 on vaarallisempi kuin tasainen 0.8.
*   **Market Disconfirm 2.0:** Jos malli haluaa lyödä vetoa kertoimella 2.0, mutta markkina "dumpataan" nopeasti 1.8:aan, joku tietää jotain mitä sinä et -> PERUUTA VETO.

## 3. EXECUTION (The Kill Switch)
*   **Smart Staking:** Siirry Flat Stakesta (10€) Kelly-kriteeriin tai sen murto-osaan (Fractional Kelly).
*   **Anti-Detection (Stealth):**
    *   Satunnaista viivettä executioniin (muutama sata millisekuntia).
    *   Vältä pyöreitä summia (lyö 10.14€ mieluummin kuin 10.00€).
*   **Automatic Kill-Switch:** Jos kassa putoaa -15% päivän aikana, sammuta kaikki scriptit automaattisesti.

## 4. INFRASTRUCTURE
*   **Docker Compose:** Paketoi koko stack (QuestDB, Spine, Brain, Dashboard).
*   **Health Checks:** Discord/Telegram-botti, joka pingaa 15 min välein: "Vektorr is alive. Wallet: 1045€".
*   **Replay Engine:** Mahdollisuus ajaa mikä tahansa eilinen peli uudelleen `main.py`:n läpi sekunnilleen samalla tavalla.

## 5. REVENUE OPS
*   **Slippage Audit:** Vertaa koodin näkemää kerrointa ja toteutunutta kerrointa. Jos ero on jatkuvasti > 0.05, järjestelmä vuotaa rahaa toteutukseen.
*   **Leagues Expansion:** Kun EPL ja La Liga toimivat, automatisoi "League Onboarding" -prosessi.
