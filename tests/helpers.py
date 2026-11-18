#!/usr/bin/env python3
"""Isolation helpers: temp data, temp sealed bank, temp medical flags, no network."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Fixture questions are dummy, not the live bank.
FIXTURE_QUESTIONS = [
    {
        "id": f"fx{i:02d}",
        "prompt": prompt,
        "options": options,
        "answers": answers,
    }
    for i, (prompt, options, answers) in enumerate(
        [
            ("What color is the test balloon?", ["A. red", "B. teal", "C. gold"], ["b", "teal"]),
            ("Name the fixture river.", [], ["silverrun", "the silverrun", "silverrun river"]),
            ("How many fixture lanterns hang in the hall?", ["A. 3", "B. 7", "C. 12"], ["7", "b"]),
            ("What is the test mascot called?", [], ["maple the fox", "maple"]),
            ("Which day is Fixture Day?", ["A. Monday", "B. Thursday", "C. Sunday"], ["thursday", "b"]),
            ("Spell the fixture passphrase word.", [], ["lumen"]),
            ("The spare key is kept in the what?", ["A. cookie jar", "B. piano bench", "C. boot"], ["piano bench", "b", "the piano bench"]),
            ("Who brews the fixture tea?", [], ["aunt nora", "nora"]),
            ("How tall is the test tower in stories?", ["A. 2", "B. 4", "C. 9"], ["4", "b"]),
            ("The garden statue is a what?", [], ["heron", "a heron"]),
            ("What instrument does the fixture band lead with?", ["A. drum", "B. flute", "C. harp"], ["flute", "b"]),
            ("Name the fixture street.", [], ["cobble walk", "cobblewalk", "cobble walk street"]),
        ],
        start=1,
    )
]


class Isolate:
    """Temp proving-ground house: data, sealed bank, medical flags, range board."""

    def __init__(self, *, now: str | None = "2026-11-20T10:00:00-06:00") -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pg-test-"))
        self.data = self.tmp / "data"
        self.sealed = self.tmp / "sealed"
        self.med = self.tmp / "medical"
        self.range_board = self.tmp / "scoreboard.jsonl"
        self.now = now
        self._old: dict[str, str | None] = {}
        self.key: bytes = b""

    def __enter__(self) -> "Isolate":
        self.data.mkdir(parents=True)
        self.sealed.mkdir(parents=True)
        (self.med / "flags").mkdir(parents=True)
        self._install_env()
        self._reset_modules()
        self._build_bank()
        self.write_qual(39, 40, rating="Expert")
        return self

    def __exit__(self, *exc) -> None:
        for key, value in self._old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._reset_modules()
        # Leave the tmp dir for debugging on failure; tests do not need to wipe it.

    def _install_env(self) -> None:
        env = {
            "PROVING_DATA": str(self.data),
            "PROVING_SEALED": str(self.sealed),
            "PROVING_RANGE_SCOREBOARD": str(self.range_board),
            "PROVING_CONSULTANT": "off",
            "PROVING_CONSULTANT_MOCK": "A canned stock-model answer about public garden paths.",
            "PROVING_MEDICAL_GUARD": str(Path(__file__).resolve().parent / "fixtures" / "medical_guard.py"),
            "MEDICAL_DATA": str(self.med),
            "PROVING_ALLOW_PEEK": "",
        }
        if self.now:
            env["PROVING_NOW"] = self.now
        for key, value in env.items():
            self._old[key] = os.environ.get(key)
            if value == "":
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _reset_modules(self) -> None:
        import house
        import paths

        house.clear_cache()
        # Paths are functions; no cache besides house.

    def _build_bank(self) -> None:
        import bank
        import seal

        self.key = seal.load_or_create_key(self.sealed)
        payload = bank.build_bank(FIXTURE_QUESTIONS, self.key)
        bank.write_bank(payload, self.key, self.sealed)

    def write_qual(self, correct: int, rounds: int = 40, rating: str = "Expert", *, ceased: bool = False) -> None:
        rec = {
            "kind": "qual",
            "course": "qual-v1",
            "qual_mode": "solo",
            "ceased": ceased,
            "rating": rating,
            "time": "2026-11-17T15:03:27-06:00",
            "timezone": "America/Chicago",
            "summary": {"correct": correct, "rounds": rounds, "points": correct},
        }
        self.range_board.write_text(json.dumps(rec) + "\n", encoding="utf-8")

    def write_practice_only(self) -> None:
        rec = {
            "kind": "practice",
            "course": "practice",
            "ceased": False,
            "time": "2026-11-17T15:03:14-06:00",
            "summary": {"correct": 16, "rounds": 16, "points": 17},
        }
        self.range_board.write_text(json.dumps(rec) + "\n", encoding="utf-8")

    def set_pen(self, on: bool, reason: str = "test") -> None:
        path = self.med / "flags" / "state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "pen": {"on": on, "reason": reason, "set_at": "2026-11-18T00:00:00-06:00", "set_by": "test", "alert_queued": False},
            "tourniquets": {},
        }
        path.write_text(json.dumps(state), encoding="utf-8")

    def set_tourniquet(self, part: str, reason: str = "test") -> None:
        path = self.med / "flags" / "state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "pen": {"on": False, "reason": None, "set_at": None, "set_by": None, "alert_queued": False},
            "tourniquets": {part: {"on": True, "reason": reason}},
        }
        path.write_text(json.dumps(state), encoding="utf-8")


def run_cli(argv: list[str]) -> tuple[int, str, str]:
    import proving

    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        try:
            code = proving.main(argv)
        except SystemExit as exc:
            code = int(exc.code or 0)
    return code, stdout.getvalue(), stderr.getvalue()
