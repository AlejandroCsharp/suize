"""Tests de los prompts interactivos.

No se abre ninguna terminal: se sustituyen las funciones de questionary por
dobles que devuelven una respuesta guionizada. Lo que se comprueba es la lógica
propia de Suize alrededor de la pregunta —validación, valores por defecto,
conversión del resultado y cancelación—, que es donde puede haber errores.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

import pytest
import questionary

from suize.config.settings import load_settings
from suize.core.nmap_runner import SCAN_PROFILES
from suize.ui.prompts import (
    PRIORITY_ALL,
    Cancelled,
    ask_grep,
    ask_lines,
    ask_priority,
    ask_scan_profile,
    ask_target,
    ask_time_range,
    ask_unit,
    confirm,
    select,
    text,
    validator,
)

#: Los presets tal como los recibe el menú: objetos TimePreset, no un diccionario.
PRESETS = load_settings().time_presets


class FakeQuestion:
    """Sustituto de una pregunta de questionary: devuelve lo que se le diga."""

    def __init__(self, answer: Any) -> None:
        self.answer = answer

    def ask(self) -> Any:
        return self.answer


def script(monkeypatch: pytest.MonkeyPatch, name: str, answer: Any) -> list[dict[str, Any]]:
    """Reemplaza ``questionary.<name>`` y registra con qué se llamó."""
    calls: list[dict[str, Any]] = []

    def fake(*args: Any, **kwargs: Any) -> FakeQuestion:
        calls.append({"args": args, "kwargs": kwargs})
        return FakeQuestion(answer)

    monkeypatch.setattr(questionary, name, fake)
    return calls


# ------------------------------------------------------------------------------ validator
#
# Adapta funciones que lanzan ValueError al formato de questionary: True si vale,
# y el mensaje de error como texto si no.


def test_a_valid_value_passes() -> None:
    assert validator(int)("42") is True


def test_an_invalid_value_returns_the_error_text() -> None:
    def check(value: str) -> None:
        raise ValueError("no me gusta")

    assert validator(check)("x") == "no me gusta"


def test_an_empty_value_is_rejected_by_default() -> None:
    def check(value: str) -> None:
        raise ValueError("vacío no vale")

    assert validator(check)("") == "vacío no vale"


def test_allow_empty_accepts_the_empty_string() -> None:
    def check(value: str) -> None:
        raise ValueError("nunca debería llamarse")

    assert validator(check, allow_empty=True)("") is True


def test_allow_empty_also_accepts_only_spaces() -> None:
    def check(value: str) -> None:
        raise ValueError("nunca debería llamarse")

    assert validator(check, allow_empty=True)("   ") is True


def test_allow_empty_still_validates_a_real_value() -> None:
    def check(value: str) -> None:
        raise ValueError("mal")

    assert validator(check, allow_empty=True)("algo") == "mal"


# --------------------------------------------------------------------------- cancelación
#
# questionary devuelve None cuando el usuario pulsa Ctrl+C: se traduce a
# Cancelled para que los flujos vuelvan al menú con un except.


def test_select_raises_cancelled_on_ctrl_c(monkeypatch: pytest.MonkeyPatch) -> None:
    script(monkeypatch, "select", None)

    with pytest.raises(Cancelled):
        select("¿Cuál?", ["a", "b"])


def test_text_raises_cancelled_on_ctrl_c(monkeypatch: pytest.MonkeyPatch) -> None:
    script(monkeypatch, "text", None)

    with pytest.raises(Cancelled):
        text("¿Qué?")


def test_confirm_raises_cancelled_on_ctrl_c(monkeypatch: pytest.MonkeyPatch) -> None:
    script(monkeypatch, "confirm", None)

    with pytest.raises(Cancelled):
        confirm("¿Seguro?")


def test_a_false_answer_is_not_a_cancellation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Responder "no" a un confirm devuelve False, que no es lo mismo que cancelar."""
    script(monkeypatch, "confirm", False)

    assert confirm("¿Seguro?") is False


