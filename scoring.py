#!/usr/bin/env python3
"""Event scoring helpers. Pure functions, no I/O, no peeking, no fudging."""

from __future__ import annotations

from typing import Mapping

EVENT_MAX = 20
EVENT_IDS = ("arc", "memory", "realworld", "shootout", "range")
EVENT_TITLES = {
    "arc": "Mini ARC puzzles",
    "memory": "Memory & continuity",
    "realworld": "Real-world task",
    "shootout": "Blind shootout",
    "range": "Range defense",
}
TOTAL_MAX = 100


def clamp_event(score: float) -> float:
    if score < 0:
        return 0.0
    if score > EVENT_MAX:
        return EVENT_MAX
    return float(score)


def half_step(value: float) -> float:
    """Round to the nearest 0.5 (halves go away from zero, not banker's)."""
    if value >= 0:
        return round(value * 2 + 0.0000001) / 2
    return round(value * 2 - 0.0000001) / 2


def scale_out_of(correct: float, total: float, points: float = EVENT_MAX) -> float:
    """Scale a raw score onto an event. Missing work is a zero, never a made-up number."""
    if total <= 0:
        return 0.0
    return clamp_event(half_step(correct * points / total))


def total_of(events: Mapping[str, float]) -> float:
    return half_step(sum(clamp_event(events.get(eid, 0) or 0) for eid in EVENT_IDS))


def per_item_score(correct: int, items: int, points: float = EVENT_MAX) -> float:
    return scale_out_of(correct, items, points)
