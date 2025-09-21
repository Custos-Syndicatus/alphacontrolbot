# XController Telegram Admin Bot (Enhanced)

Älykäs Telegram-hallintabotti, joka pysyy täysin passiivisena kunnes aktivoidaan adminin DM:llä. Tukee kiellettyjen sanojen moderointia, progressiivista kurinpitoa (mute -> ban), sekä vain adminien yksityisviesteihin reagoivaa ohjausmallia.

## Sisällys
- [Ominaisuudet](#ominaisuudet)
- [Pika-aloitus](#pika-aloitus)
- [Ympäristömuuttujat](#ympäristömuuttujat)
- [Aktivointi](#aktivointi)
- [Admin-only DM -toiminta](#admin-only-dm)
- [/orwell Multi-Add -komento](#orwell-multi-add)
- [SALT ja anonymisointi](#salt-ja-anonymisointi)
- [Moderointilogiikka](#moderointilogiikka)
- [Hakemistorakenne ja data](#hakemistorakenne-ja-data)
- [Kehitysympäristö (virtualenv)](#kehitysympäristö-virtualenv)
- [Lokitus](#lokitus)
- [Turvallisuusnäkökulmia](#turvallisuusnäkökulmia)
- [Roadmap / Mahdolliset jatkokehitykset](#roadmap--mahdolliset-jatkokehitykset)
- [Lisenssi](#lisenssi)

## Ominaisuudet
1. Aktivointivaihde: botti ei tee mitään ennen kuin admin DM: *activate*.
2. Admin-only ohjaus: vain ADMIN_USER_IDS -listatut käyttäjät saavat vastauksen / voivat ohjata botin toimintaa.
3. /orwell komento tukee useiden sanojen lisäämistä kerralla pilkuilla eroteltuna.
4. Dynaaminen kiellettyjen sanojen lista tallennettuna SQLiteen.
5. Banned word -valvonta: ensimmäinen rikkomus -> viesti poistetaan + 12h mute + lyhyt varoitus (auto-delete); toinen rikkomus 7 päivän sisällä -> pysyvä ban.
6. Käyttäjä-ID:t anonymisoidaan HMAC-SHA256 + SALT -kombolla (ei raakatekstisiä ID:itä tietokannassa).
7. SALT generoidaan tarvittaessa automaattisesti (volatiili varoituksella).
8. Uudet jäsenet ilman käyttäjänimeä potkitaan (vain aktivoituna).
9. Kevyt token bucket -rate limiter (valmius jatkolaajennuksiin).
10. Lokitus tiedostoon + konsoliin.

## Pika-aloitus

```bash
git clone https://github.com/<owner>/<repo>.git
cd <repo>

# (Suositus) Virtualenv
python -m venv .venv
source .venv/bin/activate  # Windows: .\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
cp .env.example .env   # Luo ympäristömuuttujatiedosto (jos esimerkki olemassa)
# Muokkaa .env sopivaksi (API_ID, API_HASH, BOT_TOKEN, ADMIN_USER_IDS, jne.)

python bot.py
```

## Ympäristömuuttujat

| Nimi | Pakollinen | Kuvaus |
|------|------------|--------|
| `API_ID` | Kyllä | Telegram API ID (my.telegram.org) |
| `API_HASH` | Kyllä | Telegram API hash |
| `BOT_TOKEN` | Kyllä | BotFather token |
| `ADMIN_USER_IDS` | Kyllä (käytännössä) | Pilkuilla eroteltu lista Telegram numeric user ID:itä. Vain nämä ohjaavat bottia. |
| `BANNED_WORDS` | Ei | Alustava pilkkueroteltu lista kiellettyjä sanoja (lisätään tietokantaan jos ei jo ole). |
| `SALT` | Ei | Jos puuttuu -> generoidaan volatiili satunnaisheksiarvo (32 bytes -> 64 hex). |
| `LOG_LEVEL` | Ei | (Mahdollinen lisäys, ei vielä käytössä suoraan) |
| Muut | - | Ei käytössä tällä versiolla |

Huom: Jos `ADMIN_USER_IDS` on tyhjä, bottia ei voi aktivoida eikä ohjata (varoitus logissa).

## Aktivointi

Bot ei tee mitään ennen kuin admin (ID listassa `ADMIN_USER_IDS`) lähettää yksityisviestin:  
```
activate
```
- Kirjainkoko väliä (case-insensitive)
- Ympärillä oleva whitespace siivotaan
- Tila tallennetaan SQLite `activation_state` -tauluun ja säilyy restartin yli
- Uusi aktivointiyritys aktiivisena -> vastaus: `Already active.`

## Admin-only DM

Vain admin-ID:t saavat minkään vastauksen. Muut käyttäjät ohitetaan hiljaisesti.  
Komennot:
- `activate` (jos ei vielä aktiivinen)
- `/orwell sana` tai `/orwell sana1,sana2,sana3`
Muu viesti adminilta palauttaa help-tekstin.

## /orwell Multi-Add

Pilkuilla eroteltu lista lisää useita kiellettyjä sanoja. Tyhjät tokenit siivotaan.

Esimerkki:
```
/orwell foo, bar ,baz
```
Mahdollinen vastaus:
```
Added: foo, bar | Skipped: baz
```
(Skipped-osio näytetään vain jos joku oli jo olemassa.)

Tyhjä / kelvoton syöte:
```
/orwell , ,
→ No valid words provided.
```

Ei tällä hetkellä (tarkoituksella) `list`, `remove` tai `count` alakomentoja.

## SALT ja anonymisointi

- Käytetään HMAC-SHA256: `hmac.new(SALT, user_id_bytes, sha256)`
- Tietokantaan tallennetaan vain hash (ei raakaa user_id:tä)
- Jos `SALT` puuttuu → generoidaan satunnaisesti `secrets.token_hex(32)` ja logitetaan WARNING
- Volatiilin SALT:n seurauksena vanhat hashit eivät enää vastaa samoja käyttäjiä restartin jälkeen (violation-laskurit ikään kuin nollaantuvat käyttäjätasolla)

## Moderointilogiikka

1. Viesti sisältää kielletyn sanan:
   - Poistetaan
   - Ensimmäinen rikkomus (7 pv ikkunassa): mute 12h + varoitusviesti (auto-delete 30s)
   - Toinen tai useampi rikkomus 7 päivän sisällä: pysyvä ban
2. Rikkomuslaskuri resetoi, jos edellisestä rikkomuksesta > 7 päivää.
3. Kielletyt sanat haetaan tietokannasta:
   - Tarkistetaan sekä sanakohtaiset word boundary -osumat että substring fallback (voi halutessa myöhemmin poistaa substring-tarkistuksen).
4. Kaikki moderointi pysyy pois päältä kunnes aktivoitu.

## Hakemistorakenne ja data

| Polku | Kuvaus |
|-------|--------|
| `bot.py` | Päälogiikka |
| `data/` | Istunto (`bot_session*`), tietokanta `bot.db`, lokitiedosto `bot.log` |
| `bot.db` | SQLite: taulut `violations`, `banned_words`, `activation_state` |

Jos `/data` ei ole kirjoituskelpoinen → fallback `./data`.

## Kehitysympäristö (virtualenv)

Unix/macOS:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Lokitus

- Tiedosto: `data/bot.log`
- Konsoli: sama formaatti
- Taso: INFO (voit halutessasi muuttaa `basicConfig`-kutsussa)
- Aktivointitapahtuma: INFO
- Uusi kielletty sana: INFO
- Volatiili SALT: WARNING
- Virheet: ERROR

## Turvallisuusnäkökulmia

| Aihe | Nykytila | Mahdollinen parannus |
|------|----------|----------------------|
| SALT hallinta | Ympäristömuuttuja tai volatiili generoitu | Lataa salainen arvo Vault/KMS:stä |
| Tietokanta | Paikallinen SQLite | Vaihto Postgres + kestävä tallennus jos skaalautuminen |
| ID anonymisointi | HMAC-SHA256 | Avainten rotaatio + versiointi |
| Rate limiting | TokenBucket (rakenteena) | Käytä oikeasti DM-spämmin hillintään |
| Banned words päivitys | Joka viestin yhteydessä uusi haku | Cache + invalidointi lisäyksissä |

## Roadmap / Mahdolliset jatkokehitykset

- `/orwell remove` ja `/orwell list` (valikoiden mukaan)
- `/stats` adminille: rikkomuslukemat
- `aiosqlite` → async SQLite
- Konfiguraatioluokka (Pydantic) ympäristövalidointiin
- Dockerfile + Compose
- Health check endpoint (esim. HTTP-portti)

## Esimerkkivirrat

Aktivointi:
```
Admin DM: "activate"
Bot: "Activated."
```

Lisäys:
```
/orwell spam, scam,botnet
→ Added: spam, scam, botnet
```

Tyhjä:
```
/orwell , ,
→ No valid words provided.
```

Uudelleen aktivointi:
```
activate
→ Already active.
```

## Vianetsintä

| Ongelma | Syy | Ratkaisu |
|---------|-----|----------|
| Bot ei reagoi mihinkään | Ei aktivoitu | DM: activate (adminilta) |
| "Missing required env vars" | API_ID/API_HASH/BOT_TOKEN puuttuu | Lisää .env:iin |
| Admin DM ei saa vastausta | ADMIN_USER_IDS ei sisällä user ID:täsi | Lisää ID listaan ja restart |
| Rikkomus ei nollaudu | Alle 7 päivää viimeisestä | Odota yli 7 pv tai muuta koodista logiikkaa |

## Lisenssi

```
MIT License

Copyright (c) ...
...
```

---

Made with passion and heart by Androdoge / Syndicates
