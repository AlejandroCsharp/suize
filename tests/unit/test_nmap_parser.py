"""Tests del parser de XML de Nmap contra un escaneo real (``fixtures/nmap_scan.xml``)."""

from pathlib import Path

import pytest

from suize.core.nmap_parser import NmapParseError, parse_nmap_file, parse_nmap_xml
from suize.models.host import Host, Port


@pytest.fixture
def hosts(nmap_xml: str) -> list[Host]:
    return parse_nmap_xml(nmap_xml)


def _by_address(hosts: list[Host], address: str) -> Host:
    return next(host for host in hosts if host.address == address)


def test_parses_every_host_and_ignores_hosthint(hosts: list[Host]) -> None:
    # El XML trae un <hosthint> además de los tres <host>: no debe contarse.
    assert [host.address for host in hosts] == ["127.0.0.1", "192.168.1.20", "192.168.1.30"]


def test_localhost_basic_fields(hosts: list[Host]) -> None:
    host = _by_address(hosts, "127.0.0.1")
    assert host.address_type == "ipv4"
    assert host.is_up
    assert host.hostnames == ["localhost"]  # los duplicados (user/PTR) se colapsan
    assert host.hostname == "localhost"
    assert host.mac == ""


def test_localhost_ports_states_and_versions(hosts: list[Host]) -> None:
    host = _by_address(hosts, "127.0.0.1")
    assert [(p.number, p.state) for p in host.ports] == [
        (22, "open"),
        (80, "open"),
        (631, "closed"),
        (3306, "open"),
        (6379, "filtered"),
    ]
    assert [p.number for p in host.open_ports] == [22, 80, 3306]

    ssh = host.ports[0]
    assert ssh == Port(
        number=22,
        protocol="tcp",
        state="open",
        service="ssh",
        product="OpenSSH",
        version="9.6p1 Ubuntu 3ubuntu13.5",
        extra_info="Ubuntu Linux; protocol 2.0",
    )
    assert ssh.version_label == "OpenSSH 9.6p1 Ubuntu 3ubuntu13.5 (Ubuntu Linux; protocol 2.0)"
    assert host.ports[1].version_label == "nginx 1.24.0 (Ubuntu)"
    assert host.ports[2].version_label == ""  # servicio adivinado por tabla, sin versión


def test_remote_host_mac_tunnel_and_missing_service(hosts: list[Host]) -> None:
    host = _by_address(hosts, "192.168.1.20")
    assert host.mac == "AA:BB:CC:11:22:33"
    assert host.address_type == "ipv4"  # la MAC no sustituye a la IP
    assert host.hostname == "router.lan"

    ports = {port.number: port for port in host.ports}
    assert ports[443].service == "ssl/http"  # tunnel="ssl" igual que la salida normal
    assert ports[443].version_label == "lighttpd 1.4.76"
    assert ports[9100].service == ""  # <port> sin <service>
    assert ports[9100].version_label == ""
    assert ports[9100].is_open


def test_down_host_has_no_ports(hosts: list[Host]) -> None:
    host = _by_address(hosts, "192.168.1.30")
    assert not host.is_up
    assert host.status == "down"
    assert host.ports == []
    assert host.hostname == ""


def test_parse_nmap_file_reads_from_disk(fixtures_dir: Path) -> None:
    hosts = parse_nmap_file(fixtures_dir / "nmap_scan.xml")
    assert len(hosts) == 3


def test_parse_nmap_file_missing_file(tmp_path: Path) -> None:
    with pytest.raises(NmapParseError, match="No se pudo leer"):
        parse_nmap_file(tmp_path / "no-existe.xml")


def test_host_with_only_mac_address() -> None:
    xml = (
        '<nmaprun><host><status state="up"/>'
        '<address addr="AA:BB:CC:DD:EE:FF" addrtype="mac"/></host></nmaprun>'
    )
    [host] = parse_nmap_xml(xml)
    assert host.address == "AA:BB:CC:DD:EE:FF"
    assert host.address_type == "mac"


def test_scan_without_hosts_returns_empty_list() -> None:
    assert parse_nmap_xml("<nmaprun><runstats/></nmaprun>") == []


@pytest.mark.parametrize(
    ("xml", "match"),
    [
        ("", "vacío"),
        ("   \n", "vacío"),
        ("<nmaprun><host>", "mal formado"),
        ("<html><body/></html>", "<nmaprun>"),
        (
            '<nmaprun><host><address addr="1.2.3.4" addrtype="ipv4"/>'
            '<ports><port protocol="tcp" portid="abc"/></ports></host></nmaprun>',
            "puerto inválido",
        ),
    ],
)
def test_invalid_xml_raises(xml: str, match: str) -> None:
    with pytest.raises(NmapParseError, match=match):
        parse_nmap_xml(xml)
