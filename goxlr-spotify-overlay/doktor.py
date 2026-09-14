"""Dijagnostika: pokazuje sto program stvarno vidi od GoXLR-a.

Pokretanje:  dijagnostika.bat      (ili: python goxlr_overlay.py --doktor)

Redom provjerava:
  1. slusa li itko na portu GoXLR Utilityja,
  2. javlja li daemon uredaj i koji,
  3. na kojem je slideru koji kanal,
  4. stizu li uopce informacije o pritiscima tipki (button_down).

Zadnji korak je onaj najvazniji: ako se tu ne ispise nista dok pritiskas
tipke, program nema sto uhvatiti i nijedna postavka to nece popraviti.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from urllib.parse import urlparse

import websockets

from jsonpatch_lite import apply_patch

PATCH_ID = 18446744073709551615
WATCH_SECONDS = 30.0

FADER_BUTTON = {"A": "Fader1Mute", "B": "Fader2Mute", "C": "Fader3Mute", "D": "Fader4Mute"}


def endpoint(url: str) -> tuple[str, int]:
    parsed = urlparse(url)
    return parsed.hostname or "127.0.0.1", parsed.port or 14564


async def port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
    except Exception:
        return False
    writer.close()
    with contextlib.suppress(Exception):
        await writer.wait_closed()
    return True


def offline_help(host: str, port: int) -> None:
    print(
        f"""
==========================================================================
 NE MOGU SE SPOJITI na GoXLR Utility ({host}:{port})
==========================================================================

 Ovaj dodatak ne moze raditi sa sluzbenom TC-Helicon "GoXLR App" jer ona
 nema nikakav API. Treba mu GoXLR Utility. Provjeri redom:

  1. Je li GoXLR Utility uopce instaliran?
     -> https://github.com/GoXLR-on-Linux/goxlr-utility/releases/latest
        Pod "Assets" uzmi goxlr-utility-<verzija>.exe
        (ako imas ARM racunalo: ...-arm64.exe)

  2. Je li pokrenut? Trazi njegovu ikonu u traci pored sata.

  3. Je li sluzbena GoXLR App jos uvijek upaljena?
     Njih dvije NE MOGU raditi istovremeno - obje preuzimaju uredaj.
     Ugasi sluzbenu app (desni klik na ikonu u traci -> Quit) i makni je
     iz automatskog pokretanja, pa opet pokreni GoXLR Utility.

  4. Ako si Utilityju mijenjao port, upisi novi u config.json
     (polje "websocket_url").

 Dok ovo ne proradi, mute tipke rade tvornicki: kratak pritisak muteira
 kanal i GoXLR tada sam blinka tipku - to nije ovaj program.
