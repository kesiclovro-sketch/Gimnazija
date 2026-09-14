"""Provjera dijagnostike protiv laznog daemona."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import doktor  # noqa: E402
from mock_daemon import MockDaemon  # noqa: E402

PORT = 14601


async def main() -> int:
    daemon = MockDaemon(hold_ms=400)
    server = await daemon.serve(PORT)
    holds = asyncio.create_task(daemon.hold_loop())
    doktor.WATCH_SECONDS = 3.0

    async def press_some():
        await asyncio.sleep(1.0)
        await daemon.press("Fader3Mute")
        await asyncio.sleep(0.8)
        await daemon.release("Fader3Mute")

    presses = asyncio.create_task(press_some())
    config = {"websocket_url": f"ws://127.0.0.1:{PORT}/api/websocket", "buttons": {
        "Chat": {}, "Mic": {}, "System": {}, "Music": {}}}
    code = await doktor.run(config)
    await presses

    holds.cancel()
    try:
        await holds
    except asyncio.CancelledError:
        pass
    server.close()
    await server.wait_closed()

    print(f"\n>>> doktor je vratio kod {code} (ocekivano 0)")
    return 0 if code == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
