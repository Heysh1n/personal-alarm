"""Configuration loading and validation for alarm-tui."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .i18n import SUPPORTED_LANGUAGES

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - fallback for Python < 3.11
    tomllib = None  # type: ignore[assignment]


class ConfigError(Exception):
    """Raised when an explicitly requested config file cannot be loaded."""


@dataclass(frozen=True)
class FrequencyPreset:
    """Frequency preset displayed in the TUI drum picker."""

    label_key: str
    hz: int
    custom_label: str | None = None


DEFAULT_PRESETS: tuple[FrequencyPreset, ...] = (
    FrequencyPreset("preset_deep", 300),
    FrequencyPreset("preset_soft", 440),
    FrequencyPreset("preset_mid", 600),
    FrequencyPreset("preset_default", 850),
    FrequencyPreset("preset_bright", 1200),
    FrequencyPreset("preset_high", 1800),
)


@dataclass
class AlarmConfig:
    """Validated runtime configuration with sensible defaults."""

    # General
    language: str = "auto"
    default_mode: str = "cycles"  # "cycles" | "exact"

    # Sleep calculation
    cycle_minutes: int = 90
    default_cycles: int = 5
    min_cycles: int = 1
    max_cycles: int = 10
    fall_asleep_minutes: int = 15
    bedtime_check_enabled: bool = True
    bedtime_check_delay_minutes: int = 15
    bedtime_shift_minutes: int = 15
    bedtime_check_timeout_sec: int = 60

    # Exact time defaults
    default_exact_hour: int = 7
    default_exact_minute: int = 30

    # Audio & siren ramp
    frequency_hz: int = 850
    min_frequency_hz: int = 150
    max_frequency_hz: int = 4000
    frequency_step_hz: int = 25
    test_sound_duration_sec: float = 2.0
    test_sound_volume: int = 50
    start_vol: int = 15
    max_vol: int = 100
    step_vol: int = 5
    step_sec: float = 3.0
    restore_vol: int = 50
    snooze_minutes: int = 5
    audio_sink: str = "@DEFAULT_AUDIO_SINK@"
    presets: tuple[FrequencyPreset, ...] = field(default_factory=lambda: DEFAULT_PRESETS)


@dataclass
class ConfigLoadResult:
    """Result of loading configuration, including source path and validation warnings."""

    config: AlarmConfig
    source_path: Path | None = None
    warnings: list[str] = field(default_factory=list)


def get_xdg_config_path() -> Path:
    """Return ~/.config/alarm-tui/config.toml (respecting XDG_CONFIG_HOME)."""
    xdg_home = os.environ.get("XDG_CONFIG_HOME", "").strip()
    base = Path(xdg_home).expanduser() if xdg_home else Path.home() / ".config"
    return base / "alarm-tui" / "config.toml"


def discover_config_path(cwd: Path | None = None) -> Path | None:
    """Locate config file: ~/.config/alarm-tui/config.toml or local ./config.toml."""
    xdg_path = get_xdg_config_path()
    local_path = (cwd or Path.cwd()) / "config.toml"
    if xdg_path.is_file():
        return xdg_path
    if local_path.is_file():
        return local_path
    return None


def _parse_minimal_toml_value(raw: str) -> Any:
    """Parse a single scalar or simple array value for Python < 3.11 fallback."""
    val = raw.strip()
    if not val:
        return ""
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        return val[1:-1]
    low = val.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if val.startswith("[") and val.endswith("]"):
        inner = val[1:-1].strip()
        if not inner:
            return []
        return [_parse_minimal_toml_value(part) for part in inner.split(",") if part.strip()]
    try:
        if "." in val:
            return float(val)
        return int(val)
    except ValueError:
        return val


def _strip_toml_comment(line: str) -> str:
    """Strip inline # comments outside quoted strings."""
    in_quote: str | None = None
    escaped = False
    for idx, ch in enumerate(line):
        if escaped:
            escaped = False
            continue
        if ch == "\\" and in_quote == '"':
            escaped = True
            continue
        if ch in ('"', "'"):
            if in_quote is None:
                in_quote = ch
            elif in_quote == ch:
                in_quote = None
        elif ch == "#" and in_quote is None:
            return line[:idx]
    return line


