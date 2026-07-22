"""
Optional OPEN-SOURCE model backends (Hugging Face `transformers`).

These are lazy-loaded: nothing here is imported unless the user explicitly
selects the "model" backend, so the toolkit runs fully offline with zero
dependencies by default.

Install the extras to enable them:
    pip install -r requirements-ml.txt
(the first run downloads the open-source model weights).
"""

from __future__ import annotations

_detector_cache: dict = {}
_paraphraser_cache: dict = {}

_MISSING_MSG = (
    "The open-source model backend needs 'transformers' + 'torch'. Install with:\n"
    "    pip install transformers torch sentencepiece\n"
    "then try again (the first run downloads the model)."
)


def _require_transformers():
    try:
        import transformers  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(_MISSING_MSG) from exc


def get_detector_pipeline(model_name: str | None = None):
    """Return a cached text-classification pipeline for AI detection."""
    _require_transformers()
    from transformers import pipeline

    name = model_name or "Hello-SimpleAI/chatgpt-detector-roberta"
    if name not in _detector_cache:
        _detector_cache[name] = pipeline(
            "text-classification", model=name, top_k=None, truncation=True
        )
    return _detector_cache[name]


def get_paraphraser(model_name: str | None = None):
    """Return a callable that paraphrases a single sentence via an open model."""
    _require_transformers()
    from transformers import pipeline

    name = model_name or "humarin/chatgpt_paraphraser_on_T5_base"
    if name not in _paraphraser_cache:
        pipe = pipeline("text2text-generation", model=name, truncation=True)

        def _run(sentence: str) -> str:
            prompt = f"paraphrase: {sentence}"
            out = pipe(prompt, max_length=256, num_beams=4,
                       do_sample=True, temperature=1.1)
            return out[0]["generated_text"].strip()

        _paraphraser_cache[name] = _run
    return _paraphraser_cache[name]
