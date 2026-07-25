"""
ai_detector  --  "AI implementation detection"

Estimate how likely a piece of text was AI-generated, as a PERCENTAGE with a
confidence level.

Backends:
  * heuristic  (default, pure Python) -- explainable stylometric signals.
  * model      (optional) -- an OPEN-SOURCE Hugging Face classifier.
  * ensemble   ("auto")   -- blends the model (if installed) with heuristics.

IMPORTANT / honest caveat: no AI-text detector is or can be 100% accurate.
Every backend produces an *estimate* with real false-positive and false-negative
rates. The percentage is a best-effort signal, not proof. Never use it to accuse
someone or to make a high-stakes decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import common

# Stock phrases that show up disproportionately in generic LLM prose.
AI_PHRASES = [
    "it is important to note", "it's important to note", "it is worth noting",
    "in conclusion", "in summary", "overall,", "furthermore", "moreover",
    "additionally", "however, it is", "delve into", "delving into",
    "a testament to", "tapestry", "navigating the", "in the realm of",
    "plays a crucial role", "plays a vital role", "it is essential to",
    "when it comes to", "on the other hand", "as previously mentioned",
    "a wide range of", "gain a deeper understanding", "ever-evolving",
    "cutting-edge", "seamless", "unlock the", "harness the power",
    # additional modern LLM tells
    "in today's fast-paced", "it is crucial to", "it goes without saying",
    "needless to say", "first and foremost", "last but not least",
    "a myriad of", "a plethora of", "underscore", "pivotal role",
    "the landscape of", "foster a", "let's dive", "dive into", "let's explore",
    "in essence", "ultimately,", "notably,", "consequently,", "as a result,",
    "elevate your", "the world of", "boasts", "robust", "holistic",
    "paradigm", "synergy", "game-changer", "at the end of the day",
    "rich tapestry", "testament to", "realm of", "meticulous", "meticulously",
]

CONTRACTION_RE_TOKENS = {"n't", "'re", "'ve", "'ll", "'d", "'m", "'s"}

# Label names various open-source detectors use for the AI / human class.
_AI_LABELS = {"fake", "ai", "chatgpt", "gpt", "generated", "machine",
              "label_1", "1", "llm", "bot"}
_HUMAN_LABELS = {"real", "human", "label_0", "0", "original", "person"}


@dataclass
class DetectionResult:
    score: float                       # 0..100 estimated AI-likelihood (percentage)
    verdict: str                       # human-readable band
    backend: str                       # heuristic | model | ensemble
    confidence: str = "low"            # low | medium | n/a
    signals: dict = field(default_factory=dict)
    notes: str = ""

    @property
    def percentage(self) -> str:
        return f"{self.score:.0f}%"

    def as_text(self) -> str:
        lines = [
            "=== AI detection (estimate only) ===",
            f"Backend        : {self.backend}",
            f"AI probability : {self.percentage}",
            f"Confidence     : {self.confidence}",
            f"Verdict        : {self.verdict}",
        ]
        if self.signals:
            lines.append("Signals:")
            for k, v in self.signals.items():
                lines.append(f"  - {k:<22}: {v}")
        if self.notes:
            lines.append(self.notes)
        return "\n".join(lines)


def _verdict(score: float) -> str:
    if score < 35:
        return "Likely human-written"
    if score < 65:
        return "Uncertain / mixed"
    return "Likely AI-generated"


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _confidence_for(n_words: int) -> str:
    if n_words < 40:
        return "n/a"
    if n_words < 150:
        return "low"
    return "medium"


# --------------------------------------------------------------------------- #
# Heuristic backend
# --------------------------------------------------------------------------- #
def detect_heuristic(text: str) -> DetectionResult:
    sentences = common.sentence_split(text)
    words = common.word_tokens(text)
    n_words = len(words)

    if n_words < 20 or len(sentences) < 2:
        return DetectionResult(
            score=50.0, verdict="Too short to judge", backend="heuristic",
            confidence="n/a",
            notes="Note: text is very short; the estimate is unreliable.",
        )

    lengths = [len(common.word_tokens(s)) for s in sentences]
    m_len = common.mean(lengths)
    cv = common.pstdev(lengths) / m_len if m_len else 0.0     # burstiness

    lower = [w.lower() for w in words]
    ttr = len(set(lower)) / n_words                            # vocab richness

    contractions = sum(1 for w in lower if any(w.endswith(c)
                       for c in CONTRACTION_RE_TOKENS))
    contraction_rate = contractions / len(sentences)

    low_text = " " + text.lower() + " "
    phrase_hits = sum(low_text.count(p) for p in AI_PHRASES)
    phrase_density = phrase_hits / (n_words / 100.0)           # per 100 words

    starters = [toks[0].lower() for s in sentences
                if (toks := common.word_tokens(s))]
    starter_rep = 1 - (len(set(starters)) / len(starters)) if starters else 0.0

    # Map each signal to an "AI-ness" in 0..1.
    ai_burst = _clamp(1 - cv / 0.6)          # low variance -> AI
    ai_ttr = _clamp((0.55 - ttr) / 0.35)     # low richness -> AI
    ai_contract = _clamp(1 - contraction_rate * 3)
    ai_phrase = _clamp(phrase_density / 1.5)   # stock LLM phrases: strongest tell
    ai_rep = _clamp(starter_rep * 3)

    # Weighted blend -- the stock-phrase signal is weighted highest because it's
    # the most reliable indicator of generic LLM prose.
    score = 100 * (
        0.25 * ai_burst +
        0.08 * ai_ttr +
        0.22 * ai_contract +
        0.37 * ai_phrase +
        0.08 * ai_rep
    )
    # A high density of stock LLM phrases is a strong tell on its own
    # (>= 4 per 100 words is well beyond typical human usage).
    if phrase_density >= 4:
        score = max(score, 68)

    signals = {
        "sentences": len(sentences),
        "words": n_words,
        "burstiness (CV)": f"{cv:.2f}  (higher = more human)",
        "vocab richness (TTR)": f"{ttr:.2f}",
        "contractions/sentence": f"{contraction_rate:.2f}",
        "AI-phrase hits /100w": f"{phrase_density:.2f}",
        "repeated sent. starters": f"{starter_rep:.2f}",
    }
    return DetectionResult(
        score=score, verdict=_verdict(score), backend="heuristic",
        confidence=_confidence_for(n_words), signals=signals,
        notes="Heuristic estimate -- inherently weak; not proof.",
    )


# --------------------------------------------------------------------------- #
# Optional open-source model backend
# --------------------------------------------------------------------------- #
def _ai_prob_from_scores(scores: dict) -> float:
    """Pick the AI-class probability from a label->prob mapping, robustly.

    Uses explicit label membership (NOT a falsy `or` chain) so that a genuine
    0.0 AI probability is never mistaken for 'missing'.
    """
    for label, prob in scores.items():
        if label in _AI_LABELS:
            return prob
    for label, prob in scores.items():
        if label in _HUMAN_LABELS:      # two-class head: AI = 1 - human
            return 1.0 - prob
    # Unknown label scheme: cannot map reliably -> neutral.
    return 0.5


def detect_model(text: str, model_name: str | None = None) -> DetectionResult:
    from . import backends  # local import so the tool works without transformers

    clf = backends.get_detector_pipeline(model_name)
    raw = clf(text[:4000], truncation=True)
    rows = raw if isinstance(raw[0], dict) else raw[0]
    scores = {r["label"].lower(): float(r["score"]) for r in rows}

    ai_prob = _ai_prob_from_scores(scores)
    score = ai_prob * 100
    return DetectionResult(
        score=score, verdict=_verdict(score), backend="model",
        confidence="medium",
        signals={k: f"{v:.2f}" for k, v in scores.items()},
        notes="Open-source classifier estimate -- imperfect; treat as a signal.",
    )


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def detect(text: str, backend: str = "auto", cfg: dict | None = None) -> DetectionResult:
    cfg = cfg if cfg is not None else common.load_config()
    if backend == "auto":
        backend = cfg.get("detector_backend", "auto")
    if backend == "auto":
        backend = "ensemble"          # best-effort: model if available, else heuristic

    if backend == "heuristic":
        return detect_heuristic(text)

    heur = detect_heuristic(text)
    try:
        model = detect_model(text, cfg.get("detector_model"))
    except Exception:  # noqa: BLE001 - model optional; degrade gracefully
        heur.notes += ("\n(open-source model not installed; used heuristic only. "
                       "Install 'transformers' + 'torch' for higher accuracy.)")
        return heur

    if backend == "model":
        return model

    # ensemble: blend the model (weighted higher) with the heuristic estimate.
    blended = 0.65 * model.score + 0.35 * heur.score
    return DetectionResult(
        score=blended, verdict=_verdict(blended), backend="ensemble",
        confidence="medium",
        signals={"model %": f"{model.score:.0f}",
                 "heuristic %": f"{heur.score:.0f}",
                 **{f"model[{k}]": v for k, v in model.signals.items()}},
        notes="Ensemble of open-source model + heuristics -- still an estimate.",
    )
