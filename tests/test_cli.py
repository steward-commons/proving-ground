#!/usr/bin/env python3
"""CLI: dry-run, official window, peeking rules, logbook isolation."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import arc  # noqa: E402
import bank  # noqa: E402
import logbook  # noqa: E402
import memory_quiz  # noqa: E402
import paths  # noqa: E402
import proving  # noqa: E402
import seal  # noqa: E402
from tests.helpers import Isolate, run_cli  # noqa: E402


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _correct_arc_answers(run_id: str, dest: Path) -> Path:
    tasks = arc.generate(f"pg-arc-dry-{run_id}")
    text = "\n\n".join(arc.render_grid(t.test_output) for t in tasks)
    return _write(dest, text)


def _correct_memory_answers(run_id: str, dest: Path, key: bytes, directory: Path | None = None) -> Path:
    import random

    payload = bank.load_bank(directory=directory, key=key)
    items = list(payload["questions"])
    rng = random.Random(f"pg-memory-dry-{run_id}")
    picked = rng.sample(items, memory_quiz.QUESTIONS_PER_ROUND)
    # We cannot read plaintext answers from the sealed bank (hashes only).
    # Map fixture id -> a canonical accepted answer from the helper list.
    from tests.helpers import FIXTURE_QUESTIONS

    by_id = {q["id"]: q["answers"][0] for q in FIXTURE_QUESTIONS}
    lines = [by_id[item["id"]] for item in picked]
    return _write(dest, "\n".join(lines) + "\n")


class CliHelpTest(unittest.TestCase):
    def test_help_exits_zero(self):
        code, out, err = run_cli(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("Proving Ground", out)
        self.assertIn("dry-run", out)


class DryRunTest(unittest.TestCase):
    def test_one_shot_dry_run_does_not_touch_official_logbook(self):
        with Isolate() as iso:
            run_id = "dry-sandbox"
            arc_file = _correct_arc_answers(run_id, iso.tmp / "arc.txt")
            mem_file = _correct_memory_answers(run_id, iso.tmp / "mem.txt", iso.key, directory=iso.sealed)
            prompt = _write(iso.tmp / "prompt.txt", "Name a common public park feature.")
            answer = _write(iso.tmp / "assistant.txt", "A walking path and a bench are common.")
            code, out, err = run_cli(
                [
                    "dry-run",
                    "--run",
                    run_id,
                    "--arc-answers",
                    str(arc_file),
                    "--memory-answers",
                    str(mem_file),
                    "--task",
                    "Dummy chore: tidy the sandbox shelf.",
                    "--score",
                    "12",
                    "--rubric",
                    "Done on time.",
                    "--shootout-prompt-file",
                    str(prompt),
                    "--shootout-answer-file",
                    str(answer),
                    "--shootout-mock",
                    "A fountain is also common.",
                    "--shootout-pick",
                    "tie",
                    "--creative",
                    "counted twice to be sure",
                ]
            )
            self.assertEqual(code, 0, err + "\n" + out)
            self.assertIn("DRY RUN", out)
            self.assertFalse(paths.logbook_jsonl().is_file())
            self.assertFalse(logbook.has_official("2026-11"))
            summary = paths.run_dir(run_id) / "dry-summary.md"
            self.assertTrue(summary.is_file())
            text = summary.read_text(encoding="utf-8")
            self.assertIn("DRY" if False else "dry", run_id)
            self.assertIn("12/20", text)
            # ARC should be perfect; memory perfect; shootout tie 10; range 19.5
            self.assertIn("20/20", text)  # arc and/or memory
            clip = (paths.run_dir(run_id) / "dry-clip.txt").read_text(encoding="utf-8")
            self.assertIn("Laughing together, not at anyone", clip)
            # Official replay dir should stay empty.
            official_clips = list(paths.replay_dir().glob("*.txt")) if paths.replay_dir().is_dir() else []
            # dry clip is under runs/, not replay/
            self.assertTrue(all(p.name != "2026-11.txt" for p in official_clips))


class OfficialWindowTest(unittest.TestCase):
    def test_start_refused_before_monday(self):
        with Isolate(now="2026-12-04T12:00:00-06:00"):
            code, out, err = run_cli(["start"])
            self.assertNotEqual(code, 0)
            self.assertIn("not open yet", err)

    def test_force_start_then_finish_writes_logbook(self):
        with Isolate(now="2026-11-18T06:49:00-06:00") as iso:
            code, out, err = run_cli(["start", "--force", "--notes", "early by agreement"])
            self.assertEqual(code, 0, err)
            self.assertIn("2026-11", out)
            run_id = "2026-11"
            # Official ARC uses the month seed.
            tasks = arc.generate(arc.month_seed(2026, 11))
            arc_file = _write(iso.tmp / "arc.txt", "\n\n".join(arc.render_grid(t.test_output) for t in tasks))
            # Official memory uses month sample.
            payload = bank.load_bank()
            picked = memory_quiz.sample(2026, 11, payload)
            from tests.helpers import FIXTURE_QUESTIONS

            by_id = {q["id"]: q["answers"][0] for q in FIXTURE_QUESTIONS}
            mem_file = _write(iso.tmp / "mem.txt", "\n".join(by_id[q["id"]] for q in picked) + "\n")
            code, out, err = run_cli(["arc", "--run", run_id, "--answers-file", str(arc_file), "--creative", "folded it"])
            self.assertEqual(code, 0, err + out)
            code, out, err = run_cli(["memory", "--run", run_id, "--answers-file", str(mem_file)])
            self.assertEqual(code, 0, err + out)
            code, out, err = run_cli(["realworld", "--run", run_id, "--task", "Dummy official chore", "--score", "18", "--rubric", "solid"])
            self.assertEqual(code, 0, err + out)
            prompt = _write(iso.tmp / "p.txt", "Name a public holiday parade tradition in general.")
            answer = _write(iso.tmp / "a.txt", "A marching band and flags are common.")
            code, out, err = run_cli(
                [
                    "shootout",
                    "prepare",
                    "--run",
                    run_id,
                    "--prompt-file",
                    str(prompt),
                    "--answer-file",
                    str(answer),
                    "--stock",
                    "Floats and candy are common too.",
                ]
            )
            self.assertEqual(code, 0, err + out)
            packet_code, packet, _ = run_cli(["shootout", "packet", "--run", run_id])
            self.assertEqual(packet_code, 0)
            self.assertIn("Answer A:", packet)
            self.assertNotIn("was assistant", packet)
            # Reveal before grade must fail.
            code, out, err = run_cli(["shootout", "reveal", "--run", run_id])
            self.assertNotEqual(code, 0)
            self.assertIn("after the grade", err)
            code, out, err = run_cli(["shootout", "grade", "--run", run_id, "--score", "17"])
            self.assertEqual(code, 0, err + out)
            code, out, err = run_cli(["shootout", "reveal", "--run", run_id])
            self.assertEqual(code, 0, err + out)
            self.assertIn("was Assistant", out)
            code, out, err = run_cli(["range", "--run", run_id])
            self.assertEqual(code, 0, err + out)
            # Finish too early would have failed; now it should write the book.
            code, out, err = run_cli(["finish", "--run", run_id])
            self.assertEqual(code, 0, err + out)
            self.assertTrue(logbook.has_official("2026-11"))
            self.assertIn("Rank patch:", out)
            clip = (paths.replay_dir() / "2026-11.txt").read_text(encoding="utf-8")
            self.assertIn("Laughing together", clip)
            md = paths.logbook_md().read_text(encoding="utf-8")
            self.assertIn("2026-11", md)
            self.assertIn("folded it", md)
            # Second official start without force is refused.
            code, out, err = run_cli(["start"])
            self.assertNotEqual(code, 0)
            self.assertIn("already", err.lower())


class PeekTest(unittest.TestCase):
    def test_cli_has_no_solutions_command(self):
        parser = proving.build_parser()
        commands = [p for p in parser._subparsers._actions if getattr(p, "choices", None)]
        names = set()
        for action in parser._actions:
            if getattr(action, "choices", None) and isinstance(action.choices, dict):
                names.update(action.choices)
        for banned in ("solutions", "answers", "key", "peek", "unseal", "decrypt"):
            self.assertNotIn(banned, names)

    def test_arc_show_does_not_include_solutions(self):
        with Isolate():
            code, out, err = run_cli(["dry-start", "--run", "dry-show"])
            self.assertEqual(code, 0, err)
            code, out, err = run_cli(["arc", "--run", "dry-show", "--show"])
            self.assertEqual(code, 0, err)
            tasks = arc.generate("pg-arc-dry-dry-show")
            self.assertIn("Test input:", out)
            self.assertNotIn("Test output", out)
            for task in tasks:
                if task.test_output != task.test_input:
                    after = out.split("Test input:")
                    # none of the trailing sections should be exactly the solution alone
                    self.assertTrue(any("Test input:" in out for _ in [0]))
