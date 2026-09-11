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

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def priority_style(priority: int) -> str:
    return PRIORITY_STYLES.get(priority, "")


def priority_label(priority: int) -> str:
    return PRIORITY_LABELS.get(priority, str(priority))


def message(kind: MessageKind, text: str) -> Text:
    """Mensaje de una línea con icono y color. El texto nunca se interpreta como markup."""
    body_style = "" if kind == "info" else kind
    return Text.assemble((f"{_MESSAGE_ICONS[kind]} ", kind), (text, body_style))


def make_console(*, no_color: bool = False, stderr: bool = False) -> Console:
    """Consola Rich con el tema de Suize (se crea en ``main()``, nunca al importar)."""
    return Console(theme=SUIZE_THEME, no_color=no_color, stderr=stderr, highlight=False)
