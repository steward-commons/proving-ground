#!/usr/bin/env python3
"""Load (and, at build time, write) the sealed memory-quiz bank.

The live bank lives under sealed/. Do not read it before a live run.
Tests should point PROVING_SEALED at a temporary fixture bank.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import paths
import seal


def bank_path(directory: Path | None = None) -> Path:
    return (directory or paths.sealed_root()) / seal.BANK_FILE


def build_bank(questions: Iterable[dict[str, Any]], key: bytes) -> dict[str, Any]:
    """Hash every accepted answer and drop plaintext answers from the payload."""
    packed = []
    for item in questions:
        qid = str(item["id"])
        accepted = item.get("answers") or []
        if not accepted:
            raise ValueError(f"question {qid} has no answers")
        hashes = [seal.answer_hmac(key, qid, text) for text in accepted]
        packed.append(
            {
                "id": qid,
                "prompt": item["prompt"],
                "options": list(item.get("options") or []),
                "hashes": hashes,
            }
        )
    return {"version": 1, "questions": packed}


def write_bank(payload: dict[str, Any], key: bytes, directory: Path | None = None) -> Path:
    blob = seal.seal_json(key, seal.PURPOSE_BANK, payload)
    path = bank_path(directory)
    paths.sealed_write(path, blob + b"\n")
    return path


def load_bank(directory: Path | None = None, key: bytes | None = None) -> dict[str, Any]:
    path = bank_path(directory)
    if not path.is_file():
        raise FileNotFoundError(f"sealed memory bank missing: {path}")
    master = key if key is not None else seal.load_key(directory)
    data = seal.unseal_json(master, seal.PURPOSE_BANK, path.read_bytes().strip())
    if not isinstance(data, dict) or "questions" not in data:
        raise ValueError("sealed memory bank is malformed")
    return data


def bank_info(directory: Path | None = None) -> str:
    """Status only — no question text, no hashes."""
    root = directory or paths.sealed_root()
    key_ok = (root / seal.KEY_FILE).is_file()
    path = bank_path(root)
    if not path.is_file():
        return f"Sealed bank not found at {path}. Key present: {key_ok}."
    try:
        data = load_bank(root)
        n = len(data.get("questions") or [])
        return f"Sealed memory bank is in place ({n} questions). Key present: {key_ok}. Do not open sealed/ before a live run."
    except Exception:
        return f"Sealed bank file exists but could not be read. Key present: {key_ok}."


def upgrade_sealed_store(directory: Path | None = None) -> bool:
    """Rewrite a pre-MAC bank and a raw/legacy key in place. Returns True if a file changed.

    Does not print bank contents. Safe to call if the store is already current.
    """
    root = directory or paths.sealed_root()
    key_path = root / seal.KEY_FILE
    bank = bank_path(root)
    changed = False
    if not key_path.is_file():
        raise FileNotFoundError(f"sealed key missing: {key_path}")
    raw = key_path.read_bytes()
    key = seal._decode_key(raw)
    # Rewrite raw keys as hex so later loads cannot strip whitespace bytes.
    encoded = seal._encode_key(key)
    if raw != encoded:
        paths.sealed_write(key_path, encoded)
        try:
            import os

            os.chmod(key_path, 0o600)
        except OSError:
            pass
        changed = True
    if bank.is_file():
        upgraded = seal.upgrade_legacy_blob(key, seal.PURPOSE_BANK, bank.read_bytes())
        if upgraded is not None:
            paths.sealed_write(bank, upgraded + b"\n")
            changed = True
    return changed
