"""CLI entry point for alarm-tui: argument parsing, signal safety, and TUI lifecycle."""

from __future__ import annotations

import argparse
import atexit
import curses
import locale
import os
import signal
import sys
import threading
from types import FrameType

from . import __app_name__, __version__
from .audio import AudioController
from .config import ConfigError, load_config
from .i18n import SUPPORTED_LANGUAGES, Translator, detect_system_language, resolve_language
from .inhibitor import SleepInhibitor
from .ui import AlarmTUI


def build_arg_parser(help_lang: str) -> argparse.ArgumentParser:
    """Create CLI argument parser with localized help text."""
    tr = Translator(help_lang)
    parser = argparse.ArgumentParser(
        prog=__app_name__,
        description=tr.t("cli_description"),
    )
    parser.add_argument(
        "--lang",
        choices=SUPPORTED_LANGUAGES,
        default=None,
        help=tr.t("cli_lang_help"),
    )
    parser.add_argument(
        "--config",
        dest="config_path",
        default=None,
        help=tr.t("cli_config_help"),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help=tr.t("cli_version_help"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Initialize config, i18n, audio & sleep-inhibit guards, and run the curses TUI."""
    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:
        pass

    parser = build_arg_parser(detect_system_language())
    args = parser.parse_args(argv)

    try:
        load_result = load_config(args.config_path)
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    config = load_result.config
    try:
        lang = resolve_language(cli_lang=args.lang, config_lang=config.language)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    translator = Translator(lang)
    audio = AudioController(config)
    inhibitor = SleepInhibitor()
    shutdown_event = threading.Event()
    signal_exit_code = 0

    def _cleanup_all() -> None:
        inhibitor.cleanup()
        audio.cleanup()

    # Safety net: always release sleep lock, stop speaker-test, and restore volume (50%)
    atexit.register(_cleanup_all)

    def _handle_termination_signal(signum: int, _frame: FrameType | None) -> None:
        nonlocal signal_exit_code
        signal_exit_code = 128 + signum
        shutdown_event.set()
        audio.emergency_stop_process()
        inhibitor.emergency_stop()
        if signum == signal.SIGINT:
            raise KeyboardInterrupt
        raise SystemExit(signal_exit_code)

    prev_sigint = signal.signal(signal.SIGINT, _handle_termination_signal)
    prev_sigterm = signal.signal(signal.SIGTERM, _handle_termination_signal)

    # Make Esc key responsive in ncurses
    os.environ.setdefault("ESCDELAY", "25")

    tui = AlarmTUI(
        config=config,
        translator=translator,
        audio=audio,
        shutdown_event=shutdown_event,
        inhibitor=inhibitor,
        startup_warnings=load_result.warnings,
    )

    exit_code = 0
    try:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            print("Error: alarm-tui requires an interactive terminal (TTY).", file=sys.stderr)
            return 1
        exit_code = curses.wrapper(tui.run)
    except KeyboardInterrupt:
        exit_code = signal_exit_code or 130
    except SystemExit as exc:
        if isinstance(exc.code, int):
            exit_code = exc.code
        else:
            exit_code = signal_exit_code or 143
    except curses.error as exc:
        print(f"Terminal error: {exc}", file=sys.stderr)
        exit_code = 1
    finally:
        shutdown_event.set()
        _cleanup_all()
        atexit.unregister(_cleanup_all)
        signal.signal(signal.SIGINT, prev_sigint)
        signal.signal(signal.SIGTERM, prev_sigterm)

    return signal_exit_code if signal_exit_code else exit_code
