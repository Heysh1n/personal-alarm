"""Unit tests for alarm_tui.config."""

from __future__ import annotations

from pathlib import Path

import pytest

from alarm_tui.config import (
    AlarmConfig,
    ConfigError,
    _parse_toml_fallback,
    load_config,
    validate_config,
)


def test_default_config_values() -> None:
    cfg = AlarmConfig()
    assert cfg.language == "auto"
    assert cfg.default_mode == "cycles"
    assert cfg.cycle_minutes == 90
    assert cfg.default_cycles == 5
    assert cfg.fall_asleep_minutes == 15
    assert cfg.frequency_hz == 850
    assert cfg.start_vol == 15
    assert cfg.max_vol == 100
    assert cfg.step_vol == 5
    assert cfg.step_sec == 3.0
    assert cfg.restore_vol == 50
    assert cfg.audio_sink == "@DEFAULT_AUDIO_SINK@"


def test_load_example_config_cleanly() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    example_path = repo_root / "config.example.toml"
    result = load_config(example_path)

    assert result.source_path == example_path
    assert result.warnings == []
    assert result.config.frequency_hz == 850
    assert result.config.restore_vol == 50
    assert result.config.cycle_minutes == 90
    assert result.config.fall_asleep_minutes == 15


def test_load_valid_toml_file(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
[general]
language = "tr"
default_mode = "exact"

[sleep]
cycle_minutes = 85
default_cycles = 4
fall_asleep_minutes = 20
default_exact_hour = 6
default_exact_minute = 45
bedtime_shift_minutes = 10

[audio]
frequency_hz = 1200
start_vol = 20
max_vol = 90
step_vol = 10
step_sec = 2.5
restore_vol = 40
audio_sink = "@DEFAULT_AUDIO_SINK@"
""".strip(),
        encoding="utf-8",
    )

    result = load_config(cfg_file)
    assert result.warnings == []
    cfg = result.config
    assert cfg.language == "tr"
    assert cfg.default_mode == "exact"
    assert cfg.cycle_minutes == 85
    assert cfg.default_cycles == 4
    assert cfg.fall_asleep_minutes == 20
    assert cfg.default_exact_hour == 6
    assert cfg.default_exact_minute == 45
    assert cfg.bedtime_shift_minutes == 10
    assert cfg.frequency_hz == 1200
    assert cfg.start_vol == 20
    assert cfg.max_vol == 90
    assert cfg.step_vol == 10
    assert cfg.step_sec == 2.5
    assert cfg.restore_vol == 40


def test_validate_invalid_types_fall_back_with_warnings() -> None:
    raw = {
        "general": {
            "language": "de",
            "default_mode": "invalid_mode",
        },
        "sleep": {
            "cycle_minutes": "ninety",
            "bedtime_check_enabled": "yes",
            "fall_asleep_minutes": True,
        },
        "audio": {
            "frequency_hz": "loud",
            "step_sec": False,
            "restore_vol": "half",
            "audio_sink": "   ",
        },
    }

    cfg, warnings = validate_config(raw)
    assert cfg.language == "auto"
    assert cfg.default_mode == "cycles"
    assert cfg.cycle_minutes == 90
    assert cfg.bedtime_check_enabled is True
    assert cfg.fall_asleep_minutes == 15
    assert cfg.frequency_hz == 850
    assert cfg.step_sec == 3.0
    assert cfg.restore_vol == 50
    assert cfg.audio_sink == "@DEFAULT_AUDIO_SINK@"
    assert len(warnings) >= 8


def test_validate_out_of_range_values_are_clamped() -> None:
    raw = {
        "sleep": {
            "cycle_minutes": 5,
            "min_cycles": 1,
            "max_cycles": 8,
            "default_cycles": 99,
            "fall_asleep_minutes": -10,
            "default_exact_hour": 30,
            "default_exact_minute": -1,
        },
        "audio": {
            "min_frequency_hz": 200,
            "max_frequency_hz": 3000,
            "frequency_hz": 9999,
            "start_vol": 80,
            "max_vol": 40,
            "restore_vol": 150,
            "step_sec": 0.1,
        },
    }

    cfg, warnings = validate_config(raw)
    assert cfg.cycle_minutes == 15
    assert cfg.default_cycles == 8
    assert cfg.fall_asleep_minutes == 0
    assert cfg.default_exact_hour == 23
    assert cfg.default_exact_minute == 0
    assert cfg.frequency_hz == 3000
    assert cfg.start_vol == 80
    assert cfg.max_vol == 80  # clamped to >= start_vol
    assert cfg.restore_vol == 100
    assert cfg.step_sec == 0.5
    assert len(warnings) >= 9


def test_missing_or_broken_explicit_config_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(tmp_path / "does-not-exist.toml")

    broken = tmp_path / "broken.toml"
    broken.write_text("[audio\nfrequency_hz = ===\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(broken)


def test_fallback_toml_parser_handles_sections_and_types() -> None:
    text = """
# Comment line
[general]
language = "en" # inline comment

[audio]
frequency_hz = 850
step_sec = 2.5
bedtime_check_enabled = false
frequency_presets = [300, 850, 1200]
"""
    parsed = _parse_toml_fallback(text)
    assert parsed["general"]["language"] == "en"
    assert parsed["audio"]["frequency_hz"] == 850
    assert parsed["audio"]["step_sec"] == 2.5
    assert parsed["audio"]["bedtime_check_enabled"] is False
    assert parsed["audio"]["frequency_presets"] == [300, 850, 1200]
