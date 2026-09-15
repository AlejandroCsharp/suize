"""Tablas Rich para resultados de escaneo y de correlación."""

from collections.abc import Sequence

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

from suize.core.correlator import Correlation
from suize.models.host import Host
from suize.ui.theme import PORT_STATE_STYLES, icon, message


def _host_title(host: Host) -> Text:
    title = Text(host.address, style="host")
    if host.hostname:
        title.append(f"  {host.hostname}", style="accent")
    if host.mac:
        title.append(f"  MAC {host.mac}", style="muted")
    return title


def build_ports_table(host: Host, *, only_open: bool = True) -> Table:
    """Tabla de puertos de un host (por defecto, solo los abiertos)."""
    ports = host.open_ports if only_open else host.ports
    table = Table(
        title=_host_title(host), title_justify="left", box=box.ROUNDED, header_style="bold"
    )
    table.add_column("Puerto", justify="right", style="bold")
    table.add_column("Protocolo")
    table.add_column("Estado")
    table.add_column("Servicio", style="cyan")
    table.add_column("Versión", overflow="fold")
    for port in ports:
        version = port.version_label
        table.add_row(
            str(port.number),
            Text(port.protocol),
            Text(port.state, style=PORT_STATE_STYLES.get(port.state, "")),
            Text(port.service or "—"),
            Text(version or "—", style="" if version else "muted"),
        )
    return table


def render_hosts(console: Console, hosts: Sequence[Host], *, target: str = "") -> None:
    """Muestra todos los hosts del escaneo con sus puertos abiertos."""
    if not hosts:
        console.print(
            message(
                "warning",
                f"Nmap no devolvió hosts para '{target}'. ¿Está encendido? ¿El nombre resuelve?",
            )
        )
        return
    up = sum(1 for host in hosts if host.is_up)
    header = Text.assemble(
        f"{icon('scan')}Resultados",
        (f" de {target}" if target else "", "bold"),
        (f"  ·  {up}/{len(hosts)} host(s) activos", "muted"),
    )
    console.print(header)
    for host in hosts:
        if not host.is_up:
            console.print(Text(f"  {host.address}: {host.status}", style="muted"))
        elif not host.open_ports:
            console.print(_host_title(host).append("  sin puertos abiertos", style="muted"))
        else:
            console.print(build_ports_table(host))


def render_correlations(console: Console, correlations: Sequence[Correlation]) -> None:
    """Tabla puerto → unidades candidatas → unidades existentes en el sistema."""
    if not correlations:
        console.print(message("info", "No hay puertos abiertos que correlacionar."))
        return
    table = Table(
        title=f"{icon('correlate')}Puertos ↔ unidades systemd",
        title_justify="left",
        box=box.ROUNDED,
        header_style="bold",
    )
    table.add_column("Host", style="host")
    table.add_column("Puerto", justify="right")
    table.add_column("Servicio", style="cyan")
    table.add_column("Candidatos", style="muted")
    table.add_column("Unidades en este sistema")
    for item in correlations:
        found = (
            Text(", ".join(item.units), style="success")
            if item.units
            else Text("— ninguna —", style="muted")
        )
        table.add_row(
            Text(item.host),
            f"{item.port.number}/{item.port.protocol}",
            Text(item.port.service or "—"),
            Text(", ".join(item.candidates) or "sin mapeo"),
            found,
        )
    console.print(table)
