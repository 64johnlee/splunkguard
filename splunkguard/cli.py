"""SplunkGuard CLI — investigate Splunk incidents with Gemini."""
from __future__ import annotations

import asyncio
import logging
import sys

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from .agent import SplunkGuardAgent

load_dotenv()
console = Console()

_SEVERITY_COLOR = {
    "critical": "bold red",
    "high": "red",
    "medium": "yellow",
    "low": "cyan",
    "info": "dim",
}


@click.group()
@click.option("--debug", is_flag=True, default=False)
def main(debug: bool) -> None:
    """SplunkGuard — AI-powered Splunk incident investigation using Gemini."""
    logging.basicConfig(level=logging.DEBUG if debug else logging.WARNING)


@main.command()
@click.argument("query")
@click.option("--time-range", "-t", default="-1h", show_default=True,
              help="Splunk time range (e.g. -1h, -24h, -7d).")
@click.option("--gemini-key", envvar="GEMINI_API_KEY", required=True)
@click.option("--splunk-endpoint", envvar="SPLUNK_MCP_ENDPOINT", required=True,
              help="Splunk MCP Server endpoint URL.")
@click.option("--splunk-token", envvar="SPLUNK_MCP_TOKEN", required=True,
              help="Encrypted Splunk MCP token.")
@click.option("--instance-label", envvar="SPLUNK_INSTANCE_LABEL", default="splunk")
def investigate(
    query: str,
    time_range: str,
    gemini_key: str,
    splunk_endpoint: str,
    splunk_token: str,
    instance_label: str,
) -> None:
    """Investigate an incident described in natural language QUERY.

    Examples:\n
      splunkguard investigate "high error rate on payment service last hour"\n
      splunkguard investigate "failed SSH logins from unusual IPs" -t -24h\n
      splunkguard investigate "why is web-frontend latency spiking"
    """
    agent = SplunkGuardAgent(
        gemini_api_key=gemini_key,
        splunk_mcp_endpoint=splunk_endpoint,
        splunk_mcp_token=splunk_token,
        splunk_instance_label=instance_label,
    )
    try:
        report = asyncio.run(agent.investigate(query, time_range))
    except Exception as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        sys.exit(1)

    _render_report(report)


@main.command("alert")
@click.argument("alert_name")
@click.argument("alert_spl")
@click.option("--time-range", "-t", default="-1h", show_default=True)
@click.option("--gemini-key", envvar="GEMINI_API_KEY", required=True)
@click.option("--splunk-endpoint", envvar="SPLUNK_MCP_ENDPOINT", required=True)
@click.option("--splunk-token", envvar="SPLUNK_MCP_TOKEN", required=True)
@click.option("--instance-label", envvar="SPLUNK_INSTANCE_LABEL", default="splunk")
def alert(
    alert_name: str,
    alert_spl: str,
    time_range: str,
    gemini_key: str,
    splunk_endpoint: str,
    splunk_token: str,
    instance_label: str,
) -> None:
    """Investigate a triggered Splunk ALERT_NAME with its ALERT_SPL query."""
    agent = SplunkGuardAgent(
        gemini_api_key=gemini_key,
        splunk_mcp_endpoint=splunk_endpoint,
        splunk_mcp_token=splunk_token,
        splunk_instance_label=instance_label,
    )
    try:
        report = asyncio.run(agent.investigate_alert(alert_name, alert_spl, time_range))
    except Exception as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        sys.exit(1)

    _render_report(report)


def _render_report(report) -> None:
    sev = report.severity.value
    color = _SEVERITY_COLOR.get(sev, "white")

    console.print()
    console.print(
        Panel(
            f"[{color}]{report.title}[/]\n\n"
            f"[bold]Severity:[/] [{color}]{sev.upper()}[/]  "
            f"[bold]Category:[/] {report.category.value}  "
            f"[bold]Ongoing:[/] {'yes' if report.is_ongoing else 'resolved'}\n\n"
            f"[bold]Summary:[/] {report.summary}\n\n"
            f"[bold]Root Cause:[/] {report.root_cause}",
            title="[bold cyan]SplunkGuard Incident Report[/]",
            border_style="cyan",
        )
    )

    if report.affected_components:
        t = Table(title="Affected Components", show_lines=True)
        t.add_column("Name", style="cyan")
        t.add_column("Type")
        t.add_column("Errors", justify="right")
        t.add_column("First Seen")
        t.add_column("Last Seen")
        for c in report.affected_components:
            t.add_row(c.name, c.component_type, str(c.error_count), c.first_seen, c.last_seen)
        console.print(t)

    if report.remediation_steps:
        console.print("\n[bold green]Remediation Steps[/] (in priority order):")
        for step in report.remediation_steps:
            conf_color = {"high": "green", "medium": "yellow", "low": "red"}.get(
                step.confidence.value, "white"
            )
            console.print(
                f"\n  [{conf_color}]{step.priority}.[/] [bold]{step.action}[/]\n"
                f"     {step.description}"
            )
            if step.spl_query:
                console.print(f"     [dim]Verify:[/] [cyan]{step.spl_query}[/]")

    if report.key_spl_queries:
        console.print("\n[bold]Key SPL Queries:[/]")
        for q in report.key_spl_queries:
            console.print(Markdown(f"```\n{q}\n```"))

    console.print("\n[bold]Full Analysis:[/]")
    console.print(Markdown(report.full_analysis))
