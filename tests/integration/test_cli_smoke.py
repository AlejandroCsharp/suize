"""Pruebas de humo de la CLI completa: argparse → core → ui.

``fake_system`` (ver ``conftest.py``) sustituye ``shutil.which`` y ``subprocess.run``
con ``monkeypatch``: nmap, journalctl y systemctl nunca se ejecutan de verdad y las
respuestas salen de ``tests/fixtures``.
"""

import csv
import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from suize import __version__, cli
from suize.config.settings import load_settings
from suize.ui import export, menus, prompts
from suize.utils import shell
from suize.utils.deps import check_dependencies
from suize.utils.permissions import PermissionStatus
from suize.utils.time_filter import resolve_preset
from tests.conftest import FakeSystem

NON_ROOT_IN_JOURNAL_GROUP = PermissionStatus(
    is_root=False,
    groups=frozenset({"usuario", "systemd-journal"}),
    journal_groups=frozenset({"systemd-journal"}),
)


@pytest.fixture(autouse=True)
def _fixed_permissions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Los avisos no dependen de si los tests corren como root o no."""
    monkeypatch.setattr(cli, "check_permissions", lambda: NON_ROOT_IN_JOURNAL_GROUP)


def run_cli(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = cli.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# --------------------------------------------------------------------------- general


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--version"])
    assert exc_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"suize {__version__}"


def test_without_terminal_the_menu_is_not_started(
    fake_system: FakeSystem, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, err = run_cli(capsys)
    assert code == cli.EXIT_USAGE
    assert "necesita una terminal" in err
    assert fake_system.calls == []


def test_missing_config_file(capsys: pytest.CaptureFixture[str], tmp_path: Any) -> None:
    code, _, err = run_cli(capsys, "--config", str(tmp_path / "nada.toml"), "logs")
    assert code == cli.EXIT_USAGE
    assert "Configuración inválida" in err


def test_invalid_profile_in_environment(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SUIZE_SCAN_PROFILE", "turbo")
    code, _, err = run_cli(capsys, "scan", "127.0.0.1")
    assert code == cli.EXIT_USAGE
    assert "turbo" in err


def test_import_has_no_side_effects() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import suize.cli, suize.__main__"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_python_dash_m_help() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "suize", "--help"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0
    assert "scan" in result.stdout
    assert "logs" in result.stdout


# --------------------------------------------------------------------------- scan


def test_scan_renders_table(fake_system: FakeSystem, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run_cli(capsys, "scan", "127.0.0.1")

    assert code == cli.EXIT_OK
    [call] = fake_system.calls_for("nmap")
    assert call[:2] == ["nmap", "-sV"]
    assert call[-3] == "-oX"
    assert call[-1] == "127.0.0.1"
    for text in ("127.0.0.1", "localhost", "OpenSSH", "nginx 1.24.0", "MySQL", "ssl/http"):
        assert text in out
    assert "631" not in out  # los puertos cerrados no se listan


def test_scan_json(fake_system: FakeSystem, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run_cli(capsys, "scan", "127.0.0.1", "--profile", "fast", "--json")

    assert code == cli.EXIT_OK
    assert "-F" in fake_system.calls_for("nmap")[0]
    payload = json.loads(out)
    assert payload["target"] == "127.0.0.1"
    assert [host["address"] for host in payload["hosts"]] == [
        "127.0.0.1",
        "192.168.1.20",
        "192.168.1.30",
    ]
    ssh = payload["hosts"][0]["ports"][0]
    assert ssh["number"] == 22
    assert ssh["product"] == "OpenSSH"


def test_scan_uses_default_target_from_environment(
    fake_system: FakeSystem, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SUIZE_DEFAULT_TARGET", "192.168.1.0/24")
    code, _, _ = run_cli(capsys, "scan", "--json")
    assert code == cli.EXIT_OK
    assert fake_system.calls_for("nmap")[0][-1] == "192.168.1.0/24"


def test_scan_save_xml(
    fake_system: FakeSystem, capsys: pytest.CaptureFixture[str], tmp_path: Any, nmap_xml: str
) -> None:
    destination = tmp_path / "resultado.xml"
    code, _, _ = run_cli(capsys, "scan", "127.0.0.1", "--save-xml", str(destination), "--json")
    assert code == cli.EXIT_OK
    assert destination.read_text(encoding="utf-8") == nmap_xml


def test_scan_rejects_argument_injection(
    fake_system: FakeSystem, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, err = run_cli(capsys, "scan", "--", "-iL/etc/shadow")
    assert code == cli.EXIT_USAGE
    assert "empezar por '-'" in err
    assert fake_system.calls == []


def test_scan_without_nmap(fake_system: FakeSystem, capsys: pytest.CaptureFixture[str]) -> None:
    fake_system.available.discard("nmap")
    code, _, err = run_cli(capsys, "scan", "127.0.0.1")
    assert code == cli.EXIT_MISSING_DEPENDENCY
    assert "nmap" in err
    assert "no está instalado" in err
    assert fake_system.calls == []


def test_scan_with_correlation(fake_system: FakeSystem, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run_cli(capsys, "scan", "127.0.0.1", "--correlate", "--since", "6h", "--json")

    assert code == cli.EXIT_OK
    payload = json.loads(out)
    by_port = {item["port"]: item["units"] for item in payload["correlations"]}
    # 22 → ssh y 80 → nginx existen en SYSTEMCTL_OUTPUT; mysql no. 443 es de otro host.
    assert by_port[22] == ["ssh"]
    assert by_port[80] == ["nginx"]
    assert by_port[3306] == []
    assert payload["units"] == ["nginx.service", "ssh.service"]
    assert len(payload["logs"]) == 10
    assert payload["error"] is None

    [journal_call] = fake_system.calls_for("journalctl")
    assert "--unit=nginx.service" in journal_call
    assert "--unit=ssh.service" in journal_call
    assert any(arg.startswith("--since=") for arg in journal_call)


def test_scan_correlation_renders_tables(
    fake_system: FakeSystem, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = run_cli(capsys, "scan", "127.0.0.1", "--correlate")
    assert code == cli.EXIT_OK
    assert "unidades systemd" in out
    assert "Resumen" in out
    assert "Failed password" in out


def test_scan_correlation_failure_keeps_scan_results(
    fake_system: FakeSystem, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    original_run = fake_system.run

    def broken_systemctl(cmd: Any, **kwargs: Any) -> Any:
        if cmd[0].endswith("systemctl"):
            return subprocess.CompletedProcess(list(cmd), 1, "", "System has not been booted")
        return original_run(cmd, **kwargs)

    monkeypatch.setattr(shell.subprocess, "run", broken_systemctl)
    code, out, err = run_cli(capsys, "scan", "127.0.0.1", "--correlate")

    assert code == cli.EXIT_ERROR
    assert "OpenSSH" in out  # el escaneo se muestra igualmente
    assert "No se pudo correlacionar" in err


# --------------------------------------------------------------------------- logs


def test_logs_json_with_combined_filters(
    fake_system: FakeSystem, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = run_cli(
        capsys, "logs", "-u", "ssh", "-p", "err", "--since", "1h", "-g", "Failed", "--json"
    )

    assert code == cli.EXIT_OK
    [call] = fake_system.calls_for("journalctl")
    assert call[:4] == ["journalctl", "--output=json", "--no-pager", "--quiet"]
    assert "--unit=ssh" in call
    assert "--priority=3" in call
    assert "--grep=Failed" in call
    assert "--lines=200" in call
    assert any(arg.startswith("--since=") for arg in call)

    payload = json.loads(out)
    assert payload["query"]["priority"] == "3"
    assert payload["summary"]["total"] == 10
    assert payload["summary"]["top_units"][0] == ["ssh.service", 3]
    assert payload["entries"][0]["priority_name"] == "info"


def test_logs_table_and_summary(
    fake_system: FakeSystem, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = run_cli(capsys, "logs", "--since", "yesterday", "-n", "50")

    assert code == cli.EXIT_OK
    assert "--lines=50" in fake_system.calls_for("journalctl")[0]
    for text in ("Resumen", "Total", "10 entradas", "ssh.service", "Tarea ñ", "dumped core"):
        assert text in out


def test_logs_lines_from_environment(
    fake_system: FakeSystem, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SUIZE_LOG_LINES", "5")
    code, _, _ = run_cli(capsys, "logs", "--json")
    assert code == cli.EXIT_OK
    assert "--lines=5" in fake_system.calls_for("journalctl")[0]


def test_logs_grep_without_matches(
    fake_system: FakeSystem, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_system.journal_output = ""
    fake_system.journal_returncode = 1  # journalctl --grep sin coincidencias
    code, out, _ = run_cli(capsys, "logs", "--grep", "no-existe")
    assert code == cli.EXIT_OK
    assert "No hay entradas" in out


@pytest.mark.parametrize(
    ("argv", "match"),
    [
        (["logs", "-p", "urgente"], "Prioridad inválida"),
        (["logs", "-u", "ssh;reboot"], "unidad inválido"),
        (["logs", "--since", "la semana pasada"], "Rango temporal inválido"),
        (["logs", "--since", "2026-01-02", "--until", "2026-01-01"], "posterior"),
    ],
)
def test_logs_invalid_arguments(
    fake_system: FakeSystem, capsys: pytest.CaptureFixture[str], argv: list[str], match: str
) -> None:
    code, _, err = run_cli(capsys, *argv)
    assert code == cli.EXIT_USAGE
    assert match in err
    assert fake_system.calls == []


def test_logs_without_journalctl(
    fake_system: FakeSystem, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_system.available.discard("journalctl")
    code, _, err = run_cli(capsys, "logs")
    assert code == cli.EXIT_MISSING_DEPENDENCY
    assert "journalctl" in err


def test_logs_journalctl_failure(
    fake_system: FakeSystem, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def failing(cmd: Any, **kwargs: Any) -> Any:
        return subprocess.CompletedProcess(list(cmd), 1, "", "Failed to open journal")

    monkeypatch.setattr(shell.subprocess, "run", failing)
    code, _, err = run_cli(capsys, "logs")
    assert code == cli.EXIT_ERROR
    assert "Failed to open journal" in err


# --------------------------------------------------------------------------- shell


def test_shell_reports_missing_program(fake_system: FakeSystem) -> None:
    with pytest.raises(shell.CommandError, match="No se encontró 'nmapx'"):
        shell.run(["nmapx", "-V"])


def test_shell_timeout(monkeypatch: pytest.MonkeyPatch, fake_system: FakeSystem) -> None:
    def slow(cmd: Any, **kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(shell.subprocess, "run", slow)
    with pytest.raises(shell.CommandError, match="tiempo máximo de 5 s"):
        shell.run(["nmap", "127.0.0.1"], timeout=5)


# --------------------------------------------------------------------------- menú


@pytest.fixture
def scripted_menu(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Responde al menú principal con las acciones de la lista, en orden."""
    actions: list[str] = []

    def fake_select(message: str, choices: Any, *, default: str | None = None) -> str:
        return actions.pop(0)

    monkeypatch.setattr(prompts, "select", fake_select)
    monkeypatch.setattr(cli, "_is_interactive_terminal", lambda: True)
    return actions


