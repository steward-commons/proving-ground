#!/usr/bin/env python3
"""The five events: ARC, memory, real-world, shootout, range."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import arc  # noqa: E402
import bank  # noqa: E402
import house  # noqa: E402
import memory_quiz  # noqa: E402
import range_event  # noqa: E402
import realworld  # noqa: E402
import shootout  # noqa: E402
from tests.helpers import Isolate  # noqa: E402


class ArcTest(unittest.TestCase):
    def test_seed_is_deterministic_and_months_differ(self):
        a = arc.generate(arc.month_seed(2026, 11))
        b = arc.generate(arc.month_seed(2026, 11))
        c = arc.generate(arc.month_seed(2026, 12))
        self.assertEqual([t.test_output for t in a], [t.test_output for t in b])
        self.assertNotEqual([t.test_output for t in a], [t.test_output for t in c])
        self.assertEqual(len(a), 4)

    def test_prompt_omits_the_solution(self):
        tasks = arc.generate("pg-arc-unit-1")
        text = arc.present(tasks)
        self.assertNotIn("Test output", text)
        for task in tasks:
            if task.test_output == task.test_input:
                continue
            after = task.prompt().split("Test input:", 1)[-1]
            self.assertNotIn(arc.render_grid(task.test_output), after)

    def test_grade_exact_match_only(self):
        tasks = arc.generate("pg-arc-unit-2")
        perfect = [t.test_output for t in tasks]
        result = arc.grade(tasks, perfect)
        self.assertEqual(result["score"], 20)
        self.assertEqual(result["correct"], 4)
        wrong = list(perfect)
        # Flip one cell on the first answer.
        grid = [list(row) for row in wrong[0]]
        grid[0][0] = 0 if grid[0][0] != 0 else 1
        wrong[0] = arc.make_grid(grid)
        half = arc.grade(tasks, wrong)
        self.assertEqual(half["correct"], 3)
        self.assertEqual(half["score"], 15)

    def test_parse_grids_several_formats(self):
        tasks = arc.generate("pg-arc-unit-3")
        text = "\n\n".join(arc.render_grid(t.test_output) for t in tasks)
        parsed = arc.parse_answer_list(text, 4)
        self.assertEqual(parsed, [t.test_output for t in tasks])
        oneline = " // ".join(arc.render_grid(t.test_output).replace("\n", "; ") for t in tasks)
        parsed2 = arc.parse_answer_list(oneline, 4)
        self.assertEqual(parsed2, [t.test_output for t in tasks])


class MemoryTest(unittest.TestCase):
    def test_aliases_and_wrong_answers(self):
        with Isolate() as iso:
            payload = bank.load_bank(iso.sealed, iso.key)
            # Use the full bank in a fixed order for grading, not the monthly sample.
            questions = payload["questions"][:10]
            # Answers correspond to FIXTURE_QUESTIONS 1-10 (see helpers).
            good = ["B", "Silverrun", "7", "Maple the Fox", "Thursday", "lumen", "piano bench", "Aunt Nora", "4", "a heron"]
            result = memory_quiz.grade(questions, good, key=iso.key)
            self.assertEqual(result["correct"], 10)
            self.assertEqual(result["score"], 20)
            bad = ["A"] * 10
            zero = memory_quiz.grade(questions, bad, key=iso.key)
            self.assertEqual(zero["correct"], 0)
            self.assertEqual(zero["score"], 0)

    def test_present_has_prompts_but_no_hashes(self):
        with Isolate() as iso:
            questions = memory_quiz.sample(2026, 11, bank.load_bank(iso.sealed, iso.key))
            text = memory_quiz.present(questions)
            self.assertIn("Memory & continuity", text)
            self.assertEqual(len(questions), 10)
            for item in questions:
                self.assertIn(item["prompt"], text)
                for h in item["hashes"]:
                    self.assertNotIn(h, text)


class RealWorldTest(unittest.TestCase):
    def test_records_owner_score_and_rejects_bad_values(self):
        rec = realworld.record("Fold the laundry", 16, rubric="On time, neat.", creative="used a song")
        self.assertEqual(rec["score"], 16)
        self.assertEqual(rec["task"], "Fold the laundry")
        self.assertEqual(rec["creative"], "used a song")
        self.assertIn("16/20", rec["detail"])
        with self.assertRaises(ValueError):
            realworld.record("", 10)
        with self.assertRaises(ValueError):
            realworld.record("A chore", 21)
        with self.assertRaises(ValueError):
            realworld.record("A chore", -1)


class RangeTest(unittest.TestCase):
    def test_scales_latest_qual_and_ignores_practice(self):
        with Isolate() as iso:
            rec = range_event.record()
            self.assertEqual(rec["score"], 19.5)
            self.assertEqual(rec["qual"]["correct"], 39)
            iso.write_practice_only()
            empty = range_event.record()
            self.assertEqual(empty["score"], 0)
            self.assertIsNone(empty["qual"])
            iso.write_qual(40, 40, rating="Expert")
            perfect = range_event.record()
            self.assertEqual(perfect["score"], 20)
            iso.write_qual(39, 40, ceased=True)
            ceased = range_event.record()
            self.assertEqual(ceased["score"], 0)


class ShootoutTest(unittest.TestCase):
    def test_shuffle_hides_identity_and_grade_then_reveal(self):
        with Isolate():
            prepared = shootout.prepare(
                "dry-x",
                "Name two public parks you can walk in a small town, in general terms.",
                "I would mention a courthouse square and a community ball field.",
                stock_answer="A town pond and a school track are common public places.",
                seed="fixed-seed-1",
            )
            packet = prepared["packet"]
            self.assertIn("Answer A:", packet)
            self.assertIn("Answer B:", packet)
            self.assertNotIn("Assistant", packet)
            self.assertNotIn("stock model", packet.lower())
            mapping = shootout.decode_mapping(prepared["sealed_mapping"])
            assistant_letter = next(k for k, v in mapping["labels"].items() if v == "assistant")
            stock_letter = next(k for k, v in mapping["labels"].items() if v == "stock")
            win = shootout.grade(mapping, pick=assistant_letter)
            self.assertEqual(win["score"], 20)
            lose = shootout.grade(mapping, pick=stock_letter)
            self.assertEqual(lose["score"], 0)
            tie = shootout.grade(mapping, pick="tie")
            self.assertEqual(tie["score"], 10)
            numeric = shootout.grade(mapping, score=14)
            self.assertEqual(numeric["score"], 14)
            text = shootout.reveal_text(mapping, win)
            self.assertIn("Assistant", text)
            self.assertIn("stock model", text)

    def test_private_prompt_is_refused(self):
        with Isolate():
            with self.assertRaises(RuntimeError):
                shootout.prepare("dry-x", "Here is a vault password: hunter2", "nope", stock_answer="nope")
            with self.assertRaises(RuntimeError):
                shootout.prepare(
                    "dry-x",
                    "PLACEHOLDER jailbreak test phrase.",
                    "nope",
                    stock_answer="nope",
                )

    def test_mock_is_used_when_consultant_is_off(self):
        with Isolate():
            prepared = shootout.prepare(
                "dry-x",
                "Name a public library service that is usually free.",
                "Interlibrary loan is often free for cardholders.",
            )
            self.assertIn("canned stock-model answer", prepared["stock_answer"])
