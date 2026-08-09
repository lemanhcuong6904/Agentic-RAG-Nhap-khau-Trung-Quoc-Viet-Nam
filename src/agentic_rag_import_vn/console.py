from __future__ import annotations

import sys

from rich.console import Console


def make_console() -> Console:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass
    return Console(force_terminal=False, color_system=None)
