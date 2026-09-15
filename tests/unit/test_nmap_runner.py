"""Tests de la construcción del comando de Nmap (sin ejecutar Nmap ni tocar la red)."""

import socket
from pathlib import Path
from typing import Any

import pytest

from suize.core.nmap_runner import SCAN_PROFILES, build_command, needs_ipv6
from suize.utils.validators import Resolver, is_ipv6_target

XML = Path("/tmp/scan.xml")


def test_standard_profile_builds_base_command() -> None:
    assert build_command("192.168.1.10", XML) == [
        "nmap",
        "-sV",
        "-oX",
        str(XML),
        "192.168.1.10",
    ]


@pytest.mark.parametrize(
    ("profile", "expected_flag"),
    [("fast", "-F"), ("full", "-p-")],
)
def test_profiles_add_their_flags(profile: str, expected_flag: str) -> None:
    cmd = build_command("10.0.0.1", XML, profile=profile)

    assert expected_flag in cmd
    assert cmd[-1] == "10.0.0.1"


def test_every_profile_builds_a_valid_command() -> None:
    for name in SCAN_PROFILES:
        cmd = build_command("127.0.0.1", XML, profile=name)
        assert cmd[0] == "nmap"
        assert "-sV" in cmd


def test_unknown_profile_is_rejected() -> None:
    with pytest.raises(ValueError, match="Perfil de escaneo desconocido"):
        build_command("127.0.0.1", XML, profile="turbo")


def test_target_that_looks_like_an_option_is_rejected() -> None:
    with pytest.raises(ValueError, match="no puede empezar"):
        build_command("-iL /etc/shadow", XML)


@pytest.mark.parametrize("target", ["::1", "fe80::1", "2001:db8::/64"])
def test_ipv6_targets_add_the_dash_6_flag(target: str) -> None:
    cmd = build_command(target, XML)

    assert cmd[:3] == ["nmap", "-6", "-sV"]
    assert cmd[-1] == target


@pytest.mark.parametrize("target", ["127.0.0.1", "192.168.1.0/24", "10.0.0.1-20", "router.lan"])
def test_ipv4_and_hostname_targets_do_not_use_dash_6(target: str) -> None:
    assert "-6" not in build_command(target, XML)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("::1", True),
        ("2001:db8::/64", True),
        (" fe80::1 ", True),
        ("127.0.0.1", False),
        ("192.168.1.0/24", False),
        ("scanme.nmap.org", False),
        ("no es una ip", False),
    ],
)
def test_is_ipv6_target(value: str, expected: bool) -> None:
    assert is_ipv6_target(value) is expected


# --------------------------------------------------------------------- IPv6 por nombre


def fake_resolver(*families: int) -> Resolver:
    """Devuelve un doble de ``socket.getaddrinfo`` con las familias indicadas."""

    def resolve(host: str, port: object, **kwargs: object) -> list[tuple[Any, ...]]:
        return [(family, socket.SOCK_STREAM, 6, "", ("::1", 0)) for family in families]

    return resolve


def failing_resolver(host: str, port: object, **kwargs: object) -> list[tuple[Any, ...]]:
    raise socket.gaierror(-2, "Name or service not known")


def test_hostname_that_only_resolves_to_ipv6_needs_the_flag() -> None:
    assert needs_ipv6("solo-ipv6.lan", resolver=fake_resolver(socket.AF_INET6)) is True


def test_dual_stack_hostname_does_not_need_the_flag() -> None:
    """Con registros A y AAAA, Nmap usa IPv4 y funciona sin -6."""
    resolver = fake_resolver(socket.AF_INET, socket.AF_INET6)

    assert needs_ipv6("dual.lan", resolver=resolver) is False


def test_ipv4_only_hostname_does_not_need_the_flag() -> None:
    assert needs_ipv6("solo-ipv4.lan", resolver=fake_resolver(socket.AF_INET)) is False


def test_hostname_that_does_not_resolve_does_not_need_the_flag() -> None:
    """Del error debe informar Nmap, con su propio mensaje."""
    assert needs_ipv6("no-existe.lan", resolver=failing_resolver) is False


def test_hostname_with_no_records_does_not_need_the_flag() -> None:
    assert needs_ipv6("vacio.lan", resolver=fake_resolver()) is False


@pytest.mark.parametrize("target", ["::1", "2001:db8::/64", " fe80::1 "])
def test_ipv6_literals_do_not_consult_dns(target: str) -> None:
    """Se deciden por su formato: el resolutor no debe llegar a llamarse."""
    llamadas: list[str] = []

    def spy(host: str, port: object, **kwargs: object) -> list[tuple[Any, ...]]:
        llamadas.append(host)
        return []

    assert needs_ipv6(target, resolver=spy) is True
    assert llamadas == []


@pytest.mark.parametrize("target", ["127.0.0.1", "192.168.1.0/24", "10.0.0.1-20", "192.168.1.*"])
def test_addresses_and_ranges_do_not_consult_dns(target: str) -> None:
    llamadas: list[str] = []

    def spy(host: str, port: object, **kwargs: object) -> list[tuple[Any, ...]]:
        llamadas.append(host)
        return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 0))]

    assert needs_ipv6(target, resolver=spy) is False
    assert llamadas == []


def test_force_ipv6_adds_the_flag_to_a_hostname() -> None:
    cmd = build_command("solo-ipv6.lan", XML, force_ipv6=True)

    assert cmd[:3] == ["nmap", "-6", "-sV"]


def test_build_command_never_resolves_by_itself(monkeypatch: pytest.MonkeyPatch) -> None:
    """Construir el comando debe seguir siendo una operación sin red."""

    def boom(*args: object, **kwargs: object) -> object:
        raise AssertionError("build_command no debe consultar el DNS")

    monkeypatch.setattr(socket, "getaddrinfo", boom)

    assert "-6" not in build_command("ejemplo.lan", XML)


# ----------------------------------------------------------------- descubrimiento (-Pn)


def test_skip_ping_adds_the_flag() -> None:
    assert "-Pn" in build_command("192.168.1.10", XML, skip_ping=True)


def test_the_flag_is_absent_by_default() -> None:
    assert "-Pn" not in build_command("192.168.1.10", XML)


def test_skip_ping_combines_with_ipv6_and_profile() -> None:
    cmd = build_command("::1", XML, profile="fast", skip_ping=True)

    assert cmd[:4] == ["nmap", "-6", "-Pn", "-sV"]
    assert "-F" in cmd
