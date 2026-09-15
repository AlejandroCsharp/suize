"""Tests de la carga de la configuración: precedencia entre fuentes, combinación de
archivos, variables de entorno y validación de los valores generales.

``tests/unit/test_correlator.py`` no se toca aquí: las tablas de correlación ya
tenían su cobertura y siguen abajo, sin cambios.
"""

from collections.abc import Mapping
from pathlib import Path

import pytest

from suize.config.settings import (
    ConfigError,
    default_config_text,
    load_settings,
    user_config_path,
)


def _config(tmp_path: Path, contenido: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(contenido, encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _no_real_user_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Aísla cada test del config.toml real de quien los ejecuta.

    Sin esto, un ``~/.config/suize/config.toml`` que exista de verdad en la
    máquina (el de quien corre los tests) se colaría en los resultados: es
    justo el problema que motivó esta fixture, visto en la práctica. Los
    tests que quieren ejercitar la resolución de la ruta implícita
    (``test_a_missing_implicit_file_is_not_an_error`` y el siguiente)
    monkeypatchean ``user_config_path`` ellos mismos, lo que sobreescribe esto
    sin conflicto: ambos usan la misma instancia de ``monkeypatch`` de pytest.
    """
    monkeypatch.setattr(
        "suize.config.settings.user_config_path", lambda env: tmp_path / "no-existe.toml"
    )


# --------------------------------------------------------------------- precedencia
#
# El orden documentado en el módulo (y en el README) es:
#   1. default.toml empaquetado
#   2. archivo del usuario (--config / SUIZE_CONFIG / ruta implícita)
#   3. variables de entorno SUIZE_*
#
# Cada test de esta sección fija un valor en una fuente y comprueba que una
# fuente de más precedencia lo sobrescribe, o que su ausencia no lo hace.


def test_with_nothing_set_the_packaged_defaults_apply() -> None:
    settings = load_settings(env={})

    assert settings.default_target == "127.0.0.1"
    assert settings.scan_profile == "standard"
    assert settings.sources == ("default.toml",)


def test_a_user_file_overrides_the_packaged_default(tmp_path: Path) -> None:
    path = _config(tmp_path, '[scan]\ndefault_target = "192.168.1.50"\n')

    settings = load_settings(path, env={})

    assert settings.default_target == "192.168.1.50"


def test_an_env_var_overrides_the_user_file(tmp_path: Path) -> None:
    """La variable de entorno es la fuente de mayor precedencia de las tres."""
    path = _config(tmp_path, '[scan]\ndefault_target = "del-archivo"\n')

    settings = load_settings(path, env={"SUIZE_DEFAULT_TARGET": "de-env"})

    assert settings.default_target == "de-env"


def test_an_env_var_overrides_the_packaged_default_with_no_user_file() -> None:
    settings = load_settings(env={"SUIZE_SCAN_PROFILE": "fast"})

    assert settings.scan_profile == "fast"


def test_an_unset_env_var_does_not_override_the_user_file(tmp_path: Path) -> None:
    """Ausente, no vacía: SUIZE_DEFAULT_TARGET simplemente no está en el entorno."""
    path = _config(tmp_path, '[scan]\ndefault_target = "192.168.1.50"\n')

    settings = load_settings(path, env={})

    assert settings.default_target == "192.168.1.50"


def test_a_blank_env_var_is_treated_as_unset(tmp_path: Path) -> None:
    """Vacía o solo espacios: se ignora en vez de sobrescribir con "" o fallar."""
    path = _config(tmp_path, '[scan]\ndefault_target = "192.168.1.50"\n')

    settings = load_settings(path, env={"SUIZE_DEFAULT_TARGET": "   "})

    assert settings.default_target == "192.168.1.50"


def test_each_key_is_overridden_independently(tmp_path: Path) -> None:
    """Sobrescribir una clave no debe afectar a las demás de la misma sección."""
    path = _config(tmp_path, '[scan]\ndefault_target = "192.168.1.50"\nprofile = "full"\n')

    settings = load_settings(path, env={"SUIZE_DEFAULT_TARGET": "de-env"})

    assert settings.default_target == "de-env"
    assert settings.scan_profile == "full"  # del archivo, no tocado por el env


def test_sources_records_every_layer_that_contributed(tmp_path: Path) -> None:
    path = _config(tmp_path, '[scan]\ndefault_target = "192.168.1.50"\n')

    settings = load_settings(path, env={"SUIZE_SCAN_PROFILE": "fast"})

    assert settings.sources == ("default.toml", str(path), "env:SUIZE_SCAN_PROFILE")


def test_sources_has_only_the_default_file_with_nothing_else() -> None:
    assert load_settings(env={}).sources == ("default.toml",)


# ------------------------------------------------------------------- resolución de ruta
#
# config_path (--config) > $SUIZE_CONFIG > ruta implícita ($XDG_CONFIG_HOME o ~/.config).


def test_explicit_path_wins_over_the_env_var(tmp_path: Path) -> None:
    explicit = _config(tmp_path, '[scan]\ndefault_target = "de-argumento"\n')
    from_env = tmp_path / "otro.toml"
    from_env.write_text('[scan]\ndefault_target = "de-env-config"\n', encoding="utf-8")

    settings = load_settings(explicit, env={"SUIZE_CONFIG": str(from_env)})

    assert settings.default_target == "de-argumento"


def test_suize_config_env_var_is_used_with_no_explicit_path(tmp_path: Path) -> None:
    path = _config(tmp_path, '[scan]\ndefault_target = "de-env-config"\n')

    settings = load_settings(env={"SUIZE_CONFIG": str(path)})

    assert settings.default_target == "de-env-config"


def test_suize_config_pointing_to_a_missing_file_raises(tmp_path: Path) -> None:
    missing = tmp_path / "no-existe.toml"

    with pytest.raises(ConfigError, match="No existe el archivo de configuración"):
        load_settings(env={"SUIZE_CONFIG": str(missing)})


def test_an_explicit_path_that_does_not_exist_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="No existe el archivo de configuración"):
        load_settings(tmp_path / "no-existe.toml", env={})


def test_a_blank_suize_config_falls_back_to_the_implicit_path() -> None:
    """SUIZE_CONFIG=""  no debe intentar abrir un archivo vacío como ruta."""
    settings = load_settings(env={"SUIZE_CONFIG": "  "})

    assert settings.sources == ("default.toml",)


def test_user_config_path_uses_xdg_config_home_when_set() -> None:
    assert user_config_path({"XDG_CONFIG_HOME": "/tmp/xdg"}) == Path("/tmp/xdg/suize/config.toml")


def test_user_config_path_falls_back_to_dot_config_when_xdg_is_blank() -> None:
    path = user_config_path({"XDG_CONFIG_HOME": ""})

    assert path == Path.home() / ".config" / "suize" / "config.toml"


def test_user_config_path_falls_back_to_dot_config_when_xdg_is_absent() -> None:
    assert user_config_path({}) == Path.home() / ".config" / "suize" / "config.toml"


def test_a_missing_implicit_file_is_not_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A diferencia de una ruta explícita, la implícita es opcional: si no está, no pasa nada."""
    monkeypatch.setattr(
        "suize.config.settings.user_config_path", lambda env: tmp_path / "no-existe.toml"
    )

    settings = load_settings(env={})

    assert settings.sources == ("default.toml",)


def test_an_existing_implicit_file_is_read_with_no_explicit_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sin --config ni $SUIZE_CONFIG, la ruta implícita se usa si existe."""
    implicit = tmp_path / "config.toml"
    implicit.write_text('[scan]\ndefault_target = "10.0.0.5"\n', encoding="utf-8")
    monkeypatch.setattr("suize.config.settings.user_config_path", lambda env: implicit)

    settings = load_settings(env={})

    assert settings.default_target == "10.0.0.5"
    assert settings.sources == ("default.toml", str(implicit))


# ------------------------------------------------------------------------- _deep_merge
#
# Cómo se combina el archivo del usuario con lo que ya había: las tablas se
# fusionan clave por clave (igual que hace correlation.ports con las suyas);
# los escalares y las listas del archivo del usuario reemplazan sin más.


def test_a_single_key_is_merged_without_dropping_its_siblings(tmp_path: Path) -> None:
    """Solo se sobrescribe scan.profile; scan.default_target sigue siendo el de fábrica."""
    path = _config(tmp_path, '[scan]\nprofile = "fast"\n')

    settings = load_settings(path, env={})

    assert settings.scan_profile == "fast"
    assert settings.default_target == "127.0.0.1"  # de default.toml, intacto


def test_two_different_sections_merge_independently(tmp_path: Path) -> None:
    path = _config(tmp_path, '[scan]\nprofile = "fast"\n\n[logs]\nlines = 50\n')

    settings = load_settings(path, env={})

    assert settings.scan_profile == "fast"
    assert settings.log_lines == 50
    assert settings.journal_timeout == 60  # de default.toml, ninguna de las dos lo tocó


def test_a_list_from_the_user_file_replaces_the_default_list_entirely(tmp_path: Path) -> None:
    """logs.time_presets no se fusiona elemento a elemento: la lista nueva sustituye a la vieja."""
    path = _config(
        tmp_path,
        '[[logs.time_presets]]\nkey = "5m"\nlabel = "Últimos 5 minutos"\n',
    )

    settings = load_settings(path, env={})

    assert [preset.key for preset in settings.time_presets] == ["5m"]


# ------------------------------------------------------------------ archivo de usuario


def test_a_malformed_toml_file_is_reported_with_its_path(tmp_path: Path) -> None:
    path = _config(tmp_path, "esto no es TOML válido [[[")

    with pytest.raises(ConfigError, match="TOML inválido"):
        load_settings(path, env={})


def test_an_unreadable_file_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Existe pero no se puede leer (permisos, por ejemplo): OSError se traduce a ConfigError.

    Como los tests corren como root en algunos entornos (CI incluida), ``chmod 000``
    no basta para forzar el fallo: se simula el error de lectura directamente.
    """
    path = tmp_path / "config.toml"
    path.write_text("", encoding="utf-8")  # debe existir y pasar is_file()
    original_read_text = Path.read_text

    def fake_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self == path:
            raise PermissionError(13, "Permission denied")
        return original_read_text(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    with pytest.raises(ConfigError, match="No se pudo leer"):
        load_settings(path, env={})


def test_an_empty_user_file_keeps_every_default(tmp_path: Path) -> None:
    path = _config(tmp_path, "")

    settings = load_settings(path, env={})

    assert settings.default_target == "127.0.0.1"
    assert settings.scan_profile == "standard"


# --------------------------------------------------------------------- variables de entorno


def test_a_non_numeric_int_env_var_is_rejected() -> None:
    with pytest.raises(ConfigError, match="SUIZE_SCAN_TIMEOUT debe ser un número entero"):
        load_settings(env={"SUIZE_SCAN_TIMEOUT": "no-es-un-numero"})


def test_the_rejected_value_is_shown_in_the_error() -> None:
    with pytest.raises(ConfigError, match=r"recibido: '3\.5'"):
        load_settings(env={"SUIZE_SCAN_TIMEOUT": "3.5"})


@pytest.mark.parametrize(
    ("var", "value", "getter"),
    [
        ("SUIZE_DEFAULT_TARGET", "10.0.0.5", lambda s: s.default_target),
        ("SUIZE_SCAN_TIMEOUT", "120", lambda s: s.scan_timeout),
        ("SUIZE_SCAN_PROFILE", "full", lambda s: s.scan_profile),
        ("SUIZE_LOG_LINES", "500", lambda s: s.log_lines),
        ("SUIZE_JOURNAL_TIMEOUT", "30", lambda s: s.journal_timeout),
        ("SUIZE_TIME_PRESET", "24h", lambda s: s.default_time_preset),
    ],
)
def test_every_documented_env_var_takes_effect(var: str, value: str, getter: object) -> None:
    """Las seis variables de ENV_OVERRIDES, una por una: ninguna quedó sin conectar."""
    settings = load_settings(env={var: value})

    result = getter(settings)  # type: ignore[operator]
    assert str(result) == value


def test_an_int_env_var_is_actually_an_int_not_a_string() -> None:
    """No basta con que el valor "cuadre": el tipo debe ser int para las cuentas de journalctl."""
    settings = load_settings(env={"SUIZE_LOG_LINES": "500"})

    assert settings.log_lines == 500
    assert isinstance(settings.log_lines, int)


def test_env_vars_not_in_the_documented_list_are_ignored() -> None:
    """Una variable SUIZE_* que no está en ENV_OVERRIDES no debe romper nada ni aplicarse."""
    settings = load_settings(env={"SUIZE_ALGO_INVENTADO": "x"})

    assert settings.default_target == "127.0.0.1"


# ------------------------------------------------------------------------- validadores
#
# _as_str y _as_positive_int son internos, pero se ejercitan de sobra a través
# de las secciones reales de la configuración: aquí se cubren los casos límite
# que ninguna sección concreta fuerza por sí sola.


def test_a_negative_timeout_is_rejected(tmp_path: Path) -> None:
    path = _config(tmp_path, "[scan]\ntimeout = -1\n")

    with pytest.raises(ConfigError, match="mayor que 0"):
        load_settings(path, env={})


def test_a_zero_timeout_is_rejected(tmp_path: Path) -> None:
    path = _config(tmp_path, "[scan]\ntimeout = 0\n")

    with pytest.raises(ConfigError, match="mayor que 0"):
        load_settings(path, env={})


def test_a_float_where_an_int_is_expected_is_rejected(tmp_path: Path) -> None:
    path = _config(tmp_path, "[scan]\ntimeout = 60.5\n")

    with pytest.raises(ConfigError, match="número entero"):
        load_settings(path, env={})


def test_a_bool_where_an_int_is_expected_is_rejected(tmp_path: Path) -> None:
    """bool es subclase de int en Python: sin la comprobación explícita, `true` colaría como 1."""
    path = _config(tmp_path, "[scan]\ntimeout = true\n")

    with pytest.raises(ConfigError, match="número entero"):
        load_settings(path, env={})


def test_an_empty_string_where_text_is_expected_is_rejected(tmp_path: Path) -> None:
    path = _config(tmp_path, '[scan]\ndefault_target = ""\n')

    with pytest.raises(ConfigError, match="texto no vacío"):
        load_settings(path, env={})


def test_a_blank_string_where_text_is_expected_is_rejected(tmp_path: Path) -> None:
    path = _config(tmp_path, '[scan]\ndefault_target = "   "\n')

    with pytest.raises(ConfigError, match="texto no vacío"):
        load_settings(path, env={})


def test_a_number_where_text_is_expected_is_rejected(tmp_path: Path) -> None:
    path = _config(tmp_path, "[scan]\ndefault_target = 5\n")

    with pytest.raises(ConfigError, match="texto no vacío"):
        load_settings(path, env={})


def test_a_section_that_is_not_a_table_is_rejected(tmp_path: Path) -> None:
    path = _config(tmp_path, 'scan = "no es una tabla"\n')

    with pytest.raises(ConfigError, match=r"\[scan\] debe ser una tabla"):
        load_settings(path, env={})


def test_time_presets_must_be_present() -> None:
    """No la ejercita ninguna sección real: default.toml siempre trae presets."""
    from suize.config.settings import _build_settings

    with pytest.raises(ConfigError, match="lista no vacía"):
        _build_settings({"scan": {}, "logs": {}}, ())


def test_time_presets_entries_must_be_tables(tmp_path: Path) -> None:
    path = _config(tmp_path, 'logs.time_presets = ["no-es-una-tabla"]\n')

    with pytest.raises(ConfigError, match="debe ser una tabla con key y label"):
        load_settings(path, env={})


# ---------------------------------------------------------------------------- utilidades


def test_default_config_text_is_valid_toml_and_matches_the_packaged_settings() -> None:
    """El texto crudo y los Settings que se construyen a partir de él deben coincidir."""
    import tomllib

    text = default_config_text()
    parsed = tomllib.loads(text)

    assert parsed["scan"]["default_target"] == load_settings(env={}).default_target


def test_settings_is_frozen() -> None:
    """Settings representa una configuración ya cargada; no debería poder mutarse a mano."""
    settings = load_settings(env={})

    with pytest.raises(AttributeError):
        settings.default_target = "otro"  # type: ignore[misc]


def test_settings_correlation_tables_are_read_only_mappings() -> None:
    settings = load_settings(env={})

    assert isinstance(settings.correlation_ports, Mapping)
    with pytest.raises(TypeError):
        settings.correlation_ports[9999] = ("x",)  # type: ignore[index]


def test_the_packaged_tables_load_by_default() -> None:
    settings = load_settings()

    assert settings.correlation_ports[22] == ("ssh", "sshd")
    assert settings.correlation_services["http"] == ("nginx", "apache2", "httpd")


def test_a_user_entry_is_added_without_losing_the_defaults(tmp_path: Path) -> None:
    """Se combina entrada por entrada: no hay que copiar toda la tabla."""
    path = _config(tmp_path, '[correlation.ports]\n8006 = ["pveproxy"]\n')

    settings = load_settings(path)

    assert settings.correlation_ports[8006] == ("pveproxy",)
    assert settings.correlation_ports[22] == ("ssh", "sshd")


def test_a_user_entry_replaces_the_default_one(tmp_path: Path) -> None:
    path = _config(tmp_path, '[correlation.ports]\n3306 = ["mariadb"]\n')

    assert load_settings(path).correlation_ports[3306] == ("mariadb",)


def test_an_empty_list_disables_an_entry(tmp_path: Path) -> None:
    path = _config(tmp_path, "[correlation.ports]\n27017 = []\n")

    assert load_settings(path).correlation_ports[27017] == ()


def test_service_names_are_lowercased(tmp_path: Path) -> None:
    path = _config(tmp_path, '[correlation.services]\nHTTP-ALT = ["nginx"]\n')

    assert load_settings(path).correlation_services["http-alt"] == ("nginx",)


def test_duplicate_units_are_collapsed(tmp_path: Path) -> None:
    path = _config(tmp_path, '[correlation.ports]\n22 = ["ssh", "ssh", "sshd"]\n')

    assert load_settings(path).correlation_ports[22] == ("ssh", "sshd")


# --------------------------------------------------------------------------- errores


def test_a_port_that_is_not_a_number_is_rejected(tmp_path: Path) -> None:
    path = _config(tmp_path, '[correlation.ports]\nhttp = ["nginx"]\n')

    with pytest.raises(ConfigError, match="no es un número de puerto"):
        load_settings(path)


@pytest.mark.parametrize("port", ["0", "65536", "99999"])
def test_a_port_out_of_range_is_rejected(tmp_path: Path, port: str) -> None:
    path = _config(tmp_path, f'[correlation.ports]\n{port} = ["x"]\n')

    with pytest.raises(ConfigError, match="fuera de"):
        load_settings(path)


def test_a_value_that_is_not_a_list_is_rejected(tmp_path: Path) -> None:
    path = _config(tmp_path, '[correlation.ports]\n22 = "ssh"\n')

    with pytest.raises(ConfigError, match="lista de nombres"):
        load_settings(path)


@pytest.mark.parametrize("unit", ["--output=/etc/passwd", "ssh unit", "-ssh", "uni/dad"])
def test_an_invalid_unit_name_is_rejected(tmp_path: Path, unit: str) -> None:
    """Los nombres acaban como argumento de journalctl: se validan al cargar."""
    path = _config(tmp_path, f'[correlation.ports]\n22 = ["{unit}"]\n')

    with pytest.raises(ConfigError):
        load_settings(path)


def test_a_template_instance_name_is_accepted(tmp_path: Path) -> None:
    path = _config(tmp_path, '[correlation.ports]\n5432 = ["postgresql@16-main"]\n')

    assert load_settings(path).correlation_ports[5432] == ("postgresql@16-main",)


def test_the_correlation_section_must_be_a_table(tmp_path: Path) -> None:
    path = _config(tmp_path, 'correlation = "no"\n')

    with pytest.raises(ConfigError, match="debe ser una tabla"):
        load_settings(path)


def test_the_ports_table_must_be_a_table(tmp_path: Path) -> None:
    path = _config(tmp_path, "[correlation]\nports = 3\n")

    with pytest.raises(ConfigError, match=r"\[correlation.ports\] debe ser una tabla"):
        load_settings(path)


def test_the_services_table_must_be_a_table(tmp_path: Path) -> None:
    path = _config(tmp_path, "[correlation]\nservices = 3\n")

    with pytest.raises(ConfigError, match=r"\[correlation.services\] debe ser una tabla"):
        load_settings(path)
