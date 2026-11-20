"""Unit tests for alarm_tui.i18n."""

from __future__ import annotations

import pytest

from alarm_tui.i18n import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    TRANSLATIONS,
    Translator,
    detect_system_language,
    resolve_language,
)


def test_language_resolution_priority() -> None:
    env_tr = {"LC_ALL": "tr_TR.UTF-8", "LANG": "en_US.UTF-8"}

    # 1. --lang beats config and env
    assert resolve_language(cli_lang="en", config_lang="ru", env=env_tr) == "en"
    assert resolve_language(cli_lang="TR", config_lang="en", env={"LANG": "ru_RU.UTF-8"}) == "tr"

    # 2. config.toml beats env when --lang is omitted
    assert resolve_language(cli_lang=None, config_lang="ru", env=env_tr) == "ru"
    assert resolve_language(cli_lang=None, config_lang="en", env=env_tr) == "en"

    # 3. auto / empty config defers to LC_ALL > LC_MESSAGES > LANG
    assert resolve_language(cli_lang=None, config_lang="auto", env=env_tr) == "tr"
    assert resolve_language(cli_lang=None, config_lang="", env={"LANG": "en_GB.UTF-8"}) == "en"
    assert (
        resolve_language(
            cli_lang=None,
            config_lang="auto",
            env={"LC_ALL": "", "LC_MESSAGES": "tr_TR.utf8", "LANG": "en_US.UTF-8"},
        )
        == "tr"
    )

    # 4. Fallback to ru when locale is unsupported, POSIX/C, or empty
    assert resolve_language(cli_lang=None, config_lang="auto", env={"LANG": "de_DE.UTF-8"}) == "ru"
    assert resolve_language(cli_lang=None, config_lang="auto", env={"LC_ALL": "C.UTF-8"}) == "ru"
    assert resolve_language(cli_lang=None, config_lang="auto", env={}) == DEFAULT_LANGUAGE


def test_invalid_cli_language_raises() -> None:
    with pytest.raises(ValueError):
        resolve_language(cli_lang="fr")


def test_detect_system_language_ignores_posix() -> None:
    assert detect_system_language({"LC_ALL": "POSIX", "LANG": "tr_TR.UTF-8"}) == "tr"
    assert detect_system_language({"LC_ALL": "C", "LANG": "C"}) == "ru"


def test_all_languages_have_identical_non_empty_keys() -> None:
    assert set(TRANSLATIONS.keys()) == set(SUPPORTED_LANGUAGES)
    expected_keys = set(TRANSLATIONS["en"].keys())
    assert expected_keys

    for lang in SUPPORTED_LANGUAGES:
        table = TRANSLATIONS[lang]
        assert set(table.keys()) == expected_keys, f"Key mismatch for language '{lang}'"
        for key, value in table.items():
            assert isinstance(value, str) and value.strip(), f"Empty translation: {lang}.{key}"


def test_translator_formatting_and_cycling() -> None:
    tr = Translator("en")
    assert tr.t("preview_wake", time="07:45") == "Wake up at 07:45"
    assert tr.format_duration_minutes(135) == "2h 15m"
    assert tr.format_duration_minutes(45) == "45m"

    seen = [tr.lang]
    for _ in range(len(SUPPORTED_LANGUAGES)):
        seen.append(tr.cycle_language())
    assert seen[0] == seen[-1]
    assert set(seen[:-1]) == set(SUPPORTED_LANGUAGES)
