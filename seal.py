#!/usr/bin/env python3
"""Stdlib sealing for the question bank and the shootout identity map.

This is friction plus an honor rule, not a lock against the same bot with a
shell. Answers are stored as HMAC-SHA256 only. The parent taking the test
must not read sealed/ or set PROVING_ALLOW_PEEK before a live run.

Sealed blobs are encrypt-then-MAC (XOR stream + HMAC-SHA256). A wrong key or
a tampered blob raises SealError; we never return unauthenticated garbage.
Keys are stored as hex so a binary key cannot be mangled by whitespace stripping.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
from pathlib import Path
from typing import Any

import paths

KEY_FILE = "key"
BANK_FILE = "bank.seal"
PURPOSE_BANK = b"proving-ground-bank-v1"
PURPOSE_MAP = b"proving-ground-map-v1"
FORMAT_PREFIX = b"PG1:"
MAC_LEN = 32
KEY_BYTES = 32
KEY_HEX_LEN = 64


class SealError(ValueError):
    """Sealed data failed its integrity check, or a key could not be read."""


def normalize_answer(text: str) -> str:
    """Lowercase, strip, collapse space, drop surrounding punctuation."""
    value = (text or "").strip().lower()
    value = value.replace("’", "'").replace("“", '"').replace("”", '"')
    value = re.sub(r"\s+", " ", value)
    value = value.strip(" .,;:!?\"'")
    return value


def answer_hmac(key: bytes, qid: str, text: str) -> str:
    norm = normalize_answer(text)
    msg = f"{qid}:{norm}".encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def matches(key: bytes, qid: str, text: str, known: list[str]) -> bool:
    digest = answer_hmac(key, qid, text)
    return any(hmac.compare_digest(digest, item) for item in known)


def _decode_key(data: bytes) -> bytes:
    """Read a key file without treating binary keys as text.

    New keys are 64 lowercase hex characters plus a trailing newline.
    Legacy keys were 32 raw bytes plus a trailing newline. Only that one
    trailing newline is trimmed; bytes.strip() is never used, because a
    random key may itself start or end with an ASCII whitespace byte.
    """
    if data.endswith(b"\n"):
        data = data[:-1]
    if not data:
        raise SealError("sealed key is empty")
    if len(data) == KEY_HEX_LEN:
        try:
            text = data.decode("ascii")
        except UnicodeDecodeError:
            text = ""
        if text and all(c in "0123456789abcdefABCDEF" for c in text):
            return bytes.fromhex(text)
    if len(data) == KEY_BYTES:
        return data
    raise SealError("sealed key is not a 32-byte or hex-encoded key")


def _encode_key(key: bytes) -> bytes:
    if len(key) != KEY_BYTES:
        raise SealError("sealed keys must be 32 bytes")
    return key.hex().encode("ascii") + b"\n"


def load_or_create_key(directory: Path | None = None) -> bytes:
    root = directory or paths.sealed_root()
    path = root / KEY_FILE
    if path.is_file():
        return _decode_key(path.read_bytes())
    key = secrets.token_bytes(KEY_BYTES)
    root.mkdir(parents=True, exist_ok=True)
    paths.sealed_write(path, _encode_key(key))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key


def load_key(directory: Path | None = None) -> bytes:
    root = directory or paths.sealed_root()
    path = root / KEY_FILE
    if not path.is_file():
        raise FileNotFoundError(f"sealed key missing: {path}")
    return _decode_key(path.read_bytes())


def _xor(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def _stream_key(master: bytes, purpose: bytes, length: int) -> bytes:
    blocks = max(1, (length + 31) // 32)
    return b"".join(
        hmac.new(master, purpose + b":" + i.to_bytes(4, "big"), hashlib.sha256).digest()
        for i in range(blocks)
    )[:length]


def _mac_key(master: bytes, purpose: bytes) -> bytes:
    return hmac.new(master, b"mac|" + purpose, hashlib.sha256).digest()


def _tag(master: bytes, purpose: bytes, ciphertext: bytes) -> bytes:
    return hmac.new(_mac_key(master, purpose), purpose + ciphertext, hashlib.sha256).digest()


def _as_blob(blob: bytes | str) -> bytes:
    if isinstance(blob, str):
        return blob.encode("ascii")
    return bytes(blob)


def seal_bytes(master: bytes, purpose: bytes, payload: bytes) -> bytes:
    stream = _stream_key(master, purpose, len(payload))
    ciphertext = _xor(payload, stream)
    tagged = ciphertext + _tag(master, purpose, ciphertext)
    return FORMAT_PREFIX + base64.b64encode(tagged)


def unseal_bytes(master: bytes, purpose: bytes, blob: bytes | str) -> bytes:
    """Decrypt and authenticate a PG1 blob. Wrong key or tampering raises SealError."""
    data = _as_blob(blob).strip()
    if not data.startswith(FORMAT_PREFIX):
        raise SealError("sealed data is missing its integrity header")
    try:
        raw = base64.b64decode(data[len(FORMAT_PREFIX) :], validate=False)
    except Exception as exc:
        raise SealError("sealed data is not valid base64") from exc
    if len(raw) < MAC_LEN:
        raise SealError("sealed data is too short to authenticate")
    ciphertext, got = raw[:-MAC_LEN], raw[-MAC_LEN:]
    expected = _tag(master, purpose, ciphertext)
    if not hmac.compare_digest(got, expected):
        raise SealError("sealed data failed integrity check")
    stream = _stream_key(master, purpose, len(ciphertext))
    return _xor(ciphertext, stream)


def _unseal_legacy_xor(master: bytes, purpose: bytes, blob: bytes | str) -> bytes:
    """Pre-MAC XOR-only blobs. Used only to upgrade existing files, never for a live unseal."""
    raw = base64.b64decode(_as_blob(blob).strip())
    stream = hmac.new(master, purpose, hashlib.sha256).digest()
    if len(raw) > len(stream):
        blocks = (len(raw) + 31) // 32
        stream = b"".join(
            hmac.new(master, purpose + b":" + i.to_bytes(4, "big"), hashlib.sha256).digest()
            for i in range(blocks)
        )
    return _xor(raw, stream)


def seal_json(master: bytes, purpose: bytes, obj: Any) -> bytes:
    payload = json.dumps(obj, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return seal_bytes(master, purpose, payload)


def unseal_json(master: bytes, purpose: bytes, blob: bytes | str) -> Any:
    try:
        payload = unseal_bytes(master, purpose, blob)
    except SealError:
        raise
    try:
        text = payload.decode("utf-8")
        return json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        # Authenticated but still not JSON (should not happen for our writers).
        raise SealError("sealed data was authenticated but was not valid JSON") from exc


def upgrade_legacy_blob(master: bytes, purpose: bytes, blob: bytes | str) -> bytes | None:
    """If blob is a pre-MAC XOR payload, return a PG1 reseal. Otherwise None.

    Never prints or returns the plaintext. Raises SealError if the legacy
    payload cannot be decoded as JSON with this key.
    """
    data = _as_blob(blob).strip()
    if data.startswith(FORMAT_PREFIX):
        # Already current; verify it while we're here.
        unseal_json(master, purpose, data)
        return None
    try:
        payload = _unseal_legacy_xor(master, purpose, data)
        obj = json.loads(payload.decode("utf-8"))
    except Exception as exc:
        raise SealError("legacy sealed data could not be read with this key") from exc
    return seal_json(master, purpose, obj)
