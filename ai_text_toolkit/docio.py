"""
Document text extraction for the AI Text Toolkit.

Accepts "any type of document" and returns plain text for analysis.

Dependency-free for:  .txt .md .markdown .log .csv .tsv .html .htm .rtf .docx .odt
Optional (small, pure-Python):  .pdf  needs `pypdf`  ->  pip install pypdf
"""

from __future__ import annotations

import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

PLAIN_EXT = {".txt", ".text", ".md", ".markdown", ".log", ".csv", ".tsv", ""}
RICH_EXT = {".docx", ".odt", ".html", ".htm", ".rtf", ".pdf"}
SUPPORTED_EXT = PLAIN_EXT | RICH_EXT

_DOCX_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_ODT_TEXT_NS = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def _from_html(path: Path) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    return " ".join(parser.parts)


def _from_rtf(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    raw = re.sub(r"\\'[0-9a-fA-F]{2}", "", raw)          # hex-escaped chars
    raw = re.sub(r"\\[a-zA-Z]+-?\d* ?", " ", raw)         # control words -> space
    raw = raw.replace("{", "").replace("}", "")
    return re.sub(r"[ \t]+", " ", raw).strip()


def _from_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    paragraphs = []
    for p in root.iter(_DOCX_NS + "p"):
        text = "".join(t.text for t in p.iter(_DOCX_NS + "t") if t.text)
        if text.strip():
            paragraphs.append(text)
    return "\n".join(paragraphs)


def _from_odt(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("content.xml"))
    # Only real body text: paragraphs (p) and headings (h); itertext() pulls in
    # nested spans and (via ElementTree) decodes XML entities like &amp;.
    blocks = []
    for tag in ("p", "h"):
        for el in root.iter(_ODT_TEXT_NS + tag):
            text = "".join(el.itertext())
            if text.strip():
                blocks.append(text)
    return "\n".join(blocks)


def _from_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "Reading PDF needs the 'pypdf' package (small, pure-Python).\n"
            "Install with:  pip install pypdf"
        ) from exc
    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def extract_text(path: str | Path) -> str:
    """Extract plain text from a document of (almost) any common type.

    Parse failures (corrupt/mislabelled files) are normalised into a clean
    RuntimeError so callers get a friendly message instead of a raw
    BadZipFile/ParseError/KeyError traceback.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"No such file: {path}")

    ext = path.suffix.lower()
    try:
        if ext == ".docx":
            return _from_docx(path)
        if ext == ".odt":
            return _from_odt(path)
        if ext in (".html", ".htm"):
            return _from_html(path)
        if ext == ".rtf":
            return _from_rtf(path)
        if ext == ".pdf":
            return _from_pdf(path)
        # Plain text and unknown extensions: best-effort text read.
        return path.read_text(encoding="utf-8", errors="replace")
    except (OSError, RuntimeError):
        raise  # already a clean error (missing file, "pdf needs pypdf", ...)
    except Exception as exc:  # noqa: BLE001 - normalise parser errors for callers
        raise RuntimeError(
            f"Could not read '{path.name}' as {ext or 'text'}: {exc}"
        ) from exc
