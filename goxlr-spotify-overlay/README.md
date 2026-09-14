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

> ### PRVO OVO
> Program **ne radi sa sluzbenom TC-Helicon "GoXLR App"** - ona nema API pa se
> na nju nema kako zakaciti. Treba ti **GoXLR Utility** (besplatan, ucitava
> tvoje postojece profile), a sluzbena app mora biti **ugasena**.
>
> Ako tipke samo blinkaju i nista se ne dogada na Spotifyu, to nije ovaj
> program nego tvornicko ponasanje GoXLR-a: kratak pritisak muteira kanal, a
> firmware tada sam blinka tipku. Znaci da se program nije spojio.
> Pokreni **`dijagnostika.bat`** - tocno ce ti reci sto nedostaje.

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

### 1. GoXLR Utility

Preuzmi ga sa stranice izdanja:
<https://github.com/GoXLR-on-Linux/goxlr-utility/releases/latest>

Pod naslovom **Assets** klikni datoteku **`goxlr-utility-<verzija>.exe`**
(npr. `goxlr-utility-1.2.4.exe`). Ako imas ARM racunalo, uzmi
`...-arm64.exe`. Ostale datoteke (`.deb`, `.rpm`, `.pkg`) su za Linux i Mac.

Alternativa preko naredbenog retka: `winget search goxlr-utility` pa
`winget install <id koji ti ispise>`.

Drivere ne trebas dirati - GoXLR Utility koristi iste sluzbene TC-Helicon
drivere koje vec imas jer si koristio sluzbenu aplikaciju.

### 2. Ugasi sluzbenu GoXLR App

Desni klik na njenu ikonu u traci pored sata -> Quit. Makni je i iz
automatskog pokretanja, inace ce ti se vratiti nakon svakog restarta i
"ukrasti" uredaj.

Zatim pokreni GoXLR Utility i provjeri da mu je ikona u traci.

### 3. Prijenos profila iz sluzbene aplikacije

**Ovo nemoj preskociti.** GoXLR Utility se pokrece sa svojim praznim zadanim
profilom, pa na prvi pogled izgleda kao da su sve postavke nestale. Nisu -
profili sluzbene aplikacije i dalje su netaknuti na disku, samo ih Utility jos
nije ucitao.

1. U GoXLR Utilityju otvori **Profiles** i klikni **ikonu mape** gore desno u
   tom okviru. Otvorit ce se mapa u koju Utility sprema profile.
2. U drugom prozoru otvori mapu sluzbene aplikacije:
   `C:\Users\<tvoje ime>\Documents\GoXLR\Profiles`
3. Kopiraj svoje `.goxlr` datoteke iz mape sluzbene aplikacije u mapu koju ti
   je Utility otvorio.
4. Isto ponovi za mikrofon: u okviru **Mic Profiles** klikni ikonu mape, pa
   kopiraj datoteke iz `C:\Users\<tvoje ime>\Documents\GoXLR\MicProfiles`.
5. Vrati se u Utility, osvjezi popis i **klikni svoj profil** da ga ucita.

Tek kad ti se profil ucita, slideri ce opet biti Mic / Chat / Music / System,
sto je ovom dodatku i potrebno. Ako profil nije ucitan, program ce se javiti
porukom da kanal `Music` nije ni na jednom slideru.

### 4. Python

Instaliraj **Python 3.10 ili noviji** s <https://www.python.org/downloads/>
i pri instalaciji stavi kvacicu na **"Add python.exe to PATH"**.

### 5. Pokreni

Dvoklik na **`pokreni.bat`**. Prvi put ce sam napraviti virtualno okruzenje i
instalirati ovisnosti, pa se pokrenuti.

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

Sve sto program ispise zapisuje se i u `goxlr_overlay.log`, pa se ima sto
poslati ako nesto ne stima.

## Predomislio si se? Povratak na sluzbenu aplikaciju

Nista nije izgubljeno i nista se ne mora vracati rucno:

1. Ugasi GoXLR Utility (desni klik na ikonu u traci -> Quit). Po zelji ga
   deinstaliraj kroz Postavke -> Aplikacije.
2. Pokreni sluzbenu **GoXLR App** i ucitaj svoj profil.

Profili sluzbene aplikacije u `Documents\GoXLR` cijelo vrijeme ostaju
netaknuti - Utility ih samo cita kad ih sam kopiras k sebi.

## Kad nesto ne radi: `dijagnostika.bat`

Dvoklik na **`dijagnostika.bat`**. Provjerit ce redom:

1. slusa li itko na portu GoXLR Utilityja,
2. vidi li daemon tvoj uredaj,
3. koji je kanal na kojem slideru,
4. **stizu li uopce pritisci tipki** - zadnjih 30 sekundi ceka da pritiskas
   mute tipke i ispisuje svaki pritisak i otpustanje.

Najcesci ishodi:

| Sto pise | Sto znaci |
|---|---|
| "NE MOGU SE SPOJITI" | GoXLR Utility nije instaliran ili nije pokrenut. |
| "GoXLR Utility radi, ali NE VIDI NIJEDAN UREDAJ" | Sluzbena GoXLR App je jos upaljena i drzi uredaj, ili je problem s USB-om. |
| "NISAM vidio nista" dok pritiskas tipke | Uredaj drzi netko drugi - gotovo uvijek sluzbena GoXLR App. |
| "Vidio sam N pritisaka - komunikacija radi" | Sve je u redu; ako overlay i dalje ne reagira, posalji mi taj ispis. |

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

Dijagnostika se testira zasebno:

```
python test/test_doktor.py
```
