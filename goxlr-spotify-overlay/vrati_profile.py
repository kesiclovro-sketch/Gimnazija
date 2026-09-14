"""Prenosi profile iz sluzbene GoXLR aplikacije u GoXLR Utility i ucitava ih.

Pokretanje:  vrati_profile.bat

Sto radi:
  1. pita GoXLR Utility gdje su njegove mape za profile (preko API-ja),
  2. pronalazi mapu sluzbene aplikacije (Documents\\GoXLR, i uz OneDrive),
  3. KOPIRA .goxlr i .goxlrMicProfile datoteke k Utilityju,
  4. ponudi popis profila i ucita onaj koji odaberes.

Nista se ne brise i nista se ne premjesta - datoteke sluzbene aplikacije
ostaju tocno gdje jesu. Postojeca datoteka istog imena se ne prepisuje.
"""

from __future__ import annotations

import asyncio
import filecmp
import json
import os
import shutil
import sys
import time
from pathlib import Path

import websockets

import doktor

MAIN = ("profile_directory", "goxlr", "Profiles", "profili")
MIC = ("mic_profile_directory", "goxlrMicProfile", "MicProfiles", "mikrofonski profili")


def documents_dir() -> Path | None:
    """Prava mapa Dokumenti (radi i kad ju je OneDrive preselio)."""
    try:
        import winreg
    except ImportError:
        return None
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, "Personal")
        path = Path(os.path.expandvars(value))
        return path if path.is_dir() else None
    except OSError:
        return None


def official_goxlr_dir() -> Path | None:
    """Pronadi mapu u koju sluzbena GoXLR aplikacija sprema profile."""
    home = Path.home()
    candidates: list[Path] = []

    documents = documents_dir()
    if documents:
        candidates.append(documents / "GoXLR")

    candidates.append(home / "Documents" / "GoXLR")
    candidates.append(home / "OneDrive" / "Documents" / "GoXLR")
    candidates.extend(sorted(home.glob("OneDrive*/Documents/GoXLR")))

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.is_dir():
            return candidate
    return None


def copy_profiles(source: Path, destination: Path, extension: str) -> tuple[int, list[str]]:
    """Kopiraj profile. Vrati (koliko kopirano, popis preskocenih)."""
    destination.mkdir(parents=True, exist_ok=True)
    copied = 0
    skipped: list[str] = []

    for item in sorted(source.glob(f"*.{extension}")):
        target = destination / item.name
        if target.exists():
            if not filecmp.cmp(item, target, shallow=False):
                skipped.append(item.name)
            continue
        shutil.copy2(item, target)
        copied += 1
        print(f"      kopirano: {item.name}")

    return copied, skipped


async def ask(prompt: str) -> str:
    return (await asyncio.to_thread(input, prompt)).strip()


async def request(ws, request_id: int, data) -> object:
    await ws.send(json.dumps({"id": request_id, "data": data}))
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        message = json.loads(await ws.recv())
        if message.get("id") == request_id:
            return message.get("data")
    raise TimeoutError("GoXLR Utility ne odgovara")


async def choose_and_load(ws, status: dict, serial: str, kind: tuple) -> None:
    """Ponudi popis profila i ucitaj odabrani."""
    key, _extension, _folder, label = kind
    files_key = "profiles" if key == "profile_directory" else "mic_profiles"
    command = "LoadProfile" if key == "profile_directory" else "LoadMicProfile"

    names = sorted(status.get("files", {}).get(files_key, []))
    if not names:
        print(f"\n      Nema nijednog profila u popisu ({label}).")
        return

    print(f"\n      Dostupni {label}:")
    for index, name in enumerate(names, start=1):
        print(f"        {index}. {name}")

    answer = await ask("      Broj profila za ucitati (Enter = preskoci): ")
    if not answer:
        print("      Preskacem.")
        return
    try:
        chosen = names[int(answer) - 1]
    except (ValueError, IndexError):
        print("      Neispravan izbor, preskacem.")
        return

    print(f"      Ucitavam '{chosen}' ...")
    result = await request(ws, 500, {"Command": [serial, {command: [chosen, True]}]})
    if isinstance(result, dict) and "Error" in result:
        print(f"      Nije uspjelo: {result['Error']}")
    else:
        print("      Ucitano.")


async def run(config: dict) -> int:
    url = config["websocket_url"]
    host, port = doktor.endpoint(url)

    print("=" * 74)
    print(" Prijenos profila iz sluzbene GoXLR aplikacije u GoXLR Utility")
    print("=" * 74)

    if not await doktor.port_open(host, port):
        doktor.offline_help(host, port)
        return 1

    source_root = official_goxlr_dir()
    if source_root is None:
        print(
            "\n[!] Nisam nasao mapu sluzbene aplikacije (obicno"
            " Documents\\GoXLR).\n"
            "    Upisi putanju rucno, npr. C:\\Users\\ime\\Documents\\GoXLR"
        )
        answer = await ask("    Putanja (Enter = odustani): ")
        if not answer:
            return 1
        source_root = Path(answer)
        if not source_root.is_dir():
            print("    Ta mapa ne postoji.")
            return 1

    print(f"\n[1/3] Profili sluzbene aplikacije: {source_root}")

    async with websockets.connect(url, max_size=None) as ws:
        response = await request(ws, 1, "GetStatus")
        if not isinstance(response, dict) or "Status" not in response:
            print("      GoXLR Utility nije vratio status.")
            return 1
        status = response["Status"]

        paths = status.get("paths", {})
        mixers = status.get("mixers", {})
        if not mixers:
            print("\n      GoXLR Utility ne vidi uredaj - je li sluzbena app ugasena?")
            return 1
        serial = next(iter(mixers))

        print("\n[2/3] Kopiram profile ...")
        total = 0
        conflicts: list[str] = []
        for key, extension, folder, label in (MAIN, MIC):
            destination = paths.get(key)
            if not destination:
                print(f"      Utility nije javio mapu za {label}, preskacem.")
                continue
            source = source_root / folder
            if not source.is_dir():
                print(f"      Nema mape {source} - preskacem {label}.")
                continue
            print(f"      {label}: {source}  ->  {destination}")
            copied, skipped = copy_profiles(source, Path(destination), extension)
            total += copied
            conflicts.extend(skipped)
            if not copied:
                print("      (nista novo za kopirati)")

        if conflicts:
            print(
                "\n      Ove datoteke vec postoje kod Utilityja s drukcijim"
                " sadrzajem i NISU dirane:"
            )
            for name in conflicts:
                print(f"        {name}")
            print("      Ako zelis bas te, preimenuj ih ili kopiraj rucno.")

        print(f"\n      Ukupno kopirano: {total}")

        # Daemonu treba trenutak da primijeti nove datoteke.
        if total:
            for _ in range(10):
                await asyncio.sleep(0.5)
                response = await request(ws, 2, "GetStatus")
                if isinstance(response, dict) and "Status" in response:
                    status = response["Status"]
                    if len(status.get("files", {}).get("profiles", [])) >= total:
                        break

        print("\n[3/3] Ucitavanje profila")
        await choose_and_load(ws, status, serial, MAIN)
        await choose_and_load(ws, status, serial, MIC)

    print(
        "\n"
        + "-" * 74
        + "\n  Gotovo. Profili sluzbene aplikacije ostali su netaknuti tamo gdje su"
        " bili.\n" + "-" * 74
    )
    return 0


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from goxlr_overlay import CONFIG_PATH, load_config

    config = load_config(CONFIG_PATH)
    try:
        return asyncio.run(run(config))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
