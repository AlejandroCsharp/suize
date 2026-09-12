"""Tests de la serialización a JSON y CSV."""

import csv
import io
import json
from datetime import datetime
from pathlib import Path

import pytest

from suize.core.correlator import Correlation
from suize.models.host import Host, Port
from suize.models.log_entry import LogEntry
from suize.ui import export


def _port(number: int = 22, **kwargs: str) -> Port:
    defaults = {
        "protocol": "tcp",
        "state": "open",
        "service": "ssh",
        "product": "OpenSSH",
        "version": "9.6p1",
        "extra_info": "",
    }
    return Port(number=number, **{**defaults, **kwargs})  # type: ignore[arg-type]


def _host(address: str = "127.0.0.1", ports: list[Port] | None = None, **kwargs: str) -> Host:
    defaults = {"address_type": "ipv4", "status": "up", "mac": ""}
    return Host(
        address=address,
        hostnames=["localhost"],
        ports=ports if ports is not None else [_port()],
        **{**defaults, **kwargs},  # type: ignore[arg-type]
    )


def _entry(**kwargs: object) -> LogEntry:
    defaults: dict[str, object] = {
        "timestamp": datetime(2026, 1, 15, 10, 30),
        "priority": 3,
        "unit": "nginx.service",
        "message": "bind() failed",
        "hostname": "suize-lab",
        "pid": 1201,
    }
    return LogEntry(**{**defaults, **kwargs})  # type: ignore[arg-type]


def _rows(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text)))


# ------------------------------------------------------------------------- CSV escaneo


def test_scan_csv_writes_one_row_per_port() -> None:
    stream = io.StringIO()

    rows = export.write_scan_csv([_host(ports=[_port(22), _port(80, service="http")])], stream)

    assert rows == 2
    table = _rows(stream.getvalue())
    assert table[0] == list(export.SCAN_COLUMNS)
    assert [row[4] for row in table[1:]] == ["22", "80"]


def test_scan_csv_repeats_host_columns_on_every_port() -> None:
    stream = io.StringIO()

    export.write_scan_csv([_host(ports=[_port(22), _port(80)], mac="AA:BB")], stream)

    table = _rows(stream.getvalue())
    assert [row[:4] for row in table[1:]] == [
        ["127.0.0.1", "localhost", "up", "AA:BB"],
        ["127.0.0.1", "localhost", "up", "AA:BB"],
    ]


def test_host_without_ports_keeps_a_row_with_empty_port_columns() -> None:
    """Un host caído no debe desaparecer del archivo."""
    stream = io.StringIO()

    rows = export.write_scan_csv([_host(address="192.168.1.30", ports=[], status="down")], stream)

    assert rows == 1
    table = _rows(stream.getvalue())
    assert table[1][:4] == ["192.168.1.30", "localhost", "down", ""]
    assert table[1][4:] == [""] * (len(export.SCAN_COLUMNS) - 4)


def test_scan_csv_includes_closed_and_filtered_ports() -> None:
    stream = io.StringIO()

    export.write_scan_csv([_host(ports=[_port(631, state="closed"), _port(22)])], stream)

    assert [row[6] for row in _rows(stream.getvalue())[1:]] == ["closed", "open"]


def test_scan_csv_without_hosts_writes_only_the_header() -> None:
    stream = io.StringIO()

    rows = export.write_scan_csv([], stream)

    assert rows == 0
    assert _rows(stream.getvalue()) == [list(export.SCAN_COLUMNS)]


def test_scan_csv_quotes_values_that_contain_commas() -> None:
    stream = io.StringIO()

    export.write_scan_csv(
        [_host(ports=[_port(extra_info="Ubuntu Linux; protocol 2.0, x")])], stream
    )

    # El texto debe sobrevivir al viaje de ida y vuelta por el lector de CSV.
    assert _rows(stream.getvalue())[1][10] == "Ubuntu Linux; protocol 2.0, x"


# --------------------------------------------------------------------- CSV correlación


def test_correlated_scan_csv_adds_the_units_column() -> None:
    host = _host(ports=[_port(22)])
    correlations = [
        Correlation(host="127.0.0.1", port=_port(22), candidates=("ssh",), units=("ssh",))
    ]
    stream = io.StringIO()

    export.write_scan_csv([host], stream, correlated=export.units_by_port(correlations))

    table = _rows(stream.getvalue())
    assert table[0][-1] == "unidades"
    assert table[1][-1] == "ssh"