def _parse_toml_fallback(text: str) -> dict[str, Any]:
    """Minimal stdlib-only TOML parser for flat keys and [section] tables."""
    root: dict[str, Any] = {}
    current: dict[str, Any] = root
    for raw_line in text.splitlines():
        line = _strip_toml_comment(raw_line).strip()
        if not line:
            continue
        if line.startswith("[") and not line.startswith("[["):
            if not line.endswith("]"):
                raise ValueError(f"Unclosed TOML section header: {line}")
            section = line[1:-1].strip()
            if section:
                target = root
                for part in section.split("."):
                    part = part.strip()
                    existing = target.get(part)
                    if not isinstance(existing, dict):
                        existing = {}
                        target[part] = existing
                    target = existing
                current = target
            continue
        if "=" in line:
            key, raw_val = line.split("=", 1)
            key = key.strip()
            if key:
                current[key] = _parse_minimal_toml_value(raw_val)
    return root


def parse_toml_bytes(data: bytes) -> dict[str, Any]:
    """Parse TOML bytes using stdlib tomllib or fallback parser."""
    if tomllib is not None:
        return tomllib.loads(data.decode("utf-8"))
    return _parse_toml_fallback(data.decode("utf-8"))


def _flatten_config_dict(raw: dict[str, Any]) -> dict[str, Any]:
    """Accept both sectioned ([general], [sleep], [audio], [alarm]) and flat keys."""
    flat: dict[str, Any] = {}
    for key, value in raw.items():
        if isinstance(value, dict):
            for sub_key, sub_val in value.items():
                if not isinstance(sub_val, dict):
                    flat[sub_key] = sub_val
        else:
            flat[key] = value
    return flat


def _validate_int(
    data: dict[str, Any],
    key: str,
    default: int,
    minimum: int,
    maximum: int,
    warnings: list[str],
) -> int:
    if key not in data:
        return default
    raw = data[key]
    if isinstance(raw, bool) or not isinstance(raw, int):
        warnings.append(f"Config '{key}' must be an integer; using default {default}.")
        return default
    if raw < minimum or raw > maximum:
        clamped = max(minimum, min(maximum, raw))
        warnings.append(f"Config '{key}'={raw} out of range [{minimum}..{maximum}]; clamped to {clamped}.")
        return clamped
    return raw


def _validate_float(
    data: dict[str, Any],
    key: str,
    default: float,
    minimum: float,
    maximum: float,
    warnings: list[str],
) -> float:
    if key not in data:
        return default
    raw = data[key]
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        warnings.append(f"Config '{key}' must be a number; using default {default}.")
        return default
    val = float(raw)
    if val < minimum or val > maximum:
        clamped = max(minimum, min(maximum, val))
        warnings.append(f"Config '{key}'={val} out of range [{minimum}..{maximum}]; clamped to {clamped}.")
        return clamped
    return val


def _validate_bool(data: dict[str, Any], key: str, default: bool, warnings: list[str]) -> bool:
    if key not in data:
        return default
    raw = data[key]
    if not isinstance(raw, bool):
        warnings.append(f"Config '{key}' must be true/false; using default {default}.")
        return default
    return raw


def _validate_str(data: dict[str, Any], key: str, default: str, warnings: list[str]) -> str:
    if key not in data:
        return default
    raw = data[key]
    if not isinstance(raw, str) or not raw.strip():
        warnings.append(f"Config '{key}' must be a non-empty string; using default '{default}'.")
        return default
    return raw.strip()


