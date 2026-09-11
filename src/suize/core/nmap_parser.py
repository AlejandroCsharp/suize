"""Parser del XML de Nmap (``-oX``) a dataclasses :class:`Host` / :class:`Port`.

No imprime nada ni ejecuta procesos: recibe texto o una ruta y devuelve modelos.
"""

import xml.etree.ElementTree as ET
from pathlib import Path

from suize.models.host import Host, Port


class NmapParseError(ValueError):
    """El texto recibido no es un XML de Nmap válido."""


def parse_nmap_xml(xml_text: str) -> list[Host]:
    """Devuelve un :class:`Host` por cada elemento ``<host>`` del XML.

    Raises:
        NmapParseError: si el XML está vacío, mal formado o no es de Nmap.
    """
    if not xml_text.strip():
        raise NmapParseError("El XML de Nmap está vacío.")
    try:
        # El XML proviene de un Nmap ejecutado localmente por Suize; ElementTree no
        # resuelve entidades externas y expat moderno limita la expansión de entidades.
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise NmapParseError(f"XML de Nmap mal formado: {exc}") from exc
    if root.tag != "nmaprun":
        raise NmapParseError(f"Se esperaba <nmaprun> como raíz y se encontró <{root.tag}>.")
    return [_parse_host(element) for element in root.findall("host")]


def parse_nmap_file(path: Path | str) -> list[Host]:
    """Igual que :func:`parse_nmap_xml` pero leyendo desde un archivo."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise NmapParseError(f"No se pudo leer {path}: {exc.strerror or exc}") from exc
    return parse_nmap_xml(text)


def _parse_host(element: ET.Element) -> Host:
    status_el = element.find("status")
    status = status_el.get("state", "unknown") if status_el is not None else "unknown"

    address, address_type, mac = "", "", ""
    for addr in element.findall("address"):
        kind, value = addr.get("addrtype", ""), addr.get("addr", "")
        if kind == "mac":
            mac = value
        elif not address:
            address, address_type = value, kind
    if not address and mac:
        address, address_type = mac, "mac"

    hostnames: list[str] = []
    for hostname_el in element.findall("hostnames/hostname"):
        name = hostname_el.get("name", "")
        if name and name not in hostnames:
            hostnames.append(name)

    ports = [_parse_port(port_el) for port_el in element.findall("ports/port")]
    return Host(
        address=address,
        address_type=address_type or "ipv4",
        hostnames=hostnames,
        status=status,
        mac=mac,
        ports=ports,
    )


def _parse_port(element: ET.Element) -> Port:
    raw_number = element.get("portid", "")
    try:
        number = int(raw_number)
    except ValueError:
        raise NmapParseError(f"Número de puerto inválido en el XML: '{raw_number}'.") from None

    state_el = element.find("state")
    service_el = element.find("service")
    service = product = version = extra = ""
    if service_el is not None:
        service = service_el.get("name", "")
        tunnel = service_el.get("tunnel", "")
        if tunnel and service:
            service = f"{tunnel}/{service}"  # igual que la salida normal: "ssl/http"
        product = service_el.get("product", "")
        version = service_el.get("version", "")
        extra = service_el.get("extrainfo", "")

    return Port(
        number=number,
        protocol=element.get("protocol", "tcp"),
        state=state_el.get("state", "unknown") if state_el is not None else "unknown",
        service=service,
        product=product,
        version=version,
        extra_info=extra,
    )
