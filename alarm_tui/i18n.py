"""Internationalization (en, ru, tr) for alarm-tui."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "ru", "tr")
DEFAULT_LANGUAGE: str = "ru"

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "app_title": "ALARM TUI",
        "lang_badge": "[^L] EN",
        "mode_cycles": "CYCLES",
        "mode_exact": "EXACT TIME",
        "col_cycles": "Cycles",
        "col_fall_asleep": "Fall Asleep",
        "col_hour": "Hour",
        "col_minute": "Min",
        "col_preset": "Tone Preset",
        "col_freq": "Freq (Hz)",
        "preset_deep": "Deep",
        "preset_soft": "Soft",
        "preset_mid": "Medium",
        "preset_default": "Classic",
        "preset_bright": "Bright",
        "preset_high": "High",
        "preset_manual": "Manual",
        "cycles_item": "{n} cyc",
        "fall_asleep_item": "+{m}m",
        "freq_item": "{hz} Hz",
        "preview_wake": "Wake up at {time}",
        "preview_tomorrow": "(tomorrow)",
        "preview_today": "(today)",
        "preview_cycles_detail": "{cycles} × {cycle_min}m + {fall_min}m fall asleep = {total}",
        "preview_exact_detail": "Time until alarm: {remaining}",
        "preview_audio_detail": "{freq} Hz  •  Vol: {start}% → {max}% (+{step}%/{sec}s)  •  Reset: {restore}%",
        "btn_test": "[T] Test {sec}s",
        "btn_testing": "[T] Stop Test",
        "btn_start": "[Enter] Start",
        "btn_quit": "[Q] Quit",
        "btn_back": "[Esc] Setup",
        "btn_still_awake": "[B] Awake? +{min}m",
        "btn_yes": "[Y] Yes, asleep",
        "btn_no": "[N] No (+{min}m)",
        "btn_stop_alarm": "[Enter / Space] Stop Alarm",
        "btn_snooze": "[Z] Snooze +{min}m",
        "hint_setup": "←/→ hjkl: select  ↑/↓ wheel: change  Tab/m: mode  T: test  Ctrl+L: lang  Q: quit",
        "hint_waiting": "B: bedtime check  T: test sound  Ctrl+L: lang  Esc: setup  Q: quit",
        "hint_bedtime": "Y: confirm sleep  N: shift +{min}m  Esc: back  Q: quit",
        "hint_ringing": "Enter/Space: stop alarm  Z: snooze +{min}m  Q: quit",
        "status_testing": "Testing {freq} Hz ({sec:.1f}s)...",
        "status_test_done": "Sound test done — volume restored to {vol}%",
        "status_test_stopped": "Sound test stopped — volume restored to {vol}%",
        "status_missing_speaker": "speaker-test not found (install alsa-utils)",
        "status_missing_speaker_ringing": "NO SOUND: speaker-test not found (install alsa-utils)",
        "status_missing_wpctl": "wpctl not found (install wireplumber)",
        "status_missing_inhibit": "systemd-inhibit not found — system sleep is not blocked",
        "status_shifted": "Alarm shifted +{min}m → {time}",
        "status_bedtime_confirmed": "Bedtime confirmed — sleep well!",
        "status_snoozed": "Snoozed +{min}m → {time}",
        "status_alarm_stopped": "Alarm dismissed — volume restored to {vol}%",
        "waiting_title": "ALARM ARMED",
        "waiting_now": "Now: {now}",
        "waiting_target": "Wake at: {target}",
        "waiting_remaining": "Remaining",
        "waiting_mode_cycles": "Mode: Sleep Cycles ({cycles} × {cycle_min}m + {fall_min}m)",
        "waiting_mode_exact": "Mode: Exact Time",
        "waiting_next_check": "Bedtime check at {time}",
        "waiting_confirmed": "Bedtime confirmed",
        "waiting_shifts": "Delayed {count}× (+{total_min}m)",
        "waiting_inhibit_on": "Sleep lock: ON",
        "waiting_inhibit_off": "Sleep lock: OFF",
        "bedtime_title": "BEDTIME CHECK",
        "bedtime_question": "Did you go to sleep?",
        "bedtime_subtitle": "If you are still awake, target wake time shifts by +{min} min.",
        "bedtime_auto_confirm": "Auto-confirming 'Yes' in {sec}s (alarm stays at {time})",
        "ringing_title": "WAKE UP!",
        "ringing_subtitle": "Target time {time} reached",
        "ringing_volume": "Volume: {vol}% / {max}%",
        "ringing_freq": "Tone: {freq} Hz (sine)",
        "ringing_restore_note": "Stopping resets volume to {restore}%",
        "terminal_too_small": "Terminal too small ({cols}×{rows}). Need at least {min_w}×{min_h}.",
        "terminal_resize_hint": "Resize window or press Q to quit.",
        "cli_description": "Modular Linux TUI alarm clock with sleep cycles and gradual volume ramp.",
        "cli_lang_help": "Interface language (en, ru, tr). Overrides config and environment.",
        "cli_config_help": "Path to TOML configuration file.",
        "cli_version_help": "Show program version and exit.",
        "duration_hm": "{h}h {m:02d}m",
        "duration_m": "{m}m",
    },
    "ru": {
        "app_title": "ALARM TUI",
        "lang_badge": "[^L] RU",
        "mode_cycles": "ЦИКЛЫ СНА",
        "mode_exact": "ТОЧНОЕ ВРЕМЯ",
        "col_cycles": "Циклы",
        "col_fall_asleep": "Засыпание",
        "col_hour": "Часы",
        "col_minute": "Мин",
        "col_preset": "Пресет тона",
        "col_freq": "Частота",
        "preset_deep": "Низкий",
        "preset_soft": "Мягкий",
        "preset_mid": "Средний",
        "preset_default": "Классика",
        "preset_bright": "Яркий",
        "preset_high": "Высокий",
        "preset_manual": "Вручную",
        "cycles_item": "{n} цикл.",
        "fall_asleep_item": "+{m}м",
        "freq_item": "{hz} Гц",
        "preview_wake": "Подъем в {time}",
        "preview_tomorrow": "(завтра)",
        "preview_today": "(сегодня)",
        "preview_cycles_detail": "{cycles} × {cycle_min}м + {fall_min}м засыпание = {total}",
        "preview_exact_detail": "До звонка: {remaining}",
        "preview_audio_detail": "{freq} Гц  •  Громкость: {start}% → {max}% (+{step}%/{sec}с)  •  Сброс: {restore}%",
        "btn_test": "[T] Тест {sec}с",
        "btn_testing": "[T] Стоп тест",
        "btn_start": "[Enter] Старт",
        "btn_quit": "[Q] Выход",
        "btn_back": "[Esc] Назад",
        "btn_still_awake": "[B] Не сплю +{min}м",
        "btn_yes": "[Y] Да, сплю",
        "btn_no": "[N] Нет (+{min}м)",
        "btn_stop_alarm": "[Enter / Пробел] Выключить",
        "btn_snooze": "[Z] Отложить +{min}м",
        "hint_setup": "←/→ hjkl: выбор  ↑/↓ колесо: шаг  Tab/m: режим  T: тест  Ctrl+L: язык  Q: выход",
        "hint_waiting": "B: проверка отбоя  T: тест звука  Ctrl+L: язык  Esc: назад  Q: выход",
        "hint_bedtime": "Y: уже сплю  N: сдвинуть +{min}м  Esc: назад  Q: выход",
        "hint_ringing": "Enter/Пробел: выключить  Z: отложить +{min}м  Q: выход",
        "status_testing": "Тест звука: {freq} Гц ({sec:.1f}с)...",
        "status_test_done": "Тест завершен — громкость сброшена на {vol}%",
        "status_test_stopped": "Тест остановлен — громкость сброшена на {vol}%",
        "status_missing_speaker": "speaker-test не найден (установите alsa-utils)",
        "status_missing_speaker_ringing": "НЕТ ЗВУКА: speaker-test не найден (установите alsa-utils)",
        "status_missing_wpctl": "wpctl не найден (установите wireplumber)",
        "status_missing_inhibit": "systemd-inhibit не найден — сон системы не блокируется",
        "status_shifted": "Подъем сдвинут на +{min}м → {time}",
        "status_bedtime_confirmed": "Отбой подтвержден — спокойной ночи!",
        "status_snoozed": "Отложено на +{min}м → {time}",
        "status_alarm_stopped": "Будильник выключен — громкость {vol}%",
        "waiting_title": "БУДИЛЬНИК ЗАВЕДЕН",
        "waiting_now": "Сейчас: {now}",
        "waiting_target": "Подъем: {target}",
        "waiting_remaining": "Осталось",
        "waiting_mode_cycles": "Режим: циклы сна ({cycles} × {cycle_min}м + {fall_min}м)",
        "waiting_mode_exact": "Режим: точное время",
        "waiting_next_check": "Проверка отбоя в {time}",
        "waiting_confirmed": "Отбой подтвержден",
        "waiting_shifts": "Сдвигов: {count} (+{total_min}м)",
        "waiting_inhibit_on": "Блок сна: ВКЛ",
        "waiting_inhibit_off": "Блок сна: ВЫКЛ",
        "bedtime_title": "ПРОВЕРКА ОТБОЯ",
        "bedtime_question": "Пошел ли я спать?",
        "bedtime_subtitle": "Если вы еще не спите, цель сдвинется на +{min} минут.",
        "bedtime_auto_confirm": "Автоподтверждение «Да» через {sec}с (подъем в {time})",
        "ringing_title": "ПОРА ВСТАВАТЬ!",
        "ringing_subtitle": "Наступило время подъема {time}",
        "ringing_volume": "Громкость: {vol}% / {max}%",
        "ringing_freq": "Сигнал: {freq} Гц (синус)",
        "ringing_restore_note": "При остановке громкость вернется к {restore}%",
        "terminal_too_small": "Окно терминала слишком мало ({cols}×{rows}). Нужно минимум {min_w}×{min_h}.",
        "terminal_resize_hint": "Увеличьте окно или нажмите Q для выхода.",
        "cli_description": "Модульный TUI-будильник для Linux с циклами сна и разгоном громкости.",
        "cli_lang_help": "Язык интерфейса (en, ru, tr). Переопределяет конфиг и окружение.",
        "cli_config_help": "Путь к TOML-файлу конфигурации.",
        "cli_version_help": "Показать версию программы и выйти.",
        "duration_hm": "{h}ч {m:02d}м",
        "duration_m": "{m}м",
    },
    "tr": {
        "app_title": "ALARM TUI",
        "lang_badge": "[^L] TR",
        "mode_cycles": "UYKU DÖNGÜSÜ",
        "mode_exact": "TAM SAAT",
        "col_cycles": "Döngü",
        "col_fall_asleep": "Dalış",
        "col_hour": "Saat",
        "col_minute": "Dk",
        "col_preset": "Ton Ön Ayarı",
        "col_freq": "Frekans",
        "preset_deep": "Kalın",
        "preset_soft": "Yumuşak",
        "preset_mid": "Orta",
        "preset_default": "Klasik",
        "preset_bright": "Keskin",
        "preset_high": "Tiz",
        "preset_manual": "Manuel",
        "cycles_item": "{n} dön.",
        "fall_asleep_item": "+{m}dk",
        "freq_item": "{hz} Hz",
        "preview_wake": "Uyanış: {time}",
        "preview_tomorrow": "(yarın)",
        "preview_today": "(bugün)",
        "preview_cycles_detail": "{cycles} × {cycle_min}dk + {fall_min}dk uykuya dalış = {total}",
        "preview_exact_detail": "Alarma kalan: {remaining}",
        "preview_audio_detail": "{freq} Hz  •  Ses: %{start} → %{max} (+%{step}/{sec}sn)  •  Sıfırla: %{restore}",
        "btn_test": "[T] Test {sec}sn",
        "btn_testing": "[T] Testi Durdur",
        "btn_start": "[Enter] Başlat",
        "btn_quit": "[Q] Çıkış",
        "btn_back": "[Esc] Ayarlar",
        "btn_still_awake": "[B] Uyanığım +{min}dk",
        "btn_yes": "[Y] Evet, uyuyorum",
        "btn_no": "[N] Hayır (+{min}dk)",
        "btn_stop_alarm": "[Enter / Boşluk] Alarmı Durdur",
        "btn_snooze": "[Z] Ertele +{min}dk",
        "hint_setup": "←/→ hjkl: seç  ↑/↓ teker: ayar  Tab/m: mod  T: test  Ctrl+L: dil  Q: çıkış",
        "hint_waiting": "B: uyku kontrolü  T: ses testi  Ctrl+L: dil  Esc: ayarlar  Q: çıkış",
        "hint_bedtime": "Y: uykuyu onayla  N: +{min}dk kaydır  Esc: geri  Q: çıkış",
        "hint_ringing": "Enter/Boşluk: alarmı kapat  Z: +{min}dk ertele  Q: çıkış",
        "status_testing": "Ses testi: {freq} Hz ({sec:.1f}sn)...",
        "status_test_done": "Ses testi bitti — ses %{vol} olarak sıfırlandı",
        "status_test_stopped": "Ses testi durduruldu — ses %{vol} olarak sıfırlandı",
        "status_missing_speaker": "speaker-test bulunamadı (alsa-utils kurun)",
        "status_missing_speaker_ringing": "SES YOK: speaker-test bulunamadı (alsa-utils kurun)",
        "status_missing_wpctl": "wpctl bulunamadı (wireplumber kurun)",
        "status_missing_inhibit": "systemd-inhibit bulunamadı — sistem uykusu engellenmiyor",
        "status_shifted": "Uyanış +{min}dk kaydırıldı → {time}",
        "status_bedtime_confirmed": "Uyku onaylandı — iyi geceler!",
        "status_snoozed": "+{min}dk ertelendi → {time}",
        "status_alarm_stopped": "Alarm kapatıldı — ses %{vol} oldu",
        "waiting_title": "ALARM KURULDU",
        "waiting_now": "Şimdi: {now}",
        "waiting_target": "Uyanış: {target}",
        "waiting_remaining": "Kalan Süre",
        "waiting_mode_cycles": "Mod: Uyku Döngüsü ({cycles} × {cycle_min}dk + {fall_min}dk)",
        "waiting_mode_exact": "Mod: Tam Saat",
        "waiting_next_check": "Uyku kontrolü: {time}",
        "waiting_confirmed": "Uyku onaylandı",
        "waiting_shifts": "{count} kez kaydırıldı (+{total_min}dk)",
        "waiting_inhibit_on": "Uyku kilidi: AÇIK",
        "waiting_inhibit_off": "Uyku kilidi: KAPALI",
        "bedtime_title": "UYKU KONTROLÜ",
        "bedtime_question": "Uyumaya geçtin mi?",
        "bedtime_subtitle": "Hâlâ uyanıksan hedef saat +{min} dakika ileri alınır.",
        "bedtime_auto_confirm": "{sec}sn içinde otomatik 'Evet' onaylanacak (alarm: {time})",
        "ringing_title": "UYANMA ZAMANI!",
        "ringing_subtitle": "Hedef saat {time} geldi",
        "ringing_volume": "Ses: %{vol} / %{max}",
        "ringing_freq": "Ton: {freq} Hz (sinüs)",
        "ringing_restore_note": "Durdurunca ses %{restore} seviyesine döner",
        "terminal_too_small": "Terminal çok küçük ({cols}×{rows}). En az {min_w}×{min_h} gerekli.",
        "terminal_resize_hint": "Pencereyi büyütün veya çıkmak için Q tuşuna basın.",
        "cli_description": "Uyku döngülü ve kademeli ses artışlı modüler Linux TUI alarm saati.",
        "cli_lang_help": "Arayüz dili (en, ru, tr). Yapılandırma ve ortam değişkenini geçersiz kılar.",
        "cli_config_help": "TOML yapılandırma dosyasının yolu.",
        "cli_version_help": "Program sürümünü göster ve çık.",
        "duration_hm": "{h}sa {m:02d}dk",
        "duration_m": "{m}dk",
    },
}


def _extract_lang_code(locale_value: str) -> str | None:
    """Extract normalized 2-letter language code from a POSIX locale string."""
    cleaned = locale_value.strip()
    if not cleaned:
        return None
    upper = cleaned.upper()
    if upper in ("C", "POSIX") or upper.startswith(("C.", "POSIX.")):
        return None
    primary = cleaned.split(".", 1)[0].split("@", 1)[0]
    code = primary.split("_", 1)[0].split("-", 1)[0].lower()
    return code if code in SUPPORTED_LANGUAGES else None


def detect_system_language(env: Mapping[str, str] | None = None) -> str:
    """Detect language from LC_ALL / LC_MESSAGES / LANG, falling back to ru."""
    source = os.environ if env is None else env
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        raw = source.get(var, "")
        detected = _extract_lang_code(raw)
        if detected is not None:
            return detected
    return DEFAULT_LANGUAGE


def resolve_language(
    cli_lang: str | None = None,
    config_lang: str | None = None,
    env: Mapping[str, str] | None = None,
) -> str:
    """Resolve UI language: --lang > config.toml > LC_ALL/LANG > ru."""
    if cli_lang is not None and cli_lang.strip():
        normalized = cli_lang.strip().lower()
        if normalized not in SUPPORTED_LANGUAGES:
            supported = ", ".join(SUPPORTED_LANGUAGES)
            raise ValueError(f"Unsupported language '{cli_lang}'. Supported: {supported}")
        return normalized

    if config_lang is not None:
        normalized = config_lang.strip().lower()
        if normalized in SUPPORTED_LANGUAGES:
            return normalized

    return detect_system_language(env)


class Translator:
    """Lookup and format localized strings with safe fallbacks."""

    def __init__(self, lang: str = DEFAULT_LANGUAGE) -> None:
        self._lang = lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE

    @property
    def lang(self) -> str:
        return self._lang

    def set_language(self, lang: str) -> None:
        if lang in SUPPORTED_LANGUAGES:
            self._lang = lang

    def cycle_language(self) -> str:
        idx = SUPPORTED_LANGUAGES.index(self._lang)
        self._lang = SUPPORTED_LANGUAGES[(idx + 1) % len(SUPPORTED_LANGUAGES)]
        return self._lang

    def t(self, key: str, **kwargs: Any) -> str:
        table = TRANSLATIONS.get(self._lang, TRANSLATIONS[DEFAULT_LANGUAGE])
        template = table.get(key)
        if template is None:
            template = TRANSLATIONS[DEFAULT_LANGUAGE].get(key)
        if template is None:
            template = TRANSLATIONS["en"].get(key, key)
        if not kwargs:
            return template
        try:
            return template.format(**kwargs)
        except (KeyError, ValueError):
            return template

    def format_duration_minutes(self, total_minutes: int) -> str:
        minutes = max(0, int(total_minutes))
        hours, rem = divmod(minutes, 60)
        if hours > 0:
            return self.t("duration_hm", h=hours, m=rem)
        return self.t("duration_m", m=rem)
