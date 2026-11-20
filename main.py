#!/usr/bin/env python3
"""Entry point wrapper so alarm-tui runs via `python3 main.py` or installed CLI."""

from __future__ import annotations

from alarm_tui.cli import build_arg_parser, main

__all__ = ["build_arg_parser", "main"]

if __name__ == "__main__":
    raise SystemExit(main())
