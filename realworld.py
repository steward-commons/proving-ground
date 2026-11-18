#!/usr/bin/env python3
"""Real-world task. The owner picks a fresh chore each month and scores it.

The CLI stores his description, his 0-20 score, and an optional rubric.
This event never auto-scores and never invents a grade.
"""

from __future__ import annotations

import scoring


def record(
    task: str,
    score: float,
    rubric: str = "",
    creative: str = "",
    notes: str = "",
) -> dict:
    text = (task or "").strip()
    if not text:
        raise ValueError("The owner has to pick a real-world task description.")
    try:
        raw = float(score)
    except (TypeError, ValueError) as exc:
        raise ValueError("real-world score must be a number from 0 to 20") from exc
    if raw < 0 or raw > scoring.EVENT_MAX:
        raise ValueError("real-world score must be between 0 and 20")
    value = scoring.clamp_event(scoring.half_step(raw))
    return {
        "event": "realworld",
        "score": value,
        "max": scoring.EVENT_MAX,
        "task": text,
        "rubric": (rubric or "").strip(),
        "creative": (creative or "").strip(),
        "notes": (notes or "").strip(),
        "detail": f"The owner scored {value:g}/{scoring.EVENT_MAX}",
    }
