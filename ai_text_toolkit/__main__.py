"""Entry point:  python -m ai_text_toolkit <detect|humanize> ..."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
