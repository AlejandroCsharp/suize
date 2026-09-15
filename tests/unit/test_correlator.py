"""Tests de la correlación puerto → unidad systemd (sin ejecutar systemctl)."""

from suize.config.settings import load_settings
from suize.core.correlator import (
    CorrelationTables,
    candidate_units,
    correlate,
    parse_unit_list,
    units_to_query,
)
from suize.models.host import Host, Port

#: Las tablas que trae el paquete, tal como las lee la configuración.
TABLES = CorrelationTables(
    ports=load_settings().correlation_ports,
    services=load_settings().correlation_services,
)


def _port(number: int, service: str = "", state: str = "open") -> Port:
    return Port(number=number, protocol="tcp", state=state, service=service)


def test_the_packaged_tables_cover_the_usual_services() -> None:
    assert TABLES.ports[22] == ("ssh", "sshd")
    assert TABLES.ports[80] == TABLES.ports[443] == ("nginx", "apache2", "httpd")
    assert TABLES.ports[3306] == ("mysql", "mariadb")
    assert TABLES.ports[5432] == ("postgresql",)
    assert TABLES.ports[6379] == ("redis", "redis-server")
    assert TABLES.ports[27017] == ("mongod", "mongodb")
    # CUPS escucha en el 631 en casi cualquier escritorio Linux.
    assert TABLES.ports[631] == ("cups",)
    assert TABLES.services["ipp"] == ("cups",)


def test_a_printing_service_is_recognised() -> None:
    """El caso real que motivó ampliar la tabla: puerto 631, servicio ipp."""
    assert candidate_units(_port(631, "ipp"), TABLES) == ["cups"]


def test_candidates_by_port_and_by_service() -> None:
    assert candidate_units(_port(22, "ssh"), TABLES) == ["ssh", "sshd"]  # sin duplicados
    assert candidate_units(_port(2222, "ssh"), TABLES) == ["ssh", "sshd"]  # puerto no estándar
    assert candidate_units(_port(8443, "ssl/http"), TABLES) == ["nginx", "apache2", "httpd"]
    assert candidate_units(_port(9100), TABLES) == []


def test_empty_tables_yield_no_candidates() -> None:
    assert candidate_units(_port(22, "ssh"), CorrelationTables()) == []


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

    correlations = correlate(hosts, available, TABLES)

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
    [item] = correlate(
        [Host(address="h", ports=[_port(6379, "redis")])], {"redis-sentinel"}, TABLES
    )
    assert item.units == ()


# ------------------------------------------------------------------- tablas a medida


def test_a_custom_port_is_correlated() -> None:
    """El caso de uso de la issue: reconocer un servicio propio sin tocar el código."""
    tables = CorrelationTables(ports={8006: ["pveproxy"]})
    hosts = [Host(address="h", ports=[_port(8006, "wsman")])]

    [item] = correlate(hosts, {"pveproxy", "ssh"}, tables)

    assert item.candidates == ("pveproxy",)
    assert item.units == ("pveproxy",)


def test_an_entry_with_no_units_disables_the_port() -> None:
    """Una lista vacía en la configuración quita ese puerto de la tabla."""
    tables = CorrelationTables(ports={22: []}, services={})
    hosts = [Host(address="h", ports=[_port(22, "ssh")])]

    [item] = correlate(hosts, {"ssh"}, tables)

    assert item.candidates == ()
    assert item.units == ()


def test_the_service_table_still_applies_on_a_disabled_port() -> None:
    """Desactivar el puerto no desactiva la vía del nombre de servicio."""
    tables = CorrelationTables(ports={22: []}, services={"ssh": ["ssh"]})
    hosts = [Host(address="h", ports=[_port(22, "ssh")])]

    [item] = correlate(hosts, {"ssh"}, tables)

    assert item.units == ("ssh",)


def test_candidates_keep_the_order_of_the_tables() -> None:
    tables = CorrelationTables(ports={80: ["apache2", "nginx"]}, services={"http": ["httpd"]})

    assert candidate_units(_port(80, "http"), tables) == ["apache2", "nginx", "httpd"]
