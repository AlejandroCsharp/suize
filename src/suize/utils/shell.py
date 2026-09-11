"""Wrapper centralizado de ``subprocess``.

Todas las llamadas a programas externos (nmap, journalctl, systemctl) pasan por
:func:`run`, que:

* comprueba antes con :func:`shutil.which` que el ejecutable existe,
* nunca usa ``shell=True`` (los argumentos viajan como lista),
* aplica un *timeout*,
* y traduce cualquier fallo a :class:`CommandError` con un mensaje claro.
"""

import shutil
import subprocess
from collections.abc import Collection, Sequence
from dataclasses import dataclass

DEFAULT_TIMEOUT = 60.0
_DETAIL_LIMIT = 600


class CommandError(Exception):
    """Fallo al ejecutar un comando externo: no encontrado, timeout o código inesperado."""

    def __init__(
        self,
        message: str,
        *,
        cmd: Sequence[str] = (),
        returncode: int | None = None,
        stderr: str = "",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.cmd: tuple[str, ...] = tuple(cmd)
        self.returncode = returncode
        self.stderr = stderr


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Resultado de un comando ejecutado con :func:`run`."""

    cmd: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


def run(
    cmd: Sequence[str],
    *,
    timeout: float | None = DEFAULT_TIMEOUT,
    ok_codes: Collection[int] = (0,),
) -> CommandResult:
    """Ejecuta ``cmd`` y devuelve su salida capturada.

    Args:
        cmd: programa y argumentos. ``cmd[0]`` se resuelve con ``shutil.which``.
        timeout: segundos máximos de ejecución (``None`` = sin límite).
        ok_codes: códigos de salida que se consideran correctos.

    Raises:
        CommandError: si el programa no existe, excede el timeout, no puede
            lanzarse o termina con un código fuera de ``ok_codes``.
    """
    if not cmd:
        raise CommandError("No se indicó ningún comando para ejecutar.")
    program = cmd[0]
    executable = shutil.which(program)
    if executable is None:
        raise CommandError(
            f"No se encontró '{program}' en el PATH. Instálalo o revisa tu variable PATH.",
            cmd=cmd,
        )

    try:
        completed = subprocess.run(
            [executable, *cmd[1:]],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CommandError(
            f"'{program}' superó el tiempo máximo de {exc.timeout:g} s y se canceló.", cmd=cmd
        ) from exc
    except OSError as exc:
        raise CommandError(
            f"No se pudo ejecutar '{program}': {exc.strerror or exc}", cmd=cmd
        ) from exc

    result = CommandResult(
        cmd=tuple(cmd),
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )
    if result.returncode not in ok_codes:
        detail = _tail(result.stderr) or _tail(result.stdout) or "sin mensajes de error"
        raise CommandError(
            f"'{program}' terminó con código {result.returncode}: {detail}",
            cmd=cmd,
            returncode=result.returncode,
            stderr=result.stderr,
        )
    return result


def _tail(text: str, limit: int = _DETAIL_LIMIT) -> str:
    """Últimos ``limit`` caracteres de ``text`` (los errores suelen estar al final)."""
    text = text.strip()
    return text if len(text) <= limit else "…" + text[-limit:]
