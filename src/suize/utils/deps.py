"""Verificación de dependencias externas (nmap, journalctl, systemctl)."""

import shutil
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

#: Directorio que systemd crea al arrancar como PID 1 (misma comprobación que sd_booted()).
SYSTEMD_RUNTIME_DIR = Path("/run/systemd/system")


@dataclass(frozen=True, slots=True)
class Dependency:
    """Estado de un programa externo que Suize necesita."""

    name: str
    purpose: str
    install_hint: str
    path: str | None = None

    @property
    def available(self) -> bool:
        return self.path is not None


#: Programa → (para qué se usa, cómo instalarlo).
KNOWN_DEPENDENCIES: dict[str, tuple[str, str]] = {
    "nmap": (
        "escanear hosts",
        "sudo apt install nmap · sudo dnf install nmap · sudo pacman -S nmap",
    ),
    "journalctl": (
        "leer los logs del sistema",
        "viene con systemd; no existe en sistemas sin systemd (ni en Windows o la "
        "mayoría de contenedores Docker)",
    ),
    "systemctl": (
        "correlacionar puertos con servicios systemd",
        "viene con systemd",
    ),
}


def check_dependency(name: str) -> Dependency:
    """Busca ``name`` en el PATH y devuelve su estado."""
    purpose, hint = KNOWN_DEPENDENCIES.get(name, ("", ""))
    return Dependency(name=name, purpose=purpose, install_hint=hint, path=shutil.which(name))


def check_dependencies(names: Iterable[str] = KNOWN_DEPENDENCIES) -> dict[str, Dependency]:
    """Estado de todas las dependencias indicadas (por defecto, las conocidas)."""
    return {name: check_dependency(name) for name in names}


def missing(deps: Mapping[str, Dependency], names: Iterable[str] | None = None) -> list[Dependency]:
    """Dependencias no disponibles, opcionalmente limitadas a ``names``."""
    selected = list(deps) if names is None else list(names)
    result: list[Dependency] = []
    for name in selected:
        dep = deps.get(name) or check_dependency(name)
        if not dep.available:
            result.append(dep)
    return result


def is_systemd_running(runtime_dir: Path | None = None) -> bool:
    """``True`` si el sistema arrancó con systemd.

    En WSL sin systemd habilitado o en la mayoría de contenedores Docker, journalctl y
    systemctl existen pero no tienen datos ni servicio al que conectarse. El directorio
    se resuelve en cada llamada (no como valor por defecto) para poder sustituirlo en tests.
    """
    return (runtime_dir or SYSTEMD_RUNTIME_DIR).is_dir()


def systemd_hint() -> str:
    return (
        "systemd no está en ejecución (¿WSL sin systemd o un contenedor?): journalctl no "
        "tendrá logs y la correlación no podrá listar servicios. En WSL2 activa systemd en "
        "/etc/wsl.conf (sección [boot], systemd=true) y ejecuta 'wsl --shutdown'."
    )
