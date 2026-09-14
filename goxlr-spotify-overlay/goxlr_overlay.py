#!/usr/bin/env python3
"""GoXLR Mini -> Spotify overlay.

Drzi mute tipku odabranog kanala (po defaultu Music) duze od 3.5 sekunde i sve
cetiri mute tipke ispod slidera prelaze u "Spotify" nacin rada:

    Chat   (#fc0703)  -> pauza / nastavak trenutne pjesme
    Mic    (#03fce3)  -> prethodna pjesma
    System (#03fce3)  -> sljedeca pjesma
    Music  (#17fc03)  -> treperi; pritisak vraca tipke u normalan rad

Dok je overlay aktivan, program ponistava mute koji GoXLR odradi na pritisak,
pa tipke stvarno "dobiju novu funkciju" umjesto da usput muteaju kanale.

Zahtijeva GoXLR Utility (https://github.com/GoXLR-on-Linux/goxlr-utility)
jer sluzbena TC-Helicon GoXLR App nema nikakav API za vanjske programe.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import signal
import sys
import time
from pathlib import Path

import websockets

import doktor
import media_control
from jsonpatch_lite import apply_patch

log = logging.getLogger("goxlr")

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "config.json"

# Broadcast poruke (JSON-Patch) dolaze s id = u64::MAX.
PATCH_ID = 18446744073709551615

FADER_BUTTON = {
    "A": "Fader1Mute",
    "B": "Fader2Mute",
    "C": "Fader3Mute",
    "D": "Fader4Mute",
}

DEFAULT_CONFIG = {
    "websocket_url": "ws://127.0.0.1:14564/api/websocket",
    "serial": None,
    "trigger_channel": "Music",
    "hold_seconds": 3.5,
    "blink_interval": 0.45,
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


def load_config(path: Path) -> dict:
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    if path.is_file():
        try:
            user = json.loads(path.read_text(encoding="utf-8"))
        except Exception as error:
            log.error("Ne mogu procitati %s (%s) - koristim zadane postavke.", path.name, error)
            return config
        for key, value in user.items():
            if key == "buttons" and isinstance(value, dict):
                for channel, entry in value.items():
                    merged = dict(config["buttons"].get(channel, {}))
                    merged.update(entry or {})
                    config["buttons"][channel] = merged
            else:
                config[key] = value
        log.info("Ucitane postavke iz %s", path.name)
    else:
        log.info("%s ne postoji - koristim zadane postavke.", path.name)
    return config


def normalise_colour(value: str) -> str:
    """'#fc0703' -> 'FC0703' (GoXLR Utility ocekuje RRGGBB bez ljestvica)."""
    colour = str(value).strip().lstrip("#").upper()
    if len(colour) == 8:  # AARRGGBB -> RRGGBB
        colour = colour[2:]
    if len(colour) != 6 or any(c not in "0123456789ABCDEF" for c in colour):
        raise ValueError(f"Neispravna boja: {value!r}")
    return colour


class GoXLROverlay:
    def __init__(self, config: dict):
        self.config = config
        self.hold_seconds = float(config["hold_seconds"])
        self.blink_interval = float(config["blink_interval"])

        self.ws = None
        self.status: dict = {}
        self.serial: str | None = None

        self._next_id = 1
        self._pending: dict[int, asyncio.Future] = {}
        self._resync_id: int | None = None

        # Tipka -> kanal / akcija / boja, popunjava se nakon GetStatus-a.
        self.button_channel: dict[str, str] = {}
        self.button_fader: dict[str, str] = {}
        self.trigger_button: str | None = None

        self.active = False
        self.button_down: dict[str, bool] = {}
        self.press_start: dict[str, float] = {}
        self.hold_consumed: set[str] = set()

        self.saved_lighting: dict[str, dict] = {}
        self.saved_mute: dict[str, str] = {}
        self._last_restore: dict[str, float] = {}

        self._blink_task: asyncio.Task | None = None
        self._events: asyncio.Queue | None = None
        self._stopping = False
        self._warned_offline = False
        self._seen_button_event = False
        self._warned_no_buttons = False

    # ------------------------------------------------------------------ IPC

    async def _send(self, data) -> object:
        """Posalji zahtjev daemonu i pricekaj odgovor."""
        if self.ws is None:
            raise ConnectionError("Websocket nije spojen")
        request_id = self._next_id
        self._next_id += 1
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        await self.ws.send(json.dumps({"id": request_id, "data": data}))
        try:
            return await asyncio.wait_for(future, timeout=5.0)
        finally:
            self._pending.pop(request_id, None)

    async def command(self, command: dict) -> None:
        """Posalji GoXLRCommand za nas uredaj."""
        try:
            result = await self._send({"Command": [self.serial, command]})
        except asyncio.TimeoutError:
            log.warning("Naredba %s nije dobila odgovor.", next(iter(command)))
            return
        if isinstance(result, dict) and "Error" in result:
            log.error("Naredba %s odbijena: %s", next(iter(command)), result["Error"])

    async def set_button_colour(self, button: str, colour: str) -> None:
        await self.command({"SetButtonColours": [button, colour, colour]})
        await self.command({"SetButtonOffStyle": [button, "Colour2"]})

    async def restore_button_lighting(self, button: str) -> None:
        saved = self.saved_lighting.get(button)
        if not saved:
            return
        await self.command(
            {"SetButtonColours": [button, saved["colour_one"], saved["colour_two"]]}
        )
        await self.command({"SetButtonOffStyle": [button, saved["off_style"]]})

    async def set_mute_state(self, fader: str, state: str) -> None:
        await self.command({"SetFaderMuteState": [fader, state]})

    # -------------------------------------------------------------- start-up

    async def bootstrap(self) -> None:
        status = await self._send("GetStatus")
        if not isinstance(status, dict) or "Status" not in status:
            raise RuntimeError(f"Neocekivan odgovor na GetStatus: {status!r}")
        self.status = status["Status"]

        mixers = self.status.get("mixers", {})
        if not mixers:
            raise RuntimeError("GoXLR Utility ne vidi nijedan uredaj.")

        wanted = self.config.get("serial")
        if wanted and wanted in mixers:
            self.serial = wanted
        else:
            if wanted:
                log.warning("Serijski broj %s nije pronaden - uzimam prvi uredaj.", wanted)
            self.serial = next(iter(mixers))

        mixer = mixers[self.serial]
        device = mixer["hardware"].get("device_type", "?")
        log.info("Spojen na GoXLR %s (serijski broj %s)", device, self.serial)

        self._map_buttons(mixer)
        snapshot = self.snapshot() or {"button_down": {}, "mute": {}}
        self._snapshot_mute_states(snapshot["mute"])
        self.button_down = dict(snapshot["button_down"])

    def _map_buttons(self, mixer: dict) -> None:
        """Poveži kanale iz postavki sa stvarnim mute tipkama na uredaju."""
        channel_to_fader = {
            data["channel"]: fader for fader, data in mixer["fader_status"].items()
        }
        self.button_channel.clear()
        self.button_fader.clear()

        for channel in self.config["buttons"]:
            fader = channel_to_fader.get(channel)
            if fader is None:
                log.warning("Kanal %s nije ni na jednom slideru - preskacem.", channel)
                continue
            button = FADER_BUTTON[fader]
            self.button_channel[button] = channel
            self.button_fader[button] = fader
            log.info("  %-6s -> slider %s (%s)", channel, fader, button)

        trigger_channel = self.config["trigger_channel"]
        self.trigger_button = next(
            (b for b, c in self.button_channel.items() if c == trigger_channel), None
        )
        if self.trigger_button is None:
            raise RuntimeError(
                f"Kanal za aktivaciju ({trigger_channel}) nije ni na jednom slideru."
            )
        log.info(
            "Drzi mute tipku kanala %s %.1fs za ulazak u Spotify nacin rada.",
            trigger_channel,
            self.hold_seconds,
        )

    def _snapshot_mute_states(self, mute_states: dict[str, str]) -> None:
        self.saved_mute.update(mute_states)

    def snapshot(self) -> dict | None:
        """Izvuci iz statusa samo ono na sto reagiramo (tipke + mute stanja)."""
        try:
            mixer = self.mixer
        except KeyError:
            return None
        down = mixer.get("button_down", {})
        return {
            "button_down": {b: bool(down.get(b, False)) for b in self.button_channel},
            "mute": {
                fader: mixer["fader_status"][fader]["mute_state"]
                for fader in self.button_fader.values()
            },
        }

    @property
    def mixer(self) -> dict:
        return self.status["mixers"][self.serial]

    # ----------------------------------------------------------- petlja/citac

    async def reader(self) -> None:
        assert self.ws is not None
        async for raw in self.ws:
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue

            message_id = message.get("id")
            data = message.get("data")

            if message_id == PATCH_ID and isinstance(data, dict) and "Patch" in data:
                patch = data["Patch"]
                try:
                    if not isinstance(patch, list):
                        raise TypeError(f"ocekivana lista operacija, dobio {type(patch).__name__}")
                    apply_patch(self.status, patch)
                except Exception as error:
                    log.debug("Patch nije primijenjen (%s) - trazim puni status.", error)
                    await self._request_resync()
                snapshot = self.snapshot()
                if snapshot is not None and self._events is not None:
                    self._events.put_nowait(snapshot)
                continue

            if message_id is not None and message_id == self._resync_id:
                self._resync_id = None
                if isinstance(data, dict) and "Status" in data:
                    self.status = data["Status"]
                    log.debug("Status ponovno sinkroniziran.")
                continue

            future = self._pending.get(message_id)
            if future is not None and not future.done():
                future.set_result(data)

    async def _request_resync(self) -> None:
        """Zatrazi puni status bez cekanja odgovora.

        Reader ne smije cekati odgovor jer ga sam mora procitati - zato samo
        posaljemo zahtjev i obradimo ga kad stigne.
        """
        if self.ws is None or self._resync_id is not None:
            return
        self._resync_id = self._next_id
        self._next_id += 1
        with contextlib.suppress(Exception):
            await self.ws.send(json.dumps({"id": self._resync_id, "data": "GetStatus"}))

    async def hold_watcher(self) -> None:
        """Nadzire drzanje tipke za aktivaciju (daemon nam to ne javlja)."""
        while True:
            await asyncio.sleep(0.05)
            button = self.trigger_button
            if button is None or self.active:
                continue
            started = self.press_start.get(button)
            if started is None or button in self.hold_consumed:
                continue
            if time.monotonic() - started >= self.hold_seconds:
                self.hold_consumed.add(button)
                await self.activate()

    # ------------------------------------------------------------- reagiranje

    async def processor(self) -> None:
        """Obraduje snimke statusa izvan reader petlje.

        Vazno: naredbe cekaju odgovor daemona, a taj odgovor moze isporuciti
        samo reader. Zato se obrada nikad ne smije dogadati unutar readera.
        """
        assert self._events is not None
        while True:
            snapshot = await self._events.get()
            try:
                await self.handle_snapshot(snapshot)
            except Exception:
                log.exception("Greska pri obradi promjene statusa")

    async def handle_snapshot(self, snapshot: dict) -> None:
        current = snapshot["button_down"]
        mute_states = snapshot["mute"]

        # 1. Pritisci i otpustanja tipki.
        for button in self.button_channel:
            was_down = self.button_down.get(button, False)
            is_down = bool(current.get(button, False))
            if is_down == was_down:
                continue
            self.button_down[button] = is_down
            self._seen_button_event = True
            if is_down:
                self.press_start[button] = time.monotonic()
                self.hold_consumed.discard(button)
                if not self.active:
                    # Snimi stanje muteova prije nego daemon odradi svoj hold.
                    self._snapshot_mute_states(mute_states)
            else:
                started = self.press_start.pop(button, time.monotonic())
                consumed = button in self.hold_consumed
                self.hold_consumed.discard(button)
                await self.on_release(button, time.monotonic() - started, consumed)

        # 2. Dok smo aktivni (ili usred drzanja), ponisti mute koji je GoXLR
        #    napravio sam od sebe.
        if not self.config.get("restore_mute_state", True):
            return
        protecting = self.active or bool(self.press_start)
        for fader, state in mute_states.items():
            if not protecting:
                if state != self.saved_mute.get(fader) and not self._seen_button_event:
                    self._warn_no_button_events()
                self.saved_mute[fader] = state
                continue
            wanted = self.saved_mute.get(fader, "Unmuted")
            if state == wanted:
                continue
            now = time.monotonic()
            if now - self._last_restore.get(fader, 0.0) < 0.25:
                continue
            self._last_restore[fader] = now
            log.debug("Vracam mute slidera %s na %s", fader, wanted)
            await self.set_mute_state(fader, wanted)

    def _warn_no_button_events(self) -> None:
        """Mute se mijenja, ali stanje tipki ne stize - bez toga nema drzanja."""
        if self._warned_no_buttons:
            return
        self._warned_no_buttons = True
        log.warning(
            "GoXLR javlja promjenu mutea, ali ne i pritiske tipki. Bez toga ne "
            "mogu izmjeriti drzanje od %.1f s. Pokreni dijagnostika.bat.",
            self.hold_seconds,
        )

    async def on_release(self, button: str, held: float, consumed: bool) -> None:
        channel = self.button_channel.get(button, "?")
        if consumed:
            # Ovaj pritisak je vec upotrijebljen za ulazak u nacin rada.
            return
        if not self.active:
            return

        entry = self.config["buttons"].get(channel, {})
        action = entry.get("action", "none")
        log.info("Tipka %s (%s) pritisnuta %.0f ms -> %s", channel, button, held * 1000, action)

        if action == "exit_mode":
            await self.deactivate()
            return

        await media_control.run_action(
            action,
            app_match=self.config.get("spotify_app_match", "spotify"),
            double_previous=bool(self.config.get("previous_double_press", False)),
        )

    # --------------------------------------------------------- nacin rada on/off

    async def activate(self) -> None:
        if self.active:
            return
        log.info("--- Spotify nacin rada UKLJUCEN ---")
        self.active = True

        lighting = self.mixer["lighting"]["buttons"]
        self.saved_lighting = {}
        for button in self.button_channel:
            saved = lighting.get(button)
            if saved:
                self.saved_lighting[button] = {
                    "colour_one": saved["colours"]["colour_one"],
                    "colour_two": saved["colours"]["colour_two"],
                    "off_style": saved["off_style"],
                }

        blink_button = None
        for button, channel in self.button_channel.items():
            entry = self.config["buttons"].get(channel, {})
            try:
                colour = normalise_colour(entry.get("colour", "#ffffff"))
            except ValueError as error:
                log.error("%s - preskacem %s", error, channel)
                continue
            if entry.get("blink"):
                blink_button = (button, colour)
                continue
            await self.set_button_colour(button, colour)

        # Daemon je tijekom drzanja vjerojatno napravio "mute to all" - vrati.
        if self.config.get("restore_mute_state", True):
            for fader, state in self.saved_mute.items():
                await self.set_mute_state(fader, state)

        if blink_button:
            self._blink_task = asyncio.create_task(self.blink(*blink_button))

    async def deactivate(self) -> None:
        if not self.active:
            return
        log.info("--- Spotify nacin rada ISKLJUCEN ---")
        self.active = False

        if self._blink_task:
            self._blink_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._blink_task
            self._blink_task = None

        for button in list(self.button_channel):
            await self.restore_button_lighting(button)

        if self.config.get("restore_mute_state", True):
            for fader, state in self.saved_mute.items():
                await self.set_mute_state(fader, state)

    async def blink(self, button: str, colour: str) -> None:
        try:
            while True:
                await self.set_button_colour(button, colour)
                await asyncio.sleep(self.blink_interval)
                await self.set_button_colour(button, "000000")
                await asyncio.sleep(self.blink_interval)
        except asyncio.CancelledError:
            raise

    # ------------------------------------------------------------------- run

    async def run_once(self) -> None:
        url = self.config["websocket_url"]
        log.info("Spajam se na %s ...", url)
        async with websockets.connect(url, max_size=None) as ws:
            self.ws = ws
            # Citac mora raditi prije `bootstrap()`, inace nitko ne razrijesi
            # odgovor na GetStatus.
            self._events = asyncio.Queue()
            self._resync_id = None
            reader = asyncio.create_task(self.reader())
            helpers: list[asyncio.Task] = []
            try:
                await self.bootstrap()
                helpers = [
                    asyncio.create_task(self.processor()),
                    asyncio.create_task(self.hold_watcher()),
                ]
                done, pending = await asyncio.wait(
                    [reader, *helpers], return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
                for task in done:
                    with contextlib.suppress(asyncio.CancelledError):
                        task.result()
            finally:
                for task in (reader, *helpers):
                    if not task.done():
                        task.cancel()
                        with contextlib.suppress(Exception):
                            await task
                if self.active:
                    with contextlib.suppress(Exception):
                        await self.deactivate()
                self.ws = None

    async def run_forever(self) -> None:
        delay = 2.0
        host, port = doktor.endpoint(self.config["websocket_url"])
        while not self._stopping:
            if not await doktor.port_open(host, port):
                if not self._warned_offline:
                    self._warned_offline = True
                    doktor.offline_help(host, port)
                    log.info("Cekam da se GoXLR Utility pojavi ... (Ctrl+C za izlaz)")
                await asyncio.sleep(3.0)
                continue
            try:
                await self.run_once()
                self._warned_offline = False
                delay = 2.0
            except (OSError, websockets.exceptions.WebSocketException) as error:
                log.warning("Veza s GoXLR Utilityjem prekinuta (%s).", error)
            except asyncio.TimeoutError:
                log.warning("GoXLR Utility ne odgovara na zahtjeve.")
            except RuntimeError as error:
                log.error("%s", error)
            except Exception:
                log.exception("Neocekivana greska - pokusavam se ponovno spojiti.")
            if self._stopping:
                break
            log.info("Ponovni pokusaj za %.0f s ... (Ctrl+C za izlaz)", delay)
            await asyncio.sleep(delay)
            delay = min(delay * 1.5, 30.0)

    def stop(self) -> None:
        self._stopping = True


async def main_async(args: argparse.Namespace, config: dict) -> int:
    overlay = GoXLROverlay(config)

    loop = asyncio.get_running_loop()
    main_task = asyncio.current_task()

    def request_stop() -> None:
        overlay.stop()
        if main_task:
            main_task.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError, AttributeError):
            loop.add_signal_handler(sig, request_stop)

    try:
        await overlay.run_forever()
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        overlay.stop()
    log.info("Dovidenja.")
    return 0


def setup_logging(verbose: bool) -> None:
    """Ispis u konzolu i u goxlr_overlay.log (da se ima sto poslati)."""
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    try:
        handlers.append(logging.FileHandler(HERE / "goxlr_overlay.log", encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="GoXLR Mini -> Spotify overlay")
    parser.add_argument("-c", "--config", help="putanja do config.json")
    parser.add_argument("-v", "--verbose", action="store_true", help="detaljan ispis")
    parser.add_argument(
        "--doktor",
        action="store_true",
        help="provjeri vezu s GoXLR-om i pokazi sto program vidi",
    )
    args = parser.parse_args()

    setup_logging(args.verbose)

    config = load_config(Path(args.config) if args.config else CONFIG_PATH)

    try:
        if args.doktor:
            return asyncio.run(doktor.run(config))
        return asyncio.run(main_async(args, config))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
