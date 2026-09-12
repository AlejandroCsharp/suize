"""Paginación de salidas largas.

Una consulta de logs con cientos de entradas se pierde en el desplazamiento de
la terminal. :func:`paged` envía esas salidas a ``less`` (o al paginador que
indique ``$PAGER``), pero solo cuando tiene sentido: si hay una terminal
interactiva y el contenido no cabe en pantalla.

La decisión se toma **después** de renderizar, no antes: el bloque se captura
en memoria, se cuentan sus líneas y, si caben, se escriben tal cual. Así nunca
se abre un paginador para tres filas.

El paginador envuelve llamadas de renderizado, no la lógica que las precede:
capturar una pregunta interactiva o un indicador de progreso dejaría al usuario
ante una pantalla en blanco.
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager

from rich.console import Console
from rich.pager import Pager, SystemPager

#: Opciones que se le pasan a ``less`` si el usuario no definió las suyas.
#:
#: ``F`` sale directamente si el contenido cabe en una pantalla, ``R`` deja
#: pasar los colores y ``X`` evita que la salida se borre al salir.
DEFAULT_LESS_OPTIONS = "FRX"


@contextmanager
def _less_defaults() -> Iterator[None]:
    """Define ``LESS`` para esta llamada, respetando el valor del usuario."""
    if os.environ.get("LESS"):
        yield
        return
    os.environ["LESS"] = DEFAULT_LESS_OPTIONS
    try:
        yield
    finally:
        os.environ.pop("LESS", None)


def fits_on_screen(text: str, height: int) -> bool:
    """``True`` si ``text`` cabe en una pantalla de ``height`` líneas.

    Se reserva una línea para el prompt que aparecerá después.
    """
    return text.count("\n") <= max(height - 1, 1)


@contextmanager
def paged(console: Console, *, enabled: bool = True, pager: Pager | None = None) -> Iterator[None]:
    """Pagina lo que se imprima en ``console`` dentro del bloque, si hace falta.

    No hace nada cuando ``enabled`` es ``False`` o cuando la salida no es una
    terminal (una tubería, un archivo, cron): ahí paginar rompería los scripts.

    Args:
        console: consola cuya salida se captura.
        enabled: permite desactivarlo (``--no-pager``).
        pager: paginador alternativo, para los tests.
    """
    if not enabled or not console.is_terminal:
        yield
        return

    with console.capture() as capture:
        yield
    text = capture.get()
    if not text:
        return

    if fits_on_screen(text, console.size.height):
        # Se reescribe tal cual, con sus colores: volver a pasarlo por print
        # reinterpretaría el marcado del contenido.
        console.file.write(text)
        console.file.flush()
        return

    with _less_defaults():
        (pager or SystemPager()).show(text)
