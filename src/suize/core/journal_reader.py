"""Consulta a journalctl con filtros combinables. Devuelve la salida JSON en bruto."""

from dataclasses import dataclass

from suize.utils import shell
from suize.utils.time_filter import TimeRange
from suize.utils.validators import parse_priority, validate_unit

JOURNALCTL_BINARY = "journalctl"
DEFAULT_JOURNAL_TIMEOUT = 60.0


@dataclass(frozen=True, slots=True)
class JournalQuery:
    """Filtros de una consulta; los que quedan vacíos simplemente no se aplican."""

    units: tuple[str, ...] = ()
    priority: str | None = None
    time_range: TimeRange | None = None
    grep: str | None = None
    lines: int | None = 200


def build_command(query: JournalQuery) -> list[str]:
    """Traduce una :class:`JournalQuery` a argumentos de journalctl.

    Equivalencias: ``--output=json`` (``-o json``), ``--unit`` (``-u``),
    ``--priority`` (``-p``), ``--since``/``--until``, ``--grep`` y ``--lines`` (``-n``).
    Se usa siempre la forma ``--opcion=valor`` para que un valor nunca pueda
    confundirse con otra opción. ``--quiet`` suprime avisos informativos (los permisos
    se comprueban aparte en ``utils.permissions``) y ``--no-pager`` evita abrir ``less``.

    Raises:
        ValueError: unidad, prioridad o número de líneas inválidos.
    """
    cmd = [JOURNALCTL_BINARY, "--output=json", "--no-pager", "--quiet"]
    cmd.extend(f"--unit={validate_unit(unit)}" for unit in query.units)
    if query.priority:
        cmd.append(f"--priority={parse_priority(query.priority)}")
    if query.time_range is not None:
        cmd.extend(query.time_range.to_journalctl_args())
    if query.grep:
        cmd.append(f"--grep={query.grep}")
    if query.lines is not None:
        if query.lines <= 0:
            raise ValueError("El número de líneas debe ser mayor que 0.")
        cmd.append(f"--lines={query.lines}")
    return cmd


def read_journal(query: JournalQuery, *, timeout: float = DEFAULT_JOURNAL_TIMEOUT) -> str:
    """Ejecuta journalctl y devuelve su salida (un objeto JSON por línea).

    Raises:
        ValueError: filtros inválidos.
        CommandError: journalctl no existe, falla o excede el timeout.
    """
    cmd = build_command(query)
    result = shell.run(cmd, timeout=timeout, ok_codes=(0, 1))
    if result.returncode == 0:
        return result.stdout
    # Con --grep, journalctl sale con 1 si no hay coincidencias (igual que grep).
    if not result.stdout.strip() and not result.stderr.strip():
        return ""
    detail = result.stderr.strip() or "error desconocido"
    if "pattern matching" in detail.lower() or "pcre" in detail.lower():
        detail += " (esta build de journalctl no soporta --grep: filtra por unidad o prioridad)"
    raise shell.CommandError(
        f"journalctl terminó con código 1: {detail}", cmd=cmd, returncode=1, stderr=result.stderr
    )
