"""Tests de los iconos y su desactivación con ``--no-emoji``.

Los iconos son estado de módulo (lo fija ``main()`` una sola vez), así que
cada test restaura el valor anterior con una fixture: sin ella, el orden de
ejecución cambiaría el resultado de los demás.
"""

from collections.abc import Iterator

import pytest

from suize.ui.theme import (
    ICONS,
    configure_icons,
    icon,
    icons_enabled,
    message,
)


@pytest.fixture(autouse=True)
def _restore_icons() -> Iterator[None]:
    """Deja los iconos como estaban, pase lo que pase en el test."""
    previous = icons_enabled()
    yield
    configure_icons(emoji=previous)


def _plain(kind: str, text: str) -> str:
    return str(message(kind, text))  # type: ignore[arg-type]


# ------------------------------------------------------------------------- por defecto


def test_icons_are_enabled_by_default() -> None:
    assert icons_enabled() is True


def test_a_menu_icon_includes_its_trailing_space() -> None:
    """El espacio va dentro para que f\"{icon('scan')}Texto\" quede bien en ambos modos."""
    configure_icons(emoji=True)

    assert icon("scan") == f"{ICONS['scan']} "


def test_messages_use_the_symbol_marks() -> None:
    configure_icons(emoji=True)

    assert _plain("warning", "cuidado").startswith("⚠ ")


# ------------------------------------------------------------------------- desactivados


def test_menu_icons_disappear_completely() -> None:
    configure_icons(emoji=False)

    assert icon("scan") == ""
    assert icon("logs") == ""


def test_no_menu_label_is_left_with_a_leading_space() -> None:
    """El motivo de devolver el espacio dentro del icono, y no fuera."""
    configure_icons(emoji=False)

    assert f"{icon('scan')}Escanear" == "Escanear"


@pytest.mark.parametrize(
    ("kind", "mark"),
    [("info", "[i]"), ("success", "[ok]"), ("warning", "[!]"), ("error", "[x]")],
)
def test_messages_fall_back_to_ascii_marks(kind: str, mark: str) -> None:
    """La marca se sustituye, no se quita: distingue un error de un aviso."""
    configure_icons(emoji=False)

    assert _plain(kind, "texto") == f"{mark} texto"


def test_no_symbol_survives_in_a_disabled_message() -> None:
    configure_icons(emoji=False)

    rendered = _plain("error", "algo falló")

    assert not any(symbol in rendered for symbol in ("✖", "⚠", "ℹ", "✔"))


def test_the_message_text_is_untouched() -> None:
    configure_icons(emoji=False)

    assert _plain("info", "127.0.0.1 activo").endswith("127.0.0.1 activo")


# ---------------------------------------------------------------------------- el cambio


def test_the_switch_works_in_both_directions() -> None:
    configure_icons(emoji=False)
    assert icons_enabled() is False

    configure_icons(emoji=True)
    assert icons_enabled() is True
    assert icon("exit") != ""


def test_every_menu_icon_has_a_name_that_resolves() -> None:
    """Un nombre mal escrito en una llamada a icon() debe fallar, no pasar inadvertido."""
    configure_icons(emoji=True)

    for name in ICONS:
        assert icon(name).strip() == ICONS[name]

    with pytest.raises(KeyError):
        icon("no-existe")
