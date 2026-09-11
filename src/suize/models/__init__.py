"""Estructuras de datos del dominio. Esta capa no importa nada del resto del proyecto."""

from suize.models.host import Host, Port
from suize.models.log_entry import DEFAULT_PRIORITY, PRIORITY_NAMES, LogEntry, LogSummary

__all__ = ["DEFAULT_PRIORITY", "PRIORITY_NAMES", "Host", "LogEntry", "LogSummary", "Port"]
