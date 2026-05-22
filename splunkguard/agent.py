"""Core SplunkGuard agent — Gemini 2.0 Flash + Splunk MCP tool loop."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from google import genai
from google.genai import types
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from .backends.mcp import SplunkMCPBackend
from .models import (
    AffectedComponent,
    Confidence,
    IncidentCategory,
    IncidentReport,
    RemediationStep,
    Severity,
)
from .prompts import SYSTEM_PROMPT, build_alert_prompt, build_investigation_prompt

logger = logging.getLogger(__name__)
console = Console()

_GEMINI_MODEL = "gemini-2.0-flash"
_MAX_ITERATIONS = 20   # Splunk investigations need more tool calls than CI pipelines


class SplunkGuardAgent:
    """
    Investigates Splunk incidents using Gemini 2.0 Flash.

    Gemini drives a tool-call loop against the Splunk MCP Server, autonomously
    writing SPL queries, fetching results, and correlating across indexes until
    it identifies the root cause and remediation steps.
    """

    def __init__(
        self,
        gemini_api_key: str,
        splunk_mcp_endpoint: str,
        splunk_mcp_token: str,
        splunk_instance_label: str = "splunk",
    ) -> None:
        self._genai = genai.Client(api_key=gemini_api_key)
        self._endpoint = splunk_mcp_endpoint
        self._token = splunk_mcp_token
        self._instance = splunk_instance_label

    async def investigate(self, query: str, time_range: str = "-1h") -> IncidentReport:
        """Free-form investigation: describe what to look for in Splunk."""
        prompt = build_investigation_prompt(query, time_range)
        return await self._run(prompt, query)

    async def investigate_alert(
        self, alert_name: str, alert_spl: str, time_range: str = "-1h"
    ) -> IncidentReport:
        """Investigate a triggered Splunk alert by name and its SPL."""
        prompt = build_alert_prompt(alert_name, alert_spl, time_range)
        return await self._run(prompt, alert_name)

    async def _run(self, prompt: str, title_hint: str) -> IncidentReport:
        console.print(
            Panel(
                f"[bold cyan]SplunkGuard[/] investigating: [green]{title_hint}[/]\n"
                f"[dim]instance: {self._instance}[/]",
                border_style="cyan",
            )
        )
        async with SplunkMCPBackend(self._endpoint, self._token) as backend:
            tools = await backend.list_tools_as_gemini()
            messages: list[types.Content] = [
                types.Content(role="user", parts=[types.Part(text=prompt)])
            ]
            final_text = await self._tool_loop(backend, tools, messages)

        report = _parse_report(final_text, self._instance)
        if not report.title or report.title == "Untitled Incident":
            report.title = title_hint
        return report

    async def _tool_loop(
        self,
        backend: SplunkMCPBackend,
        tools: list[types.Tool],
        messages: list[types.Content],
    ) -> str:
        final_text = ""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Investigating…", total=None)

            for iteration in range(1, _MAX_ITERATIONS + 1):
                progress.update(task, description=f"Iteration {iteration}/{_MAX_ITERATIONS}…")

                response = self._genai.models.generate_content(
                    model=_GEMINI_MODEL,
                    contents=messages,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        tools=tools,
                        temperature=0.1,
                    ),
                )

                if not response.candidates:
                    logger.warning("Gemini returned no candidates — stopping loop")
                    break

                candidate = response.candidates[0]
                messages.append(candidate.content)

                tool_calls = [p.function_call for p in candidate.content.parts if p.function_call]
                text_parts = [p.text for p in candidate.content.parts if p.text]

                if text_parts:
                    final_text = "\n".join(text_parts)

                if not tool_calls:
                    break

                tool_responses: list[types.Part] = []
                for fc in tool_calls:
                    progress.update(task, description=f"→ {fc.name}(…)")
                    console.print(f"  [dim]→ {fc.name}({_fmt(dict(fc.args))})[/]")
                    result = await backend.call_tool(fc.name, dict(fc.args))
                    tool_responses.append(
                        types.Part(
                            function_response=types.FunctionResponse(
                                name=fc.name,
                                response={"output": result},
                            )
                        )
                    )
                messages.append(types.Content(role="tool", parts=tool_responses))

        return final_text


def _fmt(args: dict[str, Any]) -> str:
    s = json.dumps(args, default=str)
    return (s[:72] + "…") if len(s) > 72 else s


def _parse_report(text: str, splunk_instance: str) -> IncidentReport:
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        try:
            d = json.loads(match.group(1))
            components = [
                AffectedComponent(
                    name=c.get("name", ""),
                    component_type=c.get("component_type", "unknown"),
                    error_count=int(c.get("error_count", 0)),
                    first_seen=c.get("first_seen", ""),
                    last_seen=c.get("last_seen", ""),
                )
                for c in d.get("affected_components", [])
            ]
            steps = sorted(
                [
                    RemediationStep(
                        action=s.get("action", ""),
                        description=s.get("description", ""),
                        spl_query=s.get("spl_query", ""),
                        confidence=Confidence(s.get("confidence", "medium")),
                        priority=int(s.get("priority", 1)),
                    )
                    for s in d.get("remediation_steps", [])
                ],
                key=lambda s: s.priority,
            )
            return IncidentReport(
                title=d.get("title", "Untitled Incident"),
                severity=Severity(d.get("severity", "medium")),
                category=IncidentCategory(d.get("category", "unknown")),
                summary=d.get("summary", ""),
                root_cause=d.get("root_cause", ""),
                is_ongoing=bool(d.get("is_ongoing", True)),
                affected_components=components,
                remediation_steps=steps,
                key_spl_queries=d.get("key_spl_queries", []),
                full_analysis=text,
                splunk_instance=splunk_instance,
            )
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            logger.debug("Could not parse structured report: %s", exc)

    return IncidentReport(
        title="Incident Report",
        severity=Severity.MEDIUM,
        full_analysis=text,
        splunk_instance=splunk_instance,
    )
