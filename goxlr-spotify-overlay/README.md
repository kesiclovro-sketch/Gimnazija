# GoXLR Mini -> Spotify overlay

Dodatak za GoXLR Mini koji mute tipkama ispod slidera daje drugu funkciju kad
ih trebas za Spotify.

Drzis mute tipku **Music** kanala dulje od **3.5 sekunde** i sve cetiri mute
tipke prelaze u Spotify nacin rada:

| Tipka (kanal) | Boja | Sto radi |
|---|---|---|
| **Chat** | `#fc0703` (crvena) | pauzira / nastavlja trenutnu pjesmu |
| **Mic** | `#03fce3` (tirkizna) | prethodna pjesma |
| **System** | `#03fce3` (tirkizna) | sljedeca pjesma |
| **Music** | `#17fc03` (zelena), **treperi** | pritisak vraca tipke u normalan rad |

Kad izadjes iz tog nacina rada, sve boje i sve funkcije tipki vracaju se tocno
na ono sto je postavljeno u GoXLR aplikaciji/profilu.

---

## Vazno prije pocetka: sluzbena GoXLR App nije dovoljna

Sluzbena TC-Helicon **GoXLR App**
(`C:\ProgramData\Microsoft\Windows\Start Menu\Programs\(Default)\GoXLR App.lnk`)
nema nikakav API, plugin sustav ni nacin da joj se izvana javi da je tipka
pritisnuta ili da joj se promijeni boja tipke. Bez toga ovakav program
jednostavno nema za sto uhvatiti.

Zato ovaj program koristi **GoXLR Utility** - besplatnu, open-source zamjenu za
sluzbenu aplikaciju: <https://github.com/GoXLR-on-Linux/goxlr-utility>

Sto to znaci za tebe:

* GoXLR Utility ucitava tvoje postojece profile iz sluzbene aplikacije, pa ne
  gubis postavke.
* **Sluzbena GoXLR App i GoXLR Utility ne mogu raditi istovremeno** - oboje
  preuzimaju uredaj. Dok koristis ovaj dodatak, sluzbena aplikacija mora biti
  ugasena (i iskljucena iz automatskog pokretanja).
* Ako ti to ne odgovara, javi - alternativa je dodatak koji *ne* dira GoXLR
  tipke nego koristi obicnu tipkovnicku precicu, ali onda nema ni boja ni
  treperenja na tipkama.

## Instalacija

1. Instaliraj **Python 3.10 ili noviji** s <https://www.python.org/downloads/>
   (kvacica na "Add python.exe to PATH" pri instalaciji).
2. Instaliraj **GoXLR Utility** (Windows installer s gornjeg linka) i pokreni
   ga. Provjeri da ti radi u traci (system tray).
3. Ugasi sluzbenu **GoXLR App** i makni je iz automatskog pokretanja.
4. Dvoklik na **`pokreni.bat`**. Prvi put ce sam napraviti virtualno okruzenje
   i instalirati ovisnosti, pa se pokrenuti.

Ako sve radi, u prozoru ces vidjeti nesto poput:

```
Spojen na GoXLR Mini (serijski broj S210xxxxxx)
  Chat   -> slider B (Fader2Mute)
  Mic    -> slider A (Fader1Mute)
  System -> slider D (Fader4Mute)
  Music  -> slider C (Fader3Mute)
Drzi mute tipku kanala Music 3.5s za ulazak u Spotify nacin rada.
```

Program sam otkriva na kojem je slideru koji kanal, pa je svejedno kojim si ih
redom posloz'o u profilu.

Za izlaz pritisni `Ctrl+C` - boje i mute stanja se vracaju na zatecene.

## Kako cilja bas Spotify

Koristi Windowsov sustav medijskih kontrola (isti onaj iz prozorcica gore
lijevo kad promijenis glasnocu) i u njemu trazi sesiju ciji je naziv aplikacije
`spotify`. Tako pauza/sljedeca/prethodna idu bas Spotifyu, cak i ako je u
fokusu igra ili preglednik.

To zahtijeva paket `winsdk` (instalira ga `pokreni.bat`). Ako ga nema, program
i dalje radi, ali salje obicne globalne medijske tipke - tada akciju moze
pokupiti neka druga medijska aplikacija ako je ona zadnja svirala.

## Postavke (`config.json`)

```json
{
  "websocket_url": "ws://127.0.0.1:14564/api/websocket",
  "serial": null,
  "trigger_channel": "Music",
  "hold_seconds": 3.5,
  "blink_interval": 0.45,
  "spotify_app_match": "spotify",
  "previous_double_press": false,
  "restore_mute_state": true,

  "buttons": {
    "Chat":   { "action": "play_pause", "colour": "#fc0703", "blink": false },
    "Mic":    { "action": "previous",   "colour": "#03fce3", "blink": false },
    "System": { "action": "next",       "colour": "#03fce3", "blink": false },
    "Music":  { "action": "exit_mode",  "colour": "#17fc03", "blink": true  }
  }
}
```

| Postavka | Znacenje |
|---|---|
| `websocket_url` | Adresa GoXLR Utility daemona. Mijenjaj samo ako si mu mijenjao port. |
| `serial` | Serijski broj uredaja; `null` = uzmi prvi pronadeni. |
| `trigger_channel` | Kanal cijom se mute tipkom ulazi u nacin rada. |
| `hold_seconds` | Koliko dugo drzati tipku (sekunde). |
| `blink_interval` | Pola perioda treperenja (0.45 = otprilike jedan bljesak po sekundi). |
| `spotify_app_match` | Dio naziva aplikacije koju treba naci medu medijskim sesijama. |
| `previous_double_press` | `true` = "prethodna" salje dva puta. Spotify prvim pritiskom vrati pjesmu na pocetak ako je odsvirano vise od par sekundi; s `true` uvijek skoci na stvarno prethodnu pjesmu. |
| `restore_mute_state` | Ponistavanje muteova koje GoXLR sam napravi na pritisak. Ostavi na `true`. |

Moguce vrijednosti za `action`: `play_pause`, `pause`, `play`, `next`,
`previous`, `exit_mode`, `none`.

## Sitnica koju je dobro znati

GoXLR sam po sebi *uvijek* mutea kanal kad mu pritisnes mute tipku - to se ne
da izvana zabraniti. Zato program odmah nakon pritiska vrati kanal u stanje u
kojem je bio. U praksi je to prekid od par desetaka milisekundi, prakticki
nezamjetno. Isto vrijedi i za samo drzanje tipke 3.5 s: GoXLR ce usput napraviti
svoj "mute to all", a program ga odmah ponisti.

Ako program nasilno ugasis (npr. preko Task Managera) dok je Spotify nacin rada
ukljucen, boje tipki ostat ce zelene/crvene. Nista strasno: pokreni program
ponovno, udi u nacin rada i izadi iz njega normalno, ili u GoXLR Utilityju
ponovno ucitaj profil.

## Test bez uredaja

U mapi `test/` je lazni GoXLR daemon, pa se cijela logika moze provjeriti bez
spojenog GoXLR-a:

```
python test/test_overlay.py
```

Prolazi kroz: drzanje 3.5 s (skraceno radi brzine), postavljanje boja,
treperenje, sve tri medijske akcije, ponistavanje muteova, izlazak iz nacina
rada i povratak boja na pocetne.
