"""Tests de presets y rangos temporales (con ``now`` fijo para que sean deterministas)."""

from datetime import datetime, timedelta

import pytest

from suize.config.settings import load_settings
from suize.utils.time_filter import (
    CUSTOM_KEY,
    DEFAULT_PRESETS,
    TimeRange,
    custom_range,
    parse_range,
    parse_relative,
    resolve_preset,
)

EXPECTED_LABELS = [
    "Últimos 15 minutos",
    "Última hora",
    "Últimas 6 horas",
    "Últimas 24 horas",
    "Últimos 7 días",
    "Hoy",
    "Ayer",
    "Personalizado (fecha exacta)",
]


def test_default_presets_have_the_expected_labels() -> None:
    assert list(DEFAULT_PRESETS.values()) == EXPECTED_LABELS


def test_default_toml_presets_match_code() -> None:
    settings = load_settings(env={})
    assert [(p.key, p.label) for p in settings.time_presets] == list(DEFAULT_PRESETS.items())
    assert settings.default_time_preset in DEFAULT_PRESETS


@pytest.mark.parametrize(
    ("key", "delta"),
    [
        ("15m", timedelta(minutes=15)),
        ("1h", timedelta(hours=1)),
        ("6h", timedelta(hours=6)),
        ("24h", timedelta(hours=24)),
        ("7d", timedelta(days=7)),
    ],
)
def test_relative_presets(key: str, delta: timedelta, fixed_now: datetime) -> None:
    time_range = resolve_preset(key, now=fixed_now)
    assert time_range.since == fixed_now - delta
    assert time_range.until is None
    assert time_range.label == DEFAULT_PRESETS[key]


def test_today(fixed_now: datetime) -> None:
    time_range = resolve_preset("today", now=fixed_now)
    assert time_range.since == datetime(2026, 1, 15, 0, 0, 0)
    assert time_range.until is None
    assert time_range.label == "Hoy"


def test_yesterday(fixed_now: datetime) -> None:
    time_range = resolve_preset("yesterday", now=fixed_now)
    assert time_range.since == datetime(2026, 1, 14, 0, 0, 0)
    assert time_range.until == datetime(2026, 1, 15, 0, 0, 0)
    assert time_range.label == "Ayer"


@pytest.mark.parametrize(("alias", "canonical"), [("hoy", "today"), (" Ayer ", "yesterday")])
def test_spanish_aliases(alias: str, canonical: str, fixed_now: datetime) -> None:
    assert resolve_preset(alias, now=fixed_now) == resolve_preset(canonical, now=fixed_now)


def test_custom_label_overrides_default(fixed_now: datetime) -> None:
    assert resolve_preset("1h", now=fixed_now, label="Mi hora").label == "Mi hora"


def test_custom_preset_needs_dates(fixed_now: datetime) -> None:
    with pytest.raises(ValueError, match="custom_range"):
        resolve_preset(CUSTOM_KEY, now=fixed_now)


def test_unknown_preset(fixed_now: datetime) -> None:
    with pytest.raises(ValueError, match="desconocido"):
        resolve_preset("mañana", now=fixed_now)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("15m", timedelta(minutes=15)),
        ("30min", timedelta(minutes=30)),
        ("90s", timedelta(seconds=90)),
        ("2d", timedelta(days=2)),
        ("1w", timedelta(weeks=1)),
        ("-3h", timedelta(hours=3)),
        (" 12H ", timedelta(hours=12)),
        ("0h", None),
        ("h", None),
        ("abc", None),
        ("1y", None),
    ],
)
def test_parse_relative(text: str, expected: timedelta | None) -> None:
    assert parse_relative(text) == expected


def test_to_journalctl_args() -> None:
    time_range = TimeRange(
        since=datetime(2026, 1, 14, 8, 0, 5), until=datetime(2026, 1, 14, 9, 30, 0)
    )
    assert time_range.to_journalctl_args() == [
        "--since=2026-01-14 08:00:05",
        "--until=2026-01-14 09:30:00",
    ]
    assert TimeRange().to_journalctl_args() == []


def test_describe(fixed_now: datetime) -> None:
    assert resolve_preset("1h", now=fixed_now).describe() == (
        "Última hora (2026-01-15 11:30:45 → ahora)"
    )
    assert TimeRange(until=datetime(2026, 1, 1)).describe() == "el inicio → 2026-01-01 00:00:00"


def test_since_after_until_is_rejected() -> None:
    with pytest.raises(ValueError, match="posterior"):
        TimeRange(since=datetime(2026, 1, 2), until=datetime(2026, 1, 1))


def test_custom_range() -> None:
    time_range = custom_range("2026-01-10 08:00", "2026-01-10 18:30:15")
    assert time_range.since == datetime(2026, 1, 10, 8, 0)
    assert time_range.until == datetime(2026, 1, 10, 18, 30, 15)
    assert custom_range("2026-01-10").until is None


class TestParseRange:
    def test_nothing_means_no_filter(self) -> None:
        assert parse_range(None) is None
        assert parse_range("", "") is None

    def test_preset_key(self, fixed_now: datetime) -> None:
        assert parse_range("1h", now=fixed_now) == resolve_preset("1h", now=fixed_now)

    def test_any_duration(self, fixed_now: datetime) -> None:
        time_range = parse_range("45m", now=fixed_now)
        assert time_range is not None
        assert time_range.since == fixed_now - timedelta(minutes=45)

    def test_preset_with_until(self, fixed_now: datetime) -> None:
        time_range = parse_range("yesterday", "2026-01-14 12:00", now=fixed_now)
        assert time_range is not None
        assert time_range.since == datetime(2026, 1, 14)
        assert time_range.until == datetime(2026, 1, 14, 12, 0)

    def test_exact_dates(self) -> None:
        time_range = parse_range("2026-01-10", "2026-01-11 06:00")
        assert time_range == TimeRange(
            since=datetime(2026, 1, 10),
            until=datetime(2026, 1, 11, 6, 0),
            label="Personalizado",
        )

    def test_only_until(self) -> None:
        time_range = parse_range(None, "2026-01-11")
        assert time_range is not None
        assert time_range.since is None
        assert time_range.until == datetime(2026, 1, 11)

    def test_custom_keyword_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="fecha exacta"):
            parse_range("custom")

    def test_garbage_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="Rango temporal inválido"):
            parse_range("la semana pasada")

    def test_invalid_until(self) -> None:
        with pytest.raises(ValueError, match="Fecha inválida"):
            parse_range("1h", "ayer a la tarde")
