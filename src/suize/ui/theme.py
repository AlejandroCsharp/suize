"""Colores, estilos y constantes visuales compartidas por toda la UI."""

from typing import Literal

from questionary import Style
from rich.console import Console
from rich.text import Text
from rich.theme import Theme

APP_NAME = "Suize"
TAGLINE = "Navaja suiza de terminal · Nmap + journalctl"

#: Prioridad de syslog → estilo Rich.
PRIORITY_STYLES: dict[int, str] = {
    0: "bold white on red",
    1: "bold white on red",
    2: "bold red",
    3: "red",
    4: "yellow",
    5: "cyan",
    6: "green",
    7: "dim",
}

PRIORITY_LABELS: dict[int, str] = {
    0: "EMERG",
    1: "ALERT",
    2: "CRIT",
    3: "ERR",
    4: "WARN",
    5: "NOTICE",
    6: "INFO",
    7: "DEBUG",
}

PORT_STATE_STYLES: dict[str, str] = {
    "open": "bold green",
    "closed": "red",
    "filtered": "yellow",
    "open|filtered": "yellow",
    "closed|filtered": "dim",
}

ICONS: dict[str, str] = {
    "scan": "🔍",
    "logs": "📋",
    "correlate": "🔗",
    "exit": "🚪",
    "bye": "👋",
}

#: Si los iconos están activos. Lo fija :func:`configure_icons` desde ``main()``;
#: no se toca al importar, como el resto del módulo.
_use_emoji = True

SUIZE_THEME = Theme(
    {
        "title": "bold cyan",
        "accent": "magenta",
        "muted": "dim",
        "host": "bold cyan",
        "info": "cyan",
        "success": "bold green",
        "warning": "bold yellow",
        "error": "bold red",
    }
)

QUESTIONARY_STYLE = Style(
    [
        ("qmark", "fg:#00afaf bold"),
        ("question", "bold"),
        ("answer", "fg:#5fd75f bold"),
        ("pointer", "fg:#00afaf bold"),
        ("highlighted", "fg:#00afaf bold"),
        ("selected", "fg:#5fd75f"),
        ("instruction", "fg:#808080 italic"),
        ("disabled", "fg:#6c6c6c italic"),
    ]
)

MessageKind = Literal["info", "success", "warning", "error"]
_MESSAGE_ICONS: dict[str, str] = {"info": "ℹ", "success": "✔", "warning": "⚠", "error": "✖"}

#: Equivalentes en ASCII, para terminales sin una fuente que incluya los símbolos.
#: Los de los mensajes se sustituyen (la marca distingue un error de un aviso);
#: los del menú simplemente desaparecen, porque el texto ya lo explica.
_ASCII_MESSAGE_ICONS: dict[str, str] = {
    "info": "[i]",
    "success": "[ok]",
    "warning": "[!]",
    "error": "[x]",
}

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_icons(*, emoji: bool) -> None:
    """Activa o desactiva los iconos para todo el proceso (opción ``--no-emoji``).

    Es estado de módulo, no un argumento, porque ``message()`` se usa en una
    treintena de sitios y arrastrar la preferencia por todos ellos ensuciaría
    cada firma sin ganar nada: es una preferencia del proceso, como los colores.
    """
    global _use_emoji
    _use_emoji = emoji


def icons_enabled() -> bool:
    """Si los iconos están activos. Pensado sobre todo para los tests."""
    return _use_emoji


def icon(name: str) -> str:
    """Icono del menú con su espacio, o cadena vacía si están desactivados.

    Devuelve el espacio incluido para poder escribir ``f"{icon('scan')}Escanear"``
    sin que quede un espacio suelto al principio cuando no hay icono.
    """
    return f"{ICONS[name]} " if _use_emoji else ""


def error_mark() -> str:
    """Marca de error suelta, para quien no puede usar :func:`message`."""
    marks = _MESSAGE_ICONS if _use_emoji else _ASCII_MESSAGE_ICONS
    return marks["error"]


def priority_style(priority: int) -> str:
    return PRIORITY_STYLES.get(priority, "")


def priority_label(priority: int) -> str:
    return PRIORITY_LABELS.get(priority, str(priority))


def message(kind: MessageKind, text: str) -> Text:
    """Mensaje de una línea con icono y color. El texto nunca se interpreta como markup."""
    body_style = "" if kind == "info" else kind
    marks = _MESSAGE_ICONS if _use_emoji else _ASCII_MESSAGE_ICONS
    return Text.assemble((f"{marks[kind]} ", kind), (text, body_style))


def make_console(*, no_color: bool = False, stderr: bool = False) -> Console:
    """Consola Rich con el tema de Suize (se crea en ``main()``, nunca al importar)."""
    return Console(theme=SUIZE_THEME, no_color=no_color, stderr=stderr, highlight=False)
