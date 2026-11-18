#!/usr/bin/env python3
"""Read-only safe-mode and tourniquet flag check.

House tools import this module by file path (never via sys.path) so their
own `paths` modules are not shadowed. This file uses only the stdlib.
A missing or unreadable flag means the house is not frozen.

The morphine pen freezes ordinary writes and runs for every hooked part.
A tourniquet freezes only the named part. The medical chart, status, and
`medic.py pen --off` stay available either way. This module never sends
mail, never pauses a server-side routine, and never walks into private/.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

PEN_PARTS = (
    "defense",
    "range",
    "consultant",
    "pet",
    "routines",
    "pride",
    "backups",
    "drive",
    "failsafe",
)
# The medical kit, the chart, and the wake path are never frozen.


def data_root() -> Path:
    raw = os.environ.get("MEDICAL_DATA", "").strip()
    if raw:
        return Path(raw).resolve()
    return Path(__file__).resolve().parent


def flags_dir() -> Path:
    return data_root() / "flags"


def state_path() -> Path:
    return flags_dir() / "state.json"


def alert_path() -> Path:
    return flags_dir() / "routine-pause-request.txt"


def empty_state() -> dict[str, Any]:
    return {
        "pen": {
            "on": False,
            "set_at": None,
            "set_by": None,
            "reason": None,
            "alert_queued": False,
        },
        "tourniquets": {},
    }


def load_state() -> dict[str, Any]:
    path = state_path()
    base = empty_state()
    if not path.is_file():
        return base
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return base
    if not isinstance(data, dict):
        return base
    pen = data.get("pen") if isinstance(data.get("pen"), dict) else {}
    base["pen"].update({k: pen.get(k, base["pen"][k]) for k in base["pen"]})
    base["pen"]["on"] = bool(base["pen"].get("on"))
    incoming = data.get("tourniquets") if isinstance(data.get("tourniquets"), dict) else {}
    cuffs: dict[str, Any] = {}
    for name, rec in incoming.items():
        if isinstance(rec, dict) and rec.get("on"):
            cuffs[str(name).strip().lower()] = rec
    base["tourniquets"] = cuffs
    return base


def pen_is_on() -> bool:
    return bool(load_state()["pen"].get("on"))


def isolated_parts() -> tuple[str, ...]:
    return tuple(sorted(load_state()["tourniquets"]))


def blocked(part: str) -> str | None:
    """Human reason this part must not write or run, or None if it may."""
    name = (part or "").strip().lower()
    if name == "medical":
        return None
    state = load_state()
    if state["pen"].get("on"):
        reason = state["pen"].get("reason") or "no reason recorded"
        return (
            f"Morphine pen (safe mode) is on ({reason}). "
            f"Ordinary writes and runs for {name or 'this part'} are frozen. "
            "The chart, status, and medic.py pen --off stay available. "
            "Server-side routines were not paused."
        )
    rec = state["tourniquets"].get(name)
    if rec:
        reason = rec.get("reason") or "no reason recorded"
        return (
            f"Tourniquet is on for {name} ({reason}). "
            "That part's writes and runs are isolated. "
            "The rest of the house stays live. Release with: "
            f"medic.py tourniquet --off {name}"
        )
    return None
