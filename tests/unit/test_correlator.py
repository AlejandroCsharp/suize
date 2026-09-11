"""Tests de la correlación puerto → unidad systemd (sin ejecutar systemctl)."""

from suize.core.correlator import (
    PORT_TO_UNITS,
    candidate_units,
    correlate,
    parse_unit_list,
    units_to_query,
)
from suize.models.host import Host, Port


def _port(number: int, service: str = "", state: str = "open") -> Port:
    return Port(number=number, protocol="tcp", state=state, service=service)


def test_port_map_contains_the_required_services() -> None:
    assert PORT_TO_UNITS[22] == ["ssh", "sshd"]
    assert PORT_TO_UNITS[80] == PORT_TO_UNITS[443] == ["nginx", "apache2", "httpd"]
    assert PORT_TO_UNITS[3306] == ["mysql", "mariadb"]
    assert PORT_TO_UNITS[5432] == ["postgresql"]
    assert PORT_TO_UNITS[6379] == ["redis", "redis-server"]
    assert PORT_TO_UNITS[27017] == ["mongod", "mongodb"]


def test_candidates_by_port_and_by_service() -> None:
    assert candidate_units(_port(22, "ssh")) == ["ssh", "sshd"]  # sin duplicados
    assert candidate_units(_port(2222, "ssh")) == ["ssh", "sshd"]  # puerto no estándar
    assert candidate_units(_port(8443, "ssl/http")) == ["nginx", "apache2", "httpd"]
    assert candidate_units(_port(9100)) == []


def test_parse_unit_list_handles_markers_and_noise() -> None:
    output = (
        "ssh.service      loaded active running OpenBSD Secure Shell server\n"
        "● mariadb.service loaded failed failed  MariaDB database server\n"
        "dbus.socket      loaded active running D-Bus System Message Bus Socket\n"
        "\n"
        "postgresql@16-main.service loaded active running PostgreSQL Cluster 16-main\n"
    )
    assert parse_unit_list(output) == {"ssh", "mariadb", "postgresql@16-main"}


def test_correlate_filters_against_existing_units() -> None:
    hosts = [
        Host(
            address="127.0.0.1",
            status="up",
            ports=[
                _port(22, "ssh"),
                _port(80, "http"),
                _port(3306, "mysql"),
                _port(5432, "postgresql"),
                _port(6379, "redis", state="filtered"),  # no abierto → se ignora
            ],
        )
    ]
    available = {"ssh", "nginx", "postgresql@16-main", "cron"}

    correlations = correlate(hosts, available)

    assert [(c.port.number, c.units) for c in correlations] == [
        (22, ("ssh",)),
        (80, ("nginx",)),
        (3306, ()),
        (5432, ("postgresql@16-main",)),
    ]
    assert [c.matched for c in correlations] == [True, True, False, True]
    assert units_to_query(correlations) == [
        "nginx.service",
        "postgresql@16-main.service",
        "ssh.service",
    ]


def test_prefix_does_not_match_other_units() -> None:
    # "redis" no debe coincidir con "redis-sentinel" (solo nombre exacto o instancia @).
    [item] = correlate([Host(address="h", ports=[_port(6379, "redis")])], {"redis-sentinel"})
    assert item.units == ()