def test_several_units_are_joined_with_semicolons() -> None:
    """Una coma rompería la celda, así que se usa punto y coma."""
    correlations = [
        Correlation(
            host="127.0.0.1",
            port=_port(80, service="http"),
            candidates=("nginx", "apache2"),
            units=("nginx", "apache2"),
        )
    ]
    stream = io.StringIO()

    export.write_scan_csv(
        [_host(ports=[_port(80, service="http")])],
        stream,
        correlated=export.units_by_port(correlations),
    )

    assert _rows(stream.getvalue())[1][-1] == "nginx;apache2"


def test_port_without_correlation_gets_an_empty_units_cell() -> None:
    stream = io.StringIO()

    export.write_scan_csv([_host(ports=[_port(3306)])], stream, correlated={})

    assert _rows(stream.getvalue())[1][-1] == ""


def test_units_column_is_absent_without_correlation() -> None:
    stream = io.StringIO()

    export.write_scan_csv([_host()], stream)

    assert "unidades" not in _rows(stream.getvalue())[0]


# ----------------------------------------------------------------------------- CSV logs


def test_logs_csv_writes_one_row_per_entry() -> None:
    stream = io.StringIO()

    rows = export.write_logs_csv([_entry(), _entry(priority=6)], stream)

    assert rows == 2
    table = _rows(stream.getvalue())
    assert table[0] == list(export.LOG_COLUMNS)
    assert len(table) == 3


def test_logs_csv_adds_the_priority_name() -> None:
    stream = io.StringIO()

    export.write_logs_csv([_entry(priority=3)], stream)

    row = _rows(stream.getvalue())[1]
    assert row[1] == "3"
    assert row[2] == "err"


def test_logs_csv_formats_the_timestamp_as_iso() -> None:
    stream = io.StringIO()

    export.write_logs_csv([_entry(timestamp=datetime(2026, 1, 15, 10, 31, 5))], stream)

    assert _rows(stream.getvalue())[1][0] == "2026-01-15T10:31:05"


def test_logs_csv_leaves_the_pid_empty_when_missing() -> None:
    stream = io.StringIO()

    export.write_logs_csv([_entry(pid=None)], stream)

    assert _rows(stream.getvalue())[1][5] == ""


def test_logs_csv_preserves_multiline_messages() -> None:
    stream = io.StringIO()

    export.write_logs_csv([_entry(message="linea 1\nlinea 2")], stream)

    assert _rows(stream.getvalue())[1][6] == "linea 1\nlinea 2"


# ---------------------------------------------------------------------------- destino


def test_open_output_writes_to_the_given_file(tmp_path: Path) -> None:
    destination = tmp_path / "salida.csv"

    with export.open_output(destination) as stream:
        stream.write("hola\n")

    assert destination.read_text(encoding="utf-8") == "hola\n"


def test_open_output_yields_stdout_when_the_path_is_none(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with export.open_output(None) as stream:
        stream.write("por stdout\n")

    assert capsys.readouterr().out == "por stdout\n"


def test_open_output_does_not_close_stdout() -> None:
    """Cerrar sys.stdout dejaría inservible el resto del proceso."""
    with export.open_output(None):
        pass

    import sys

    assert not sys.stdout.closed


def test_csv_file_has_no_carriage_returns(tmp_path: Path) -> None:
    """newline='' más lineterminator='\\n' evitan el CRLF por defecto del módulo csv."""
    destination = tmp_path / "salida.csv"

    with export.open_output(destination) as stream:
        export.write_logs_csv([_entry()], stream)

    assert b"\r" not in destination.read_bytes()


# ------------------------------------------------------------------------------- JSON


def test_dump_json_serializes_datetimes() -> None:
    stream = io.StringIO()

    export.dump_json({"cuando": datetime(2026, 1, 15, 10, 30)}, stream)

    assert json.loads(stream.getvalue()) == {"cuando": "2026-01-15T10:30:00"}


def test_dump_json_keeps_accents_readable() -> None:
    stream = io.StringIO()

    export.dump_json({"mensaje": "conexión"}, stream)

    assert "conexión" in stream.getvalue()


def test_json_default_rejects_unknown_types() -> None:
    with pytest.raises(TypeError, match="no serializable"):
        export.json_default(object())


def test_entry_to_json_includes_the_priority_name() -> None:
    assert export.entry_to_json(_entry(priority=4))["priority_name"] == "warning"