# ------------------------------------------------------------------------------ primitivas


def test_text_trims_the_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    script(monkeypatch, "text", "  valor  ")

    assert text("¿Qué?") == "valor"


def test_select_passes_the_default_through(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = script(monkeypatch, "select", "b")

    select("¿Cuál?", ["a", "b"], default="b")

    assert calls[0]["kwargs"]["default"] == "b"


# --------------------------------------------------------------------------------- scan


def test_ask_target_returns_the_normalised_value(monkeypatch: pytest.MonkeyPatch) -> None:
    script(monkeypatch, "text", "  192.168.1.10  ")

    assert ask_target("127.0.0.1") == "192.168.1.10"


def test_ask_target_offers_the_configured_default(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = script(monkeypatch, "text", "127.0.0.1")

    ask_target("10.0.0.5")

    assert calls[0]["kwargs"]["default"] == "10.0.0.5"


def test_ask_target_validates_before_returning(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si questionary devolviera algo inválido, no debe colarse hacia Nmap."""
    script(monkeypatch, "text", "-oN /etc/passwd")

    with pytest.raises(ValueError, match="no puede empezar"):
        ask_target("127.0.0.1")


def test_ask_scan_profile_offers_every_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = script(monkeypatch, "select", "fast")

    assert ask_scan_profile(SCAN_PROFILES, "standard") == "fast"
    assert len(calls[0]["kwargs"]["choices"]) == len(SCAN_PROFILES)


def test_ask_scan_profile_uses_the_configured_default(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = script(monkeypatch, "select", "standard")

    ask_scan_profile(SCAN_PROFILES, "full")

    assert calls[0]["kwargs"]["default"] == "full"


def test_an_unknown_default_profile_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un perfil inválido en la configuración no debe romper el menú."""
    calls = script(monkeypatch, "select", "standard")

    ask_scan_profile(SCAN_PROFILES, "no-existe")

    assert calls[0]["kwargs"]["default"] is None


# --------------------------------------------------------------------------------- logs


def test_ask_time_range_resolves_the_chosen_preset(monkeypatch: pytest.MonkeyPatch) -> None:
    script(monkeypatch, "select", "1h")

    result = ask_time_range(PRESETS, "24h")

    assert result.since is not None
    assert result.until is None


def test_ask_time_range_keeps_the_preset_label(monkeypatch: pytest.MonkeyPatch) -> None:
    """La etiqueta se muestra luego en el panel de resumen."""
    script(monkeypatch, "select", "1h")

    result = ask_time_range(PRESETS, "1h")

    assert "hora" in result.describe().lower()


def test_an_unknown_default_range_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = script(monkeypatch, "select", "1h")

    ask_time_range(PRESETS, "no-existe")

    assert calls[0]["kwargs"]["default"] is None


def test_choosing_custom_asks_for_exact_dates(monkeypatch: pytest.MonkeyPatch) -> None:
    script(monkeypatch, "select", "custom")
    answers = iter(["2026-01-15 08:00", "2026-01-15 09:30"])
    monkeypatch.setattr(questionary, "text", lambda *a, **k: FakeQuestion(next(answers)))

    result = ask_time_range(PRESETS, "1h")

    assert result.since == datetime(2026, 1, 15, 8, 0)
    assert result.until == datetime(2026, 1, 15, 9, 30)


def test_an_empty_until_means_now(monkeypatch: pytest.MonkeyPatch) -> None:
    script(monkeypatch, "select", "custom")
    answers = iter(["2026-01-15 08:00", ""])
    monkeypatch.setattr(questionary, "text", lambda *a, **k: FakeQuestion(next(answers)))

    assert ask_time_range(PRESETS, "1h").until is None


def test_an_inverted_range_is_asked_again(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si "hasta" es anterior a "desde", se vuelve a preguntar en vez de fallar."""
    script(monkeypatch, "select", "custom")
    answers = iter(
        [
            "2026-01-15 09:00",  # desde
            "2026-01-15 08:00",  # hasta: anterior, se rechaza
            "2026-01-15 08:00",  # desde, segundo intento
            "2026-01-15 09:00",  # hasta
        ]
    )
    printed: list[str] = []
    monkeypatch.setattr(questionary, "text", lambda *a, **k: FakeQuestion(next(answers)))
    monkeypatch.setattr(questionary, "print", lambda msg, **k: printed.append(msg))

    result = ask_time_range(PRESETS, "1h")

    assert result.since == datetime(2026, 1, 15, 8, 0)
    assert printed, "debería avisar de por qué se repite la pregunta"


def test_ask_priority_returns_none_for_all(monkeypatch: pytest.MonkeyPatch) -> None:
    script(monkeypatch, "select", PRIORITY_ALL)

    assert ask_priority() is None


def test_ask_priority_returns_the_level_as_text(monkeypatch: pytest.MonkeyPatch) -> None:
    script(monkeypatch, "select", "3")

    assert ask_priority() == "3"


def test_ask_priority_offers_every_level_plus_all(monkeypatch: pytest.MonkeyPatch) -> None:
    from suize.models.log_entry import PRIORITY_NAMES

    calls = script(monkeypatch, "select", PRIORITY_ALL)

    ask_priority()

    assert len(calls[0]["kwargs"]["choices"]) == len(PRIORITY_NAMES) + 1


def test_ask_unit_uses_autocomplete_when_units_are_known(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = script(monkeypatch, "autocomplete", "nginx")
    script(monkeypatch, "text", "no-deberia-usarse")

    assert ask_unit(["nginx.service", "ssh.service"]) == "nginx"
    assert calls, "con unidades conocidas debe ofrecer autocompletado"


def test_ask_unit_falls_back_to_plain_text_without_units(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = script(monkeypatch, "text", "ssh")

    assert ask_unit([]) == "ssh"
    assert calls


def test_an_empty_unit_means_no_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    script(monkeypatch, "text", "   ")

    assert ask_unit([]) is None


def test_ask_grep_returns_none_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    script(monkeypatch, "text", "")

    assert ask_grep() is None


def test_ask_grep_returns_the_pattern(monkeypatch: pytest.MonkeyPatch) -> None:
    script(monkeypatch, "text", "Failed password")

    assert ask_grep() == "Failed password"


def test_ask_lines_returns_an_int(monkeypatch: pytest.MonkeyPatch) -> None:
    script(monkeypatch, "text", "500")

    result = ask_lines(200)

    assert result == 500
    assert isinstance(result, int)


def test_ask_lines_offers_the_configured_default(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = script(monkeypatch, "text", "200")

    ask_lines(200)

    assert calls[0]["kwargs"]["default"] == "200"


# --------------------------------------------------------------------- validadores vivos
#
# Cada pregunta le pasa a questionary un validador; aquí se comprueba que el que
# llega es el correcto, ejecutándolo sobre valores buenos y malos.


def _validate_of(calls: Sequence[dict[str, Any]]) -> Any:
    return calls[0]["kwargs"]["validate"]


def test_the_target_validator_rejects_an_option_like_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = script(monkeypatch, "text", "127.0.0.1")

    ask_target("127.0.0.1")

    validate = _validate_of(calls)
    assert validate("192.168.1.1") is True
    assert isinstance(validate("-oN /etc/passwd"), str)


def test_the_lines_validator_rejects_zero_and_text(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = script(monkeypatch, "text", "200")

    ask_lines(200)

    validate = _validate_of(calls)
    assert validate("10") is True
    assert isinstance(validate("0"), str)
    assert isinstance(validate("muchas"), str)


def test_the_unit_validator_accepts_an_empty_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """Vacío significa "todas las unidades", así que debe pasar la validación."""
    calls = script(monkeypatch, "text", "")

    ask_unit([])

    validate = _validate_of(calls)
    assert validate("") is True
    assert validate("nginx") is True
    assert isinstance(validate("uni dad"), str)
