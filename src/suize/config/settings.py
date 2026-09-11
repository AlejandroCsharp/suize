"""Carga de la configuración.

Precedencia, de menor a mayor:

1. ``default.toml`` incluido en el paquete.
2. Archivo del usuario: el argumento ``config_path`` (``--config``), la variable
   ``SUIZE_CONFIG`` o, si existe, ``$XDG_CONFIG_HOME/suize/config.toml``
   (por defecto ``~/.config/suize/config.toml``).
3. Variables de entorno ``SUIZE_*`` (ver :data:`ENV_OVERRIDES`).

Este módulo solo usa la stdlib y no importa nada del resto del proyecto.
"""

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Literal

CONFIG_ENV_VAR = "SUIZE_CONFIG"

#: Variable de entorno → (sección TOML, clave, tipo).
ENV_OVERRIDES: dict[str, tuple[str, str, Literal["str", "int"]]] = {
    "SUIZE_DEFAULT_TARGET": ("scan", "default_target", "str"),
    "SUIZE_SCAN_TIMEOUT": ("scan", "timeout", "int"),
    "SUIZE_SCAN_PROFILE": ("scan", "profile", "str"),
    "SUIZE_LOG_LINES": ("logs", "lines", "int"),
    "SUIZE_JOURNAL_TIMEOUT": ("logs", "timeout", "int"),
    "SUIZE_TIME_PRESET": ("logs", "default_time_preset", "str"),
}


class ConfigError(Exception):
    """La configuración no se pudo leer o contiene valores inválidos."""


@dataclass(frozen=True, slots=True)
class TimePreset:
    """Preset temporal que ofrece el menú de logs."""

    key: str
    label: str


@dataclass(frozen=True, slots=True)
class Settings:
    """Configuración efectiva, ya validada."""

    default_target: str
    scan_timeout: int
    scan_profile: str
    log_lines: int
    journal_timeout: int
    top_units: int
    default_time_preset: str
    time_presets: tuple[TimePreset, ...]
    sources: tuple[str, ...] = ()


def default_config_text() -> str:
    """Contenido de ``default.toml`` empaquetado junto al código."""
    return resources.files("suize.config").joinpath("default.toml").read_text(encoding="utf-8")


def user_config_path(env: Mapping[str, str]) -> Path:
    """Ruta implícita del archivo de configuración del usuario."""
    base = env.get("XDG_CONFIG_HOME", "").strip()
    root = Path(base) if base else Path.home() / ".config"
    return root / "suize" / "config.toml"


def load_settings(
    config_path: Path | None = None, *, env: Mapping[str, str] | None = None
) -> Settings:
    """Construye :class:`Settings` combinando las tres fuentes de configuración.

    Raises:
        ConfigError: si un archivo no existe o no es TOML válido, o si algún valor
            tiene un tipo o rango incorrecto.
    """
    environ: Mapping[str, str] = os.environ if env is None else env
    data = _parse_toml(default_config_text(), "default.toml")
    sources = ["default.toml"]

    env_path = environ.get(CONFIG_ENV_VAR, "").strip()
    explicit = config_path or (Path(env_path).expanduser() if env_path else None)
    if explicit is not None:
        if not explicit.is_file():
            raise ConfigError(f"No existe el archivo de configuración: {explicit}")
        data = _deep_merge(data, _read_toml(explicit))
        sources.append(str(explicit))
    else:
        implicit = user_config_path(environ)
        if implicit.is_file():
            data = _deep_merge(data, _read_toml(implicit))
            sources.append(str(implicit))

    data = _apply_env(data, environ, sources)
    return _build_settings(data, tuple(sources))


# --------------------------------------------------------------------------- internos


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"No se pudo leer {path}: {exc.strerror or exc}") from exc
    return _parse_toml(text, str(path))


def _parse_toml(text: str, origin: str) -> dict[str, Any]:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"TOML inválido en {origin}: {exc}") from exc


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Combina diccionarios anidados; las listas y escalares de ``override`` reemplazan."""
    result = dict(base)
    for key, value in override.items():
        current = result.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            result[key] = _deep_merge(current, value)
        else:
            result[key] = value
    return result


def _apply_env(data: dict[str, Any], env: Mapping[str, str], sources: list[str]) -> dict[str, Any]:
    result = dict(data)
    for var, (section, key, kind) in ENV_OVERRIDES.items():
        raw = env.get(var, "").strip()
        if not raw:
            continue
        value: str | int = raw
        if kind == "int":
            try:
                value = int(raw)
            except ValueError:
                raise ConfigError(f"{var} debe ser un número entero (recibido: '{raw}').") from None
        current = result.get(section)
        section_data = dict(current) if isinstance(current, Mapping) else {}
        section_data[key] = value
        result[section] = section_data
        sources.append(f"env:{var}")
    return result


def _section(data: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = data.get(name, {})
    if not isinstance(value, Mapping):
        raise ConfigError(f"[{name}] debe ser una tabla TOML.")
    return value


def _as_str(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"'{name}' debe ser un texto no vacío.")
    return value.strip()


def _as_positive_int(value: object, name: str) -> int:
    # bool es subclase de int en Python: se excluye explícitamente.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"'{name}' debe ser un número entero.")
    if value <= 0:
        raise ConfigError(f"'{name}' debe ser mayor que 0.")
    return value


def _build_presets(raw: object) -> tuple[TimePreset, ...]:
    if not isinstance(raw, list) or not raw:
        raise ConfigError("'logs.time_presets' debe ser una lista no vacía de tablas {key, label}.")
    presets: list[TimePreset] = []
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise ConfigError(f"'logs.time_presets[{index}]' debe ser una tabla con key y label.")
        presets.append(
            TimePreset(
                key=_as_str(item.get("key"), f"logs.time_presets[{index}].key"),
                label=_as_str(item.get("label"), f"logs.time_presets[{index}].label"),
            )
        )
    return tuple(presets)


def _build_settings(data: Mapping[str, Any], sources: tuple[str, ...]) -> Settings:
    scan = _section(data, "scan")
    logs = _section(data, "logs")
    presets = _build_presets(logs.get("time_presets"))
    return Settings(
        default_target=_as_str(scan.get("default_target"), "scan.default_target"),
        scan_timeout=_as_positive_int(scan.get("timeout"), "scan.timeout"),
        scan_profile=_as_str(scan.get("profile"), "scan.profile"),
        log_lines=_as_positive_int(logs.get("lines"), "logs.lines"),
        journal_timeout=_as_positive_int(logs.get("timeout"), "logs.timeout"),
        top_units=_as_positive_int(logs.get("top_units"), "logs.top_units"),
        default_time_preset=_as_str(
            logs.get("default_time_preset", presets[0].key), "logs.default_time_preset"
        ),
        time_presets=presets,
        sources=sources,
    )
