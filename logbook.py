#!/usr/bin/env python3
"""Append-only logbook: per-event scores, totals, ranks, creative solutions, trends.

Official runs only. Dry runs never write here. There is no edit command.
"""

from __future__ import annotations

import json
from typing import Any

import paths
import ranks
import scoring

EVENTS = scoring.EVENT_IDS


def load_entries(official_only: bool = True) -> list[dict[str, Any]]:
    path = paths.logbook_jsonl()
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
        if not isinstance(rec, dict):
            continue
        if official_only and rec.get("kind") != "official":
            continue
        out.append(rec)
    return out


def has_official(month_id: str) -> bool:
    return any(rec.get("id") == month_id and rec.get("kind") == "official" for rec in load_entries(True))


def append(entry: dict[str, Any]) -> None:
    house_mod = __import__("house")
    house_mod.require_writable()
    if entry.get("kind") != "official":
        raise ValueError("refusing to write a non-official entry to the logbook")
    paths.safe_append(paths.logbook_jsonl(), json.dumps(entry, sort_keys=True) + "\n")
    write_markdown()


def write_markdown() -> None:
    entries = load_entries(True)
    lines = [
        "# Proving Ground Logbook",
        "",
        "Auto-generated from `data/logbook.jsonl`. There is no edit command.",
        "Times are America/Chicago. Creative solutions are logged, never used to fudge a score.",
        "",
    ]
    if not entries:
        lines.append("No official runs yet.")
        paths.safe_write(paths.logbook_md(), "\n".join(lines) + "\n")
        return
    lines += [
        "## Runs",
        "",
        "| Month | Total | Rank | ARC | Memory | Real-world | Shootout | Range | Creative solutions |",
        "|---|---:|---|---:|---:|---:|---:|---:|---|",
    ]
    for rec in entries:
        ev = rec.get("events") or {}
        creative = _creative_cell(ev, rec.get("notes") or "")
        cells = [
            rec.get("id") or "",
            f"{rec.get('total'):g}" if rec.get("total") is not None else "",
            rec.get("rank") or "",
        ]
        for eid in EVENTS:
            item = ev.get(eid) or {}
            cells.append("" if item.get("score") is None else f"{item.get('score'):g}")
        cells.append(creative or "—")
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["", "## Trends", "", trends_text(entries), ""]
    paths.safe_write(paths.logbook_md(), "\n".join(lines) + "\n")


def _creative_cell(events: dict, notes: str) -> str:
    bits = []
    for eid in EVENTS:
        text = ((events.get(eid) or {}).get("creative") or "").strip()
        if text:
            bits.append(f"{scoring.EVENT_TITLES[eid]}: {text}")
    if notes.strip():
        bits.append(notes.strip())
    return "; ".join(bits).replace("|", "/")


def trends_text(entries: list[dict[str, Any]] | None = None) -> str:
    rows = entries if entries is not None else load_entries(True)
    if len(rows) < 1:
        return "No official runs to trend yet."
    lines = []
    totals = [r.get("total") for r in rows if r.get("total") is not None]
    if len(totals) >= 2:
        delta = totals[-1] - totals[-2]
        sign = "+" if delta >= 0 else ""
        lines.append(f"Latest total {totals[-1]:g} ({sign}{delta:g} vs previous {totals[-2]:g}).")
    elif totals:
        lines.append(f"Latest total {totals[-1]:g} (first official run).")
    best = max(totals) if totals else None
    if best is not None:
        lines.append(f"Personal best: {best:g} / {scoring.TOTAL_MAX} ({ranks.rank(best)}).")
    for eid in EVENTS:
        scores = []
        for r in rows:
            item = (r.get("events") or {}).get(eid) or {}
            if item.get("score") is not None:
                scores.append(item["score"])
        if not scores:
            continue
        avg = sum(scores) / len(scores)
        last = scores[-1]
        note = f"{scoring.EVENT_TITLES[eid]}: last {last:g}, average {avg:.1f}"
        if len(scores) >= 2:
            d = last - scores[-2]
            note += f", {d:+g} vs previous"
        lines.append(note)
    return "\n".join(lines) if lines else "No official runs to trend yet."


def format_entry(rec: dict[str, Any]) -> str:
    ev = rec.get("events") or {}
    lines = [
        f"Proving Ground {rec.get('id')} ({rec.get('kind')})",
        f"When: {rec.get('time')} ({rec.get('timezone') or paths.TZ_LABEL})",
        f"Total: {rec.get('total'):g} / {scoring.TOTAL_MAX} — {rec.get('rank')}",
        "",
    ]
    for eid in EVENTS:
        item = ev.get(eid) or {}
        title = scoring.EVENT_TITLES[eid]
        score = item.get("score")
        detail = item.get("detail") or ""
        creative = item.get("creative") or ""
        line = f"- {title}: {score:g}/{item.get('max', scoring.EVENT_MAX)}" if score is not None else f"- {title}: not scored"
        if detail:
            line += f" ({detail})"
        lines.append(line)
        if creative:
            lines.append(f"    Creative: {creative}")
    if rec.get("notes"):
        lines.append(f"- Notes: {rec['notes']}")
    return "\n".join(lines) + "\n"
