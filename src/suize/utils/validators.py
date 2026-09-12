"""Validación de entradas: objetivos de Nmap, fechas, prioridades y nombres de unidad.

Las funciones ``validate_*`` y ``parse_*`` lanzan ``ValueError`` con un mensaje en
español listo para mostrar al usuario; las ``is_*`` devuelven ``bool``.
"""

import ipaddress
import re
import socket
from collections.abc import Callable
from datetime import datetime
from typing import Any

from suize.models.log_entry import PRIORITY_NAMES

DATE_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d",
)
DATE_HELP = "AAAA-MM-DD, AAAA-MM-DD HH:MM o AAAA-MM-DD HH:MM:SS"

#: Nombres aceptados para las prioridades (los de journalctl más algunos alias).
PRIORITY_ALIASES: dict[str, int] = {
    **{name: level for level, name in PRIORITY_NAMES.items()},
    "panic": 0,
    "error": 3,
    "warn": 4,
}

_HOSTNAME_LABEL_RE = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)$")
_OCTET_RE = re.compile(r"^(\d{1,3})(?:-(\d{1,3}))?$")
# Cuatro grupos de dígitos, guiones o asteriscos: algo que pretende ser una IP o un rango.
_IPV4_LIKE_RE = re.compile(r"^[\d*-]+(?:\.[\d*-]+){3}$")
# Nombres de unidad systemd; se admiten los comodines que acepta `journalctl -u`.
_UNIT_RE = re.compile(r"^[A-Za-z0-9:_.@\\*?\[\]-]+$")


# --------------------------------------------------------------------------- objetivos


def is_valid_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def is_ipv6_target(value: str) -> bool:
    """``True`` si el objetivo es una dirección o red IPv6 (Nmap exige ``-6`` para ellas)."""
    candidate = value.strip()
    try:
        if "/" in candidate:
            return ipaddress.ip_network(candidate, strict=False).version == 6
        return ipaddress.ip_address(candidate).version == 6
    except ValueError:
        return False


#: Firma de :func:`socket.getaddrinfo`, inyectable para poder probar sin red.
Resolver = Callable[..., list[tuple[Any, ...]]]


def is_hostname_target(value: str) -> bool:
    """``True`` si el objetivo es un nombre de host, no una IP, red o rango."""
    target = value.strip()
    if is_valid_ip(target) or is_valid_network(target) or is_valid_nmap_range(target):
        return False
    # "192.168.1.300" encaja en el formato de hostname pero es una IPv4 mal escrita.
    return _IPV4_LIKE_RE.match(target) is None and is_valid_hostname(target)


def resolves_only_to_ipv6(host: str, *, resolver: Resolver | None = None) -> bool:
    """``True`` si ``host`` resuelve a direcciones IPv6 y a ninguna IPv4.

    Un nombre con registros A y AAAA devuelve ``False``: Nmap usará IPv4 por
    defecto y funcionará sin ``-6``.

    Si el nombre no resuelve se devuelve ``False`` y no se lanza nada: quien
    debe informar del error es Nmap, con su propio mensaje.

    La consulta es bloqueante y usa los tiempos de espera del resolutor del
    sistema (unos segundos en el peor caso, cuando el DNS no responde).
    ``resolver`` permite inyectar un doble en los tests; por defecto se usa
    :func:`socket.getaddrinfo`.
    """
    resolve = resolver or socket.getaddrinfo
    try:
        results = resolve(host, None, proto=socket.IPPROTO_TCP)
    except OSError:
        # gaierror (no resuelve) y cualquier otro fallo de red.
        return False
    families = {entry[0] for entry in results}
    return bool(families) and families == {socket.AF_INET6}


def is_valid_network(value: str) -> bool:
    """Red en notación CIDR, p. ej. ``192.168.1.0/24``."""
    if "/" not in value:
        return False
    try:
        ipaddress.ip_network(value, strict=False)
    except ValueError:
        return False
    return True


def is_valid_nmap_range(value: str) -> bool:
    """Rango IPv4 al estilo Nmap: ``192.168.1.1-50``, ``10.0.0-3.*``."""
    parts = value.split(".")
    if len(parts) != 4:
        return False
    has_range = False
    for part in parts:
        if part == "*":
            has_range = True
            continue
        match = _OCTET_RE.match(part)
        if match is None:
            return False
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) is not None else start
        has_range = has_range or match.group(2) is not None
        if not 0 <= start <= end <= 255:
            return False
    return has_range


