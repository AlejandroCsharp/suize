"""Tests de la construcción del comando de Nmap (sin ejecutar Nmap)."""

from pathlib import Path

import pytest

from suize.core.nmap_runner import SCAN_PROFILES, build_command
from suize.utils.validators import is_ipv6_target

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
