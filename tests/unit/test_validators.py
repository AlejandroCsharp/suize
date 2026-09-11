"""Tests de validación de entradas del usuario."""

from datetime import datetime

import pytest

from suize.utils.validators import (
    is_loopback,
    is_valid_target,
    parse_datetime,
    parse_priority,
    validate_positive_int,
    validate_target,
    validate_unit,
)


@pytest.mark.parametrize(
    "target",
    [
        "127.0.0.1",
        "192.168.1.10",
        "::1",
        "fe80::1",
        "192.168.1.0/24",
        "10.0.0.0/8",
        "192.168.1.1-50",
        "10.0.0-3.*",
        "localhost",
        "scanme.nmap.org",
        "router.lan.",
        "mi-servidor",
    ],
)
def test_valid_targets(target: str) -> None:
    assert validate_target(f"  {target} ") == target
    assert is_valid_target(target)


@pytest.mark.parametrize(
    ("target", "match"),
    [
        ("", "vacío"),
        ("   ", "vacío"),
        ("-iL /etc/shadow", "empezar por '-'"),
        ("--script=vuln", "empezar por '-'"),
        ("192.168.1.1 10.0.0.1", "sin espacios"),
        ("999.1.1.1", "no es una IP"),
        ("192.168.1.300-400", "no es una IP"),
        ("192.168.1.50-10", "no es una IP"),
        ("host_con_guion_bajo", "no es una IP"),
        ("-mal.example.com", "empezar por '-'"),
        ("host;rm -rf", "sin espacios"),
        ("$(id)", "no es una IP"),
    ],
)
def test_invalid_targets(target: str, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        validate_target(target)
    assert not is_valid_target(target)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("3", "3"),
        ("0", "0"),
        ("7", "7"),
        ("err", "3"),
        ("error", "3"),
        ("WARNING", "4"),
        ("warn", "4"),
        ("emerg", "0"),
        ("panic", "0"),
        ("debug", "7"),
        ("0..4", "0..4"),
        ("emerg..err", "0..3"),
        (" 2..warning ", "2..4"),
    ],
)
def test_parse_priority(value: str, expected: str) -> None:
    assert parse_priority(value) == expected


@pytest.mark.parametrize("value", ["8", "-1", "10", "foo", "", "4..0", "err..", "..3"])
def test_invalid_priority(value: str) -> None:
    with pytest.raises(ValueError, match="rioridad"):
        parse_priority(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-01-15", datetime(2026, 1, 15)),
        ("2026-01-15 10:30", datetime(2026, 1, 15, 10, 30)),
        ("2026-01-15 10:30:45", datetime(2026, 1, 15, 10, 30, 45)),
        ("2026-01-15T10:30:45", datetime(2026, 1, 15, 10, 30, 45)),
        (" 2026-01-15T10:30 ", datetime(2026, 1, 15, 10, 30)),
    ],
)
def test_parse_datetime(value: str, expected: datetime) -> None:
    assert parse_datetime(value) == expected


@pytest.mark.parametrize("value", ["15/01/2026", "2026-13-01", "ayer", "", "2026-01-15 25:00"])
def test_invalid_datetime(value: str) -> None:
    with pytest.raises(ValueError, match="Fecha inválida"):
        parse_datetime(value)


@pytest.mark.parametrize(
    "unit",
    ["ssh", "ssh.service", "postgresql@16-main.service", "systemd-*", "user@1000.service"],
)
def test_valid_units(unit: str) -> None:
    assert validate_unit(unit) == unit


@pytest.mark.parametrize("unit", ["", "   ", "-x", "--help", "ssh;reboot", "ssh service", "a/b"])
def test_invalid_units(unit: str) -> None:
    with pytest.raises(ValueError, match="unidad"):
        validate_unit(unit)


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("localhost", True),
        ("LOCALHOST", True),
        ("127.0.0.1", True),
        ("127.8.9.10", True),
        ("::1", True),
        ("192.168.1.1", False),
        ("example.com", False),
    ],
)
def test_is_loopback(address: str, expected: bool) -> None:
    assert is_loopback(address) is expected


def test_validate_positive_int() -> None:
    assert validate_positive_int("25") == 25
    assert validate_positive_int(3) == 3
    with pytest.raises(ValueError, match="mayor que 0"):
        validate_positive_int("0", "Las líneas")
    with pytest.raises(ValueError, match="número entero"):
        validate_positive_int("diez")