def _parse_custom_presets(
    raw_presets: Any,
    min_hz: int,
    max_hz: int,
    warnings: list[str],
) -> tuple[FrequencyPreset, ...]:
    """Parse optional preset list (either list of ints or list of {label, hz} dicts)."""
    if not isinstance(raw_presets, list) or not raw_presets:
        return DEFAULT_PRESETS

    parsed: list[FrequencyPreset] = []
    for item in raw_presets:
        if isinstance(item, int) and not isinstance(item, bool):
            hz = max(min_hz, min(max_hz, item))
            parsed.append(FrequencyPreset("preset_manual", hz, custom_label=f"{hz} Hz"))
        elif isinstance(item, dict) and isinstance(item.get("hz"), int):
            hz = max(min_hz, min(max_hz, item["hz"]))
            label = str(item.get("label", f"{hz} Hz")).strip() or f"{hz} Hz"
            parsed.append(FrequencyPreset("preset_manual", hz, custom_label=label))
        else:
            warnings.append(f"Ignoring invalid frequency preset entry: {item!r}.")

    return tuple(parsed) if parsed else DEFAULT_PRESETS


def validate_config(raw: dict[str, Any]) -> tuple[AlarmConfig, list[str]]:
    """Build and validate an AlarmConfig from parsed TOML mapping."""
    warnings: list[str] = []
    defaults = AlarmConfig()
    data = _flatten_config_dict(raw)

    # Language
    language = defaults.language
    if "language" in data:
        raw_lang = data["language"]
        if isinstance(raw_lang, str):
            norm = raw_lang.strip().lower()
            if norm in ("", "auto", *SUPPORTED_LANGUAGES):
                language = norm or "auto"
            else:
                warnings.append(
                    f"Unsupported config language '{raw_lang}'; falling back to auto-detection."
                )
        else:
            warnings.append("Config 'language' must be a string; falling back to auto-detection.")

    # Default mode
    default_mode = defaults.default_mode
    if "default_mode" in data:
        raw_mode = data["default_mode"]
        if isinstance(raw_mode, str) and raw_mode.strip().lower() in ("cycles", "exact"):
            default_mode = raw_mode.strip().lower()
        else:
            warnings.append("Config 'default_mode' must be 'cycles' or 'exact'; using 'cycles'.")

    # Sleep settings
    cycle_minutes = _validate_int(data, "cycle_minutes", defaults.cycle_minutes, 15, 180, warnings)
    min_cycles = _validate_int(data, "min_cycles", defaults.min_cycles, 1, 12, warnings)
    max_cycles = _validate_int(data, "max_cycles", defaults.max_cycles, min_cycles, 16, warnings)
    default_cycles = _validate_int(
        data, "default_cycles", defaults.default_cycles, min_cycles, max_cycles, warnings
    )
    fall_asleep_minutes = _validate_int(
        data, "fall_asleep_minutes", defaults.fall_asleep_minutes, 0, 120, warnings
    )
    bedtime_check_enabled = _validate_bool(
        data, "bedtime_check_enabled", defaults.bedtime_check_enabled, warnings
    )
    bedtime_check_delay_minutes = _validate_int(
        data,
        "bedtime_check_delay_minutes",
        defaults.bedtime_check_delay_minutes,
        1,
        120,
        warnings,
    )
    bedtime_shift_minutes = _validate_int(
        data, "bedtime_shift_minutes", defaults.bedtime_shift_minutes, 1, 60, warnings
    )
    bedtime_check_timeout_sec = _validate_int(
        data, "bedtime_check_timeout_sec", defaults.bedtime_check_timeout_sec, 10, 600, warnings
    )

    # Exact time defaults
    default_exact_hour = _validate_int(
        data, "default_exact_hour", defaults.default_exact_hour, 0, 23, warnings
    )
    default_exact_minute = _validate_int(
        data, "default_exact_minute", defaults.default_exact_minute, 0, 59, warnings
    )

    # Frequency settings
    min_frequency_hz = _validate_int(
        data, "min_frequency_hz", defaults.min_frequency_hz, 50, 2000, warnings
    )
    max_frequency_hz = _validate_int(
        data, "max_frequency_hz", defaults.max_frequency_hz, min_frequency_hz, 10000, warnings
    )
    frequency_hz = _validate_int(
        data, "frequency_hz", defaults.frequency_hz, min_frequency_hz, max_frequency_hz, warnings
    )
    frequency_step_hz = _validate_int(
        data, "frequency_step_hz", defaults.frequency_step_hz, 1, 500, warnings
    )

    # Audio volume & ramp settings
    test_sound_duration_sec = _validate_float(
        data, "test_sound_duration_sec", defaults.test_sound_duration_sec, 0.5, 10.0, warnings
    )
    test_sound_volume = _validate_int(
        data, "test_sound_volume", defaults.test_sound_volume, 1, 100, warnings
    )
    start_vol = _validate_int(data, "start_vol", defaults.start_vol, 0, 100, warnings)
    max_vol = _validate_int(data, "max_vol", defaults.max_vol, max(1, start_vol), 150, warnings)
    step_vol = _validate_int(data, "step_vol", defaults.step_vol, 1, 50, warnings)
    step_sec = _validate_float(data, "step_sec", defaults.step_sec, 0.5, 60.0, warnings)
    restore_vol = _validate_int(data, "restore_vol", defaults.restore_vol, 0, 100, warnings)
    snooze_minutes = _validate_int(data, "snooze_minutes", defaults.snooze_minutes, 1, 60, warnings)
    audio_sink = _validate_str(data, "audio_sink", defaults.audio_sink, warnings)

    # Optional custom presets (top-level or inside [audio])
    raw_presets = data.get("frequency_presets")
    if raw_presets is None and isinstance(raw.get("audio"), dict):
        raw_presets = raw["audio"].get("frequency_presets")
    presets = (
        _parse_custom_presets(raw_presets, min_frequency_hz, max_frequency_hz, warnings)
        if raw_presets is not None
        else DEFAULT_PRESETS
    )

    config = AlarmConfig(
        language=language,
        default_mode=default_mode,
        cycle_minutes=cycle_minutes,
        default_cycles=default_cycles,
        min_cycles=min_cycles,
        max_cycles=max_cycles,
        fall_asleep_minutes=fall_asleep_minutes,
        bedtime_check_enabled=bedtime_check_enabled,
        bedtime_check_delay_minutes=bedtime_check_delay_minutes,
        bedtime_shift_minutes=bedtime_shift_minutes,
        bedtime_check_timeout_sec=bedtime_check_timeout_sec,
        default_exact_hour=default_exact_hour,
        default_exact_minute=default_exact_minute,
        frequency_hz=frequency_hz,
        min_frequency_hz=min_frequency_hz,
        max_frequency_hz=max_frequency_hz,
        frequency_step_hz=frequency_step_hz,
        test_sound_duration_sec=test_sound_duration_sec,
        test_sound_volume=test_sound_volume,
        start_vol=start_vol,
        max_vol=max_vol,
        step_vol=step_vol,
        step_sec=step_sec,
        restore_vol=restore_vol,
        snooze_minutes=snooze_minutes,
        audio_sink=audio_sink,
        presets=presets,
    )
    return config, warnings


def load_config(config_path: str | Path | None = None, cwd: Path | None = None) -> ConfigLoadResult:
    """Load and validate configuration from TOML file, falling back to defaults."""
    explicit = config_path is not None
    resolved_path: Path | None
    if explicit:
        resolved_path = Path(config_path).expanduser()
        if not resolved_path.is_file():
            raise ConfigError(f"Config file not found: {resolved_path}")
    else:
        resolved_path = discover_config_path(cwd=cwd)

    if resolved_path is None:
        return ConfigLoadResult(config=AlarmConfig(), source_path=None, warnings=[])

    try:
        raw_bytes = resolved_path.read_bytes()
        parsed = parse_toml_bytes(raw_bytes)
    except Exception as exc:
        if explicit:
            raise ConfigError(f"Failed to parse config '{resolved_path}': {exc}") from exc
        return ConfigLoadResult(
            config=AlarmConfig(),
            source_path=None,
            warnings=[f"Failed to read '{resolved_path}' ({exc}); using defaults."],
        )

    config, warnings = validate_config(parsed)
    return ConfigLoadResult(config=config, source_path=resolved_path, warnings=warnings)
