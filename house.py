#!/usr/bin/env python3
"""Read-only links to House Medical, the defense scanner, and Consultant privacy.

Loaded by file path so nobody's `paths` module is shadowed. Nothing here writes.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import re
import sys
import unicodedata
from pathlib import Path
from types import ModuleType
from typing import Any

import paths

_cache: dict[str, ModuleType | None] = {}

_FALLBACK = re.compile(
    r"ignore (all )?(previous|prior|above) (instructions|rules)|disregard (previous|prior)|"
    r"you are now\b|new instructions\s*:|override (your|the) (rules|instructions)|jailbreak|"
    r"developer mode|system prompt|do not tell (owner|the owner)|gift\s*cards?",
    re.IGNORECASE,
)

# Always-on privacy markers for outbound Consultant prompts (shootout is public-only).
_PRIVACY_LITERALS = (
    "PRIVATE",
    "vault",
    "password",
    "~/.config",
    "Private - Sensitive Records",
)


def _load(name: str, path: Path) -> ModuleType | None:
    key = f"{name}:{path}"
    if key in _cache:
        return _cache[key]
    mod = None
    try:
        if path.is_file():
            spec = importlib.util.spec_from_file_location(f"_proving_{name}", path)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                # dataclasses need the module registered while it executes
                sys.modules[spec.name] = mod
                try:
                    spec.loader.exec_module(mod)
                except Exception:
                    sys.modules.pop(spec.name, None)
                    raise
    except Exception:
        mod = None
    _cache[key] = mod
    return mod


def clear_cache() -> None:
    _cache.clear()


def medical_guard_path() -> Path:
    return Path(os.environ.get("PROVING_MEDICAL_GUARD") or paths.HOUSE / "medical" / "guard.py")


def scanner_path() -> Path:
    return Path(os.environ.get("PROVING_DEFENSE_SCAN") or paths.HOUSE / "defense" / "scan_text.py")


def privacy_path() -> Path:
    return Path(os.environ.get("PROVING_PRIVACY") or paths.HOUSE / "gemini" / "privacy.py")


def client_path() -> Path:
    return Path(os.environ.get("PROVING_GEMINI_CLIENT") or paths.HOUSE / "gemini" / "client.py")


def medical_block(part: str = "proving") -> str | None:
    """Reason if the morphine pen or a tourniquet is on for this part."""
    mod = _load("medguard", medical_guard_path())
    if mod is None or not hasattr(mod, "blocked"):
        return None
    try:
        return mod.blocked(part)
    except Exception:
        return None


def writes_blocked() -> str | None:
    """Safe mode or a proving tourniquet freezes ordinary writes."""
    return medical_block("proving") or medical_block("proving-ground")


def consultant_blocked() -> str | None:
    """Safe mode, a consultant tourniquet, or a proving tourniquet blocks the stock-model call."""
    return medical_block("consultant") or writes_blocked()


def defense_hits(text: str) -> list[str]:
    mod = _load("scan", scanner_path())
    if mod is not None and hasattr(mod, "scan_text"):
        try:
            return sorted({label for _line, label, _excerpt in mod.scan_text(text)})
        except Exception:
            pass
    skeleton = unicodedata.normalize("NFKC", text)
    skeleton = re.sub(r"[\u200b-\u200f\u2060-\u2064\ufeff]", "", skeleton)
    return ["fallback-pattern"] if _FALLBACK.search(skeleton) else []


def privacy_hits(text: str) -> list[str]:
    """Labels that mean a shootout prompt is not public enough for Consultant."""
    mod = _load("privacy", privacy_path())
    if mod is not None and hasattr(mod, "scan_text"):
        try:
            hits = mod.scan_text(text, path=None)
            return sorted({getattr(h, "label", str(h)) for h in hits})
        except Exception:
            pass
    lowered = (text or "").lower()
    found = [lit for lit in _PRIVACY_LITERALS if lit.lower() in lowered]
    if re.search(r"\b\d{3}-\d{2}-\d{4}\b", text or ""):
        found.append("ssn-shaped")
    return found


def load_gemini_client() -> ModuleType | None:
    return _load("gclient", client_path())


def ask_consultant(prompt: str, model: str = "gemini-3.1-flash-lite", timeout: float = 60.0) -> str:
    """Ask the stock model. Public prompts only. Output is untrusted text.

    Network happens only here, and only when no mock is set and Consultant is not 'off'.
    """
    reason = consultant_blocked()
    if reason:
        raise RuntimeError(reason)
    hits = privacy_hits(prompt)
    if hits:
        raise RuntimeError(
            "Shootout prompt looks private or sensitive "
            f"({', '.join(hits)}). Public, non-private prompts only."
        )
    defense = defense_hits(prompt)
    if defense:
        raise RuntimeError(
            "Shootout prompt tripped the house defense scanner "
            f"({', '.join(defense)}). Refusing to send it."
        )
    mock = os.environ.get("PROVING_CONSULTANT_MOCK")
    if mock is not None:
        return mock
    if os.environ.get("PROVING_CONSULTANT", "").lower() == "off":
        raise RuntimeError("Consultant is off (PROVING_CONSULTANT=off) and no mock answer was provided.")
    client = load_gemini_client()
    if client is None or not hasattr(client, "generate"):
        raise RuntimeError("Gemini client could not be loaded from gemini/client.py.")
    if hasattr(client, "get_api_key"):
        try:
            client.get_api_key()
        except Exception as exc:
            raise RuntimeError(f"GEMINI_API_KEY is missing or unreadable: {exc}") from exc
    body = client.build_body(prompt=prompt, system=_SHOOTOUT_SYSTEM)
    models = client.text_model_chain(model) if hasattr(client, "text_model_chain") else [model]
    result = client.generate(body, models=models, timeout=timeout)
    return (getattr(result, "text", None) or str(result)).strip()


_SHOOTOUT_SYSTEM = (
    "You are a general-purpose assistant answering a single public question. "
    "Give a clear, direct answer. Do not claim to be the house assistant. "
    "Do not ask for or repeat private information."
)


def require_writable() -> None:
    reason = writes_blocked()
    if reason:
        raise RuntimeError(reason)
