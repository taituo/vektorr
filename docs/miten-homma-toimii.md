# Miten tämä homma oikeasti toimii

Tämä ei ole käyttöohje älykotelolle vaan ihmisluettava kertomus siitä, mitä järjestelmä tekee kun maailmassa pelataan futista ja kurssit elävät. Tekninen nimi repossa on nykyään **Doomsignal** — bränditasolla “varoitus että jotain kohtaa ennen kuin painat nappia”.

---

## Mikä tämä on yhdellä lauseella?

**Live‑urheilumarkkinoiden päätöskone**, joka yrittää löytää hetken jossa data, latenssi ja markkinahinta näyttävät samaan suuntaan — ja jos mikään ei täsmää, tulos on aina sama: **ei vetoa**.

Se ei ole “tee miljoona vetoa sekunnissa” ‑väline. Pikemminkin päinvastoin: jälki on täynnä ei‑vetoja ja syitä (reason codet), koska järjestelmä on suunniteltu **epäonnistumaan suljetusti**. Parempi jättää raha liikkumatta kuin liikuttaa sitä sumussa.

---

## Kolme käytännön palikkaa — ja yksi säiliö

Kuvittele tehdasviiva, jossa kukaan ei koputa toisen olkapäätä käytävällä töissä koska rajapinta on HTTP ja taulukot.

### 1. Spine (Rust) — “kun data tulee ovista sisään”

**Spine** ei päätä mitään filosofisesti. Sen tehtävä on kestää websocketit, polling, provider‑adapterit (esim. SportMonks + Odds API), normalisoida tapahtumat ja kurssit yhteiseen muotoon sekä puskea ne eteenpäin logeihin ja tietokantaan.

Käytännössä: HTTP‑palvelin, jolle voit lähettää `event`- ja `odds` ‑payloadeja; tai vaihtoehtoisesti valmiit adapterit hakevat dataa kun annat avaimet ja liigalistat. Spine voi lähettää normalisoidun sisällön suoraan **Brainille** (`--brain-url`), jotta päätösputki pyörii samassa tahdissa kuin data.

Alle menee **QuestDB** ingestillä (`events`- ja `odds`‑tasot aikasarjana). Tämä ei ole sisustusvalinta: kun haluat jälkikäteen kysellä “miksi kello kahdeksantoista tapahtui mitä tapahtui”, historia on siellä.

Lyhyt anekdootti: Spine on se kaveri jonka luokse tuodaan sählätty sählättyjä JSON‑pulloja ja joka huutaa vain “tässä on nyt järjestelmällinen tikki ja latenssi, ota tästä”.

### 2. Brain (Python) — “kun logiikka sanoo kyllä tai ei”

**Brain** on päätökset irrotettuina omaan pakettiinsa: `engine.py` laskee metriikat (mm. TPS, painotettu xG), pyörittää gateja ja voi käyttää “Phase 2” ‑malleja (dynamic lambda, execution risk, markkinahinnoittelu‑skoori).

Tärkeää henkilökemiaa: Brain on **tilaton** filosofiassa — sama syötteet + sama konfig ⇒ sama päätös. Se sopii sekä paperiin että myöhemmin live‑replay‑ajoon: jos kahdesti sama historia, kahdesti sama tulos tai olet löytänyt nondeterminismin bugista.

Brain pyörii palveluna (esim. `uvicorn` portissa 8090). Spine tai testit voivat mätkiä tikkejä sisään; vastauksessa on se mitä järjestelmä uskoo pelistä ja markkinasta — tai syyt miksi hiljainen linja säilyy.

Konfig‑tiedostossa (juuren `config.yaml` tyyppiin) elävät kynnykset: latenssi, EV‑minimi, vigin käsittely, MMS, paperilompakon koko, Kelly vs flat stake. Ne eivät ole koristeita; ne ovat käytännössä tuotannon “temperamentti”.

### 3. Execution (Python) — kun teoreettinen veto kohtaa todellisuuden

**Execution** on erillinen vaihe joka lukitsee päätöksiä käytännön riski‑ ja toteutuskäsittelyn kautta. Oletuksena **dry‑run**: mitään oikeaa vaihtokauppaa ei tehdä ennen kuin joku tietoisesti kytkee oikeaan bookkeri‑API:in (mallissa Betfair‑mapping QuestDB‑taulujen kanssa).

