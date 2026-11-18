#!/usr/bin/env python3
"""Memory & continuity quiz.

Questions and answer hashes live in the sealed bank. This module loads them,
samples a monthly set, presents questions, and grades against hashes only.
It never prints the answer key.
"""

from __future__ import annotations

import random
import re
from typing import Any, Sequence

import bank
import paths
import scoring
import seal

QUESTIONS_PER_ROUND = 10


def parse_answer_list(text: str, expected: int) -> list[str]:
    lines = []
    for raw in (text or "").replace("\r\n", "\n").splitlines():
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"^(q\s*)?\d+\s*[.)\-:]\s*", "", line, flags=re.I)
        lines.append(line)
    if len(lines) != expected:
        raise ValueError(f"expected {expected} answers, got {len(lines)}")
    return lines


def sample(year: int, month: int, payload: dict[str, Any] | None = None, count: int = QUESTIONS_PER_ROUND) -> list[dict[str, Any]]:
    data = payload if payload is not None else bank.load_bank()
    items = list(data.get("questions") or [])
    if len(items) < count:
        raise RuntimeError("sealed memory bank does not have enough questions")
    rng = random.Random(f"pg-memory-v1-{year:04d}-{month:02d}")
    return rng.sample(items, count)


def present(questions: Sequence[dict[str, Any]]) -> str:
    lines = [
        "Memory & continuity quiz — 10 questions, 2 points each, 20 points total.",
        "Answer in order. Multiple-choice items take the letter. Short answers are judged after normalizing case and punctuation.",
        "No peeking at the key.",
        "",
    ]
    for i, item in enumerate(questions, 1):
        lines.append(f"{i}. {item['prompt']}")
        options = item.get("options") or []
        for opt in options:
            lines.append(f"    {opt}")
        lines.append("")
    return "\n".join(lines)


def letter_to_option(item: dict[str, Any], given: str) -> str | None:
    """Map a bare letter answer (A, b, "C)") to that option's text, if any."""
    m = re.fullmatch(r"\s*\(?([A-Za-z])\)?[.)]?\s*", given or "")
    options = item.get("options") or []
    if not m or not options:
        return None
    idx = ord(m.group(1).upper()) - ord("A")
    if not 0 <= idx < len(options):
        return None
    return re.sub(r"^\s*\(?[A-Za-z]\s*[.):\-]\s*", "", str(options[idx])).strip()


def grade(questions: Sequence[dict[str, Any]], answers: Sequence[str], key: bytes | None = None) -> dict:
    master = key if key is not None else seal.load_key()
    results = []
    correct = 0
    for i, item in enumerate(questions):
        given = answers[i] if i < len(answers) else ""
        hashes = list(item.get("hashes") or [])
        ok = seal.matches(master, item["id"], given, hashes)
        if not ok:
            mapped = letter_to_option(item, given)
            if mapped:
                ok = seal.matches(master, item["id"], mapped, hashes)
        if ok:
            correct += 1
        results.append({"id": item["id"], "ok": ok, "points": 2 if ok else 0})
    score = scoring.per_item_score(correct, len(questions), scoring.EVENT_MAX)
    return {
        "event": "memory",
        "correct": correct,
        "items": len(questions),
        "score": score,
        "max": scoring.EVENT_MAX,
        "detail": f"{correct}/{len(questions)} questions",
        "per_question": results,
    }
