"""Centered curses TUI with drum pickers, mouse support, bedtime check, and alarm screens."""

from __future__ import annotations

import curses
import locale
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from .audio import AudioController
from .config import AlarmConfig, FrequencyPreset
from .i18n import Translator
from .inhibitor import SleepInhibitor
from .sleep import (
    AlarmMode,
    SleepPlan,
    apply_bedtime_check,
    calculate_cycles_wake_time,
    calculate_exact_wake_time,
    create_cycles_plan,
    create_exact_plan,
    create_snooze_plan,
    format_countdown,
    format_hm,
    format_hms,
    is_alarm_due,
    is_bedtime_check_due,
    time_remaining,
)

# Portable mouse wheel constants (BUTTON5_PRESSED may be absent on some builds)
_MOUSE_WHEEL_UP = getattr(curses, "BUTTON4_PRESSED", 0x10000)
_MOUSE_WHEEL_DOWN = getattr(curses, "BUTTON5_PRESSED", 0x200000)
_MOUSE_CLICK_MASK = curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED

_MIN_TERM_W = 64
_MIN_TERM_H = 20
_CARD_H = 20

_FALL_ASLEEP_MIN = 0
_FALL_ASLEEP_DEFAULT_MAX = 45
_FALL_ASLEEP_STEP = 5

_KEY_CTRL_L = 12  # Ctrl+L

_MANUAL_PRESET = FrequencyPreset(label_key="preset_manual", hz=-1)


class ScreenState(Enum):
    """Active TUI screen."""

    SETUP = "setup"
    WAITING = "waiting"
    BEDTIME_CHECK = "bedtime_check"
    RINGING = "ringing"


@dataclass(frozen=True)
class HitRect:
    """Clickable or scrollable rectangle in screen coordinates."""

    y: int
    x: int
    h: int
    w: int
    action: str
    payload: Any = None

    def contains(self, my: int, mx: int) -> bool:
        return self.y <= my < self.y + self.h and self.x <= mx < self.x + self.w


@dataclass(frozen=True)
class _BoxChars:
    tl: str
    tr: str
    bl: str
    br: str
    h: str
    v: str
    lt: str
    rt: str
    up: str
    down: str
    left_ptr: str
    right_ptr: str
    bar_fill: str
    bar_empty: str


_UNICODE_BOX = _BoxChars(
    tl="╭",
    tr="╮",
    bl="╰",
    br="╯",
    h="─",
    v="│",
    lt="├",
    rt="┤",
    up="▲",
    down="▼",
    left_ptr="▸",
    right_ptr="◂",
    bar_fill="█",
    bar_empty="░",
)

_ASCII_BOX = _BoxChars(
    tl="+",
    tr="+",
    bl="+",
    br="+",
    h="-",
    v="|",
    lt="+",
    rt="+",
    up="^",
    down="v",
    left_ptr=">",
    right_ptr="<",
    bar_fill="#",
    bar_empty="-",
)


def _supports_utf8() -> bool:
    encoding = locale.getpreferredencoding(False) or ""
    return "UTF-8" in encoding.upper() or "UTF8" in encoding.upper()


def _safe_addstr(win: curses.window, y: int, x: int, text: str, attr: int = 0) -> None:
    """Write text safely inside window boundaries, never writing the bottom-right cell."""
    max_y, max_x = win.getmaxyx()
    if y < 0 or y >= max_y or x >= max_x or not text:
        return
    if x < 0:
        text = text[-x:]
        x = 0
    avail = max_x - x
    if y == max_y - 1:
        avail -= 1
    if avail <= 0:
        return
    clipped = text[:avail]
    try:
        win.addstr(y, x, clipped, attr)
    except curses.error:
        pass


def _clip_center(text: str, width: int) -> str:
    if width <= 0:
        return ""
    if len(text) > width:
        if width <= 1:
            return text[:width]
        return text[: width - 1] + "…"
    return text.center(width)


