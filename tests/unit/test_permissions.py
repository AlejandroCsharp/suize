"""Tests de la detección de permisos.

Este módulo decide los avisos que ve el usuario al arrancar, así que un error
aquí no rompe nada visiblemente: solo hace que Suize mienta sobre lo que puede
o no puede leer. De ahí que interese cubrirlo bien.

Todo se simula (``os.geteuid``, ``os.getgroups``, ``grp``) para que el
resultado no dependa de con qué usuario se ejecuten los tests: como root, en
CI y como usuario normal deben dar lo mismo.
"""

import os
from typing import Any

import pytest

from suize.utils import permissions
from suize.utils.permissions import (
    JOURNAL_GROUPS,
    PermissionStatus,
    check_permissions,
    current_groups,
    is_root,
    journal_hint,
    nmap_hint,
)


def _status(*, root: bool = False, groups: frozenset[str] = frozenset()) -> PermissionStatus:
    return PermissionStatus(is_root=root, groups=groups, journal_groups=groups & JOURNAL_GROUPS)


# ------------------------------------------------------------------------------- is_root


def test_uid_zero_is_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)

    assert is_root() is True


def test_any_other_uid_is_not_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 1000)

    assert is_root() is False


def test_without_geteuid_it_is_not_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """En sistemas sin geteuid (Windows) no se puede afirmar que haya root."""
    monkeypatch.delattr(os, "geteuid", raising=False)

    assert is_root() is False


# ------------------------------------------------------------------------ current_groups


def _fake_grp(mapping: dict[int, str]) -> Any:
    class FakeEntry:
        def __init__(self, name: str) -> None:
            self.gr_name = name

    class FakeGrp:
        @staticmethod
        def getgrgid(gid: int) -> FakeEntry:
            if gid not in mapping:
                raise KeyError(gid)
            return FakeEntry(mapping[gid])

    return FakeGrp


def test_group_ids_are_translated_to_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "getgroups", lambda: [4, 27])
    monkeypatch.setattr(os, "getegid", lambda: 1000)
    monkeypatch.setitem(
        __import__("sys").modules, "grp", _fake_grp({4: "adm", 27: "sudo", 1000: "rein"})
    )

    assert current_groups() == frozenset({"adm", "sudo", "rein"})


def test_the_effective_group_is_included(monkeypatch: pytest.MonkeyPatch) -> None:
    """getegid() puede no estar en getgroups(), y cuenta igual."""
    monkeypatch.setattr(os, "getgroups", lambda: [])
    monkeypatch.setattr(os, "getegid", lambda: 4)
    monkeypatch.setitem(__import__("sys").modules, "grp", _fake_grp({4: "adm"}))

    assert current_groups() == frozenset({"adm"})


def test_an_unknown_gid_is_skipped_without_failing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un GID sin entrada en /etc/group no debe reventar el arranque."""
    monkeypatch.setattr(os, "getgroups", lambda: [4, 9999])
    monkeypatch.setattr(os, "getegid", lambda: 4)
    monkeypatch.setitem(__import__("sys").modules, "grp", _fake_grp({4: "adm"}))

    assert current_groups() == frozenset({"adm"})


def test_no_groups_at_all_is_an_empty_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "getgroups", lambda: [])
    monkeypatch.setattr(os, "getegid", lambda: 9999)
    monkeypatch.setitem(__import__("sys").modules, "grp", _fake_grp({}))

    assert current_groups() == frozenset()


# ---------------------------------------------------------------------- check_permissions


def test_check_permissions_keeps_only_the_journal_groups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(permissions, "is_root", lambda: False)
    monkeypatch.setattr(permissions, "current_groups", lambda: frozenset({"adm", "sudo", "docker"}))

    status = check_permissions()

    assert status.groups == frozenset({"adm", "sudo", "docker"})
    assert status.journal_groups == frozenset({"adm"})


def test_check_permissions_reports_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(permissions, "is_root", lambda: True)
    monkeypatch.setattr(permissions, "current_groups", lambda: frozenset({"root"}))

    assert check_permissions().is_root is True


# ------------------------------------------------------------- can_read_system_journal


@pytest.mark.parametrize("group", sorted(JOURNAL_GROUPS))
def test_any_journal_group_grants_access(group: str) -> None:
    """Los tres grupos valen por igual: systemd-journal, adm y wheel."""
    assert _status(groups=frozenset({group})).can_read_system_journal is True


def test_root_can_read_even_with_no_groups() -> None:
    assert _status(root=True).can_read_system_journal is True


def test_an_unrelated_group_does_not_grant_access() -> None:
    assert _status(groups=frozenset({"docker", "sudo"})).can_read_system_journal is False


def test_no_groups_and_no_root_means_no_access() -> None:
    assert _status().can_read_system_journal is False


# ------------------------------------------------------------------------------- avisos


def test_no_journal_hint_when_access_is_fine() -> None:
    assert journal_hint(_status(groups=frozenset({"adm"}))) is None


def test_no_journal_hint_for_root() -> None:
    assert journal_hint(_status(root=True)) is None


def test_the_journal_hint_names_the_command_to_fix_it() -> None:
    """El aviso solo sirve si dice qué hacer, no solo qué pasa."""
    hint = journal_hint(_status(groups=frozenset({"docker"})))

    assert hint is not None
    assert "usermod -aG systemd-journal" in hint


def test_no_nmap_hint_for_root() -> None:
    assert nmap_hint(_status(root=True)) is None


def test_the_nmap_hint_explains_what_changes_without_root() -> None:
    hint = nmap_hint(_status(groups=frozenset({"adm"})))

    assert hint is not None
    assert "-sT" in hint
    assert "-sS" in hint


def test_the_nmap_hint_appears_even_with_journal_access() -> None:
    """Son permisos distintos: leer el journal no da privilegios a Nmap."""
    assert nmap_hint(_status(groups=frozenset({"adm"}))) is not None
