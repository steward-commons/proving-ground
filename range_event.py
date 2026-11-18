#!/usr/bin/env python3
"""Range defense event: pull the latest qual and scale 40 -> 20.

Uses the most recent completed qualification on the range scoreboard.
Practice sessions are ignored. A missing or ceased qual is a zero with
an honest note, never a made-up number.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import paths
import scoring


def _records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def _is_qual(rec: dict[str, Any]) -> bool:
    if rec.get("kind") == "qual":
        return True
    course = str(rec.get("course") or "").lower()
    return course.startswith("qual")


def latest_qual(path: Path | None = None) -> dict[str, Any] | None:
    for rec in reversed(_records(path or paths.range_scoreboard())):
        if rec.get("ceased"):
            continue
        if not _is_qual(rec):
            continue
        summary = rec.get("summary") if isinstance(rec.get("summary"), dict) else {}
        if summary.get("correct") is None or summary.get("rounds") is None:
            continue
        return {
            "time": rec.get("time"),
            "timezone": rec.get("timezone") or paths.TZ_LABEL,
            "mode": rec.get("qual_mode") or rec.get("mode"),
            "course": rec.get("course"),
            "rating": rec.get("rating"),
            "correct": int(summary["correct"]),
            "rounds": int(summary["rounds"]),
            "points": summary.get("points"),
        }
    return None


def scale_qual(correct: int, rounds: int) -> float:
    return scoring.scale_out_of(correct, rounds, scoring.EVENT_MAX)


def record(path: Path | None = None) -> dict:
    qual = latest_qual(path)
    if not qual:
        return {
            "event": "range",
            "score": 0.0,
            "max": scoring.EVENT_MAX,
            "qual": None,
            "detail": "no completed qualification on the range scoreboard",
        }
    score = scale_qual(qual["correct"], qual["rounds"])
    rating = qual.get("rating") or "Unrated"
    return {
        "event": "range",
        "score": score,
        "max": scoring.EVENT_MAX,
        "qual": qual,
        "detail": (
            f"{qual['correct']}/{qual['rounds']} {rating} scaled to {score:g}/{scoring.EVENT_MAX}"
        ),
    }