def is_valid_hostname(value: str) -> bool:
    """Hostname según RFC 1123 (la última etiqueta no puede ser solo numérica)."""
    name = value.removesuffix(".")
    if not name or len(name) > 253:
        return False
    labels = name.split(".")
    if labels[-1].isdigit():
        return False
    return all(_HOSTNAME_LABEL_RE.match(label) for label in labels)


def validate_target(value: str) -> str:
    """Valida un objetivo de Nmap y lo devuelve limpio.

    Rechaza valores que empiecen por ``-`` para que nunca se interpreten como una
    opción de Nmap (inyección de argumentos, p. ej. ``-iL /etc/shadow``).
    """
    target = value.strip()
    if not target:
        raise ValueError("El objetivo no puede estar vacío.")
    if target.startswith("-"):
        raise ValueError("El objetivo no puede empezar por '-' (Nmap lo tomaría como una opción).")
    if any(char.isspace() for char in target):
        raise ValueError("Indica un único objetivo, sin espacios.")
    if is_valid_ip(target) or is_valid_network(target) or is_valid_nmap_range(target):
        return target
    # "192.168.1.300-400" cumpliría el formato de hostname, pero es un rango mal escrito.
    if _IPV4_LIKE_RE.match(target) is None and is_valid_hostname(target):
        return target
    raise ValueError(f"'{target}' no es una IP, red CIDR, rango de Nmap ni hostname válido.")


def is_valid_target(value: str) -> bool:
    try:
        validate_target(value)
    except ValueError:
        return False
    return True


def is_loopback(address: str) -> bool:
    """``True`` para ``localhost`` y direcciones de loopback (127.0.0.0/8, ::1)."""
    if address.lower() in {"localhost", "localhost.localdomain"}:
        return True
    try:
        return ipaddress.ip_address(address).is_loopback
    except ValueError:
        return False


# --------------------------------------------------------------------------- fechas


def parse_datetime(value: str) -> datetime:
    """Convierte un texto en ``datetime`` (hora local) según :data:`DATE_FORMATS`."""
    text = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"Fecha inválida: '{value}'. Formatos aceptados: {DATE_HELP}.")


def is_valid_datetime(value: str) -> bool:
    try:
        parse_datetime(value)
    except ValueError:
        return False
    return True


# --------------------------------------------------------------------------- journal


def _priority_level(token: str) -> int:
    token = token.strip().lower()
    if len(token) == 1 and token in "01234567":
        return int(token)
    if token in PRIORITY_ALIASES:
        return PRIORITY_ALIASES[token]
    names = ", ".join(PRIORITY_NAMES.values())
    raise ValueError(f"Prioridad inválida: '{token}'. Usa 0-7 o un nombre: {names}.")


def parse_priority(value: str) -> str:
    """Normaliza una prioridad para ``journalctl -p``.

    Acepta ``"3"``, ``"err"``, ``"warning"`` o rangos ``"0..4"`` / ``"emerg..err"``,
    y devuelve siempre la forma numérica (``"3"`` o ``"0..4"``).
    """
    text = value.strip()
    if ".." in text:
        low_raw, _, high_raw = text.partition("..")
        low, high = _priority_level(low_raw), _priority_level(high_raw)
        if low > high:
            raise ValueError("En un rango de prioridades va primero la más grave (p. ej. 0..4).")
        return f"{low}..{high}"
    return str(_priority_level(text))


def is_valid_priority(value: str) -> bool:
    try:
        parse_priority(value)
    except ValueError:
        return False
    return True


def validate_unit(value: str) -> str:
    """Valida un nombre de unidad systemd (con o sin sufijo, admite comodines)."""
    unit = value.strip()
    if not unit:
        raise ValueError("El nombre de la unidad no puede estar vacío.")
    if unit.startswith("-") or _UNIT_RE.match(unit) is None:
        raise ValueError(f"Nombre de unidad inválido: '{unit}'.")
    return unit


def validate_positive_int(value: str | int, name: str = "El valor") -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} debe ser un número entero.") from None
    if number <= 0:
        raise ValueError(f"{name} debe ser mayor que 0.")
    return number
