"""Tests de la carga de las tablas de correlación desde la configuración."""

from pathlib import Path

import pytest

from suize.config.settings import ConfigError, load_settings


def _config(tmp_path: Path, contenido: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(contenido, encoding="utf-8")
    return path


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
