#!/usr/bin/env python3
"""Safe mode, no-network dry path, live-bank leak guard, no destruction."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import house  # noqa: E402
import paths  # noqa: E402
from tests.helpers import Isolate, run_cli  # noqa: E402

LIVE_ROOT = Path(__file__).resolve().parents[1]
SHIPPED_SKIP = {"sealed", "data", "__pycache__", "tests"}


class SafeModeTest(unittest.TestCase):
    def test_pen_blocks_writes_but_status_still_works(self):
        with Isolate() as iso:
            iso.set_pen(True, reason="unit test")
            house.clear_cache()
            self.assertIsNotNone(house.writes_blocked())
            code, out, err = run_cli(["status"])
            self.assertEqual(code, 0, err)
            self.assertIn("WRITES FROZEN", out)
            code, out, err = run_cli(["dry-start", "--run", "dry-frozen"])
            self.assertNotEqual(code, 0)
            self.assertIn("safe mode", err.lower() + out.lower())
            # Official logbook must not have been created.
            self.assertFalse(paths.logbook_jsonl().is_file())

    def test_consultant_tourniquet_blocks_stock_call(self):
        with Isolate() as iso:
            iso.set_tourniquet("consultant")
            house.clear_cache()
            self.assertIsNotNone(house.consultant_blocked())
            # --stock bypasses the network, but prepare still checks consultant_blocked via ask? 
            # prepare uses stock_answer if provided, so the call is skipped.
            # Without --stock and with Consultant=off, ask_consultant should fail on the tourniquet first.
            os.environ.pop("PROVING_CONSULTANT_MOCK", None)
            import shootout

            with self.assertRaises(RuntimeError):
                shootout.prepare(
                    "dry-x",
                    "Name a public park feature.",
                    "A bench.",
                    stock_answer=None,
                )


class LeakGuardTest(unittest.TestCase):
    def test_shipped_files_do_not_contain_live_bank_prompts(self):
        live_sealed = LIVE_ROOT / "sealed"
        bank_file = live_sealed / "bank.seal"
        key_file = live_sealed / "key"
        if not bank_file.is_file() or not key_file.is_file():
            self.skipTest("live sealed bank is not built yet")
        # Load without pointing PROVING_SEALED at the live folder if an Isolate is active.
        # This test should be run without Isolate, or we load by explicit path.
        import bank as bankmod
        import seal as sealmod

        key = sealmod.load_key(live_sealed)
        data = sealmod.unseal_json(key, sealmod.PURPOSE_BANK, bank_file.read_bytes())
        prompts = [q["prompt"] for q in data.get("questions") or []]
        hashes = [h for q in data.get("questions") or [] for h in q.get("hashes") or []]
        self.assertGreaterEqual(len(prompts), 20)
        leaked = []
        for path in LIVE_ROOT.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(LIVE_ROOT)
            if rel.parts and rel.parts[0] in {"sealed", "data"}:
                continue
            if path.suffix not in {".py", ".md", ".txt", ".json"}:
                continue
            if path.name.startswith("."):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for prompt in prompts:
                if prompt and prompt in text:
                    leaked.append(path.name)
                    break
            else:
                for digest in hashes:
                    if digest and digest in text:
                        leaked.append(path.name)
                        break
        if leaked:
            self.fail(f"live bank content leaked into {sorted(set(leaked))}")

    def test_do_not_peek_notice_exists(self):
        notice = LIVE_ROOT / "sealed" / "DO_NOT_PEEK.md"
        self.assertTrue(notice.is_file())
        text = notice.read_text(encoding="utf-8").lower()
        self.assertIn("do not open", text)
        self.assertIn("peeking", text)


class NoDestructionTest(unittest.TestCase):
    def test_range_scoreboard_is_not_rewritten(self):
        with Isolate() as iso:
            before = iso.range_board.read_bytes()
            code, out, err = run_cli(["dry-start", "--run", "dry-r"])
            self.assertEqual(code, 0, err)
            code, out, err = run_cli(["range", "--run", "dry-r"])
            self.assertEqual(code, 0, err + out)
            self.assertEqual(iso.range_board.read_bytes(), before)
