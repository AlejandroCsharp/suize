"""Fixtures compartidas.

Los tests nunca ejecutan nmap, journalctl ni systemctl de verdad: ``fake_system``
sustituye ``shutil.which`` y ``subprocess.run`` con ``monkeypatch`` y responde con
los fixtures de ``tests/fixtures``.
"""

import os
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from suize.utils import deps, shell

FIXTURES_DIR = Path(__file__).parent / "fixtures"

SYSTEMCTL_OUTPUT = """\
cron.service              loaded active running Regular background program processing daemon
nginx.service             loaded active running A high performance web server
ssh.service               loaded active running OpenBSD Secure Shell server
systemd-journald.service  loaded active running Journal Service
"""


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Evita que la config del usuario o variables SUIZE_* afecten a los tests."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    for name in list(os.environ):
        if name.startswith("SUIZE_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("COLUMNS", "200")


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def nmap_xml() -> str:
    return (FIXTURES_DIR / "nmap_scan.xml").read_text(encoding="utf-8")


@pytest.fixture
def journal_json() -> str:
    return (FIXTURES_DIR / "journal_sample.json").read_text(encoding="utf-8")


@pytest.fixture
def fixed_now() -> datetime:
    return datetime(2026, 1, 15, 12, 30, 45)


@dataclass
class FakeSystem:
    """Simula los binarios externos y registra cada comando ejecutado."""

    nmap_xml: str
    journal_output: str
    available: set[str] = field(default_factory=lambda: {"nmap", "journalctl", "systemctl"})
    journal_returncode: int = 0
    systemctl_output: str = SYSTEMCTL_OUTPUT
    calls: list[list[str]] = field(default_factory=list)

    def which(self, name: str, *args: Any, **kwargs: Any) -> str | None:
        return f"/usr/bin/{name}" if name in self.available else None

    def run(self, cmd: Sequence[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        argv = [Path(cmd[0]).name, *cmd[1:]]
        self.calls.append(argv)
        program = argv[0]
        if program == "nmap":
            xml_path = Path(argv[argv.index("-oX") + 1])
            xml_path.write_text(self.nmap_xml, encoding="utf-8")
            return subprocess.CompletedProcess(list(cmd), 0, "Nmap done", "")
        if program == "journalctl":
            return subprocess.CompletedProcess(
                list(cmd), self.journal_returncode, self.journal_output, ""
            )
        if program == "systemctl":
            return subprocess.CompletedProcess(list(cmd), 0, self.systemctl_output, "")
        raise AssertionError(f"Comando inesperado: {argv}")

    def calls_for(self, program: str) -> list[list[str]]:
        return [call for call in self.calls if call[0] == program]


@pytest.fixture
def fake_system(monkeypatch: pytest.MonkeyPatch, nmap_xml: str, journal_json: str) -> FakeSystem:
    fake = FakeSystem(nmap_xml=nmap_xml, journal_output=journal_json)
    monkeypatch.setattr(shell.shutil, "which", fake.which)
    monkeypatch.setattr(shell.subprocess, "run", fake.run)
    # Simula un sistema arrancado con systemd, independientemente de la máquina.
    monkeypatch.setattr(deps, "SYSTEMD_RUNTIME_DIR", FIXTURES_DIR)
    return fake
