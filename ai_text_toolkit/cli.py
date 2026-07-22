"""
Command-line interface for the AI Text Toolkit.

    python -m ai_text_toolkit detect   --file essay.txt
    python -m ai_text_toolkit detect   --text "some text here"
    python -m ai_text_toolkit humanize --file essay.txt --out clean.txt
    echo "some text" | python -m ai_text_toolkit humanize --stdin --strength strong
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import common, ai_detector, ai_humanizer


def _read_input(args) -> str:
    if args.stdin:
        return sys.stdin.read()
    try:
        return common.read_text_source(args.text, args.file)
    except (OSError, RuntimeError) as exc:
        # RuntimeError covers e.g. a PDF without pypdf installed.
        print(f"Could not read input: {exc}", file=sys.stderr)
        raise SystemExit(2)


def _output(text: str, out: str | None) -> None:
    if out:
        Path(out).write_text(text, encoding="utf-8")
        print(f"Wrote {len(text)} chars to {out}")
    else:
        print(text)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ai_text_toolkit",
        description="Open-source AI-text detector + humanizer (offline by default).",
    )
    sub = p.add_subparsers(dest="command", required=True)

    def add_common(sp):
        g = sp.add_mutually_exclusive_group(required=True)
        g.add_argument("--text", help="Literal text to process.")
        g.add_argument("--file", help="Read input from this file.")
        g.add_argument("--stdin", action="store_true", help="Read input from stdin.")
        sp.add_argument("--out", help="Write result to this file instead of stdout.")

    d = sub.add_parser("detect", help="Estimate AI-likelihood of text.")
    add_common(d)
    d.add_argument("--backend", choices=["auto", "heuristic", "model"], default="auto")

    h = sub.add_parser("humanize", help="Rewrite AI-sounding text to read naturally.")
    add_common(h)
    h.add_argument("--backend", choices=["auto", "rules", "model"], default="auto")
    h.add_argument("--strength", choices=["light", "medium", "strong"], default=None)
    h.add_argument("--report", action="store_true",
                   help="Show before/after AI-% and the exact before->after diff.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = common.load_config()
    text = _read_input(args)
    if not text.strip():
        print("No input text provided.", file=sys.stderr)
        return 2

    if args.command == "detect":
        result = ai_detector.detect(text, backend=args.backend, cfg=cfg)
        _output(result.as_text(), args.out)
    elif args.command == "humanize":
        if args.report:
            report = ai_humanizer.humanize_with_report(
                text, backend=args.backend, strength=args.strength, cfg=cfg)
            _output(report.as_text() if not args.out else report.humanized, args.out)
            if args.out:
                print(f"AI probability {report.before_pct:.0f}% -> "
                      f"{report.after_pct:.0f}% ({report.reduction_pct:+.0f} pts)")
        else:
            out = ai_humanizer.humanize(text, backend=args.backend,
                                        strength=args.strength, cfg=cfg)
            _output(out, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
