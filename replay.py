#!/usr/bin/env python3
"""Replay clips for the Moot projector.

Short, kid-safe text summaries. Laughing together, not at anyone.
No question text, no answer keys, no private details.
"""

from __future__ import annotations

from typing import Any

import paths
import ranks
import scoring


def clip_for(entry: dict[str, Any]) -> str:
    ev = entry.get("events") or {}
    total = entry.get("total")
    patch = entry.get("rank") or (ranks.rank(total) if total is not None else "Unrated")
    month = entry.get("id") or "unknown"
    lines = [
        f"Proving Ground replay — {month}",
        f"Assistant posted {total:g} / {scoring.TOTAL_MAX} and earned {patch}.",
    ]
    bits = []
    for eid in scoring.EVENT_IDS:
        item = ev.get(eid) or {}
        if item.get("score") is None:
            continue
        bits.append(f"{scoring.EVENT_TITLES[eid]} {item['score']:g}")
    if bits:
        lines.append("By event: " + "; ".join(bits) + ".")
    creatives = []
    for eid in scoring.EVENT_IDS:
        text = ((ev.get(eid) or {}).get("creative") or "").strip()
        if text:
            creatives.append(text)
    if creatives:
        lines.append("Creative play of the month: " + " ".join(creatives))
    # High-level shootout outcome, no identity spoilers beyond the official record.
    shoot = ev.get("shootout") or {}
    if shoot.get("pick") == "TIE":
        lines.append("The blind shootout was too close to call, so they split the points.")
    elif shoot.get("score") == scoring.EVENT_MAX:
        lines.append("On the blind shootout, the owner went with the house answer.")
    elif shoot.get("score") == 0 and shoot.get("pick") in {"A", "B"}:
        lines.append("On the blind shootout, the stock model got the nod this time. There's always next month.")
    range_item = ev.get("range") or {}
    qual = range_item.get("qual") or {}
    if qual:
        lines.append(
            f"Range carry-over: {qual.get('correct')}/{qual.get('rounds')} "
            f"{qual.get('rating') or ''} scaled to {range_item.get('score'):g}.".replace("  ", " ")
        )
    lines.append("Laughing together, not at anyone. See you at the next Moot.")
    return "\n".join(lines) + "\n"


def write_clip(entry: dict[str, Any]):
    text = clip_for(entry)
    path = paths.replay_dir() / f"{entry.get('id') or 'run'}.txt"
    paths.safe_write(path, text)
    return path


def list_clips() -> list[str]:
    root = paths.replay_dir()
    if not root.is_dir():
        return []
    return [p.read_text(encoding="utf-8") for p in sorted(root.glob("*.txt"))]
