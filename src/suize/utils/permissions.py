"""Detección de permisos relevantes: lectura del journal del sistema y privilegios de Nmap."""

import os
from dataclasses import dataclass

#: Grupos que, por defecto en systemd, tienen acceso de lectura al journal del sistema.
JOURNAL_GROUPS = frozenset({"systemd-journal", "adm", "wheel"})


@dataclass(frozen=True, slots=True)
class PermissionStatus:
    """Resumen de los permisos del proceso actual."""

    is_root: bool
    groups: frozenset[str]
    journal_groups: frozenset[str]

    @property
    def can_read_system_journal(self) -> bool:
        return self.is_root or bool(self.journal_groups)


def is_root() -> bool:
    """``True`` si el proceso corre con UID efectivo 0."""
    geteuid = getattr(os, "geteuid", None)
    return geteuid is not None and geteuid() == 0


def current_groups() -> frozenset[str]:
    """Nombres de los grupos del proceso actual (vacío en sistemas sin ``grp``)."""
    try:
        import grp
    except ImportError:  # pragma: no cover - solo en sistemas no POSIX
        return frozenset()
    gids = set(os.getgroups())
    getegid = getattr(os, "getegid", None)
    if getegid is not None:
        gids.add(getegid())
    names: set[str] = set()
    for gid in gids:
        try:
            names.add(grp.getgrgid(gid).gr_name)
        except KeyError:
            continue
    return frozenset(names)


def check_permissions() -> PermissionStatus:
    groups = current_groups()
    return PermissionStatus(
        is_root=is_root(), groups=groups, journal_groups=groups & JOURNAL_GROUPS
    )


def journal_hint(status: PermissionStatus) -> str | None:
    """Consejo para el usuario si no puede leer el journal completo; ``None`` si todo va bien."""
    if status.can_read_system_journal:
        return None
    return (
        "Tu usuario no está en 'systemd-journal', 'adm' ni 'wheel': journalctl solo mostrará "
        "tus propios logs. Solución: sudo usermod -aG systemd-journal $USER (y vuelve a "
        "iniciar sesión), o ejecuta Suize con sudo."
    )


def nmap_hint(status: PermissionStatus) -> str | None:
    """Aviso sobre las limitaciones de Nmap sin root; ``None`` si se ejecuta como root."""
    if status.is_root:
        return None
    return (
        "Sin root, Nmap usa TCP connect (-sT) en lugar de SYN (-sS) y no ve direcciones MAC. "
        "La detección de versiones (-sV) funciona igual."
    )
