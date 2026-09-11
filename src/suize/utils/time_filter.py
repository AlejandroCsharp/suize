"""Presets y parseo de rangos temporales para journalctl.

Los rangos se calculan como fechas absolutas en hora local (igual que interpreta
journalctl ``--since``/``--until``). Así el resultado es determinista y fácil de
testear inyectando ``now``.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from suize.utils.validators import DATE_HELP, parse_datetime

JOURNAL_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
CUSTOM_KEY = "custom"

#: Presets estándar: clave → etiqueta legible.
DEFAULT_PRESETS: dict[str, str] = {
    "15m": "Últimos 15 minutos",
    "1h": "Última hora",
    "6h": "Últimas 6 horas",
    "24h": "Últimas 24 horas",
    "7d": "Últimos 7 días",
    "today": "Hoy",
    "yesterday": "Ayer",
    CUSTOM_KEY: "Personalizado (fecha exacta)",
}

_KEY_ALIASES: dict[str, str] = {"hoy": "today", "ayer": "yesterday", "personalizado": CUSTOM_KEY}
_RELATIVE_RE = re.compile(r"^-?\s*(\d+)\s*(s|min|m|h|d|w)$", re.IGNORECASE)
_UNIT_SECONDS: dict[str, int] = {
    "s": 1,
    "m": 60,
    "min": 60,
    "h": 3600,
    "d": 86400,
    "w": 604800,
}


@dataclass(frozen=True, slots=True)
class TimeRange:
    """Rango temporal. ``None`` en un extremo significa "sin límite"."""

    since: datetime | None = None
    until: datetime | None = None
    label: str = ""

    def __post_init__(self) -> None:
        if self.since is not None and self.until is not None and self.since > self.until:
            raise ValueError("La fecha de inicio es posterior a la fecha de fin.")

    def to_journalctl_args(self) -> list[str]:
        args: list[str] = []
        if self.since is not None:
            args.append(f"--since={self.since.strftime(JOURNAL_TIME_FORMAT)}")
        if self.until is not None:
            args.append(f"--until={self.until.strftime(JOURNAL_TIME_FORMAT)}")
        return args

    def describe(self) -> str:
        """Texto legible, p. ej. ``Última hora (2026-01-15 11:30:00 → ahora)``."""
        start = self.since.strftime(JOURNAL_TIME_FORMAT) if self.since else "el inicio"
        end = self.until.strftime(JOURNAL_TIME_FORMAT) if self.until else "ahora"
        span = f"{start} → {end}"
        return f"{self.label} ({span})" if self.label else span


def normalize_key(key: str) -> str:
    """Minúsculas, sin espacios y con los alias en español resueltos."""
    cleaned = key.strip().lower()
    return _KEY_ALIASES.get(cleaned, cleaned)


def parse_relative(text: str) -> timedelta | None:
    """``"15m"`` → 15 minutos, ``"2d"`` → 2 días... ``None`` si no es una duración."""
    match = _RELATIVE_RE.match(text.strip())
    if match is None:
        return None
    amount, unit = int(match.group(1)), match.group(2).lower()
    if amount <= 0:
        return None
    return timedelta(seconds=amount * _UNIT_SECONDS[unit])


def _midnight(moment: datetime) -> datetime:
    return moment.replace(hour=0, minute=0, second=0, microsecond=0)


def resolve_preset(key: str, *, now: datetime | None = None, label: str | None = None) -> TimeRange:
    """Convierte la clave de un preset en un :class:`TimeRange` absoluto.

    Raises:
        ValueError: si la clave es ``custom`` (necesita fechas) o no se reconoce.
    """
    reference = now or datetime.now()
    normalized = normalize_key(key)
    text = label or DEFAULT_PRESETS.get(normalized, f"Últimos {normalized}")
    if normalized == CUSTOM_KEY:
        raise ValueError("El preset 'custom' necesita fechas exactas: usa custom_range().")
    if normalized == "today":
        return TimeRange(since=_midnight(reference), label=text)
    if normalized == "yesterday":
        today = _midnight(reference)
        return TimeRange(since=today - timedelta(days=1), until=today, label=text)
    delta = parse_relative(normalized)
    if delta is None:
        raise ValueError(f"Preset temporal desconocido: '{key}'.")
    return TimeRange(since=reference - delta, label=text)


def custom_range(since: str, until: str | None = None) -> TimeRange:
    """Rango a partir de fechas exactas (``until`` vacío = hasta ahora)."""
    return TimeRange(
        since=parse_datetime(since),
        until=parse_datetime(until) if until else None,
        label="Personalizado",
    )


def parse_range(
    since: str | None, until: str | None = None, *, now: datetime | None = None
) -> TimeRange | None:
    """Interpreta los valores de ``--since``/``--until`` de la línea de comandos.

    ``since`` acepta una clave de preset (``15m``, ``1h``, ``today``, ``ayer``...),
    cualquier duración (``30m``, ``2d``) o una fecha exacta. ``until`` siempre es una
    fecha exacta. Devuelve ``None`` si no se indicó ninguno de los dos.
    """
    if not since and not until:
        return None
    until_dt = parse_datetime(until) if until else None
    if not since:
        return TimeRange(until=until_dt, label="Personalizado")

    key = normalize_key(since)
    if key == CUSTOM_KEY:
        raise ValueError(f"'custom' necesita una fecha exacta: --since '{DATE_HELP}'.")
    if key in {"today", "yesterday"} or parse_relative(key) is not None:
        base = resolve_preset(key, now=now)
        if until_dt is None:
            return base
        return TimeRange(since=base.since, until=until_dt, label=base.label)
    try:
        since_dt = parse_datetime(since)
    except ValueError as exc:
        raise ValueError(
            f"Rango temporal inválido: '{since}'. Usa un preset (15m, 1h, 6h, 24h, 7d, today, "
            f"yesterday), una duración (p. ej. 30m, 2d) o una fecha ({DATE_HELP})."
        ) from exc
    return TimeRange(since=since_dt, until=until_dt, label="Personalizado")
