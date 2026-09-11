"""Modelos de logs: :class:`LogEntry` y :class:`LogSummary`."""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Self

#: Niveles de syslog tal como los nombra journalctl.
PRIORITY_NAMES: dict[int, str] = {
    0: "emerg",
    1: "alert",
    2: "crit",
    3: "err",
    4: "warning",
    5: "notice",
    6: "info",
    7: "debug",
}

#: Prioridad que se asume cuando una entrada no trae el campo PRIORITY.
DEFAULT_PRIORITY = 6


@dataclass(frozen=True, slots=True)
class LogEntry:
    """Una entrada del journal ya normalizada."""

    timestamp: datetime
    priority: int
    unit: str
    message: str
    hostname: str = ""
    pid: int | None = None

    @property
    def priority_name(self) -> str:
        return PRIORITY_NAMES.get(self.priority, str(self.priority))


@dataclass(frozen=True, slots=True)
class LogSummary:
    """Resumen estadístico de un conjunto de entradas."""

    total: int
    by_priority: dict[int, int] = field(default_factory=dict)
    top_units: list[tuple[str, int]] = field(default_factory=list)
    first: datetime | None = None
    last: datetime | None = None

    @classmethod
    def from_entries(cls, entries: Iterable[LogEntry], top_n: int = 5) -> Self:
        """Calcula total, conteo por prioridad, top de unidades y rango de fechas."""
        items = list(entries)
        if not items:
            return cls(total=0)
        priorities = Counter(entry.priority for entry in items)
        units = Counter(entry.unit for entry in items)
        stamps = [entry.timestamp for entry in items]
        return cls(
            total=len(items),
            by_priority=dict(sorted(priorities.items())),
            top_units=units.most_common(top_n),
            first=min(stamps),
            last=max(stamps),
        )
