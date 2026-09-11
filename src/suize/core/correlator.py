"""Correlación Nmap ↔ logs: qué unidades systemd corresponden a los puertos abiertos."""

from collections.abc import Iterable
from dataclasses import dataclass

from suize.models.host import Host, Port
from suize.utils import shell

SYSTEMCTL_BINARY = "systemctl"

#: Puerto → nombres de unidad systemd candidatos (sin sufijo ``.service``).
PORT_TO_UNITS: dict[int, list[str]] = {
    22: ["ssh", "sshd"],
    80: ["nginx", "apache2", "httpd"],
    443: ["nginx", "apache2", "httpd"],
    3306: ["mysql", "mariadb"],
    5432: ["postgresql"],
    6379: ["redis", "redis-server"],
    27017: ["mongod", "mongodb"],
}

#: Nombre de servicio de Nmap → unidades candidatas. Cubre servicios en puertos
#: no estándar (p. ej. SSH en el 2222 o nginx en el 8080).
SERVICE_TO_UNITS: dict[str, list[str]] = {
    "ssh": ["ssh", "sshd"],
    "http": ["nginx", "apache2", "httpd"],
    "https": ["nginx", "apache2", "httpd"],
    "mysql": ["mysql", "mariadb"],
    "postgresql": ["postgresql"],
    "redis": ["redis", "redis-server"],
    "mongodb": ["mongod", "mongodb"],
}


@dataclass(frozen=True, slots=True)
class Correlation:
    """Un puerto abierto con sus unidades candidatas y las que existen en el sistema."""

    host: str
    port: Port
    candidates: tuple[str, ...]
    units: tuple[str, ...]

    @property
    def matched(self) -> bool:
        return bool(self.units)


def candidate_units(port: Port) -> list[str]:
    """Unidades candidatas para un puerto, por número y por nombre de servicio."""
    service = port.service.lower().rsplit("/", 1)[-1]  # "ssl/http" → "http"
    names = PORT_TO_UNITS.get(port.number, []) + SERVICE_TO_UNITS.get(service, [])
    return list(dict.fromkeys(names))  # sin duplicados, conservando el orden


def parse_unit_list(output: str) -> set[str]:
    """Extrae los nombres de servicio de ``systemctl list-units --plain --no-legend``."""
    units: set[str] = set()
    for line in output.splitlines():
        parts = line.replace("●", " ").split()
        if parts and parts[0].endswith(".service"):
            units.add(parts[0].removesuffix(".service"))
    return units


def list_system_services(*, timeout: float = 15.0) -> set[str]:
    """Servicios cargados en el sistema (activos o no), sin el sufijo ``.service``.

    Raises:
        CommandError: systemctl no existe o falla.
    """
    result = shell.run(
        [
            SYSTEMCTL_BINARY,
            "list-units",
            "--type=service",
            "--all",
            "--no-legend",
            "--no-pager",
            "--plain",
        ],
        timeout=timeout,
    )
    return parse_unit_list(result.stdout)


def _unit_matches(candidate: str, unit: str) -> bool:
    # "postgresql" también debe encontrar instancias como "postgresql@16-main".
    return unit == candidate or unit.startswith(f"{candidate}@")


def correlate(hosts: Iterable[Host], available_units: set[str]) -> list[Correlation]:
    """Cruza los puertos abiertos de ``hosts`` con las unidades existentes."""
    correlations: list[Correlation] = []
    for host in hosts:
        for port in host.open_ports:
            candidates = candidate_units(port)
            units = sorted(
                unit
                for unit in available_units
                if any(_unit_matches(candidate, unit) for candidate in candidates)
            )
            correlations.append(
                Correlation(
                    host=host.address,
                    port=port,
                    candidates=tuple(candidates),
                    units=tuple(units),
                )
            )
    return correlations


def units_to_query(correlations: Iterable[Correlation]) -> list[str]:
    """Unidades únicas (con sufijo ``.service``) para pasar a journalctl."""
    return sorted({f"{unit}.service" for item in correlations for unit in item.units})
