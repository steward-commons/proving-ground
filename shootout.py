#!/usr/bin/env python3
"""Blind shootout against a stock model via Consultant.

the assistant's answer and the stock answer are shuffled as A/B. The owner grades the
unlabeled pair. The mapping is sealed until reveal. Public prompts only.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import house
import paths
import scoring
import seal

DEFAULT_MODEL = "gemini-3.1-flash-lite"


def _run_paths(run_id: str) -> dict[str, Path]:
    root = paths.run_dir(run_id)
    return {
        "root": root,
        "packet": root / "shootout-blind.md",
        "seal": root / "shootout-seal.json",
        "grade": root / "shootout-grade.json",
    }


def prepare(
    run_id: str,
    prompt: str,
    assistant_answer: str,
    *,
    stock_answer: str | None = None,
    model: str = DEFAULT_MODEL,
    seed: str | None = None,
) -> dict[str, Any]:
    text = (prompt or "").strip()
    answer = (assistant_answer or "").strip()
    if not text:
        raise ValueError("shootout needs a public prompt")
    if not answer:
        raise ValueError("shootout needs the assistant's answer before the shuffle")
    hits = house.privacy_hits(text) or house.privacy_hits(answer)
    if hits:
        raise RuntimeError(
            "Shootout text looks private or sensitive "
            f"({', '.join(hits)}). Public, non-private prompts only."
        )
    defense = house.defense_hits(text)
    if defense:
        raise RuntimeError(
            "Shootout prompt tripped the house defense scanner "
            f"({', '.join(defense)}). Refusing to send it."
        )
    stock = (stock_answer if stock_answer is not None else house.ask_consultant(text, model=model)).strip()
    if not stock:
        raise RuntimeError("The stock model returned an empty answer.")
    rng = random.Random(seed or f"pg-shootout-{run_id}")
    order = ["assistant", "stock"]
    rng.shuffle(order)
    labels = {"A": order[0], "B": order[1]}
    text_by_who = {"assistant": answer, "stock": stock}
    packet = _render_packet(prompt=text, a=text_by_who[labels["A"]], b=text_by_who[labels["B"]])
    mapping = {"labels": labels, "model": model, "prompt": text}
    # Seal the mapping with the bank key if present, else a run-local key kept next to it
    # in the same sealed blob so a casual peek at the packet does not reveal who is who.
    try:
        key = seal.load_key()
    except (FileNotFoundError, ValueError):
        key = seal.load_or_create_key()
    blob = seal.seal_json(key, seal.PURPOSE_MAP, mapping).decode("ascii")
    return {
        "packet": packet,
        "sealed_mapping": blob,
        "labels": labels,  # only returned to callers that already may peek (tests / after reveal)
        "model": model,
        "prompt": text,
        "stock_answer": stock,
        "assistant_answer": answer,
    }


def _render_packet(prompt: str, a: str, b: str) -> str:
    return (
        "Blind shootout — do not peek at the key.\n"
        "Two answers, labeled A and B. The owner grades without knowing who wrote which.\n"
        "Score with: proving.py shootout grade --pick A|B|tie   or   --score 0-20\n"
        "Reveal only after the grade is saved.\n\n"
        f"Prompt:\n{prompt}\n\n"
        f"Answer A:\n{a}\n\n"
        f"Answer B:\n{b}\n"
    )


def decode_mapping(sealed_blob: str, key: bytes | None = None) -> dict[str, Any]:
    master = key if key is not None else seal.load_key()
    return seal.unseal_json(master, seal.PURPOSE_MAP, sealed_blob.encode("ascii") if isinstance(sealed_blob, str) else sealed_blob)


def grade(
    mapping: dict[str, Any],
    *,
    pick: str | None = None,
    score: float | None = None,
    notes: str = "",
    creative: str = "",
) -> dict:
    labels = mapping.get("labels") or {}
    assistant_letter = next((letter for letter, who in labels.items() if who == "assistant"), None)
    stock_letter = next((letter for letter, who in labels.items() if who == "stock"), None)
    if score is not None and pick:
        raise ValueError("give either --pick or --score, not both")
    if score is not None:
        raw = float(score)
        if raw < 0 or raw > scoring.EVENT_MAX:
            raise ValueError("shootout score must be between 0 and 20")
        value = scoring.clamp_event(scoring.half_step(raw))
        source = "numeric"
    elif pick:
        choice = pick.strip().upper()
        if choice == "TIE":
            value = scoring.half_step(scoring.EVENT_MAX / 2)
        elif choice in {"A", "B"}:
            value = float(scoring.EVENT_MAX) if labels.get(choice) == "assistant" else 0.0
        else:
            raise ValueError("pick must be A, B, or tie")
        source = f"pick:{choice}"
    else:
        raise ValueError("The owner grades the shootout with --pick A|B|tie or --score 0-20")
    return {
        "event": "shootout",
        "score": value,
        "max": scoring.EVENT_MAX,
        "pick": (pick or "").strip().upper() or None,
        "source": source,
        "assistant_was": assistant_letter,
        "stock_was": stock_letter,
        "notes": (notes or "").strip(),
        "creative": (creative or "").strip(),
        "detail": _detail(value, source, assistant_letter),
        "model": mapping.get("model") or DEFAULT_MODEL,
    }


def _detail(value: float, source: str, assistant_letter: str | None) -> str:
    if source.startswith("pick:"):
        choice = source.split(":", 1)[1]
        if choice == "TIE":
            return f"The owner called a tie; {value:g}/{scoring.EVENT_MAX}"
        return f"The owner picked {choice}; assistant was {assistant_letter}; {value:g}/{scoring.EVENT_MAX}"
    return f"The owner scored {value:g}/{scoring.EVENT_MAX} (assistant was {assistant_letter})"


def reveal_text(mapping: dict[str, Any], result: dict | None = None) -> str:
    labels = mapping.get("labels") or {}
    lines = ["Shootout reveal (after the grade, not before):"]
    for letter in ("A", "B"):
        who = "Assistant" if labels.get(letter) == "assistant" else "stock model (Consultant)"
        lines.append(f"  {letter} was {who}")
    if result is not None:
        lines.append(f"  Score: {result.get('score')} / {scoring.EVENT_MAX}")
        if result.get("pick"):
            lines.append(f"  the owner picked: {result['pick']}")
    return "\n".join(lines) + "\n"