Jos kartta puuttuu, veto ohitetaan — ei arvaa markkinoita sokeasti. Lokit voivat kulkea taas QuestDB:hen kun konfig käskee niin.

Tämän voi nähdä anekdoottisesti: Spine ja Brain pohdiskelevat; Execution on köyhän miehen järjestelmällinen “no niin, toistetaanko tämä oikeasti vai ei” — ja usein vastaus on ei tai simulaatio.

### QuestDB — “musta laatikko joka ei ole musta**

Ilman säiliötä kyse olisi päiväkirjasta joka häviää. Kun tikit ja päätökset ja myöhemmin toteutukset kirjataan, systeemistä voidaan tehdä **auditoida** vaihtoehtoisesti tai vähintään opettava historia.

---

## Yksi tikki käytävällä — mitä järjestelmä näkee silmillään

1. Jostain tulee tapahtuma (maali, veto, laukaus…) tai kurssimuutos aikaleimoilla (`t_event`, `t_recv`).
2. Spine normalisoi, laskee tai välittää latenssi‑ajatuksen ja sysää dataa sekä lokille että ajoittain Brainille.
3. Brain päivittää matsin tilaa mielessään (tikkejä käytettävässä palvelussa rajoitetusti TTL + max matsit ‑periaatteella — ei ikuisuuksia säilöstä).
4. Gate logiikka kysyy käytännöllisesti: onko tämä veto kelvollinen tähän dataan ja tähän hetkeen vai pitääkö sanoa että “me emme koske” (NO BET tai vastaavat reason codet käytössä)?
5. Jos jonnekin asti löytyisi “bettilupa”, Execution tai paperimoduuli hoitaa kokoomisen — ja jälki kirjataan.

Tärkeää: järjestelmä **ei yritä olla ihmisen korvike joka näkee televisiosta samoin**. Event feed on “pelimaailman totuuden” läheltä oleva jäljennös; TV‑kommentaattori on eri universumissa ellei eksplisiittisesti kytketä.

---

## Filosofinen ystävä — LLM:t ja soft signaalit suunnitelmissa

Pidemmän dokumentaation tekstit (katso `docs/articles/`) jakavat maailman **Hub‑Spoke‑Frontier**: kova ydin päätökset tekee, tekstipohjaiset/signaaliset jutut eivät saa koskaan kävellä rahavirralla etulinjaan käytettävään tarinaan päinvastoin kuin jotkut Twitter‑fantasiat.

Tämä dokumentti ei avaa Hub‑Spoke‑kaavia uudestaan; riittää että kotona muistaa: **raha kulkee vain siitä portista jossa on kovat säännöt**.

---

## Paperi vs oikeasti

- **Paper / demo**: sama putki mutta veto virtuaalisesti tai kokonaan simuloituna Executionin kynnyksellä — opit ilman että oma pankkisaldo opettaa takaisinpäin.
- **Live**: vaatii avaimia, Compose‑ympäristön, kartoituksen bookkerin marketteihin — ja järkevän ihmisen lukemassa viikkolokit.

Repossa backlog (esim. `docs/planning/BACKLOG.md`) kertoo avoimen työn teemoittain: data‑sopimukset, integraatiotunnelma, toteutusrajat — eli realismia siitä että “koodi on green” ei tarkoita vielä “maailma on green”.

---

## Mistä löytyy enemmän “virallista” pohjaa**

- `README.md` — järjestelmätason kiteytys englanniksi.
- `roadmap.md` — vaiheet ja filosofia vaihe‑poistumisista suomeksi tai sekoitetusti katso dokumentti.
- `docs/articles/` — pitkiä speksi-/arkkitehtuuritekstejä jotka sopivat ihmiselle jolla on kahvi ja aikaa.
- Spine/Brain/Execution hakemistojen `README.md` — käynnistysohjeisiin ja taulukkonimiin käytännössä.

---

## Loppukesäinen virke

**Doomsignal** ei ole projekti joka yrittää tunkea päätään ovesta väkisin. Se on järjestelmä joka rakentuu epäilyn ympärille ja toivoo että joskus data ja markkinamaailma osoittavat samaan suuntaan — ja jos ei osoita, ovi pysyy kiinni. Loput on säätöjä, kirjauksia ja kärsivällisyyttä.