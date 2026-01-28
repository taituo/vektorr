# BROKER INFO & "THE MACHINE" (MollyBet/Black)

Tämä dokumentti avaa ammattimaisen vedonlyönnin "mustan laatikon": **Brokerit ja Aggregaattorit.**

## 1. Mikä on "The Machine" (Aggregaattori)?

Ammattilaiset eivät kirjaudu viidelle eri sivustolle etsimään kertoimia. He käyttävät **Aggregaattoria** (usein MollyBet-pohjainen alusta).

### Miten se toimii?
1.  **Yksi tili:** Talletat rahaa yhdelle brokerille (esim. BetInAsia, Sportmarket).
2.  **Yksi käyttöliittymä:** Näet kaikki kertoimet yhdessä näkymässä.
3.  **Älykäs reititys:** Kun lyöt vedon, moottori pilkkoo sen ja lähettää sinne, missä on paras kerroin ja likviditeetti.
    *   *Esimerkki:* Lyöt 1000€ HJK:lle. Moottori laittaa 600€ Pinnaclelle (kerroin 1.95) ja 400€ Betfairille (kerroin 1.94), koska yksi paikka ei ottanut koko summaa.

### Ketä siellä on taustalla?
*   **PS3838 (Pinnacle):** Volyymikuningas. Ei rajoita voittajia.
*   **Betfair / Orbit / Matchbook:** Pörssit (lyöt muita vastaan).
*   **SBO / IBC / ISN:** Perinteiset Aasian bookkerit (isot tasoitusvedot).

---

## 2. Broker-vaihtoehdot (Niche-liigoihin)

Pohjoismaisissa sarjoissa (Veikkausliiga jne.) **likviditeetti on kuningas**. Broker auttaa löytämään ne "piilossa olevat" eurot.

| Broker | Alusta (UI) | API Saatavuus | Minimi (Tili) | Niche-sopivuus |
| :--- | :--- | :--- | :--- | :--- |
| **BetInAsia** | BLACK (Molly) | **Kyllä** (pyynnöstä) | 100€ | ⭐⭐⭐⭐ (Hyvä yleisratkaisu) |
| **Sportmarket** | PRO (Molly) | **Kyllä** (Kallis/Vaikea) | 250€ | ⭐⭐⭐⭐⭐ (Paras valikoima) |
| **AsianConnect** | AsianOdds | Kyllä | 10€ | ⭐⭐⭐ (Perusvarma) |
| **Vodafone** | Molly | Vain isot pelaajat | 5000€+ | ⭐⭐⭐⭐⭐ (HFT-taso) |

**Huom:** Useimmat käyttävät samaa MollyBet-teknologiaa, vain "kuoret" ja ehdot (komissiot) vaihtelevat.

---

## 3. API-integraatio: Realiteetit

Koodarin näkökulmasta API on unelma, mutta taloudellisesti se on usein muurin takana.

### Haasteet
1.  **Turnover-vaatimukset:** Moni broker vaatii esim. 50 000 € / kk liikevaihtoa, jotta API pysyy auki ilman maksua.
2.  **Maksullisuus:** Jos volyymi ei täyty, API voi maksaa satoja euroja kuussa.
3.  **Dokumentaatio:** MollyBet API on tehokas mutta monimutkainen (Session hallinta, Order placement flow).

### Strategia Niche-liigoihin
Koska Veikkausliigan volyymit ovat pieniä, **API-kustannus syö helposti tuoton**.

**Suositus:**
1.  Aloita **Manuaalisesti (Monitor + Broker UI)**.
2.  Pidä Monitori auki yhdellä näytöllä, Brokerin "Black"-näkymä toisella.
3.  Kun Monitori huutaa **FIRE**, iske veto sisään Brokerin käyttöliittymästä. Se on sekunneissa kiinni Pinnaclella.

---

## 4. Tekniset termit (Jos koodaat adapterin)

Jos päätät rakentaa adapterin, tässä on sanasto:

*   **Limit Order:** "Haluan vähintään kertoimen 1.90". Jos kerroin putoaa 1.89:ään, veto ei mene läpi (tai jää roikkumaan).
*   **Unmatched:** Veto on markkinoilla, mutta kukaan ei ole ottanut sitä kiinni (yleistä pörsseissä).
*   **Fill Rate:** Kuinka suuri osa vedosta meni läpi (esim. pyysit 100€, sait 42€).
*   **Closing Line Value (CLV):** Brokerin kautta näet "todellisen markkinahinnan", johon voit verrata omaa malliasi.

---

## 5. Yhteenveto

*   **Brokerit ovat ammattilaisen työkalu.** Ne poistavat limit-ongelmat ja antavat parhaan kertoimen.
*   **MollyBet ("Black")** on se moottori, jota useimmat käyttävät.
*   **Aloita manuaalisesti.** API on kallis ja vaatii volyymia. Rusinat pullasta -taktiikalla ihmiskäsi on tarpeeksi nopea Veikkausliigaan.
