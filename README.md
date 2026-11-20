<div align="center">

# ⏰ alarm-tui

[![Python Version](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Linux-FCC624?logo=linux&logoColor=black)](https://kernel.org/)
[![Version](https://img.shields.io/badge/Version-1.0.0-blue?logo=semver&logoColor=white)](pyproject.toml)
[![Dependencies](https://img.shields.io/badge/Dependencies-stdlib%20only-brightgreen)](pyproject.toml)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

*Wake up between sleep cycles, never sleep through an alarm, and always return your system volume to 50%.*

</div>

---

## 📖 What is alarm-tui?

**alarm-tui** is a modular Linux terminal alarm clock written in pure **Python 3** (`curses` + standard library, zero third-party runtime dependencies).

It combines sleep-cycle math, an interactive centered TUI with drum pickers, safe PipeWire/WirePlumber audio ramping, and `systemd-inhibit` sleep blocking into a lightweight terminal tool:

* Schedule wake-up times by **Sleep Cycles** (`cycles × cycle_minutes + fall_asleep_minutes`) or **Exact Time** (`HH:MM` with automatic rollover to tomorrow).
* Catch late bedtimes with an interactive **Bedtime Check** that shifts your target by `+15 min` when you are still awake—and auto-confirms if you already fell asleep.
* Keep your Linux machine awake until the alarm fires with automatic **`systemd-inhibit`** management.
* Ramp a sine-wave siren smoothly via **`speaker-test`** and **`wpctl`**, with guaranteed process teardown and **`50%` volume restoration** on every exit path.

---

## ✨ Key Features

| Feature | Description |
| --- | --- |
| **Dual Scheduling Modes** | Switch between **CYCLES** (default `90m` cycles + live `0–45m` fall-asleep drum) and **EXACT TIME** (`HH:MM` with automatic next-day rollover). |
| **Interactive Drum Pickers** | Centered `curses` card displaying `prev / current / next` values with full keyboard (`arrows` / `hjkl`) and mouse (click + scroll wheel) control. |
| **Bedtime Check (`+15m`)** | Prompts *"Did you go to sleep?"* after `15m`; answering **No** shifts the wake target by `+15m` and reschedules the check. Auto-confirms **Yes** after `60s` so sleeping users never miss their alarm. |
| **Sleep Inhibition** | Automatically holds `systemd-inhibit --what=sleep:idle` while armed or ringing (`WAITING`, `BEDTIME_CHECK`, `RINGING`) and releases it cleanly on cancel, dismiss, or exit. |
| **Tone Presets & Manual Hz** | Six built-in sine-wave presets (default `850 Hz`) plus fine-grained manual frequency tuning (`150–4000 Hz`, step `25 Hz`) and a 2-second sound test (`T`). |
| **Gradual Siren Ramp & Safety** | Unmutes `@DEFAULT_AUDIO_SINK@`, ramps volume from `15%` to `100%` (`+5%` every `3s`), and unconditionally kills `speaker-test` and restores volume to `50%` on `Q`, `Ctrl+C` (`SIGINT`), `SIGTERM`, or alarm dismissal. |
| **Trilingual UI (`en` / `ru` / `tr`)** | Resolves language via `--lang` → `config.toml` → `LC_ALL` / `LC_MESSAGES` / `LANG` → `ru`, and switches live via `Ctrl+L`, `F2`, or clicking the `[^L]` badge. |
| **Terminal-Safe Rendering** | Adapts cleanly to terminal resizing, guards against tiny terminal dimensions without `curses` crashes, and restores cursor/mouse state on exit. |

---

## 📦 Installation & Requirements

### System Requirements

* **OS:** Linux
* **Python:** `3.10+` (uses stdlib `tomllib` on `3.11+` and a built-in TOML fallback parser on `3.10`)
* **`alsa-utils`:** provides `speaker-test` for sine-wave audio output
* **`wireplumber`:** provides `wpctl` for volume control and unmuting `@DEFAULT_AUDIO_SINK@`
* **`systemd`** *(optional, preinstalled on most distros)*: provides `systemd-inhibit` for sleep/idle locking

Install system utilities:

```bash
# Arch Linux / Manjaro
sudo pacman -S python alsa-utils wireplumber

# Debian / Ubuntu
sudo apt install python3 alsa-utils wireplumber

# Fedora
sudo dnf install python3 alsa-utils wireplumber
```

### Install as CLI (`alarm-tui`)

```bash
# Install globally in an isolated environment with uv
uv tool install .
alarm-tui

# Or install in editable mode with pip
pip install -e .
alarm-tui --lang en
```

### Run Directly Without Installing

```bash
python3 main.py
python3 main.py --lang en
python3 main.py --config /path/to/config.toml
```

---

## 🚀 CLI Flags

| Flag | Values | Description |
| --- | --- | --- |
| `--lang` | `en`, `ru`, `tr` | Override interface language (takes priority over `config.toml` and environment variables). |
| `--config` | `<path>` | Load configuration from a specific TOML file (exits with status `2` if missing or invalid). |
| `--version` | — | Print `alarm-tui 1.0.0` and exit. |

---

## 🎛️ Controls & Tone Presets

### Keyboard Shortcuts

| Key | Action |
| --- | --- |
| `←` / `→` or `h` / `l` | Move focus between drum columns (`Cycles`, `Fall Asleep`, `Preset`, `Freq` or `Hour`, `Min`, `Preset`, `Freq`) |
| `↑` / `↓` or `k` / `j` | Step the focused drum (`Fall Asleep`: `5m` step across `0–45m`) |
| `PgUp` / `PgDn` | Coarse step (`Fall Asleep` `±15m`, `Hour` `±3`, `Min` `±5`, `Freq` `±100 Hz`) |
| `+` / `-` | Increment / decrement the focused drum |
| `Tab` or `m` | Toggle mode (`CYCLES` ↔ `EXACT TIME`) |
| `T` | Start or stop the 2-second sound test at the selected frequency |
| `Enter` | Arm the alarm and enter countdown (`WAITING`) |
| `B` | Open the Bedtime Check prompt manually while waiting |
| `Y` / `N` | Answer Bedtime Check (`Yes, asleep` / `No, shift +15m`) |
| `Enter` / `Space` | Dismiss a ringing alarm (stops siren, restores volume to `50%`, releases `systemd-inhibit`) |
| `Z` | Snooze a ringing alarm (`+5m` by default) |
| `Esc` | Return to the setup screen |
| `Ctrl+L` or `F2` | Cycle UI language (`EN` → `RU` → `TR`) without conflicting with `hjkl` |
| `Q` or `Ctrl+C` | Quit safely (stops `speaker-test`, releases `systemd-inhibit`, restores volume to `50%`) |

### Mouse Controls

* **Mode tabs:** Click `CYCLES` or `EXACT TIME` to switch modes.
* **Drum pickers:** Click a drum to focus it; click the upper/lower rows (`▲` / `▼`) or scroll the mouse wheel (`BUTTON4` / `BUTTON5`) to change values.
* **Action buttons & badge:** Click `Test`, `Start`, `Quit`, `Awake?`, `Yes`/`No`, `Stop Alarm`, `Snooze`, or the top-right `[^L]` language badge.

### Built-in Frequency Presets

| Preset | Frequency | Character |
| --- | --- | --- |
| **Deep** | `300 Hz` | Low, warm sine tone |
| **Soft** | `440 Hz` | Concert A4 tone |
| **Medium** | `600 Hz` | Balanced mid-range tone |
| **Classic** *(default)* | `850 Hz` | Clear classic alarm pitch |
| **Bright** | `1200 Hz` | Sharp, attention-grabbing tone |
| **High** | `1800 Hz` | High-pitched piercing tone |
| **Manual** | `150–4000 Hz` | Custom frequency tuned in `25 Hz` steps |

---

## ⚙️ Configuration

Configuration files are discovered automatically in the following order:

1. Path passed via `--config <path>`
2. `~/.config/alarm-tui/config.toml` (respecting `$XDG_CONFIG_HOME`)
3. Local `./config.toml` in the current working directory
4. Built-in safe defaults

Create your user configuration from [`config.example.toml`](config.example.toml):

```bash
mkdir -p ~/.config/alarm-tui
cp config.example.toml ~/.config/alarm-tui/config.toml
```

```toml
[general]
language = "auto"        # "en", "ru", "tr", or "auto" (LC_ALL / LANG -> fallback "ru")
default_mode = "cycles"  # "cycles" or "exact"

[sleep]
cycle_minutes = 90
default_cycles = 5
min_cycles = 1
max_cycles = 10
fall_asleep_minutes = 15
bedtime_check_enabled = true
bedtime_check_delay_minutes = 15
bedtime_shift_minutes = 15
bedtime_check_timeout_sec = 60
default_exact_hour = 7
default_exact_minute = 30
snooze_minutes = 5

[audio]
frequency_hz = 850
min_frequency_hz = 150
max_frequency_hz = 4000
frequency_step_hz = 25
test_sound_duration_sec = 2.0
test_sound_volume = 50
start_vol = 15
max_vol = 100
step_vol = 5
step_sec = 3.0
restore_vol = 50
audio_sink = "@DEFAULT_AUDIO_SINK@"
```

* Invalid types fall back to defaults with a startup warning; out-of-range numeric values are safely clamped.
* If `speaker-test` is unavailable when the alarm fires, the ringing screen displays an explicit no-sound warning instead of failing silently.
* If `systemd-inhibit` is absent, the alarm continues operating normally and notifies you in the status line.

---

## 🧪 Testing

Install development dependencies (`pytest>=7.0`) and run the test suite:

```bash
pip install -e ".[dev]"
pytest -v
```

Test coverage includes sleep-cycle and exact-time rollover math, bedtime checks and snooze plans, TOML parsing/validation/clamping, language resolution and translation key parity (`en`/`ru`/`tr`), and `systemd-inhibit` lifecycle handling.

---

## 🏗️ Architecture

```text
personal-alarm/
├── pyproject.toml           # Package metadata, alarm-tui CLI entrypoint, and pytest settings
├── main.py                  # Direct execution wrapper (`python3 main.py`)
├── config.example.toml      # Documented example TOML configuration
├── LICENSE                  # MIT License
├── README.md                # Project documentation
├── alarm_tui/
│   ├── __init__.py          # Package version and app metadata
│   ├── cli.py               # CLI parser (--lang, --config), signal/atexit guards, TUI bootstrap
│   ├── i18n.py              # Localization dictionaries (en, ru, tr) and locale resolution
│   ├── config.py            # TOML loader (tomllib + fallback parser) and config validation
│   ├── audio.py             # speaker-test playback, wpctl volume ramp, and 50% reset safety
│   ├── inhibitor.py         # systemd-inhibit sleep/idle lock lifecycle manager
│   ├── sleep.py             # Sleep cycles, exact-time rollover, bedtime check (+15m), snooze
│   └── ui.py                # Centered curses TUI, drum pickers, mouse handling, state screens
└── tests/
    ├── test_sleep.py        # Unit tests for sleep calculations, bedtime check, and snooze
    ├── test_config.py       # Unit tests for defaults, TOML parsing, validation, and clamping
    ├── test_i18n.py         # Unit tests for language priority and en/ru/tr key parity
    └── test_inhibitor.py    # Unit tests for systemd-inhibit acquire/release and fallback
```

---

## 📜 License

[MIT](LICENSE) — © 2026 [Heysh1n](https://github.com/Heysh1n)

 
<p align="center">Made with ❤️ by Heysh1n</p> 