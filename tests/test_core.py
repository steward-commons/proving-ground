#!/usr/bin/env python3
"""Ranks, scoring, schedule, sealing, logbook, replay, write gate."""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import logbook  # noqa: E402
import paths  # noqa: E402
import ranks  # noqa: E402
import replay  # noqa: E402
import schedule  # noqa: E402
import scoring  # noqa: E402
import seal  # noqa: E402
from tests.helpers import Isolate  # noqa: E402


class RankTest(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual(ranks.rank(0), ranks.UNQUALIFIED)
        self.assertEqual(ranks.rank(59.5), ranks.UNQUALIFIED)
        self.assertEqual(ranks.rank(59.999), ranks.UNQUALIFIED)
        self.assertEqual(ranks.rank(60), ranks.MARKSMAN)
        self.assertEqual(ranks.rank(74.5), ranks.MARKSMAN)
        self.assertEqual(ranks.rank(75), ranks.SHARPSHOOTER)
        self.assertEqual(ranks.rank(89.5), ranks.SHARPSHOOTER)
        self.assertEqual(ranks.rank(90), ranks.EXPERT)
        self.assertEqual(ranks.rank(100), ranks.EXPERT)


class ScoringTest(unittest.TestCase):
    def test_scale_40_to_20(self):
        self.assertEqual(scoring.scale_out_of(40, 40), 20)
        self.assertEqual(scoring.scale_out_of(39, 40), 19.5)
        self.assertEqual(scoring.scale_out_of(38, 40), 19)
        self.assertEqual(scoring.scale_out_of(0, 40), 0)
        self.assertEqual(scoring.scale_out_of(20, 0), 0)

    def test_clamp_and_total(self):
        self.assertEqual(scoring.clamp_event(-1), 0)
        self.assertEqual(scoring.clamp_event(25), 20)
        self.assertEqual(scoring.total_of({"arc": 20, "memory": 20, "realworld": 20, "shootout": 20, "range": 19.5}), 99.5)

    def test_half_step(self):
        self.assertEqual(scoring.half_step(19.24), 19.0)
        self.assertEqual(scoring.half_step(19.25), 19.5)
        self.assertEqual(scoring.half_step(19.75), 20.0)


class ScheduleTest(unittest.TestCase):
    def test_first_monday_november_2026(self):
        self.assertEqual(schedule.first_monday(2026, 11).isoformat(), "2026-11-02")
        self.assertEqual(schedule.first_monday(2026, 12).isoformat(), "2026-12-07")

    def test_window_closed_before_first_monday(self):
        sun = datetime.fromisoformat("2026-11-01T12:00:00-06:00")
        self.assertFalse(schedule.in_window(sun))
        opens, _ = schedule.window_for(sun)
        self.assertEqual(opens.day, 2)
        self.assertEqual(opens.hour, 9)
        self.assertEqual(opens.minute, 0)

    def test_window_open_monday_morning(self):
        before = datetime.fromisoformat("2026-11-02T08:59:00-06:00")
        after = datetime.fromisoformat("2026-11-02T09:00:00-06:00")
        later = datetime.fromisoformat("2026-11-18T06:49:00-06:00")
        self.assertFalse(schedule.in_window(before))
        self.assertTrue(schedule.in_window(after))
        self.assertTrue(schedule.in_window(later))


class SealTest(unittest.TestCase):
    def test_round_trip_and_normalized_hashes(self):
        with Isolate() as iso:
            payload = {"hello": "world", "n": 3}
            blob = seal.seal_json(iso.key, seal.PURPOSE_BANK, payload)
            self.assertEqual(seal.unseal_json(iso.key, seal.PURPOSE_BANK, blob), payload)
            h1 = seal.answer_hmac(iso.key, "q1", "Maple the Fox")
            h2 = seal.answer_hmac(iso.key, "q1", "  maple the fox. ")
            self.assertEqual(h1, h2)
            self.assertTrue(seal.matches(iso.key, "q1", "MAPLE THE FOX", [h1]))
            self.assertFalse(seal.matches(iso.key, "q1", "birch the wolf", [h1]))
            self.assertFalse(seal.matches(iso.key, "q2", "Maple the Fox", [h1]))

    def test_wrong_key_or_tamper_raises_seal_error(self):
        with Isolate() as iso:
            blob = seal.seal_json(iso.key, seal.PURPOSE_BANK, {"hello": "world"})
            other = bytes((b + 1) % 256 for b in iso.key)
            with self.assertRaises(seal.SealError):
                seal.unseal_json(other, seal.PURPOSE_BANK, blob)
            # Flip one byte in the ciphertext, keep the prefix so this is tampering.
            raw = bytearray(blob)
            raw[-2] = (raw[-2] + 1) % 256
            with self.assertRaises(seal.SealError):
                seal.unseal_json(iso.key, seal.PURPOSE_BANK, bytes(raw))
            with self.assertRaises(seal.SealError):
                seal.unseal_json(iso.key, seal.PURPOSE_BANK, b"not-a-seal")

    def test_key_file_preserves_whitespace_bytes(self):
        # Regression: bytes.strip() used to eat leading/trailing ASCII whitespace
        # in a raw 32-byte key, so a later load unsealed with the wrong key.
        with Isolate() as iso:
            for key in (
                b"\n" + b"A" * 31,
                b"A" * 31 + b"\n",
                b" " + b"B" * 31,
                b"B" * 31 + b" ",
                b"\t" + b"C" * 30 + b"\r",
            ):
                path = iso.sealed / seal.KEY_FILE
                # Write through the encoder (hex) and also as a legacy raw file.
                path.write_bytes(key + b"\n")
                loaded = seal._decode_key(path.read_bytes())
                self.assertEqual(loaded, key)
                path.write_bytes(seal._encode_key(key))
                self.assertEqual(seal.load_key(iso.sealed), key)
                blob = seal.seal_json(key, seal.PURPOSE_BANK, {"k": "v"})
                self.assertEqual(seal.unseal_json(seal.load_key(iso.sealed), seal.PURPOSE_BANK, blob), {"k": "v"})
            # Restore a valid fixture key so Isolate cleanup and later loads stay coherent.
            path = iso.sealed / seal.KEY_FILE
            path.write_bytes(seal._encode_key(iso.key))


class LogbookTest(unittest.TestCase):
    def _entry(self, month: str, total: float, creative: str = "") -> dict:
        ev = {
            "arc": {"score": 15, "max": 20, "detail": "3/4", "creative": creative},
            "memory": {"score": 16, "max": 20, "detail": "8/10", "creative": ""},
            "realworld": {"score": 16, "max": 20, "detail": "The owner scored 16/20", "task": "sandbox chore", "creative": ""},
            "shootout": {"score": 20, "max": 20, "detail": "pick A", "creative": ""},
            "range": {"score": 19.5, "max": 20, "detail": "example score", "creative": ""},
        }
        # Adjust total if needed; tests pass explicit total
        return {
            "id": month,
            "kind": "official",
            "time": f"{month}-20T10:00:00-06:00",
            "timezone": "America/Chicago",
            "events": ev,
            "total": total,
            "rank": ranks.rank(total),
            "notes": "",
        }

    def test_append_only_official_and_trends(self):
        with Isolate():
            logbook.append(self._entry("2026-09", 80))
            logbook.append(self._entry("2026-10", 86, creative="tried a sideways fold"))
            self.assertTrue(logbook.has_official("2026-10"))
            self.assertFalse(logbook.has_official("2026-11"))
            text = logbook.trends_text()
            self.assertIn("+6", text)
            self.assertIn("Personal best: 86", text)
            md = paths.logbook_md().read_text(encoding="utf-8")
            self.assertIn("tried a sideways fold", md)
            self.assertIn("Sharpshooter", md)
            with self.assertRaises(ValueError):
                logbook.append({**self._entry("2026-11", 90), "kind": "dry"})

    def test_creative_does_not_change_score(self):
        a = self._entry("2026-11", 86.5, creative="wild idea")
        b = self._entry("2026-11", 86.5, creative="")
        self.assertEqual(a["total"], b["total"])
        self.assertEqual(a["events"]["arc"]["score"], 15)


class ReplayTest(unittest.TestCase):
    def test_clip_is_kid_safe_and_has_no_keys(self):
        entry = {
            "id": "2026-11",
            "kind": "official",
            "total": 90.5,
            "rank": "Expert",
            "events": {
                "arc": {"score": 15, "max": 20, "creative": "noticed a fold"},
                "memory": {"score": 18, "max": 20},
                "realworld": {"score": 18, "max": 20},
                "shootout": {"score": 20, "max": 20, "pick": "A"},
                "range": {"score": 19.5, "max": 20, "qual": {"correct": 39, "rounds": 40, "rating": "Expert"}},
            },
        }
        text = replay.clip_for(entry)
        self.assertIn("Expert", text)
        self.assertIn("90.5", text)
        self.assertIn("Laughing together, not at anyone", text)
        self.assertNotIn("answer key", text.lower())
        self.assertNotIn("password", text.lower())
        self.assertNotIn("hashes", text.lower())
        with Isolate():
            path = replay.write_clip(entry)
            self.assertTrue(path.is_file())
            self.assertTrue(str(path).startswith(str(paths.data_root())))


class WriteGateTest(unittest.TestCase):
    def test_refuses_writes_outside_data(self):
        with Isolate() as iso:
            with self.assertRaises(paths.WriteOutsideData):
                paths.safe_write(iso.tmp / "outside.txt", "nope")
