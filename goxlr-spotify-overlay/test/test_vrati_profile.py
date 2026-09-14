"""Provjera prijenosa profila protiv laznog daemona i lazne mape Dokumenti."""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import vrati_profile  # noqa: E402
from mock_daemon import MockDaemon  # noqa: E402

PORT = 14602
FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    print(f"  [{'OK' if condition else 'FAIL'}]   {label} {detail if not condition else ''}")
    if not condition:
        FAILURES.append(label)


async def main() -> int:
    root = Path(tempfile.mkdtemp())
    official = root / "Documents" / "GoXLR"
    (official / "Profiles").mkdir(parents=True)
    (official / "MicProfiles").mkdir(parents=True)
    (official / "Profiles" / "Moj Profil.goxlr").write_text("glavni profil")
    (official / "Profiles" / "Stream.goxlr").write_text("drugi profil")
    (official / "MicProfiles" / "Mikrofon.goxlrMicProfile").write_text("mic")

    utility = root / "AppData" / "GoXLR-Utility"
    (utility / "profiles").mkdir(parents=True)
    (utility / "mic-profiles").mkdir(parents=True)
    # Datoteka istog imena, ali drukciji sadrzaj - ne smije se prepisati.
    (utility / "profiles" / "Stream.goxlr").write_text("vec postoji, drukciji")

    daemon = MockDaemon()
    daemon.status["paths"]["profile_directory"] = str(utility / "profiles")
    daemon.status["paths"]["mic_profile_directory"] = str(utility / "mic-profiles")
    server = await daemon.serve(PORT)

    vrati_profile.official_goxlr_dir = lambda: official
    answers = iter(["1", "1"])  # odaberi prvi profil, pa prvi mic profil
    vrati_profile.ask = lambda prompt: asyncio.sleep(0, result=next(answers, ""))

    code = await vrati_profile.run(
        {"websocket_url": f"ws://127.0.0.1:{PORT}/api/websocket"}
    )

    server.close()
    await server.wait_closed()

    print("\nProvjere:")
    check("izlazni kod je 0", code == 0, str(code))
    check(
        "glavni profil je kopiran",
        (utility / "profiles" / "Moj Profil.goxlr").read_text() == "glavni profil",
    )
    check(
        "mic profil je kopiran",
        (utility / "mic-profiles" / "Mikrofon.goxlrMicProfile").read_text() == "mic",
    )
    check(
        "postojeca datoteka NIJE prepisana",
        (utility / "profiles" / "Stream.goxlr").read_text() == "vec postoji, drukciji",
    )
    check(
        "izvorne datoteke su ostale netaknute",
        (official / "Profiles" / "Moj Profil.goxlr").is_file()
        and (official / "MicProfiles" / "Mikrofon.goxlrMicProfile").is_file(),
    )
    check(
        "ucitan je glavni profil",
        ("LoadProfile", "Moj Profil") in daemon.loaded,
        str(daemon.loaded),
    )
    check(
        "ucitan je mic profil",
        ("LoadMicProfile", "Mikrofon") in daemon.loaded,
        str(daemon.loaded),
    )

    print()
    if FAILURES:
        print(f"NEUSPJESNO: {FAILURES}")
        return 1
    print("SVE PROVJERE PROSLE")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
