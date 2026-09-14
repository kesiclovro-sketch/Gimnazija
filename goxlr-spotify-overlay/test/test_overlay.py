"""Integracijski test overlaya protiv laznog GoXLR daemona.

Pokretanje:  python test/test_overlay.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import media_control  # noqa: E402
from goxlr_overlay import GoXLROverlay  # noqa: E402
from mock_daemon import SERIAL, MockDaemon  # noqa: E402

PORT = 14599

MEDIA_CALLS: list[str] = []


async def fake_run_action(action, app_match="spotify", double_previous=False):
    MEDIA_CALLS.append(action)


media_control.run_action = fake_run_action

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  [OK]   {label}")
    else:
        FAILURES.append(label)
        print(f"  [FAIL] {label} {detail}")


def config() -> dict:
    return {
        "websocket_url": f"ws://127.0.0.1:{PORT}/api/websocket",
        "serial": None,
        "trigger_channel": "Music",
        "hold_seconds": 1.0,
        "blink_interval": 0.15,
        "spotify_app_match": "spotify",
        "previous_double_press": False,
        "restore_mute_state": True,
        "buttons": {
            "Chat": {"action": "play_pause", "colour": "#fc0703", "blink": False},
            "Mic": {"action": "previous", "colour": "#03fce3", "blink": False},
            "System": {"action": "next", "colour": "#03fce3", "blink": False},
            "Music": {"action": "exit_mode", "colour": "#17fc03", "blink": True},
        },
    }


async def tap(daemon: MockDaemon, button: str, hold: float = 0.05) -> None:
    await daemon.press(button)
    await asyncio.sleep(hold)
    await daemon.release(button)
    await asyncio.sleep(0.35)


def colour_of(daemon: MockDaemon, button: str) -> str:
    return daemon.mixer["lighting"]["buttons"][button]["colours"]["colour_one"]


def mute_of(daemon: MockDaemon, fader: str) -> str:
    return daemon.mixer["fader_status"][fader]["mute_state"]


async def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    daemon = MockDaemon(hold_ms=400)
    server = await daemon.serve(PORT)
    holds = asyncio.create_task(daemon.hold_loop())

    overlay = GoXLROverlay(config())
    runner = asyncio.create_task(overlay.run_forever())
    await asyncio.sleep(0.6)

    print("\n1. Drzanje Music mute tipke 1.5 s")
    await daemon.press("Fader3Mute")          # Music = slider C
    await asyncio.sleep(1.5)
    check("overlay se ukljucio", overlay.active)
    await daemon.release("Fader3Mute")
    await asyncio.sleep(0.4)

    check("overlay ostaje ukljucen nakon otpustanja", overlay.active)
    check("Chat tipka je #fc0703", colour_of(daemon, "Fader2Mute") == "FC0703",
          colour_of(daemon, "Fader2Mute"))
    check("Mic tipka je #03fce3", colour_of(daemon, "Fader1Mute") == "03FCE3",
          colour_of(daemon, "Fader1Mute"))
    check("System tipka je #03fce3", colour_of(daemon, "Fader4Mute") == "03FCE3",
          colour_of(daemon, "Fader4Mute"))
    check("Music kanal nije ostao mutean", mute_of(daemon, "C") == "Unmuted",
          mute_of(daemon, "C"))

    print("\n2. Music tipka treperi")
    seen = set()
    for _ in range(14):
        seen.add(colour_of(daemon, "Fader3Mute"))
        await asyncio.sleep(0.08)
    check("treperi izmedu #17fc03 i ugaseno", {"17FC03", "000000"} <= seen, seen)

    print("\n3. Nova funkcija mute tipki")
    MEDIA_CALLS.clear()
    await tap(daemon, "Fader2Mute")           # Chat
    check("Chat -> play_pause", MEDIA_CALLS == ["play_pause"], MEDIA_CALLS)
    check("Chat kanal nije ostao mutean", mute_of(daemon, "B") == "Unmuted", mute_of(daemon, "B"))

    MEDIA_CALLS.clear()
    await tap(daemon, "Fader1Mute")           # Mic
    check("Mic -> previous", MEDIA_CALLS == ["previous"], MEDIA_CALLS)
    check("Mic kanal nije ostao mutean", mute_of(daemon, "A") == "Unmuted", mute_of(daemon, "A"))

    MEDIA_CALLS.clear()
    await tap(daemon, "Fader4Mute")           # System
    check("System -> next", MEDIA_CALLS == ["next"], MEDIA_CALLS)
    check("System kanal nije ostao mutean", mute_of(daemon, "D") == "Unmuted", mute_of(daemon, "D"))

    print("\n4. Ponovni klik na Music gasi nacin rada")
    MEDIA_CALLS.clear()
    await tap(daemon, "Fader3Mute")
    await asyncio.sleep(0.3)
    check("overlay je iskljucen", not overlay.active)
    check("bez medijske akcije pri izlasku", MEDIA_CALLS == [], MEDIA_CALLS)
    for button in ("Fader1Mute", "Fader2Mute", "Fader3Mute", "Fader4Mute"):
        entry = daemon.mixer["lighting"]["buttons"][button]
        check(
            f"{button}: boje vracene na pocetne",
            entry["colours"]["colour_one"] == "00FFFF"
            and entry["colours"]["colour_two"] == "000000"
            and entry["off_style"] == "Dimmed",
            entry,
        )

    print("\n5. Nakon izlaska tipke opet normalno muteaju")
    MEDIA_CALLS.clear()
    await tap(daemon, "Fader2Mute")
    check("bez medijske akcije", MEDIA_CALLS == [], MEDIA_CALLS)
    check("Chat je sada mutean", mute_of(daemon, "B") == "MutedToX", mute_of(daemon, "B"))
    await tap(daemon, "Fader2Mute")
    check("Chat je opet odmutean", mute_of(daemon, "B") == "Unmuted", mute_of(daemon, "B"))

    overlay.stop()
    runner.cancel()
    holds.cancel()
    for task in (runner, holds):
        try:
            await task
        except asyncio.CancelledError:
            pass
    server.close()
    await server.wait_closed()

    print()
    if FAILURES:
        print(f"NEUSPJESNO: {len(FAILURES)} provjera - {FAILURES}")
        return 1
    print("SVE PROVJERE PROSLE")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
