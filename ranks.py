#!/usr/bin/env python3
"""Rank patches earned from a Proving Ground total.

Cutoffs approved by the owner:
  below 60  Unqualified
  60        Marksman
  75        Sharpshooter
  90 or up  Expert
"""

from __future__ import annotations

UNQUALIFIED = "Unqualified"
MARKSMAN = "Marksman"
SHARPSHOOTER = "Sharpshooter"
EXPERT = "Expert"

MARKSMAN_MIN = 60
SHARPSHOOTER_MIN = 75
EXPERT_MIN = 90
TOTAL_MAX = 100


def rank(total: float) -> str:
    """Return the patch for a 0-100 total. Exact 60 / 75 / 90 make the named rank."""
    if total >= EXPERT_MIN:
        return EXPERT
    if total >= SHARPSHOOTER_MIN:
        return SHARPSHOOTER
    if total >= MARKSMAN_MIN:
        return MARKSMAN
    return UNQUALIFIED


def describe(total: float) -> str:
    patch = rank(total)
    return f"{total:g} / {TOTAL_MAX} — {patch}"