class AlarmTUI:
    """Interactive centered curses interface for alarm-tui."""

    def __init__(
        self,
        config: AlarmConfig,
        translator: Translator,
        audio: AudioController,
        shutdown_event: threading.Event,
        inhibitor: SleepInhibitor | None = None,
        startup_warnings: list[str] | None = None,
    ) -> None:
        self._config = config
        self._tr = translator
        self._audio = audio
        self._inhibitor = inhibitor
        self._shutdown_event = shutdown_event
        self._box = _UNICODE_BOX if _supports_utf8() else _ASCII_BOX

        # Mode and picker state
        self._mode = AlarmMode.EXACT if config.default_mode == "exact" else AlarmMode.CYCLES
        self._cycles = config.default_cycles
        self._fall_asleep_minutes = config.fall_asleep_minutes
        self._fall_asleep_max = max(_FALL_ASLEEP_DEFAULT_MAX, config.fall_asleep_minutes)
        self._exact_hour = config.default_exact_hour
        self._exact_minute = config.default_exact_minute
        self._freq_hz = config.frequency_hz

        self._presets: tuple[FrequencyPreset, ...] = (*config.presets, _MANUAL_PRESET)
        self._preset_idx = self._find_preset_index_for_freq(self._freq_hz)
        self._focus_col = 0

        # Runtime state
        self._state = ScreenState.SETUP
        self._plan: SleepPlan | None = None
        self._bedtime_prompt_started: float = 0.0

        # Hit-testing regions rebuilt on each draw
        self._click_rects: list[HitRect] = []
        self._wheel_rects: list[HitRect] = []

        # Status banner (thread-safe for audio worker callbacks)
        self._status_lock = threading.Lock()
        self._status_msg: str = ""
        self._status_is_warn: bool = False
        self._init_startup_status(startup_warnings or [])

        # Color pair attributes (populated in _init_colors)
        self._attr_accent = curses.A_BOLD
        self._attr_warn = curses.A_BOLD
        self._attr_ok = curses.A_BOLD
        self._attr_alert = curses.A_BOLD
        self._attr_dim = curses.A_DIM
        self._attr_selected = curses.A_REVERSE | curses.A_BOLD
        self._attr_tab_active = curses.A_REVERSE | curses.A_BOLD
        self._attr_btn_primary = curses.A_REVERSE | curses.A_BOLD
        self._attr_btn_danger = curses.A_REVERSE | curses.A_BOLD

    def _init_startup_status(self, startup_warnings: list[str]) -> None:
        if not self._audio.speaker_test_available:
            self._set_status(self._tr.t("status_missing_speaker"), is_warn=True)
        elif not self._audio.wpctl_available:
            self._set_status(self._tr.t("status_missing_wpctl"), is_warn=True)
        elif startup_warnings:
            self._set_status(startup_warnings[0], is_warn=True)

    def _set_status(self, message: str, is_warn: bool = False) -> None:
        with self._status_lock:
            self._status_msg = message
            self._status_is_warn = is_warn

    def _get_status(self) -> tuple[str, bool]:
        with self._status_lock:
            return self._status_msg, self._status_is_warn

    def _init_colors(self) -> None:
        if not curses.has_colors():
            return
        try:
            curses.start_color()
            try:
                curses.use_default_colors()
                bg = -1
            except curses.error:
                bg = curses.COLOR_BLACK

            curses.init_pair(1, curses.COLOR_CYAN, bg)
            curses.init_pair(2, curses.COLOR_YELLOW, bg)
            curses.init_pair(3, curses.COLOR_GREEN, bg)
            curses.init_pair(4, curses.COLOR_RED, bg)
            curses.init_pair(5, curses.COLOR_WHITE, bg)
            curses.init_pair(6, curses.COLOR_BLACK, curses.COLOR_CYAN)
            curses.init_pair(7, curses.COLOR_BLACK, curses.COLOR_GREEN)
            curses.init_pair(8, curses.COLOR_WHITE, curses.COLOR_RED)

            self._attr_accent = curses.color_pair(1) | curses.A_BOLD
            self._attr_warn = curses.color_pair(2) | curses.A_BOLD
            self._attr_ok = curses.color_pair(3) | curses.A_BOLD
            self._attr_alert = curses.color_pair(4) | curses.A_BOLD
            self._attr_dim = curses.color_pair(5) | curses.A_DIM
            self._attr_selected = curses.color_pair(6) | curses.A_BOLD
            self._attr_tab_active = curses.color_pair(6) | curses.A_BOLD
            self._attr_btn_primary = curses.color_pair(7) | curses.A_BOLD
            self._attr_btn_danger = curses.color_pair(8) | curses.A_BOLD
        except curses.error:
            pass

    def _columns_for_mode(self) -> tuple[str, ...]:
        if self._mode == AlarmMode.CYCLES:
            return ("cycles", "fall_asleep", "preset", "freq")
        return ("hour", "minute", "preset", "freq")

    def _find_preset_index_for_freq(self, hz: int) -> int:
        for idx, preset in enumerate(self._presets):
            if preset.hz == hz:
                return idx
        return len(self._presets) - 1  # Manual

    def _preset_label(self, preset: FrequencyPreset) -> str:
        if preset.hz < 0:
            return self._tr.t("preset_manual")
        if preset.custom_label:
            return preset.custom_label
        name = self._tr.t(preset.label_key)
        return f"{name} {preset.hz}"

    def _step_column(self, col_id: str, delta: int, coarse: bool = False) -> None:
        if col_id == "cycles":
            span = self._config.max_cycles - self._config.min_cycles + 1
            offset = (self._cycles - self._config.min_cycles + delta) % span
            self._cycles = self._config.min_cycles + offset
        elif col_id == "fall_asleep":
            step = delta * (15 if coarse else _FALL_ASLEEP_STEP)
            new_val = self._fall_asleep_minutes + step
            self._fall_asleep_minutes = max(_FALL_ASLEEP_MIN, min(self._fall_asleep_max, new_val))
        elif col_id == "hour":
            step = delta * (3 if coarse else 1)
            self._exact_hour = (self._exact_hour + step) % 24
        elif col_id == "minute":
            step = delta * (5 if coarse else 1)
            self._exact_minute = (self._exact_minute + step) % 60
        elif col_id == "preset":
            self._preset_idx = (self._preset_idx + delta) % len(self._presets)
            chosen = self._presets[self._preset_idx]
            if chosen.hz > 0:
                self._freq_hz = chosen.hz
        elif col_id == "freq":
            base_step = self._config.frequency_step_hz * (4 if coarse else 1)
            new_hz = self._freq_hz + delta * base_step
            self._freq_hz = max(
                self._config.min_frequency_hz,
                min(self._config.max_frequency_hz, new_hz),
            )
            self._preset_idx = self._find_preset_index_for_freq(self._freq_hz)

    def _drum_triplet(self, col_id: str) -> tuple[str, str, str]:
        if col_id == "cycles":
            span = self._config.max_cycles - self._config.min_cycles + 1
            prev_v = self._config.min_cycles + (self._cycles - self._config.min_cycles - 1) % span
            next_v = self._config.min_cycles + (self._cycles - self._config.min_cycles + 1) % span
            return (
                self._tr.t("cycles_item", n=prev_v),
                self._tr.t("cycles_item", n=self._cycles),
                self._tr.t("cycles_item", n=next_v),
            )
        if col_id == "fall_asleep":
            prev_m = self._fall_asleep_minutes - _FALL_ASLEEP_STEP
            next_m = self._fall_asleep_minutes + _FALL_ASLEEP_STEP
            prev_str = (
                self._tr.t("fall_asleep_item", m=prev_m) if prev_m >= _FALL_ASLEEP_MIN else "---"
            )
            curr_str = self._tr.t("fall_asleep_item", m=self._fall_asleep_minutes)
            next_str = (
                self._tr.t("fall_asleep_item", m=next_m) if next_m <= self._fall_asleep_max else "---"
            )
            return prev_str, curr_str, next_str
        if col_id == "hour":
            return (
                f"{(self._exact_hour - 1) % 24:02d}",
                f"{self._exact_hour:02d}",
                f"{(self._exact_hour + 1) % 24:02d}",
            )
        if col_id == "minute":
            return (
                f"{(self._exact_minute - 1) % 60:02d}",
                f"{self._exact_minute:02d}",
                f"{(self._exact_minute + 1) % 60:02d}",
            )
        if col_id == "preset":
            n = len(self._presets)
            prev_p = self._presets[(self._preset_idx - 1) % n]
            curr_p = self._presets[self._preset_idx]
            next_p = self._presets[(self._preset_idx + 1) % n]
            return (
                self._preset_label(prev_p),
                self._preset_label(curr_p),
                self._preset_label(next_p),
            )
        # freq
        step = self._config.frequency_step_hz
        prev_hz = self._freq_hz - step
        next_hz = self._freq_hz + step
        prev_str = (
            self._tr.t("freq_item", hz=prev_hz)
            if prev_hz >= self._config.min_frequency_hz
            else "---"
        )
        curr_str = self._tr.t("freq_item", hz=self._freq_hz)
        next_str = (
            self._tr.t("freq_item", hz=next_hz)
            if next_hz <= self._config.max_frequency_hz
            else "---"
        )
        return prev_str, curr_str, next_str

    def _toggle_mode(self, target: AlarmMode | None = None) -> None:
        if target is None:
            self._mode = AlarmMode.EXACT if self._mode == AlarmMode.CYCLES else AlarmMode.CYCLES
        else:
            self._mode = target
        cols = self._columns_for_mode()
        self._focus_col = min(self._focus_col, len(cols) - 1)

    def _acquire_sleep_inhibit(self) -> None:
        if self._inhibitor is None:
            return
        acquired = self._inhibitor.acquire()
        if not acquired and not self._inhibitor.available:
            self._set_status(self._tr.t("status_missing_inhibit"), is_warn=True)

    def _release_sleep_inhibit(self) -> None:
        if self._inhibitor is not None:
            self._inhibitor.release()

    def _trigger_sound_test(self) -> None:
        status = self._audio.get_status()
        if status.is_testing:
            self._audio.stop_test()
            self._set_status(
                self._tr.t("status_test_stopped", vol=self._config.restore_vol),
                is_warn=False,
            )
            return

        if not status.speaker_test_available:
            self._set_status(self._tr.t("status_missing_speaker"), is_warn=True)
            return

        freq = self._freq_hz
        dur = self._config.test_sound_duration_sec
        self._set_status(self._tr.t("status_testing", freq=freq, sec=dur), is_warn=False)

        def _on_done(completed: bool) -> None:
            key = "status_test_done" if completed else "status_test_stopped"
            self._set_status(self._tr.t(key, vol=self._config.restore_vol), is_warn=False)

        self._audio.test_sound(freq_hz=freq, duration_sec=dur, on_finish=_on_done)

    def _start_alarm(self) -> None:
        self._audio.stop_test()
        now = datetime.now()
        if self._mode == AlarmMode.CYCLES:
            self._plan = create_cycles_plan(
                cycles=self._cycles,
                cycle_minutes=self._config.cycle_minutes,
                fall_asleep_minutes=self._fall_asleep_minutes,
                bedtime_check_enabled=self._config.bedtime_check_enabled,
                bedtime_check_delay_minutes=self._config.bedtime_check_delay_minutes,
                bedtime_shift_minutes=self._config.bedtime_shift_minutes,
                now=now,
            )
        else:
            self._plan = create_exact_plan(
                hour=self._exact_hour,
                minute=self._exact_minute,
                bedtime_shift_minutes=self._config.bedtime_shift_minutes,
                now=now,
            )
        self._state = ScreenState.WAITING
        self._set_status("", is_warn=False)
        self._acquire_sleep_inhibit()

    def _open_bedtime_check(self) -> None:
        if self._plan is None:
            return
        self._state = ScreenState.BEDTIME_CHECK
        self._bedtime_prompt_started = time.monotonic()

    def _answer_bedtime_check(self, went_to_sleep: bool) -> None:
        if self._plan is None:
            self._state = ScreenState.SETUP
            self._release_sleep_inhibit()
            return
        self._plan = apply_bedtime_check(
            self._plan,
            went_to_sleep=went_to_sleep,
            now=datetime.now(),
            shift_minutes=self._config.bedtime_shift_minutes,
        )
        self._state = ScreenState.WAITING
        if went_to_sleep:
            self._set_status(self._tr.t("status_bedtime_confirmed"), is_warn=False)
        else:
            self._set_status(
                self._tr.t(
                    "status_shifted",
                    min=self._config.bedtime_shift_minutes,
                    time=format_hm(self._plan.target_time),
                ),
                is_warn=False,
            )

    def _enter_ringing(self) -> None:
        self._state = ScreenState.RINGING
        started = self._audio.start_siren(freq_hz=self._freq_hz)
        if not started:
            self._set_status(self._tr.t("status_missing_speaker_ringing"), is_warn=True)
        else:
            self._set_status("", is_warn=False)

    def _dismiss_alarm(self) -> None:
        self._audio.stop_siren()
        self._release_sleep_inhibit()
        self._plan = None
        self._state = ScreenState.SETUP
        self._set_status(
            self._tr.t("status_alarm_stopped", vol=self._config.restore_vol),
            is_warn=False,
        )

    def _snooze_alarm(self) -> None:
        self._audio.stop_siren()
        if self._plan is None:
            self._release_sleep_inhibit()
            self._state = ScreenState.SETUP
            return
        self._plan = create_snooze_plan(
            self._plan,
            snooze_minutes=self._config.snooze_minutes,
            now=datetime.now(),
        )
        self._state = ScreenState.WAITING
        self._acquire_sleep_inhibit()
        self._set_status(
            self._tr.t(
                "status_snoozed",
                min=self._config.snooze_minutes,
                time=format_hm(self._plan.target_time),
            ),
            is_warn=False,
        )

    def _return_to_setup(self) -> None:
        self._audio.stop_all(restore_vol=True)
        self._release_sleep_inhibit()
        self._plan = None
        self._state = ScreenState.SETUP

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _draw_card_frame(
        self,
        stdscr: curses.window,
        top: int,
        left: int,
        width: int,
        height: int,
        title: str,
        border_attr: int,
        show_lang_badge: bool = True,
    ) -> None:
        b = self._box
        inner_w = width - 2

        # Top border with centered title
        title_block = f" {title} "
        if len(title_block) > inner_w - 4:
            title_block = title_block[: max(0, inner_w - 4)]
        left_fill = max(1, (inner_w - len(title_block)) // 2)
        right_fill = max(0, inner_w - left_fill - len(title_block))
        top_line = f"{b.tl}{b.h * left_fill}{title_block}{b.h * right_fill}{b.tr}"
        _safe_addstr(stdscr, top, left, top_line, border_attr)

        # Clickable language badge in top-right corner
        if show_lang_badge and inner_w >= 28:
            badge = f" {self._tr.t('lang_badge')} "
            bx = left + width - len(badge) - 2
            _safe_addstr(stdscr, top, bx, badge, self._attr_dim | curses.A_BOLD)
            self._click_rects.append(HitRect(top, bx, 1, len(badge), "cycle_lang"))

        # Side borders
        for row in range(1, height - 1):
            _safe_addstr(stdscr, top + row, left, b.v, border_attr)
            _safe_addstr(stdscr, top + row, left + width - 1, b.v, border_attr)

        # Bottom border
        bot_line = f"{b.bl}{b.h * inner_w}{b.br}"
        _safe_addstr(stdscr, top + height - 1, left, bot_line, border_attr)

    def _draw_divider(
        self,
        stdscr: curses.window,
        y: int,
        left: int,
        width: int,
        attr: int,
    ) -> None:
        b = self._box
        _safe_addstr(stdscr, y, left, f"{b.lt}{b.h * (width - 2)}{b.rt}", attr)

    def _draw_button(
        self,
        stdscr: curses.window,
        y: int,
        x: int,
        label: str,
        attr: int,
        action: str,
        payload: Any = None,
    ) -> int:
        padded = f" {label} "
        _safe_addstr(stdscr, y, x, padded, attr)
        self._click_rects.append(HitRect(y, x, 1, len(padded), action, payload))
        return len(padded)

    def _draw_drum(
        self,
        stdscr: curses.window,
        top: int,
        left: int,
        width: int,
        col_id: str,
        header: str,
        focused: bool,
    ) -> None:
        b = self._box
        prev_txt, curr_txt, next_txt = self._drum_triplet(col_id)

        # Header
        hdr_attr = self._attr_accent if focused else self._attr_dim
        _safe_addstr(stdscr, top, left, _clip_center(header, width), hdr_attr)

        # Up arrow row
        up_attr = self._attr_accent if focused else self._attr_dim
        _safe_addstr(stdscr, top + 1, left, _clip_center(b.up, width), up_attr)
        self._click_rects.append(HitRect(top + 1, left, 1, width, "drum_step", (col_id, -1)))

        # Previous value row
        _safe_addstr(stdscr, top + 2, left, _clip_center(prev_txt, width), self._attr_dim)
        self._click_rects.append(HitRect(top + 2, left, 1, width, "drum_step", (col_id, -1)))

        # Current value row (highlighted)
        if focused:
            inner = max(1, width - 2)
            centered = _clip_center(curr_txt, inner)
            display = f"{b.left_ptr}{centered}{b.right_ptr}"
            curr_attr = self._attr_selected
        else:
            display = _clip_center(curr_txt, width)
            curr_attr = curses.A_BOLD
        _safe_addstr(stdscr, top + 3, left, display, curr_attr)
        self._click_rects.append(HitRect(top + 3, left, 1, width, "drum_focus", col_id))

        # Next value row
        _safe_addstr(stdscr, top + 4, left, _clip_center(next_txt, width), self._attr_dim)
        self._click_rects.append(HitRect(top + 4, left, 1, width, "drum_step", (col_id, 1)))

        # Down arrow row
        _safe_addstr(stdscr, top + 5, left, _clip_center(b.down, width), up_attr)
        self._click_rects.append(HitRect(top + 5, left, 1, width, "drum_step", (col_id, 1)))

        # Register whole drum area for mouse wheel scrolling
        self._wheel_rects.append(HitRect(top, left, 6, width, "drum_wheel", col_id))

    def _draw_setup(
        self,
        stdscr: curses.window,
        top: int,
        left: int,
        width: int,
        height: int,
    ) -> None:
        inner_w = width - 4
        inner_x = left + 2
        self._draw_card_frame(
            stdscr, top, left, width, height, self._tr.t("app_title"), self._attr_accent
        )

        # Mode tabs (row 2)
        cycles_lbl = f"  {self._tr.t('mode_cycles')}  "
        exact_lbl = f"  {self._tr.t('mode_exact')}  "
        gap = 3
        total_tabs_w = len(cycles_lbl) + gap + len(exact_lbl)
        tab_x = left + max(2, (width - total_tabs_w) // 2)

        cyc_attr = self._attr_tab_active if self._mode == AlarmMode.CYCLES else self._attr_dim
        ex_attr = self._attr_tab_active if self._mode == AlarmMode.EXACT else self._attr_dim

        _safe_addstr(stdscr, top + 2, tab_x, cycles_lbl, cyc_attr)
        self._click_rects.append(HitRect(top + 2, tab_x, 1, len(cycles_lbl), "set_mode", AlarmMode.CYCLES))

        ex_x = tab_x + len(cycles_lbl) + gap
        _safe_addstr(stdscr, top + 2, ex_x, exact_lbl, ex_attr)
        self._click_rects.append(HitRect(top + 2, ex_x, 1, len(exact_lbl), "set_mode", AlarmMode.EXACT))

        self._draw_divider(stdscr, top + 3, left, width, self._attr_dim)

        # Drum pickers (rows 5..10)
        drum_top = top + 5

        if self._mode == AlarmMode.CYCLES:
            # Cycles | Fall Asleep | Preset | Freq
            cyc_w = max(9, inner_w // 6)
            fall_w = max(10, inner_w // 6)
            col_gap = 2
            rest_w = inner_w - (cyc_w + fall_w + col_gap * 3)
            preset_w = max(14, int(rest_w * 0.56))
            freq_w = max(12, rest_w - preset_w)
            total_w = cyc_w + fall_w + preset_w + freq_w + col_gap * 3
            cx = left + max(2, (width - total_w) // 2)

            self._draw_drum(stdscr, drum_top, cx, cyc_w, "cycles", self._tr.t("col_cycles"), self._focus_col == 0)

            fall_x = cx + cyc_w + col_gap
            self._draw_drum(
                stdscr, drum_top, fall_x, fall_w, "fall_asleep", self._tr.t("col_fall_asleep"), self._focus_col == 1
            )

            pre_x = fall_x + fall_w + col_gap
            self._draw_drum(stdscr, drum_top, pre_x, preset_w, "preset", self._tr.t("col_preset"), self._focus_col == 2)

            frq_x = pre_x + preset_w + col_gap
            self._draw_drum(stdscr, drum_top, frq_x, freq_w, "freq", self._tr.t("col_freq"), self._focus_col == 3)
        else:
            # Exact time: Hour : Min | Preset | Freq
            hm_w = max(8, inner_w // 6)
            colon_w = 3
            rest_w = inner_w - (hm_w * 2 + colon_w + 4)
            preset_w = max(14, int(rest_w * 0.56))
            freq_w = max(12, rest_w - preset_w)
            total_w = hm_w * 2 + colon_w + preset_w + freq_w + 4
            cx = left + max(2, (width - total_w) // 2)

            self._draw_drum(stdscr, drum_top, cx, hm_w, "hour", self._tr.t("col_hour"), self._focus_col == 0)
            colon_x = cx + hm_w
            _safe_addstr(stdscr, drum_top + 3, colon_x, " : ", self._attr_accent)

            min_x = colon_x + colon_w
            self._draw_drum(stdscr, drum_top, min_x, hm_w, "minute", self._tr.t("col_minute"), self._focus_col == 1)

            pre_x = min_x + hm_w + 2
            self._draw_drum(stdscr, drum_top, pre_x, preset_w, "preset", self._tr.t("col_preset"), self._focus_col == 2)

            frq_x = pre_x + preset_w + 2
            self._draw_drum(stdscr, drum_top, frq_x, freq_w, "freq", self._tr.t("col_freq"), self._focus_col == 3)

        self._draw_divider(stdscr, top + 12, left, width, self._attr_dim)

        # Live wake-time preview (rows 13..15)
        now = datetime.now()
        if self._mode == AlarmMode.CYCLES:
            target = calculate_cycles_wake_time(
                now=now,
                cycles=self._cycles,
                cycle_minutes=self._config.cycle_minutes,
                fall_asleep_minutes=self._fall_asleep_minutes,
            )
            is_tomorrow = target.date() > now.date()
            day_tag = self._tr.t("preview_tomorrow") if is_tomorrow else self._tr.t("preview_today")
            wake_line = f"{self._tr.t('preview_wake', time=format_hm(target))} {day_tag}"
            total_min = self._cycles * self._config.cycle_minutes + self._fall_asleep_minutes
            detail_line = self._tr.t(
                "preview_cycles_detail",
                cycles=self._cycles,
                cycle_min=self._config.cycle_minutes,
                fall_min=self._fall_asleep_minutes,
                total=self._tr.format_duration_minutes(total_min),
            )
        else:
            target, is_tomorrow = calculate_exact_wake_time(
                now=now, hour=self._exact_hour, minute=self._exact_minute
            )
            day_tag = self._tr.t("preview_tomorrow") if is_tomorrow else self._tr.t("preview_today")
            wake_line = f"{self._tr.t('preview_wake', time=format_hm(target))} {day_tag}"
            rem_min = max(1, int(time_remaining(target, now).total_seconds() // 60))
            detail_line = self._tr.t(
                "preview_exact_detail",
                remaining=self._tr.format_duration_minutes(rem_min),
            )

        audio_line = self._tr.t(
            "preview_audio_detail",
            freq=self._freq_hz,
            start=self._config.start_vol,
            max=self._config.max_vol,
            step=self._config.step_vol,
            sec=f"{self._config.step_sec:g}",
            restore=self._config.restore_vol,
        )

        _safe_addstr(stdscr, top + 13, inner_x, _clip_center(wake_line, inner_w), self._attr_warn)
        _safe_addstr(stdscr, top + 14, inner_x, _clip_center(detail_line, inner_w), curses.A_NORMAL)
        _safe_addstr(stdscr, top + 15, inner_x, _clip_center(audio_line, inner_w), self._attr_dim)

        self._draw_divider(stdscr, top + 16, left, width, self._attr_dim)

        # Action buttons (row 17)
        audio_status = self._audio.get_status()
        test_lbl = (
            self._tr.t("btn_testing")
            if audio_status.is_testing
            else self._tr.t("btn_test", sec=f"{self._config.test_sound_duration_sec:g}")
        )
        start_lbl = self._tr.t("btn_start")
        quit_lbl = self._tr.t("btn_quit")

        btn_gap = 3
        total_btn_w = (len(test_lbl) + 2) + (len(start_lbl) + 2) + (len(quit_lbl) + 2) + btn_gap * 2
        bx = left + max(2, (width - total_btn_w) // 2)

        test_attr = self._attr_warn if audio_status.is_testing else self._attr_accent
        bx += self._draw_button(stdscr, top + 17, bx, test_lbl, test_attr, "test_sound") + btn_gap
        bx += self._draw_button(stdscr, top + 17, bx, start_lbl, self._attr_btn_primary, "start_alarm") + btn_gap
        self._draw_button(stdscr, top + 17, bx, quit_lbl, self._attr_dim | curses.A_BOLD, "quit")

        # Status line (row 18)
        msg, is_warn = self._get_status()
        if msg:
            s_attr = self._attr_warn if is_warn else self._attr_ok
            _safe_addstr(stdscr, top + 18, inner_x, _clip_center(msg, inner_w), s_attr)

    def _draw_waiting(
        self,
        stdscr: curses.window,
        top: int,
        left: int,
        width: int,
        height: int,
    ) -> None:
        if self._plan is None:
            return
        inner_w = width - 4
        inner_x = left + 2
        now = datetime.now()
        rem = time_remaining(self._plan.target_time, now)

        self._draw_card_frame(
            stdscr, top, left, width, height, self._tr.t("waiting_title"), self._attr_ok
        )

        # Now & target header
        now_txt = self._tr.t("waiting_now", now=format_hms(now))
        tgt_txt = self._tr.t("waiting_target", target=format_hm(self._plan.target_time))
        _safe_addstr(stdscr, top + 2, inner_x, _clip_center(f"{now_txt}     •     {tgt_txt}", inner_w), curses.A_BOLD)
        self._draw_divider(stdscr, top + 3, left, width, self._attr_dim)

        # Large countdown block
        _safe_addstr(stdscr, top + 5, inner_x, _clip_center(self._tr.t("waiting_remaining"), inner_w), self._attr_dim)
        countdown_str = f"  {format_countdown(rem)}  "
        _safe_addstr(stdscr, top + 7, inner_x, _clip_center(countdown_str, inner_w), self._attr_warn)

        # Mode + bedtime status + sleep inhibit info
        if self._plan.mode == AlarmMode.CYCLES and self._plan.cycles is not None:
            mode_line = self._tr.t(
                "waiting_mode_cycles",
                cycles=self._plan.cycles,
                cycle_min=self._plan.cycle_minutes,
                fall_min=self._plan.fall_asleep_minutes,
            )
        else:
            mode_line = self._tr.t("waiting_mode_exact")
        _safe_addstr(stdscr, top + 10, inner_x, _clip_center(mode_line, inner_w), curses.A_NORMAL)

        if self._plan.next_bedtime_check is not None and not self._plan.bedtime_confirmed:
            bed_line = self._tr.t("waiting_next_check", time=format_hm(self._plan.next_bedtime_check))
            bed_attr = self._attr_accent
        else:
            bed_line = self._tr.t("waiting_confirmed")
            bed_attr = self._attr_ok
        if self._plan.shifts_count > 0:
            shift_txt = self._tr.t(
                "waiting_shifts",
                count=self._plan.shifts_count,
                total_min=self._plan.shifts_count * self._plan.bedtime_shift_minutes,
            )
            bed_line = f"{bed_line}  •  {shift_txt}"
        if self._inhibitor is not None:
            lock_txt = (
                self._tr.t("waiting_inhibit_on")
                if self._inhibitor.active
                else self._tr.t("waiting_inhibit_off")
            )
            bed_line = f"{bed_line}  •  {lock_txt}"
        _safe_addstr(stdscr, top + 12, inner_x, _clip_center(bed_line, inner_w), bed_attr)

        audio_line = self._tr.t(
            "preview_audio_detail",
            freq=self._freq_hz,
            start=self._config.start_vol,
            max=self._config.max_vol,
            step=self._config.step_vol,
            sec=f"{self._config.step_sec:g}",
            restore=self._config.restore_vol,
        )
        _safe_addstr(stdscr, top + 14, inner_x, _clip_center(audio_line, inner_w), self._attr_dim)

        self._draw_divider(stdscr, top + 16, left, width, self._attr_dim)

        # Buttons
        awake_lbl = self._tr.t("btn_still_awake", min=self._config.bedtime_shift_minutes)
        back_lbl = self._tr.t("btn_back")
        quit_lbl = self._tr.t("btn_quit")
        gap = 3
        total_w = (len(awake_lbl) + 2) + (len(back_lbl) + 2) + (len(quit_lbl) + 2) + gap * 2
        bx = left + max(2, (width - total_w) // 2)
        bx += self._draw_button(stdscr, top + 17, bx, awake_lbl, self._attr_warn, "open_bedtime") + gap
        bx += self._draw_button(stdscr, top + 17, bx, back_lbl, self._attr_accent, "back_setup") + gap
        self._draw_button(stdscr, top + 17, bx, quit_lbl, self._attr_dim | curses.A_BOLD, "quit")

        msg, is_warn = self._get_status()
        if msg:
            _safe_addstr(stdscr, top + 18, inner_x, _clip_center(msg, inner_w), self._attr_warn if is_warn else self._attr_ok)

    def _draw_bedtime_check(
        self,
        stdscr: curses.window,
        top: int,
        left: int,
        width: int,
        height: int,
    ) -> None:
        if self._plan is None:
            return
        inner_w = width - 4
        inner_x = left + 2
        elapsed = time.monotonic() - self._bedtime_prompt_started
        rem_sec = max(0, int(self._config.bedtime_check_timeout_sec - elapsed))

        self._draw_card_frame(
            stdscr, top, left, width, height, self._tr.t("bedtime_title"), self._attr_warn
        )

        _safe_addstr(stdscr, top + 4, inner_x, _clip_center(self._tr.t("bedtime_question"), inner_w), self._attr_warn)
        _safe_addstr(
            stdscr,
            top + 6,
            inner_x,
            _clip_center(self._tr.t("bedtime_subtitle", min=self._config.bedtime_shift_minutes), inner_w),
            curses.A_NORMAL,
        )

        # Countdown info
        now = datetime.now()
        rem = time_remaining(self._plan.target_time, now)
        target_info = (
            f"{self._tr.t('waiting_target', target=format_hm(self._plan.target_time))}"
            f"  ({format_countdown(rem)})"
        )
        _safe_addstr(stdscr, top + 9, inner_x, _clip_center(target_info, inner_w), self._attr_accent)

        auto_line = self._tr.t(
            "bedtime_auto_confirm",
            sec=rem_sec,
            time=format_hm(self._plan.target_time),
        )
        _safe_addstr(stdscr, top + 11, inner_x, _clip_center(auto_line, inner_w), self._attr_dim)

        self._draw_divider(stdscr, top + 14, left, width, self._attr_dim)

        yes_lbl = self._tr.t("btn_yes")
        no_lbl = self._tr.t("btn_no", min=self._config.bedtime_shift_minutes)
        gap = 4
        total_w = (len(yes_lbl) + 2) + (len(no_lbl) + 2) + gap
        bx = left + max(2, (width - total_w) // 2)
        bx += self._draw_button(stdscr, top + 16, bx, yes_lbl, self._attr_btn_primary, "bedtime_yes") + gap
        self._draw_button(stdscr, top + 16, bx, no_lbl, self._attr_warn | curses.A_REVERSE, "bedtime_no")

    def _draw_ringing(
        self,
        stdscr: curses.window,
        top: int,
        left: int,
        width: int,
        height: int,
    ) -> None:
        inner_w = width - 4
        inner_x = left + 2
        pulse = int(time.monotonic() * 2) % 2 == 0
        border_attr = self._attr_alert if pulse else self._attr_warn

        self._draw_card_frame(
            stdscr,
            top,
            left,
            width,
            height,
            self._tr.t("ringing_title"),
            border_attr,
            show_lang_badge=False,
        )

        # Pulsing wake banner
        banner = f"***  {self._tr.t('ringing_title')}  ***"
        banner_attr = self._attr_btn_danger if pulse else self._attr_alert
        _safe_addstr(stdscr, top + 3, inner_x, _clip_center(banner, inner_w), banner_attr)

        target_str = format_hm(self._plan.target_time) if self._plan else format_hm(datetime.now())
        _safe_addstr(
            stdscr,
            top + 5,
            inner_x,
            _clip_center(self._tr.t("ringing_subtitle", time=target_str), inner_w),
            curses.A_BOLD,
        )

        # Audio status & volume ramp bar
        audio_status = self._audio.get_status()
        vol = audio_status.current_vol
        max_vol = max(1, self._config.max_vol)
        ratio = max(0.0, min(1.0, vol / max_vol))
        bar_w = min(36, max(16, inner_w - 16))
        filled = int(round(bar_w * ratio))
        bar = f"[{self._box.bar_fill * filled}{self._box.bar_empty * (bar_w - filled)}]"

        vol_txt = self._tr.t("ringing_volume", vol=vol, max=max_vol)
        freq_txt = self._tr.t("ringing_freq", freq=self._freq_hz)
        _safe_addstr(stdscr, top + 8, inner_x, _clip_center(vol_txt, inner_w), self._attr_warn)
        _safe_addstr(stdscr, top + 9, inner_x, _clip_center(bar, inner_w), self._attr_alert)
        _safe_addstr(stdscr, top + 11, inner_x, _clip_center(freq_txt, inner_w), self._attr_accent)
        _safe_addstr(
            stdscr,
            top + 13,
            inner_x,
            _clip_center(self._tr.t("ringing_restore_note", restore=self._config.restore_vol), inner_w),
            self._attr_dim,
        )

        self._draw_divider(stdscr, top + 15, left, width, border_attr)

        stop_lbl = self._tr.t("btn_stop_alarm")
        snooze_lbl = self._tr.t("btn_snooze", min=self._config.snooze_minutes)
        gap = 3
        total_w = (len(stop_lbl) + 2) + (len(snooze_lbl) + 2) + gap
        bx = left + max(2, (width - total_w) // 2)
        bx += self._draw_button(stdscr, top + 17, bx, stop_lbl, self._attr_btn_danger, "stop_alarm") + gap
        self._draw_button(stdscr, top + 17, bx, snooze_lbl, self._attr_accent, "snooze_alarm")

        # Explicit missing-audio warning or status on ringing screen (row 18)
        if not audio_status.speaker_test_available:
            _safe_addstr(
                stdscr,
                top + 18,
                inner_x,
                _clip_center(self._tr.t("status_missing_speaker_ringing"), inner_w),
                self._attr_alert,
            )
        else:
            msg, is_warn = self._get_status()
            if msg:
                _safe_addstr(
                    stdscr,
                    top + 18,
                    inner_x,
                    _clip_center(msg, inner_w),
                    self._attr_warn if is_warn else self._attr_ok,
                )

    def _draw_small_terminal(self, stdscr: curses.window, max_y: int, max_x: int) -> None:
        msg1 = self._tr.t(
            "terminal_too_small",
            cols=max_x,
            rows=max_y,
            min_w=_MIN_TERM_W,
            min_h=_MIN_TERM_H,
        )
        msg2 = self._tr.t("terminal_resize_hint")
        mid_y = max(0, max_y // 2 - 1)
        _safe_addstr(stdscr, mid_y, 0, _clip_center(msg1, max_x), self._attr_warn)
        if mid_y + 1 < max_y:
            _safe_addstr(stdscr, mid_y + 1, 0, _clip_center(msg2, max_x), self._attr_dim)

    def _render(self, stdscr: curses.window) -> None:
        self._click_rects.clear()
        self._wheel_rects.clear()
        stdscr.erase()
        max_y, max_x = stdscr.getmaxyx()

        if max_x < _MIN_TERM_W or max_y < _MIN_TERM_H:
            self._draw_small_terminal(stdscr, max_y, max_x)
            stdscr.noutrefresh()
            curses.doupdate()
            return

        card_w = min(74, max_x - 2)
        card_h = _CARD_H
        top = max(0, (max_y - card_h - 1) // 2)
        left = max(0, (max_x - card_w) // 2)

        if self._state == ScreenState.SETUP:
            self._draw_setup(stdscr, top, left, card_w, card_h)
            hint = self._tr.t("hint_setup")
        elif self._state == ScreenState.WAITING:
            self._draw_waiting(stdscr, top, left, card_w, card_h)
            hint = self._tr.t("hint_waiting")
        elif self._state == ScreenState.BEDTIME_CHECK:
            self._draw_bedtime_check(stdscr, top, left, card_w, card_h)
            hint = self._tr.t("hint_bedtime", min=self._config.bedtime_shift_minutes)
        else:
            self._draw_ringing(stdscr, top, left, card_w, card_h)
            hint = self._tr.t("hint_ringing", min=self._config.snooze_minutes)

        hint_y = top + card_h
        if hint_y < max_y:
            _safe_addstr(stdscr, hint_y, 0, _clip_center(hint, max_x), self._attr_dim)

        stdscr.noutrefresh()
        curses.doupdate()

    # ------------------------------------------------------------------
    # Input Handling
    # ------------------------------------------------------------------

    def _dispatch_action(self, action: str, payload: Any = None) -> bool:
        """Execute a UI action; return True if the application should exit."""
        if action == "quit":
            return True
        if action == "cycle_lang":
            self._tr.cycle_language()
        elif action == "set_mode" and self._state == ScreenState.SETUP:
            self._toggle_mode(payload)
        elif action == "drum_focus" and self._state == ScreenState.SETUP:
            cols = self._columns_for_mode()
            if payload in cols:
                self._focus_col = cols.index(payload)
        elif action == "drum_step" and self._state == ScreenState.SETUP:
            col_id, delta = payload
            cols = self._columns_for_mode()
            if col_id in cols:
                self._focus_col = cols.index(col_id)
                self._step_column(col_id, delta)
        elif action == "test_sound":
            self._trigger_sound_test()
        elif action == "start_alarm" and self._state == ScreenState.SETUP:
            self._start_alarm()
        elif action == "open_bedtime" and self._state == ScreenState.WAITING:
            self._open_bedtime_check()
        elif action == "back_setup" and self._state in (ScreenState.WAITING, ScreenState.BEDTIME_CHECK):
            self._return_to_setup()
        elif action == "bedtime_yes" and self._state == ScreenState.BEDTIME_CHECK:
            self._answer_bedtime_check(True)
        elif action == "bedtime_no" and self._state == ScreenState.BEDTIME_CHECK:
            self._answer_bedtime_check(False)
        elif action == "stop_alarm" and self._state == ScreenState.RINGING:
            self._dismiss_alarm()
        elif action == "snooze_alarm" and self._state == ScreenState.RINGING:
            self._snooze_alarm()
        return False

    def _handle_mouse(self) -> bool:
        try:
            _, mx, my, _, bstate = curses.getmouse()
        except curses.error:
            return False

        # Wheel scroll (BUTTON4 = up / prev, BUTTON5 = down / next)
        if self._state == ScreenState.SETUP:
            wheel_delta = 0
            if bstate & _MOUSE_WHEEL_UP:
                wheel_delta = -1
            elif bstate & _MOUSE_WHEEL_DOWN:
                wheel_delta = 1

            if wheel_delta != 0:
                cols = self._columns_for_mode()
                for rect in self._wheel_rects:
                    if rect.contains(my, mx):
                        col_id = rect.payload
                        if col_id in cols:
                            self._focus_col = cols.index(col_id)
                            self._step_column(col_id, wheel_delta)
                            return False
                # Scroll outside a specific drum adjusts the focused drum
                if cols:
                    self._step_column(cols[self._focus_col], wheel_delta)
                return False

        # Left click
        if bstate & _MOUSE_CLICK_MASK:
            for rect in self._click_rects:
                if rect.contains(my, mx):
                    return self._dispatch_action(rect.action, rect.payload)

        return False

    def _handle_key(self, ch: int) -> bool:
        if ch == -1 or ch == curses.KEY_RESIZE:
            return False
        if ch == curses.KEY_MOUSE:
            return self._handle_mouse()

        # Global quit (Q / q)
        if ch in (ord("q"), ord("Q")):
            return True

        # Language switcher via Ctrl+L or F2 (no conflict with hjkl/HJKL navigation)
        if ch in (_KEY_CTRL_L, curses.KEY_F2) and self._state != ScreenState.RINGING:
            self._tr.cycle_language()
            return False

        if self._state == ScreenState.SETUP:
            return self._handle_setup_key(ch)
        if self._state == ScreenState.WAITING:
            return self._handle_waiting_key(ch)
        if self._state == ScreenState.BEDTIME_CHECK:
            return self._handle_bedtime_key(ch)
        return self._handle_ringing_key(ch)

    def _handle_setup_key(self, ch: int) -> bool:
        cols = self._columns_for_mode()
        if ch in (curses.KEY_LEFT, ord("h"), ord("H")):
            self._focus_col = (self._focus_col - 1) % len(cols)
        elif ch in (curses.KEY_RIGHT, ord("l"), ord("L")):
            self._focus_col = (self._focus_col + 1) % len(cols)
        elif ch in (curses.KEY_UP, ord("k"), ord("K")):
            self._step_column(cols[self._focus_col], -1)
        elif ch in (curses.KEY_DOWN, ord("j"), ord("J")):
            self._step_column(cols[self._focus_col], 1)
        elif ch == curses.KEY_PPAGE:
            self._step_column(cols[self._focus_col], -1, coarse=True)
        elif ch == curses.KEY_NPAGE:
            self._step_column(cols[self._focus_col], 1, coarse=True)
        elif ch in (ord("+"), ord("=")):
            self._step_column(cols[self._focus_col], 1)
        elif ch == ord("-"):
            self._step_column(cols[self._focus_col], -1)
        elif ch in (9, ord("m"), ord("M")):  # Tab or m
            self._toggle_mode()
        elif ch in (ord("t"), ord("T")):
            self._trigger_sound_test()
        elif ch in (10, 13, curses.KEY_ENTER):
            self._start_alarm()
        return False

    def _handle_waiting_key(self, ch: int) -> bool:
        if ch in (ord("b"), ord("B")):
            self._open_bedtime_check()
        elif ch in (ord("t"), ord("T")):
            self._trigger_sound_test()
        elif ch == 27:  # Esc
            self._return_to_setup()
        return False

    def _handle_bedtime_key(self, ch: int) -> bool:
        if ch in (ord("y"), ord("Y"), 10, 13, curses.KEY_ENTER):
            self._answer_bedtime_check(True)
        elif ch in (ord("n"), ord("N")):
            self._answer_bedtime_check(False)
        elif ch == 27:  # Esc
            self._return_to_setup()
        return False

    def _handle_ringing_key(self, ch: int) -> bool:
        if ch in (10, 13, curses.KEY_ENTER, ord(" "), 27):
            self._dismiss_alarm()
        elif ch in (ord("z"), ord("Z"), ord("s"), ord("S")):
            self._snooze_alarm()
        return False

    # ------------------------------------------------------------------
    # State Machine Tick & Main Loop
    # ------------------------------------------------------------------

    def _tick_timers(self) -> None:
        if self._plan is None:
            return
        now = datetime.now()

        if self._state in (ScreenState.WAITING, ScreenState.BEDTIME_CHECK):
            if is_alarm_due(self._plan.target_time, now):
                self._enter_ringing()
                return

        if self._state == ScreenState.WAITING:
            if is_bedtime_check_due(self._plan, now):
                self._open_bedtime_check()
        elif self._state == ScreenState.BEDTIME_CHECK:
            elapsed = time.monotonic() - self._bedtime_prompt_started
            if elapsed >= self._config.bedtime_check_timeout_sec:
                self._answer_bedtime_check(True)

    def run(self, stdscr: curses.window) -> int:
        """Execute main curses event loop; always restores terminal cursor/mouse."""
        try:
            curses.curs_set(0)
        except curses.error:
            pass

        stdscr.keypad(True)
        stdscr.timeout(200)
        self._init_colors()

        mouse_enabled = False
        try:
            curses.mousemask(curses.ALL_MOUSE_EVENTS)
            curses.mouseinterval(150)
            mouse_enabled = True
        except curses.error:
            mouse_enabled = False

        try:
            while not self._shutdown_event.is_set():
                self._tick_timers()
                self._render(stdscr)
                try:
                    ch = stdscr.getch()
                except KeyboardInterrupt:
                    return 130
                if self._shutdown_event.is_set():
                    break
                if self._handle_key(ch):
                    break
            return 0
        finally:
            self._release_sleep_inhibit()
            if mouse_enabled:
                try:
                    curses.mousemask(0)
                except curses.error:
                    pass
            try:
                curses.curs_set(1)
            except curses.error:
                pass
