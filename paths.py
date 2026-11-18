#!/usr/bin/env python3
"""Paths, time, and the write gate for the Proving Ground.

Env overrides (tests and dry-runs use these):
  PROVING_DATA              run data, logbook, replay clips (default: ./data)
  PROVING_SEALED            sealed question bank (default: ./sealed)
  PROVING_RANGE_SCOREBOARD  path to range logs/scoreboard.jsonl
  PROVING_CONSULTANT             path to consultant.py, or "off"
  PROVING_CONSULTANT_MOCK        if set, use this text as the stock-model answer
  PROVING_MEDICAL_GUARD     path to medical/guard.py
  PROVING_DEFENSE_SCAN      path to defense/scan_text.py
  PROVING_PRIVACY           path to gemini/privacy.py
  PROVING_NOW               ISO timestamp to pretend it is (tests only)
  PROVING_ALLOW_PEEK        "1" lets tests inspect solutions; the live CLI refuses
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Chicago")
TZ_LABEL = "America/Chicago"
CODE_ROOT = Path(__file__).resolve().parent
HOUSE = CODE_ROOT.parent


def data_root() -> Path:
    raw = os.environ.get("PROVING_DATA")
    return Path(raw).resolve() if raw else (CODE_ROOT / "data").resolve()


def sealed_root() -> Path:
    raw = os.environ.get("PROVING_SEALED")
    return Path(raw).resolve() if raw else (CODE_ROOT / "sealed").resolve()


def range_scoreboard() -> Path:
    raw = os.environ.get("PROVING_RANGE_SCOREBOARD")
    if raw:
        return Path(raw).resolve()
    return (HOUSE / "range" / "logs" / "scoreboard.jsonl").resolve()


def consultant_script() -> Path | None:
    raw = os.environ.get("PROVING_CONSULTANT")
    if raw and raw.lower() == "off":
        return None
    path = Path(raw) if raw else (HOUSE / "gemini" / "consultant.py")
    return path if path.is_file() else None


def peek_allowed() -> bool:
    return os.environ.get("PROVING_ALLOW_PEEK", "").strip() == "1"


def now() -> datetime:
    raw = os.environ.get("PROVING_NOW")
    if raw:
        value = datetime.fromisoformat(raw)
        return value if value.tzinfo else value.replace(tzinfo=TZ)
    return datetime.now(TZ)


def now_iso() -> str:
    return now().isoformat(timespec="seconds")


def now_human() -> str:
    stamp = now()
    try:
        text = stamp.strftime("%Y-%m-%d %-I:%M %p")
    except ValueError:
        text = stamp.strftime("%Y-%m-%d %I:%M %p").lstrip("0").replace(" 0", " ")
    return f"{text} ({TZ_LABEL})"


def month_id(when: datetime | None = None) -> str:
    stamp = when or now()
    return f"{stamp.year:04d}-{stamp.month:02d}"


def logbook_jsonl() -> Path:
    return data_root() / "logbook.jsonl"


def logbook_md() -> Path:
    return data_root() / "logbook.md"


def runs_dir() -> Path:
    return data_root() / "runs"


def run_dir(run_id: str) -> Path:
    return runs_dir() / run_id


def replay_dir() -> Path:
    return data_root() / "replay"


class WriteOutsideData(RuntimeError):
    """A write tried to leave the proving-ground data folder."""


def _inside(path: Path, root: Path) -> Path:
    target = path.resolve()
    base = root.resolve()
    if target != base and base not in target.parents:
        raise WriteOutsideData(f"refusing to write outside {base}: {target}")
    return target


def safe_write(path: Path, text: str) -> Path:
    """Atomic write, only inside data_root()."""
    target = _inside(path, data_root())
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, target)
    return target


def safe_append(path: Path, text: str) -> Path:
    target = _inside(path, data_root())
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(text)
    return target


def sealed_write(path: Path, data: bytes) -> Path:
    """Atomic write, only inside sealed_root(). Used to build the bank, not during a run."""
    target = _inside(path, sealed_root())
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, target)
    return target
