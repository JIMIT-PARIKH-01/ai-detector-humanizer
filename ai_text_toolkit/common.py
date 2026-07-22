"""
Shared helpers for the AI Text Toolkit (detector + humanizer).

Pure standard library -- no third-party dependencies. The optional
open-source model backends live in `backends.py`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

TOOLKIT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = TOOLKIT_DIR / "config.json"

DEFAULT_CONFIG = {
    "detector_backend": "auto",     # auto | heuristic | model
    "humanizer_backend": "auto",    # auto | rules | model
    "humanizer_strength": "medium",  # light | medium | strong
    "detector_model": "Hello-SimpleAI/chatgpt-detector-roberta",
    "paraphraser_model": "humarin/chatgpt_paraphraser_on_T5_base",
}

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                cfg.update({k: v for k, v in json.load(fh).items() if v is not None})
        except (json.JSONDecodeError, OSError):
            pass
    else:
        save_config(cfg)
    return cfg


def save_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)


# --------------------------------------------------------------------------- #
# Lightweight tokenization (regex based -- no nltk needed)
# --------------------------------------------------------------------------- #
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")
_WORD_RE = re.compile(r"[A-Za-z']+")


def sentence_split(text: str) -> list[str]:
    """Split text into sentences (good enough for stylometric features)."""
    text = text.strip()
    if not text:
        return []
    # Normalise newlines to spaces so paragraph breaks don't create empties.
    flat = re.sub(r"\s*\n\s*", " ", text)
    parts = _SENT_SPLIT.split(flat)
    return [p.strip() for p in parts if p.strip()]


def word_tokens(text: str) -> list[str]:
    return _WORD_RE.findall(text)


def read_text_source(text: str | None, file: str | None) -> str:
    """Resolve input text from a literal string or a document of any type."""
    if text is not None:
        return text
    if file:
        from . import docio  # local import keeps common.py dependency-free at import
        return docio.extract_text(file)
    return ""


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def pstdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = mean(values)
    return (sum((v - m) ** 2 for v in values) / len(values)) ** 0.5
