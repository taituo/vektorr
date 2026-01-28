# TODO

## Stubit / aukot
- Match-ID sovitus on hauras (team-nimi + kickoff); vaatii provider-pohjainen match-map.
- SportMonks events: xG=0, score/period puuttuu, event-tyypitys heuristiikka.
- Odds API: `is_suspended` oletus false, line/point puuttuu, in-play-flagin tuki puuttuu.
- Provider polling hakee koko listan joka kierros; luottaa deduppiin.
- Brain: minute/score arvio karkeasti, ei virallista match clockia.
- QuestDB: kirjoittaa rivi-riviltä (ei batchingiä).

## Antipatternit
- Päätöslogiikan ja data-mäppäyksen vastuu jakautuu epäselvästi.
- Provider-kohtainen mapping / ID-silta puuttuu.

## Ehdotetut korjaukset (järjestys)
1) Match-map-taulu QuestDB: `provider_id + provider -> match_id`.
2) Laajenna data contract:
   - Odds: line/point + is_suspended nullable.
   - Events: score + period (jos provider tarjoaa).
3) Provider-filtterit:
   - SportMonks: liigat (EPL, LaLiga, Serie A, Bundesliga, Ligue 1 + Nordics).
   - Odds API: vastaavat sport keys listauksesta.
4) In-play-only rajaus, jos API tukee.
5) Batch-write QuestDB:lle (write_lines / buffering).

## Tarvitsen sinulta
- SportMonks league-IDt (EPL, LaLiga, Serie A, Bundesliga, Ligue 1 + Suomi/Ruotsi/Tanska/Norja).
- The Odds API sport keys (listattavissa `cargo run -- --odds-api-list-sports --odds-api-key YOUR_KEY`).
