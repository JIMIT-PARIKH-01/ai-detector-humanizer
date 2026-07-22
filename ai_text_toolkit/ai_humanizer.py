"""
ai_humanizer  --  "AI to humanize converter"

Rewrite stiff / generic AI-sounding text so it reads more naturally.

Two backends:
  * rules  (default, pure Python) -- safe, transparent edits: contractions,
            trimming stock filler phrases, light sentence-variety tweaks.
  * model  (optional) -- an OPEN-SOURCE Hugging Face paraphrase model.

Responsible use: this is a readability / tone tool. Don't use it to
misrepresent AI-written work as your own where that would be dishonest
(e.g. graded assignments). Rewriting does not reliably "beat" detectors,
and this tool does not promise to.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

from . import common

# Formal -> contracted forms (applied case-insensitively, keep leading capital).
CONTRACTIONS = {
    r"\bdo not\b": "don't",
    r"\bdoes not\b": "doesn't",
    r"\bdid not\b": "didn't",
    r"\bis not\b": "isn't",
    r"\bare not\b": "aren't",
    r"\bwas not\b": "wasn't",
    r"\bwere not\b": "weren't",
    r"\bcannot\b": "can't",
    r"\bcan not\b": "can't",
    r"\bwill not\b": "won't",
    r"\bwould not\b": "wouldn't",
    r"\bshould not\b": "shouldn't",
    r"\bcould not\b": "couldn't",
    r"\bhave not\b": "haven't",
    r"\bhas not\b": "hasn't",
    r"\bit is\b": "it's",
    r"\bthat is\b": "that's",
    r"\bthere is\b": "there's",
    r"\bwho is\b": "who's",
    r"\byou are\b": "you're",
    r"\bthey are\b": "they're",
    r"\bwe are\b": "we're",
    r"\byou will\b": "you'll",
    r"\bwe will\b": "we'll",
    r"\bI am\b": "I'm",
    r"\blet us\b": "let's",
}

# Stock AI transition / filler -> simpler wording ("" means delete).
PHRASE_REPLACEMENTS = {
    r"\bit is important to note that\b": "",
    r"\bit's important to note that\b": "",
    r"\bit is worth noting that\b": "",
    r"\bit should be noted that\b": "",
    r"\bas previously mentioned\b,?": "",
    r"\bin the realm of\b": "in",
    r"\bin order to\b": "to",
    r"\ba wide range of\b": "many",
    r"\bplays a crucial role in\b": "is key to",
    r"\bplays a vital role in\b": "is key to",
    r"\bfurthermore\b,?": "also,",
    r"\bmoreover\b,?": "also,",
    r"\badditionally\b,?": "also,",
    r"\bin conclusion\b,?": "so,",
    r"\bin summary\b,?": "in short,",
    r"\butilize\b": "use",
    r"\butilizes\b": "uses",
    r"\bleverage\b": "use",
    r"\bcommence\b": "start",
    r"\bnumerous\b": "many",
    r"\bsubsequently\b": "then",
    r"\bapproximately\b": "about",
}

STRENGTH_STEPS = {
    "light": ("phrases",),
    "medium": ("phrases", "contractions"),
    "strong": ("phrases", "contractions", "variety"),
}


def _apply_case_preserving(pattern: str, repl: str, text: str) -> str:
    """Replace pattern with repl, keeping a leading capital if the match had one."""
    def _sub(m: re.Match) -> str:
        original = m.group(0)
        out = repl
        if out and original[:1].isupper():
            out = out[:1].upper() + out[1:]
        return out
    return re.compile(pattern, re.IGNORECASE).sub(_sub, text)


def _tidy_whitespace(text: str) -> str:
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)      # no space before punctuation
    text = re.sub(r",\s*,+", ",", text)                # collapse ",," -> ","
    text = text.strip()
    # Recapitalise sentence starts left lowercase after a deletion/replacement.
    text = re.sub(r"(^|[.!?]\s+)([a-z])",
                  lambda m: m.group(1) + m.group(2).upper(), text)
    return text


def _add_variety(text: str) -> str:
    """Break the occasional long, comma-spliced sentence into two."""
    out = []
    for sent in common.sentence_split(text):
        words = sent.split()
        if len(words) > 28 and ", " in sent:
            # split at a middle comma into two shorter sentences
            idx = sent.find(", ", len(sent) // 3)
            if idx != -1:
                first = sent[:idx].strip()
                second = sent[idx + 2:].strip()
                if second:
                    second = second[0].upper() + second[1:]
                out.append(first + ". " + second)
                continue
        out.append(sent)
    return " ".join(out)


def humanize_rules(text: str, strength: str = "medium") -> str:
    steps = STRENGTH_STEPS.get(strength, STRENGTH_STEPS["medium"])
    result = text
    if "phrases" in steps:
        for pat, repl in PHRASE_REPLACEMENTS.items():
            result = _apply_case_preserving(pat, repl, result)
    if "contractions" in steps:
        for pat, repl in CONTRACTIONS.items():
            result = _apply_case_preserving(pat, repl, result)
    if "variety" in steps:
        result = _add_variety(result)
    return _tidy_whitespace(result)


def humanize_model(text: str, strength: str = "medium",
                   model_name: str | None = None) -> str:
    from . import backends  # local import; only needed for the model backend

    paraphrase = backends.get_paraphraser(model_name)
    sentences = common.sentence_split(text) or [text]
    rewritten = [paraphrase(s) for s in sentences]
    return " ".join(rewritten)


def humanize(text: str, backend: str = "auto", strength: str | None = None,
             cfg: dict | None = None) -> str:
    cfg = cfg if cfg is not None else common.load_config()
    strength = strength or cfg.get("humanizer_strength", "medium")
    if backend == "auto":
        backend = cfg.get("humanizer_backend", "auto")
    if backend == "model":
        try:
            return humanize_model(text, strength, cfg.get("paraphraser_model"))
        except Exception:  # noqa: BLE001 - fall back to rules silently but safely
            return humanize_rules(text, strength)
    return humanize_rules(text, strength)


@dataclass
class HumanizeReport:
    original: str
    humanized: str
    before_pct: float          # AI probability before, 0..100
    after_pct: float           # AI probability after, 0..100
    diff: list = field(default_factory=list)   # unified-diff lines (sentence level)

    @property
    def reduction_pct(self) -> float:
        return self.before_pct - self.after_pct

    def as_text(self) -> str:
        direction = ("reduced by" if self.reduction_pct > 0 else
                     "increased by" if self.reduction_pct < 0 else "unchanged at")
        change = (f"AI-likelihood {direction} {abs(self.reduction_pct):.0f} points"
                  if self.reduction_pct else "AI-likelihood unchanged")
        lines = [
            "=== Humanization report ===",
            f"AI probability : {self.before_pct:.0f}%  ->  {self.after_pct:.0f}%   ({change})",
            "",
            "--- Changes (before -> after) ---",
        ]
        lines.extend(self.diff or ["(no changes were made)"])
        lines.append("")
        lines.append("--- Humanized text ---")
        lines.append(self.humanized)
        return "\n".join(lines)


def humanize_with_report(text: str, backend: str = "auto", strength: str | None = None,
                         cfg: dict | None = None) -> HumanizeReport:
    """Humanize and measure the exact conversion: before/after AI-% and a diff."""
    from . import ai_detector  # local import avoids an import cycle at module load

    cfg = cfg if cfg is not None else common.load_config()
    before = ai_detector.detect(text, backend="auto", cfg=cfg)
    humanized = humanize(text, backend=backend, strength=strength, cfg=cfg)
    after = ai_detector.detect(humanized, backend="auto", cfg=cfg)

    diff = [ln for ln in difflib.unified_diff(
        common.sentence_split(text) or [text],
        common.sentence_split(humanized) or [humanized],
        fromfile="original", tofile="humanized", lineterm="")]

    return HumanizeReport(original=text, humanized=humanized,
                          before_pct=before.score, after_pct=after.score, diff=diff)
