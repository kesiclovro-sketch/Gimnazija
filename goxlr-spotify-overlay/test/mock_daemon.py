"""Lazni GoXLR Utility daemon za testiranje overlaya bez uredaja.

Oponasa ono sto radi pravi daemon:
  * odgovara na GetStatus punim DaemonStatus objektom,
  * izvrsava SetButtonColours / SetButtonOffStyle / SetFaderMuteState,
  * nakon svake promjene salje JSON-Patch svim klijentima (id = u64::MAX),
  * na drzanje mute tipke duze od `hold_ms` sam postavlja MutedToAll,
  * na kratki pritisak toggla mute (kao pravi GoXLR).
"""

from __future__ import annotations

import asyncio
import copy
import json
import time

import websockets

PATCH_ID = 18446744073709551615
SERIAL = "S000000000"

FADER_BUTTON = {"A": "Fader1Mute", "B": "Fader2Mute", "C": "Fader3Mute", "D": "Fader4Mute"}
BUTTON_FADER = {v: k for k, v in FADER_BUTTON.items()}


def initial_status() -> dict:
    buttons = {}
    for button in FADER_BUTTON.values():
        buttons[button] = {
            "off_style": "Dimmed",
            "colours": {"colour_one": "00FFFF", "colour_two": "000000"},
        }
    return {
        "config": {"http_settings": {"enabled": True, "port": 14564}},
        "mixers": {
            SERIAL: {
                "hardware": {"serial_number": SERIAL, "device_type": "Mini"},
                "fader_status": {
                    "A": {"channel": "Mic", "mute_type": "All", "mute_state": "Unmuted"},
                    "B": {"channel": "Chat", "mute_type": "All", "mute_state": "Unmuted"},
                    "C": {"channel": "Music", "mute_type": "All", "mute_state": "Unmuted"},
                    "D": {"channel": "System", "mute_type": "All", "mute_state": "Unmuted"},
                },
                "lighting": {"buttons": buttons},
                "button_down": {b: False for b in FADER_BUTTON.values()},
            }
        },
    }


def diff(old, new, path=""):
    """Vrlo jednostavan JSON-Patch diff (dovoljan za ovaj test)."""
    ops = []
    if isinstance(old, dict) and isinstance(new, dict):
        for key in new:
            sub = f"{path}/{key}"
            if key not in old:
                ops.append({"op": "add", "path": sub, "value": new[key]})
            else:
                ops.extend(diff(old[key], new[key], sub))
        for key in old:
            if key not in new:
                ops.append({"op": "remove", "path": f"{path}/{key}"})
    elif old != new:
        ops.append({"op": "replace", "path": path, "value": new})
    return ops


class MockDaemon:
    def __init__(self, hold_ms: int = 1000):
        self.status = initial_status()
        self.clients: set = set()
        self.hold_ms = hold_ms
        self.press_time: dict[str, float] = {}
        self.hold_handled: set[str] = set()
        self.colour_calls: list[tuple] = []

    @property
    def mixer(self) -> dict:
        return self.status["mixers"][SERIAL]

    async def broadcast(self, before: dict) -> None:
        ops = diff(before, self.status)
        if not ops:
            return
        message = json.dumps({"id": PATCH_ID, "data": {"Patch": ops}})
        for client in list(self.clients):
            try:
                await client.send(message)
            except Exception:
                self.clients.discard(client)

    async def mutate(self, fn) -> None:
        before = copy.deepcopy(self.status)
        fn()
        await self.broadcast(before)

    # ------------------------------------------------- simulacija hardvera

    async def press(self, button: str) -> None:
        self.press_time[button] = time.monotonic()
        self.hold_handled.discard(button)
        await self.mutate(lambda: self.mixer["button_down"].__setitem__(button, True))

    async def release(self, button: str) -> None:
        _held = (time.monotonic() - self.press_time.pop(button, time.monotonic())) * 1000
        handled = button in self.hold_handled
        self.hold_handled.discard(button)

        def apply():
            self.mixer["button_down"][button] = False
            # Pravi daemon toggla mute na otpustanje samo ako "hold" nije vec
            # odradio svoje.
            if not handled:
                fader = BUTTON_FADER[button]
                state = self.mixer["fader_status"][fader]["mute_state"]
                self.mixer["fader_status"][fader]["mute_state"] = (
                    "Unmuted" if state != "Unmuted" else "MutedToX"
                )

        await self.mutate(apply)

    async def tick_holds(self) -> None:
        """Pravi daemon na duzi pritisak radi 'mute to all'."""
        now = time.monotonic()
        for button, started in list(self.press_time.items()):
            if button in self.hold_handled:
                continue
            if (now - started) * 1000 >= self.hold_ms:
                self.hold_handled.add(button)
                fader = BUTTON_FADER[button]
                await self.mutate(
                    lambda f=fader: self.mixer["fader_status"][f].__setitem__(
                        "mute_state", "MutedToAll"
                    )
                )

    async def hold_loop(self) -> None:
        while True:
            await asyncio.sleep(0.02)
            await self.tick_holds()

    # ------------------------------------------------------------ naredbe

    async def run_command(self, command: dict) -> dict | str:
        name, args = next(iter(command.items()))

        if name == "SetButtonColours":
            button, one, two = args
            self.colour_calls.append((button, one, two))

            def apply():
                entry = self.mixer["lighting"]["buttons"][button]
                entry["colours"]["colour_one"] = one
                entry["colours"]["colour_two"] = two if two is not None else one

            await self.mutate(apply)
            return "Ok"

        if name == "SetButtonOffStyle":
            button, style = args
            await self.mutate(
                lambda: self.mixer["lighting"]["buttons"][button].__setitem__("off_style", style)
            )
            return "Ok"

        if name == "SetFaderMuteState":
            fader, state = args
            await self.mutate(
                lambda: self.mixer["fader_status"][fader].__setitem__("mute_state", state)
            )
            return "Ok"

        return {"Error": f"Nepoznata naredba: {name}"}

    async def handler(self, ws) -> None:
        self.clients.add(ws)
        try:
            async for raw in ws:
                request = json.loads(raw)
                request_id = request["id"]
                data = request["data"]

                if data == "GetStatus":
                    response = {"Status": copy.deepcopy(self.status)}
                elif data == "Ping":
                    response = "Ok"
                elif isinstance(data, dict) and "Command" in data:
                    serial, command = data["Command"]
                    if serial != SERIAL:
                        response = {"Error": "Nepoznat uredaj"}
                    else:
                        response = await self.run_command(command)
                else:
                    response = {"Error": "Nepoznat zahtjev"}

                await ws.send(json.dumps({"id": request_id, "data": response}))
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.clients.discard(ws)

    async def serve(self, port: int):
        return await websockets.serve(self.handler, "127.0.0.1", port)
