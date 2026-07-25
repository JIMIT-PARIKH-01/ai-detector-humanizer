"""Offline tests for the AI Text Toolkit (detector + humanizer + docio)."""

import os
import tempfile

from ai_text_toolkit import ai_detector, ai_humanizer, common, docio


def test_detector_ai_scores_higher_than_human():
    ai_ish = ("It is important to note that artificial intelligence plays a crucial role in "
              "modern society. Furthermore, it is worth noting that we utilize numerous "
              "cutting-edge tools. Moreover, these seamless solutions unlock the power of data.")
    human = ("So I grabbed coffee this morning and it was freezing outside. Weird for July, "
             "right? My dog refused to walk, he just sat there, stubborn little guy. We gave up.")
    assert ai_detector.detect_heuristic(ai_ish).score > ai_detector.detect_heuristic(human).score


def test_detector_score_in_range():
    r = ai_detector.detect(
        "This is a longer piece of text with several words to analyze here today, friend.",
        backend="heuristic")
    assert 0 <= r.score <= 100


def test_humanizer_rules_rewrites():
    out = ai_humanizer.humanize_rules("It is important to note that we utilize numerous tools.")
    assert "use" in out and "many" in out
    assert "important to note" not in out.lower()


def test_humanizer_contractions():
    out = ai_humanizer.humanize_rules("It is not a simple task.", strength="medium")
    assert "isn't" in out


def test_common_tokenizers():
    assert common.word_tokens("hello, world!") == ["hello", "world"]
    assert len(common.sentence_split("One. Two. Three.")) == 3


def test_docio_html_strips_scripts():
    html = "<html><body><h1>Title</h1><p>Hello world</p><script>bad()</script></body></html>"
    d = tempfile.mkdtemp()
    f = os.path.join(d, "x.html")
    with open(f, "w", encoding="utf-8") as fh:
        fh.write(html)
    txt = docio.extract_text(f)
    assert "Title" in txt and "Hello world" in txt and "bad()" not in txt
