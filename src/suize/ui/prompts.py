"""Helpers reutilizables para preguntar al usuario (questionary).

Todos lanzan :class:`Cancelled` si el usuario pulsa Ctrl+C o Esc, así los flujos
vuelven al menú con un simple ``except Cancelled``.
"""

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import questionary
from questionary import Choice

from suize.config.settings import TimePreset
from suize.core.nmap_runner import ScanProfile
from suize.models.log_entry import PRIORITY_NAMES
from suize.ui.theme import QUESTIONARY_STYLE, error_mark
from suize.utils.time_filter import (
    CUSTOM_KEY,
    TimeRange,
    custom_range,
    normalize_key,
    resolve_preset,
)
from suize.utils.validators import (
    DATE_HELP,
    parse_datetime,
    validate_positive_int,
    validate_target,
    validate_unit,
)

PRIORITY_ALL = "all"

Validator = Callable[[str], bool | str]


class Cancelled(Exception):
    """El usuario canceló la pregunta (Ctrl+C o Esc)."""


def _require(answer: Any) -> Any:
    # questionary devuelve None cuando el usuario cancela con Ctrl+C.
    if answer is None:
        raise Cancelled
    return answer


def validator(check: Callable[[str], object], *, allow_empty: bool = False) -> Validator:
    """Adapta una función que lanza ``ValueError`` al formato de validación de questionary."""

    def validate(value: str) -> bool | str:
        if allow_empty and not value.strip():
            return True
        try:
            check(value)
        except ValueError as exc:
            return str(exc)
        return True

    return validate


# --------------------------------------------------------------------------- primitivas


def select(message: str, choices: Sequence[str | Choice], *, default: str | None = None) -> str:
    question = questionary.select(
        message,
        choices=list(choices),
        default=default,
        style=QUESTIONARY_STYLE,
        instruction="(↑/↓ y Enter)",
    )
    return str(_require(question.ask()))


def confirm(message: str, *, default: bool = True) -> bool:
    question = questionary.confirm(message, default=default, style=QUESTIONARY_STYLE)
    return bool(_require(question.ask()))


def text(message: str, *, default: str = "", validate: Validator | None = None) -> str:
    question = questionary.text(
        message, default=default, validate=validate, style=QUESTIONARY_STYLE
    )
    return str(_require(question.ask())).strip()


# --------------------------------------------------------------------------- escaneo


def ask_target(default: str) -> str:
    answer = text(
        "Objetivo (IP, hostname, red CIDR o rango):",
        default=default,
        validate=validator(validate_target),
    )
    return validate_target(answer)


def ask_scan_profile(profiles: Mapping[str, ScanProfile], default: str) -> str:
    choices = [Choice(profile.description, value=name) for name, profile in profiles.items()]
    return select("Tipo de escaneo:", choices, default=default if default in profiles else None)


# --------------------------------------------------------------------------- logs


def ask_time_range(presets: Sequence[TimePreset], default_key: str) -> TimeRange:
    """Pregunta por un preset temporal; ``custom`` pide fechas exactas."""
    labels = {preset.key: preset.label for preset in presets}
    choices = [Choice(preset.label, value=preset.key) for preset in presets]
    key = select("Rango temporal:", choices, default=default_key if default_key in labels else None)
    if normalize_key(key) == CUSTOM_KEY:
        return _ask_custom_range()
    return resolve_preset(key, label=labels.get(key))


def _ask_custom_range() -> TimeRange:
    while True:
        since = text(f"Desde ({DATE_HELP}):", validate=validator(parse_datetime))
        until = text("Hasta (vacío = ahora):", validate=validator(parse_datetime, allow_empty=True))
        try:
            return custom_range(since, until or None)
        except ValueError as exc:
            # El mismo texto que message("error", ...), pero por questionary,
            # que es quien controla la pantalla mientras hay un prompt abierto.
            questionary.print(f"{error_mark()} {exc}", style="fg:ansired bold")


def ask_priority() -> str | None:
    """Prioridad máxima a mostrar (journalctl incluye también las más graves)."""
    choices: list[str | Choice] = [Choice("Todas las prioridades (sin filtro)", value=PRIORITY_ALL)]
    for level, name in PRIORITY_NAMES.items():
        scope = "" if level == 0 else f"  (incluye 0-{level})"
        choices.append(Choice(f"{level} · {name}{scope}", value=str(level)))
    answer = select("Prioridad:", choices, default=PRIORITY_ALL)
    return None if answer == PRIORITY_ALL else answer


def ask_unit(known_units: Sequence[str] = ()) -> str | None:
    """Unidad systemd a filtrar (con autocompletado si se conoce la lista)."""
    message = "Unidad systemd (vacío = todas, Tab para autocompletar):"
    check = validator(validate_unit, allow_empty=True)
    if known_units:
        question = questionary.autocomplete(
            message,
            choices=list(known_units),
            validate=check,
            match_middle=True,
            style=QUESTIONARY_STYLE,
        )
    else:
        question = questionary.text(message, validate=check, style=QUESTIONARY_STYLE)
    value = str(_require(question.ask())).strip()
    return validate_unit(value) if value else None


def ask_grep() -> str | None:
    value = text("Buscar texto (expresión regular, vacío = sin filtro):")
    return value or None


def ask_lines(default: int) -> int:
    answer = text(
        "Número máximo de entradas:",
        default=str(default),
        validate=validator(lambda value: validate_positive_int(value, "El número de entradas")),
    )
    return validate_positive_int(answer)