==========================================================================
"""
    )


async def run(config: dict) -> int:
    url = config["websocket_url"]
    host, port = endpoint(url)

    print("=" * 74)
    print(" GoXLR -> Spotify overlay: dijagnostika")
    print("=" * 74)
    print(f"\n[1/4] Provjeravam slusa li itko na {host}:{port} ...")

    if not await port_open(host, port):
        print("      NE.")
        offline_help(host, port)
        return 1
    print("      DA, netko slusa.")

    print(f"\n[2/4] Spajam se na {url} ...")
    try:
        connection = websockets.connect(url, max_size=None)
    except Exception as error:
        print(f"      Greska: {error}")
        return 1

    async with connection as ws:
        await ws.send(json.dumps({"id": 1, "data": "GetStatus"}))
        status = None
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            message = json.loads(await ws.recv())
            if message.get("id") == 1:
                data = message.get("data")
                if isinstance(data, dict) and "Status" in data:
                    status = data["Status"]
                break
        if status is None:
            print("      Spojio sam se, ali daemon nije vratio status.")
            return 1

        version = status.get("config", {}).get("daemon_version", "?")
        print(f"      Spojeno. GoXLR Utility verzija {version}.")

        mixers = status.get("mixers", {})
        if not mixers:
            print(
                "\n      GoXLR Utility radi, ali NE VIDI NIJEDAN UREDAJ.\n"
                "      Provjeri USB kabel i je li sluzbena GoXLR App ugasena."
            )
            return 1

        serial = next(iter(mixers))
        mixer = mixers[serial]
        device = mixer.get("hardware", {}).get("device_type", "?")
        print(f"\n[3/4] Uredaj: GoXLR {device}, serijski broj {serial}")

        print("\n      Raspored kanala po sliderima:")
        for fader, data in sorted(mixer.get("fader_status", {}).items()):
            print(
                f"        slider {fader}  ->  {data.get('channel', '?'):<10}"
                f" (tipka {FADER_BUTTON.get(fader, '?')}, "
                f"mute funkcija: {data.get('mute_type', '?')}, "
                f"stanje: {data.get('mute_state', '?')})"
            )

        wanted = set(config.get("buttons", {}))
        have = {d.get("channel") for d in mixer.get("fader_status", {}).values()}
        missing = wanted - have
        if missing:
            print(
                f"\n      UPOZORENJE: ovi kanali iz config.json nisu ni na jednom"
                f" slideru: {', '.join(sorted(missing))}"
            )

        hold_ms = mixer.get("settings", {}).get("mute_hold_duration", "?")
        print(f"\n      GoXLR-ovo vlastito 'drzanje' tipke: {hold_ms} ms")

        if "button_down" not in mixer:
            print(
                "\n      GRESKA: ovaj daemon ne javlja stanje tipki (button_down).\n"
                "      Nadogradi GoXLR Utility na noviju verziju."
            )
            return 1

        print(f"\n[4/4] Sada PRITISNI mute tipke ispod slidera ({WATCH_SECONDS:.0f} s).")
        print("      Drzi Music mute tipku i dulje od 3.5 s da vidis oba dogadaja.\n")

        presses = 0
        mute_changes = 0
        previous = {
            "button_down": dict(mixer.get("button_down", {})),
            "mute": {
                f: d.get("mute_state") for f, d in mixer.get("fader_status", {}).items()
            },
        }
        press_start: dict[str, float] = {}
        deadline = time.monotonic() + WATCH_SECONDS

        while time.monotonic() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=deadline - time.monotonic())
            except asyncio.TimeoutError:
                break
            except Exception:
                break

            message = json.loads(raw)
            if message.get("id") != PATCH_ID:
                continue
            data = message.get("data")
            if not isinstance(data, dict) or not isinstance(data.get("Patch"), list):
                continue
            try:
                apply_patch(status, data["Patch"])
            except Exception:
                continue

            mixer = status["mixers"][serial]
            now = time.strftime("%H:%M:%S")

            for button, is_down in mixer.get("button_down", {}).items():
                if bool(is_down) == bool(previous["button_down"].get(button)):
                    continue
                previous["button_down"][button] = bool(is_down)
                if is_down:
                    press_start[button] = time.monotonic()
                    print(f"  {now}  tipka {button}: PRITISNUTA")
                else:
                    held = time.monotonic() - press_start.pop(button, time.monotonic())
                    presses += 1
                    print(f"  {now}  tipka {button}: otpustena nakon {held:.2f} s")

            for fader, entry in mixer.get("fader_status", {}).items():
                state = entry.get("mute_state")
                if state == previous["mute"].get(fader):
                    continue
                previous["mute"][fader] = state
                mute_changes += 1
                print(f"  {now}  slider {fader} ({entry.get('channel')}): mute -> {state}")

        print("\n" + "-" * 74)
        if presses:
            print(f"  Vidio sam {presses} pritisak(a) tipki - komunikacija radi.")
            print("  Ako overlay i dalje ne reagira, posalji mi ovaj ispis.")
            result = 0
        elif mute_changes:
            print(
                "  Vidio sam promjene mutea, ali NIJEDAN pritisak tipke.\n"
                "  Nadogradi GoXLR Utility - ova verzija ne javlja stanje tipki."
            )
            result = 1
        else:
            print(
                "  NISAM vidio nista.\n\n"
                "  Ako si stvarno pritiskao mute tipke ispod slidera, onda ih\n"
                "  GoXLR Utility ne cuje - najcesce zato sto je sluzbena GoXLR App\n"
                "  jos uvijek upaljena i drzi uredaj. Ugasi ju pa ponovi."
            )
            result = 1
        print("-" * 74)
        return result