def test_menu_logs_flow_then_exit(
    fake_system: FakeSystem,
    scripted_menu: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    scripted_menu.extend([menus.ACTION_LOGS, menus.ACTION_EXIT])
    monkeypatch.setattr(prompts, "ask_time_range", lambda presets, key: resolve_preset("24h"))
    monkeypatch.setattr(prompts, "ask_priority", lambda: "0..4")
    monkeypatch.setattr(prompts, "ask_unit", lambda known=(): "nginx.service")
    monkeypatch.setattr(prompts, "ask_grep", lambda: None)
    monkeypatch.setattr(prompts, "ask_lines", lambda default: 30)

    code, out, _ = run_cli(capsys)

    assert code == cli.EXIT_OK
    journal_call = fake_system.calls_for("journalctl")[0]
    assert "--unit=nginx.service" in journal_call
    assert "--priority=0..4" in journal_call
    assert "--lines=30" in journal_call
    assert "Logs de nginx.service" in out
    assert "Hasta luego" in out


def test_menu_correlate_flow(
    fake_system: FakeSystem,
    scripted_menu: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    scripted_menu.extend([menus.ACTION_CORRELATE, menus.ACTION_EXIT])
    monkeypatch.setattr(prompts, "ask_target", lambda default: "127.0.0.1")
    monkeypatch.setattr(prompts, "ask_scan_profile", lambda profiles, default: "fast")
    monkeypatch.setattr(prompts, "ask_time_range", lambda presets, key: resolve_preset("1h"))

    code, out, _ = run_cli(capsys)

    assert code == cli.EXIT_OK
    assert "-F" in fake_system.calls_for("nmap")[0]
    assert fake_system.calls_for("systemctl")
    assert "--unit=ssh.service" in fake_system.calls_for("journalctl")[0]
    assert "Logs de nginx.service, ssh.service" in out


def test_menu_survives_errors_and_cancellation(
    fake_system: FakeSystem,
    scripted_menu: list[str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    scripted_menu.extend([menus.ACTION_SCAN, menus.ACTION_SCAN, menus.ACTION_EXIT])
    targets = iter(["-iL/etc/shadow"])

    def ask_target(default: str) -> str:
        try:
            return next(targets)  # 1.ª vez: objetivo inválido → error mostrado
        except StopIteration:
            raise prompts.Cancelled from None  # 2.ª vez: el usuario pulsa Ctrl+C

    monkeypatch.setattr(prompts, "ask_target", ask_target)
    monkeypatch.setattr(prompts, "ask_scan_profile", lambda profiles, default: "standard")

    code, out, _ = run_cli(capsys)

    assert code == cli.EXIT_OK
    assert "empezar por '-'" in out
    assert "Operación cancelada" in out
    assert fake_system.calls_for("nmap") == []


def test_menu_disables_options_without_dependencies(fake_system: FakeSystem) -> None:
    fake_system.available = {"journalctl"}
    ctx = menus.AppContext(
        console=cli.make_console(no_color=True),
        settings=load_settings(env={}),
        deps=check_dependencies(),
        permissions=NON_ROOT_IN_JOURNAL_GROUP,
    )
    choices = {choice.value: choice.disabled for choice in menus._main_choices(ctx)}  # type: ignore[union-attr]
    assert choices[menus.ACTION_SCAN] == "requiere nmap"
    assert choices[menus.ACTION_LOGS] is None
    assert choices[menus.ACTION_CORRELATE] == "requiere nmap, systemctl"
    assert choices[menus.ACTION_EXIT] is None


def test_broken_pipe_is_handled_quietly(
    fake_system: FakeSystem,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`suize scan ... --json | head` no debe terminar con una traza de BrokenPipeError."""
    silenced: list[bool] = []

    def closed_pipe(payload: object, stream: object) -> None:
        raise BrokenPipeError

    monkeypatch.setattr(cli, "dump_json", closed_pipe)
    # No se toca el stdout real del proceso de pytest.
    monkeypatch.setattr(cli, "_silence_stdout", lambda: silenced.append(True))

    code, _, err = run_cli(capsys, "scan", "127.0.0.1", "--json", "-q")

    assert code == cli.EXIT_ERROR
    assert silenced == [True]
    assert "Traceback" not in err


def test_scan_correlate_warns_when_target_is_remote(
    fake_system: FakeSystem, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, err = run_cli(capsys, "scan", "192.168.1.10", "--correlate")

    assert code == cli.EXIT_OK
    assert "ESTA máquina" in err


def test_scan_correlate_on_loopback_does_not_warn(
    fake_system: FakeSystem, capsys: pytest.CaptureFixture[str]
) -> None:
    _, _, err = run_cli(capsys, "scan", "127.0.0.1", "--correlate")

    assert "ESTA máquina" not in err


# ------------------------------------------------------------------------- exportación


def test_scan_csv_goes_to_stdout(
    fake_system: FakeSystem, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = run_cli(capsys, "scan", "127.0.0.1", "--format", "csv", "-q")

    assert code == cli.EXIT_OK
    assert out.splitlines()[0] == ",".join(export.SCAN_COLUMNS)
    assert "22,tcp,open,ssh" in out


def test_scan_csv_writes_the_requested_file(
    fake_system: FakeSystem, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    destination = tmp_path / "puertos.csv"

    code, out, err = run_cli(
        capsys, "scan", "127.0.0.1", "--format", "csv", "--output", str(destination)
    )

    assert code == cli.EXIT_OK
    assert out == ""  # nada por stdout: todo fue al archivo
    assert "puertos.csv" in err  # confirmación informativa
    rows = list(csv.reader(io.StringIO(destination.read_text(encoding="utf-8"))))
    assert rows[0] == list(export.SCAN_COLUMNS)
    assert len(rows) > 1


def test_scan_csv_with_correlate_adds_the_units_column(
    fake_system: FakeSystem, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    destination = tmp_path / "correlacion.csv"

    code, _, _ = run_cli(
        capsys,
        "scan",
        "127.0.0.1",
        "--correlate",
        "--format",
        "csv",
        "--output",
        str(destination),
        "-q",
    )

    assert code == cli.EXIT_OK
    header = destination.read_text(encoding="utf-8").splitlines()[0]
    assert header.endswith(",unidades")


def test_logs_csv_writes_the_requested_file(
    fake_system: FakeSystem, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    destination = tmp_path / "logs.csv"

    code, out, _ = run_cli(
        capsys, "logs", "--since", "24h", "--format", "csv", "--output", str(destination)
    )

    assert code == cli.EXIT_OK
    assert out == ""
    rows = list(csv.reader(io.StringIO(destination.read_text(encoding="utf-8"))))
    assert rows[0] == list(export.LOG_COLUMNS)
    assert len(rows) > 1


def test_json_flag_still_works_as_a_shortcut(
    fake_system: FakeSystem, capsys: pytest.CaptureFixture[str]
) -> None:
    """--json se mantiene por compatibilidad con los scripts existentes."""
    _, with_flag, _ = run_cli(capsys, "scan", "127.0.0.1", "--json", "-q")
    _, with_format, _ = run_cli(capsys, "scan", "127.0.0.1", "--format", "json", "-q")

    assert json.loads(with_flag) == json.loads(with_format)


def test_json_can_also_be_written_to_a_file(
    fake_system: FakeSystem, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    destination = tmp_path / "resultado.json"

    code, out, _ = run_cli(
        capsys, "scan", "127.0.0.1", "--format", "json", "--output", str(destination), "-q"
    )

    assert code == cli.EXIT_OK
    assert out == ""
    assert json.loads(destination.read_text(encoding="utf-8"))["target"] == "127.0.0.1"


def test_quiet_hides_the_written_file_notice(
    fake_system: FakeSystem, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    destination = tmp_path / "silencio.csv"

    _, _, err = run_cli(capsys, "logs", "--format", "csv", "--output", str(destination), "-q")

    assert "silencio.csv" not in err


def test_unwritable_output_reports_an_error(
    fake_system: FakeSystem, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    inexistente = tmp_path / "sin" / "crear" / "salida.csv"

    code, _, err = run_cli(capsys, "logs", "--format", "csv", "--output", str(inexistente), "-q")

    assert code == cli.EXIT_ERROR
    assert "No se pudo escribir" in err


def test_invalid_format_is_rejected(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["scan", "127.0.0.1", "--format", "xml"])

    assert exc_info.value.code == 2


def test_written_notice_uses_the_singular_for_one_row(
    fake_system: FakeSystem, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    destination = tmp_path / "una.csv"
    # Una sola entrada en el journal simulado.
    fake_system.journal_output = fake_system.journal_output.splitlines()[0]

    _, _, err = run_cli(capsys, "logs", "--format", "csv", "--output", str(destination))

    assert "(1 fila)" in err
