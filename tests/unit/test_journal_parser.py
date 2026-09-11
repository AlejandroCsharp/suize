"""Tests del parser de ``journalctl -o json`` contra ``fixtures/journal_sample.json``."""

import json
from datetime import datetime

import pytest

from suize.core.journal_parser import (
    UNKNOWN_UNIT,
    JournalParseError,
    parse_journal_json,
    parse_record,
    summarize,
)
from suize.models.log_entry import DEFAULT_PRIORITY, LogEntry


@pytest.fixture
def entries(journal_json: str) -> list[LogEntry]:
    return parse_journal_json(journal_json)


def test_parses_all_entries(entries: list[LogEntry]) -> None:
    assert len(entries) == 10


def test_timestamp_is_microseconds_since_epoch(entries: list[LogEntry]) -> None:
    first = entries[0]
    # __REALTIME_TIMESTAMP = 1768473000123456 µs → fecha local con microsegundos.
    assert first.timestamp == datetime.fromtimestamp(1768473000123456 / 1_000_000)
    assert first.timestamp.microsecond == 123456


def test_basic_fields(entries: list[LogEntry]) -> None:
    first = entries[0]
    assert first.unit == "ssh.service"
    assert first.priority == 6
    assert first.priority_name == "info"
    assert first.message == "Server listening on 0.0.0.0 port 22."
    assert first.hostname == "suize-lab"
    assert first.pid == 812


def test_unit_falls_back_to_syslog_identifier(entries: list[LogEntry]) -> None:
    kernel = next(entry for entry in entries if "usb 1-1" in entry.message)
    assert kernel.unit == "kernel"  # sin _SYSTEMD_UNIT → SYSLOG_IDENTIFIER
    assert kernel.priority_name == "warning"


def test_missing_priority_uses_default(entries: list[LogEntry]) -> None:
    backup = next(entry for entry in entries if entry.unit == "backup-script")
    assert backup.priority == DEFAULT_PRIORITY


def test_binary_message_is_decoded(entries: list[LogEntry]) -> None:
    cron = next(entry for entry in entries if entry.unit == "cron.service")
    # journalctl serializa los campos binarios como listas de bytes.
    assert cron.message == "Tarea ñ"


def test_entries_keep_journal_order(entries: list[LogEntry]) -> None:
    stamps = [entry.timestamp for entry in entries]
    assert stamps == sorted(stamps)


def test_summary_counts(entries: list[LogEntry]) -> None:
    summary = summarize(entries, top_n=2)
    assert summary.total == 10
    assert summary.by_priority == {2: 1, 3: 1, 4: 1, 5: 1, 6: 5, 7: 1}
    assert list(summary.by_priority) == sorted(summary.by_priority)
    assert summary.top_units == [("ssh.service", 3), ("nginx.service", 2)]
    assert summary.first == entries[0].timestamp
    assert summary.last == entries[-1].timestamp


def test_summary_of_nothing() -> None:
    summary = summarize([])
    assert summary.total == 0
    assert summary.by_priority == {}
    assert summary.top_units == []
    assert summary.first is None
    assert summary.last is None


def test_empty_output_returns_no_entries() -> None:
    assert parse_journal_json("") == []
    assert parse_journal_json("\n\n  \n") == []


def test_invalid_lines_are_skipped_unless_strict(journal_json: str) -> None:
    lines = journal_json.splitlines()
    noisy = "\n".join([lines[0], "esto no es json", "", lines[1]])
    assert len(parse_journal_json(noisy)) == 2
    with pytest.raises(JournalParseError, match="Línea 2"):
        parse_journal_json(noisy, strict=True)


def test_accepts_json_array(journal_json: str) -> None:
    records = [json.loads(line) for line in journal_json.splitlines()]
    assert len(parse_journal_json(json.dumps(records))) == 10


def test_invalid_json_array_raises() -> None:
    with pytest.raises(JournalParseError, match="Array JSON inválido"):
        parse_journal_json("[{]")


def test_non_object_records() -> None:
    assert parse_journal_json('[1, "x"]') == []
    with pytest.raises(JournalParseError, match="Registro 1"):
        parse_journal_json("[1]", strict=True)


def test_record_without_valid_timestamp_is_discarded() -> None:
    assert parse_record({"MESSAGE": "sin fecha"}) is None
    assert parse_record({"__REALTIME_TIMESTAMP": "abc", "MESSAGE": "x"}) is None


def test_record_fallbacks_and_normalization() -> None:
    base = {"__REALTIME_TIMESTAMP": "1768473000000000"}

    only_comm = parse_record({**base, "_COMM": "bash", "PRIORITY": "9", "MESSAGE": "hola\n"})
    assert only_comm is not None
    assert only_comm.unit == "bash"
    assert only_comm.priority == 7  # fuera de rango → se acota a 0-7
    assert only_comm.message == "hola"  # sin salto de línea final
    assert only_comm.pid is None

    anonymous = parse_record({**base, "MESSAGE": ["primero", "segundo"]})
    assert anonymous is not None
    assert anonymous.unit == UNKNOWN_UNIT
    assert anonymous.message == "primero"  # campo repetido → primer valor
