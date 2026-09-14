"""Upravljanje Spotifyem na Windowsima.

Dvije razine:

1. Windows "Global System Media Transport Controls" (GSMTC) - isti sustav koji
   koristi medijski prozorcic gore lijevo na Windowsima. Preko njega ciljamo
   tocno Spotify, bez obzira koja je aplikacija u fokusu. Zahtijeva paket
   `winsdk` (ili stariji `winrt`).
2. Ako GSMTC nije dostupan, saljemo globalne medijske tipke (Play/Pause, Next,
   Prev). Radi bez ijedne dodatne biblioteke, ali ih moze pokupiti neka druga
   medijska aplikacija ako je ona zadnja svirala.
"""

from __future__ import annotations

import asyncio
import ctypes
import logging

log = logging.getLogger("media")

VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_KEYUP = 0x0002

_control_module = None
_control_checked = False


def _import_control():
    """Ucitaj WinRT modul za medijske kontrole (ako postoji)."""
    global _control_module, _control_checked
    if _control_checked:
        return _control_module
    _control_checked = True
    for name in ("winsdk.windows.media.control", "winrt.windows.media.control"):
        try:
            _control_module = __import__(name, fromlist=["x"])
            log.debug("Koristim %s za medijske kontrole", name)
            return _control_module
        except Exception:
            continue
    log.info(
        "winsdk nije instaliran - koristim globalne medijske tipke. "
        "Za precizno ciljanje Spotifya pokreni: pip install winsdk"
    )
    return None


def _tap(vk: int) -> None:
    """Posalji pritisak medijske tipke cijelom sustavu."""
    try:
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    except AttributeError:
        log.warning("Medijske tipke rade samo na Windowsima.")
        return
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


async def _spotify_session(app_match: str):
    """Pronadi medijsku sesiju koja pripada Spotifyu."""
    mod = _import_control()
    if mod is None:
        return None
    manager_cls = mod.GlobalSystemMediaTransportControlsSessionManager
    manager = await manager_cls.request_async()
    needle = app_match.lower()
    for session in manager.get_sessions():
        try:
            aumid = (session.source_app_user_model_id or "").lower()
        except Exception:
            continue
        if needle in aumid:
            return session
    return None


async def _via_gsmtc(action: str, app_match: str) -> bool:
    """Pokusaj izvrsiti akciju preko GSMTC-a. Vrati True ako je uspjelo."""
    try:
        session = await asyncio.wait_for(_spotify_session(app_match), timeout=2.0)
    except Exception as error:
        log.debug("GSMTC nedostupan: %s", error)
        return False
    if session is None:
        log.debug("Spotify sesija nije pronadena (je li Spotify pokrenut?)")
        return False

    try:
        if action == "play_pause":
            ok = await session.try_toggle_play_pause_async()
        elif action == "pause":
            ok = await session.try_pause_async()
        elif action == "play":
            ok = await session.try_play_async()
        elif action == "next":
            ok = await session.try_skip_next_async()
        elif action == "previous":
            ok = await session.try_skip_previous_async()
        else:
            return False
        return bool(ok)
    except Exception as error:
        log.debug("GSMTC poziv nije uspio: %s", error)
        return False


async def run_action(action: str, app_match: str = "spotify", double_previous: bool = False) -> None:
    """Izvrsi medijsku akciju; GSMTC prvo, medijske tipke kao rezerva."""
    if action in ("none", ""):
        return

    repeats = 2 if (action == "previous" and double_previous) else 1

    for index in range(repeats):
        if index:
            await asyncio.sleep(0.12)
        if await _via_gsmtc(action, app_match):
            continue
        if action in ("play_pause", "pause", "play"):
            _tap(VK_MEDIA_PLAY_PAUSE)
        elif action == "next":
            _tap(VK_MEDIA_NEXT_TRACK)
        elif action == "previous":
            _tap(VK_MEDIA_PREV_TRACK)
