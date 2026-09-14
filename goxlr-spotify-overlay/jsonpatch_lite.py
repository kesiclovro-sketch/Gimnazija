"""Minimalna RFC 6902 (JSON Patch) implementacija.

GoXLR Utility salje preko websocketa JSON-Patch poruke s inkrementalnim
promjenama statusa. Koristimo vlastitu implementaciju umjesto vanjske
biblioteke kako bi program imao sto manje ovisnosti.
"""

from __future__ import annotations

import copy
from typing import Any


class PatchError(Exception):
    pass


def _unescape(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def _split(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise PatchError(f"Neispravan JSON pointer: {pointer!r}")
    return [_unescape(part) for part in pointer[1:].split("/")]


def _resolve_parent(doc: Any, tokens: list[str]) -> tuple[Any, str]:
    """Vrati (roditelj, zadnji_token) za zadani pointer."""
    node = doc
    for token in tokens[:-1]:
        if isinstance(node, list):
            node = node[int(token)]
        elif isinstance(node, dict):
            if token not in node:
                raise PatchError(f"Putanja ne postoji: {token!r}")
            node = node[token]
        else:
            raise PatchError(f"Ne mogu ici dublje od {token!r}")
    return node, tokens[-1]


def get_value(doc: Any, pointer: str) -> Any:
    node = doc
    for token in _split(pointer):
        if isinstance(node, list):
            node = node[int(token)]
        else:
            node = node[token]
    return node


def _apply_one(doc: Any, op: dict) -> Any:
    kind = op.get("op")
    path = op.get("path", "")
    tokens = _split(path)

    if kind in ("add", "replace"):
        if not tokens:
            return copy.deepcopy(op["value"])
        parent, last = _resolve_parent(doc, tokens)
        value = copy.deepcopy(op["value"])
        if isinstance(parent, list):
            if last == "-":
                parent.append(value)
            elif kind == "add":
                parent.insert(int(last), value)
            else:
                parent[int(last)] = value
        else:
            parent[last] = value
        return doc

    if kind == "remove":
        if not tokens:
            return None
        parent, last = _resolve_parent(doc, tokens)
        if isinstance(parent, list):
            del parent[int(last)]
        else:
            parent.pop(last, None)
        return doc

    if kind in ("move", "copy"):
        value = copy.deepcopy(get_value(doc, op["from"]))
        if kind == "move":
            doc = _apply_one(doc, {"op": "remove", "path": op["from"]})
        return _apply_one(doc, {"op": "add", "path": path, "value": value})

    if kind == "test":
        if get_value(doc, path) != op["value"]:
            raise PatchError(f"Test nije prosao za {path!r}")
        return doc

    raise PatchError(f"Nepoznata operacija: {kind!r}")


def apply_patch(doc: Any, patch: list[dict]) -> Any:
    """Primijeni listu JSON-Patch operacija na `doc` (mijenja ga na mjestu)."""
    for op in patch:
        doc = _apply_one(doc, op)
    return doc
