"""Serialización de resultados a formatos legibles por otras herramientas.

Reúne el volcado a JSON y a CSV, y la apertura del destino (un archivo o la
salida estándar). Es la contrapartida de :mod:`suize.ui.render_nmap` y
:mod:`suize.ui.render_logs`: aquellos producen tablas para una persona, este
produce datos para un script o una hoja de cálculo.

Ninguna función imprime por su cuenta: todas escriben en el flujo que reciben,
así que se pueden probar contra un ``StringIO``.
"""

import csv
import json
import sys
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

from suize.core.correlator import Correlation
from suize.models.host import Host
from suize.models.log_entry import LogEntry

#: Formatos que aceptan ``--format``.
OUTPUT_FORMATS = ("table", "json", "csv")

#: Encabezados del CSV de escaneo. La columna ``unidades`` solo aparece con --correlate.
SCAN_COLUMNS = (
    "direccion",
    "hostname",
    "estado_host",
    "mac",
    "puerto",
    "protocolo",
    "estado",
    "servicio",
    "producto",
    "version",
    "info_extra",
)

#: Encabezados del CSV de logs.
LOG_COLUMNS = (
    "fecha",
    "prioridad",
    "prioridad_nombre",
    "unidad",
    "hostname",
    "pid",
    "mensaje",
)

#: Clave con la que se localizan las unidades correlacionadas de un puerto.
PortKey = tuple[str, int, str]


@contextmanager
def open_output(path: Path | None) -> Iterator[TextIO]:
    """Abre ``path`` para escritura, o cede ``sys.stdout`` si es ``None``.

    ``newline=""`` es obligatorio para el módulo ``csv``: sin él, Python añade
    un retorno de carro extra en cada fila.
    """
    if path is None:
        yield sys.stdout
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        yield handle


# ------------------------------------------------------------------------------- JSON


def json_default(value: object) -> str:
    """Serializa los tipos que ``json`` no conoce (por ahora, ``datetime``)."""
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Tipo no serializable: {type(value).__name__}")


def dump_json(payload: Mapping[str, Any], stream: TextIO) -> None:
    """Escribe ``payload`` como JSON indentado, con un salto de línea final."""
    stream.write(json.dumps(payload, ensure_ascii=False, indent=2, default=json_default))
    stream.write("\n")


def entry_to_json(entry: LogEntry) -> dict[str, Any]:
    """Convierte una entrada de log añadiendo el nombre de su prioridad."""
    return {**asdict(entry), "priority_name": entry.priority_name}


def correlation_to_json(item: Correlation) -> dict[str, Any]:
    """Aplana una correlación: del puerto solo interesan número, protocolo y servicio."""
    return {
        "host": item.host,
        "port": item.port.number,
        "protocol": item.port.protocol,
        "service": item.port.service,
        "candidates": list(item.candidates),
        "units": list(item.units),
    }


# -------------------------------------------------------------------------------- CSV


def units_by_port(correlations: Sequence[Correlation]) -> dict[PortKey, list[str]]:
    """Indexa las unidades correlacionadas por (host, puerto, protocolo)."""
    return {
        (item.host, item.port.number, item.port.protocol): list(item.units) for item in correlations
    }


def write_scan_csv(
    hosts: Sequence[Host],
    stream: TextIO,
    *,
    correlated: Mapping[PortKey, Sequence[str]] | None = None,
) -> int:
    """Escribe una fila por puerto y devuelve el número de filas de datos.

    Los hosts sin ningún puerto generan una fila con las columnas del puerto
    vacías, para que no desaparezcan del archivo. Si ``correlated`` no es
    ``None`` se añade la columna ``unidades``, con los nombres separados por
    punto y coma (una coma rompería la celda).
    """
    columns = [*SCAN_COLUMNS, "unidades"] if correlated is not None else list(SCAN_COLUMNS)
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(columns)

    rows = 0
    for host in hosts:
        base = [
            host.address,
            host.hostname,
            host.status,
            host.mac,
        ]
        if not host.ports:
            # El host existe aunque no tenga puertos: se conserva con celdas vacías.
            empty = ["" for _ in range(len(columns) - len(base))]
            writer.writerow([*base, *empty])
            rows += 1
            continue

        for port in host.ports:
            row = [
                *base,
                port.number,
                port.protocol,
                port.state,
                port.service,
                port.product,
                port.version,
                port.extra_info,
            ]
            if correlated is not None:
                units = correlated.get((host.address, port.number, port.protocol), ())
                row.append(";".join(units))
            writer.writerow(row)
            rows += 1
    return rows


def write_logs_csv(entries: Sequence[LogEntry], stream: TextIO) -> int:
    """Escribe una fila por entrada de log y devuelve el número de filas de datos."""
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(LOG_COLUMNS)
    for entry in entries:
        writer.writerow(
            [
                entry.timestamp.isoformat(),
                entry.priority,
                entry.priority_name,
                entry.unit,
                entry.hostname,
                entry.pid if entry.pid is not None else "",
                entry.message,
            ]
        )
    return len(entries)
