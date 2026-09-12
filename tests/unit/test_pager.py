"""Tests del paginador de salidas largas."""

import io
import os
import re

import pytest
from rich.console import Console

from suize.ui.pager import DEFAULT_LESS_OPTIONS, fits_on_screen, paged


class FakePager:
    """Doble del paginador: guarda lo que se le manda en vez de abrir less."""

    def __init__(self) -> None:
        self.content: str | None = None
        self.less_options: str | None = None

    def show(self, content: str) -> None:
        self.content = content
        # Se anota aquí porque la variable solo existe durante la llamada.
        self.less_options = os.environ.get("LESS")


def _console(*, terminal: bool = True, height: int = 20) -> tuple[Console, io.StringIO]:
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=terminal, width=60, height=height)
    return console, buffer


def _visible(text: str) -> str:
    """Quita los códigos ANSI para comparar solo el texto que se ve."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _print_lines(console: Console, count: int) -> None:
    for number in range(count):
        console.print(f"linea {number}")


# --------------------------------------------------------------------------- decisión


def test_short_output_is_printed_without_the_pager() -> None:
    console, buffer = _console(height=20)
    pager = FakePager()

    with paged(console, pager=pager):
        _print_lines(console, 3)

    assert pager.content is None
    assert buffer.getvalue().count("\n") == 3


def test_long_output_goes_to_the_pager() -> None:
    console, buffer = _console(height=10)
    pager = FakePager()

    with paged(console, pager=pager):
        _print_lines(console, 40)

    assert pager.content is not None
    assert pager.content.count("\n") == 40
    assert buffer.getvalue() == ""  # nada se escribió directamente


def test_output_is_not_duplicated_when_it_is_paged() -> None:
    """El contenido va al paginador o a la consola, nunca a los dos."""
    console, buffer = _console(height=5)
    pager = FakePager()

    with paged(console, pager=pager):
        _print_lines(console, 30)

    assert "linea 0" not in buffer.getvalue()


def test_pipes_are_never_paged() -> None:
    """Con una tubería o un archivo, paginar rompería los scripts."""
    console, buffer = _console(terminal=False, height=10)
    pager = FakePager()

    with paged(console, pager=pager):
        _print_lines(console, 50)

    assert pager.content is None
    assert buffer.getvalue().count("\n") == 50


def test_disabled_pager_prints_everything_directly() -> None:
    console, buffer = _console(height=5)
    pager = FakePager()

    with paged(console, enabled=False, pager=pager):
        _print_lines(console, 50)

    assert pager.content is None
    assert buffer.getvalue().count("\n") == 50


def test_empty_block_does_nothing() -> None:
    console, buffer = _console(height=5)
    pager = FakePager()

    with paged(console, pager=pager):
        pass

    assert pager.content is None
    assert buffer.getvalue() == ""


# ------------------------------------------------------------------------- contenido


def test_colors_survive_the_trip_to_the_pager() -> None:
    console, _ = _console(height=5)
    pager = FakePager()

    with paged(console, pager=pager):
        console.print("[bold red]peligro[/bold red]")
        _print_lines(console, 30)

    assert pager.content is not None
    assert "\x1b[" in pager.content


def test_short_output_keeps_its_colors_too() -> None:
    console, buffer = _console(height=30)

    with paged(console, pager=FakePager()):
        console.print("[bold red]peligro[/bold red]")

    assert "\x1b[" in buffer.getvalue()


def test_markup_in_the_content_is_not_reinterpreted() -> None:
    """Al reescribir el texto capturado, los corchetes deben llegar intactos."""
    console, buffer = _console(height=30)

    with paged(console, pager=FakePager()):
        console.print("nginx: [emerg] bind() failed", markup=False)

    assert _visible(buffer.getvalue()).strip() == "nginx: [emerg] bind() failed"


# ----------------------------------------------------------------------------- less


def test_less_options_are_set_for_the_pager_call() -> None:
    console, _ = _console(height=5)
    pager = FakePager()

    with paged(console, pager=pager):
        _print_lines(console, 30)

    assert pager.less_options == DEFAULT_LESS_OPTIONS


def test_user_less_options_are_respected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LESS", "S")
    console, _ = _console(height=5)
    pager = FakePager()

    with paged(console, pager=pager):
        _print_lines(console, 30)

    assert pager.less_options == "S"


def test_less_variable_is_restored_afterwards() -> None:
    console, _ = _console(height=5)

    with paged(console, pager=FakePager()):
        _print_lines(console, 30)

    assert "LESS" not in os.environ


# ------------------------------------------------------------------------ fits_on_screen


@pytest.mark.parametrize(
    ("lines", "height", "expected"),
    [
        (1, 24, True),
        (23, 24, True),
        (24, 24, False),  # la última línea se reserva para el prompt
        (100, 24, False),
        (1, 1, True),
    ],
)
def test_fits_on_screen(lines: int, height: int, expected: bool) -> None:
    text = "x\n" * lines

    assert fits_on_screen(text, height) is expected
