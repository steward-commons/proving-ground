#!/usr/bin/env python3
"""In-progress run files. Official and dry runs live under data/runs/."""

from __future__ import annotations

import json
from typing import Any

import house
import paths
import scoring

RUN_FILE = "run.json"


def load(run_id: str) -> dict[str, Any]:
    path = paths.run_dir(run_id) / RUN_FILE
    if not path.is_file():
        raise FileNotFoundError(f"no run named {run_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"run {run_id} is malformed")
    return data


def exists(run_id: str) -> bool:
    return (paths.run_dir(run_id) / RUN_FILE).is_file()


def latest_in_progress(kind: str | None = None) -> dict[str, Any] | None:
    root = paths.runs_dir()
    if not root.is_dir():
        return None
    found: list[dict[str, Any]] = []
    for folder in root.iterdir():
        path = folder / RUN_FILE
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if data.get("status") != "in_progress":
            continue
        if kind and data.get("kind") != kind:
            continue
        found.append(data)
    if not found:
        return None
    found.sort(key=lambda r: r.get("started") or "")
    return found[-1]


def save(run: dict[str, Any]) -> None:
    house.require_writable()
    run_id = run["id"]
    path = paths.run_dir(run_id) / RUN_FILE
    paths.safe_write(path, json.dumps(run, indent=2, sort_keys=True) + "\n")


def create(run_id: str, kind: str, *, notes: str = "") -> dict[str, Any]:
    if exists(run_id) and load(run_id).get("status") == "in_progress":
        raise RuntimeError(f"run {run_id} is already in progress")
    if exists(run_id) and load(run_id).get("status") == "complete" and kind == "official":
        raise RuntimeError(f"official run {run_id} is already complete")
    house.require_writable()
    run = {
        "id": run_id,
        "kind": kind,
        "status": "in_progress",
        "started": paths.now_iso(),
        "timezone": paths.TZ_LABEL,
        "events": {},
        "total": None,
        "rank": None,
        "notes": notes,
        "replay": None,
        "finished": None,
    }
    save(run)
    return run


def put_event(run: dict[str, Any], result: dict[str, Any], creative: str = "") -> dict[str, Any]:
    event = result.get("event")
    if event not in scoring.EVENT_IDS:
        raise ValueError(f"unknown event {event}")
    payload = dict(result)
    if creative and not payload.get("creative"):
        payload["creative"] = creative
    # Never keep ARC solutions or memory hashes on the run file after grading.
    payload.pop("per_task", None)
    payload.pop("per_question", None)
    payload.pop("stock_answer", None)
    payload.pop("assistant_answer", None)
    payload.pop("labels", None)
    run.setdefault("events", {})[event] = payload
    save(run)
    return run


def missing_events(run: dict[str, Any]) -> list[str]:
    ev = run.get("events") or {}
    return [eid for eid in scoring.EVENT_IDS if eid not in ev or ev[eid].get("score") is None]
