# SplunkGuard — Architecture

## Overview

SplunkGuard is an agentic AI system that connects **Gemini 2.0 Flash** to a live **Splunk** environment through the official **Splunk MCP Server**. The agent autonomously writes and executes SPL queries, correlates findings across indexes, and produces structured incident reports.

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        USER / ALERT TRIGGER                         │
│                                                                     │
│   splunkguard investigate "high error rate on payment service"      │
│   splunkguard alert "DB Connection Spike" "<SPL query>"             │
└───────────────────────────────────┬─────────────────────────────────┘
                                    │ natural language prompt
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    SplunkGuardAgent  (agent.py)                     │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              Gemini 2.0 Flash  (google-genai)               │   │
│  │                                                              │   │
│  │  System prompt: SPL expert + incident investigator           │   │
│  │  Temperature: 0.1  (deterministic, analytical)              │   │
│  │                                                              │   │
│  │  Each iteration:                                             │   │
│  │    1. Receive tool results from previous step               │   │
│  │    2. Decide next tool call(s) OR produce final report      │   │
│  │    3. Return: function_call(s) OR final text                │   │
│  └─────────────────────────────┬────────────────────────────────┘   │
│                                │ function_call {name, args}          │
│                                ▼                                    │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │            SplunkMCPBackend  (backends/mcp.py)              │   │
│  │                                                              │   │
│  │  - Converts MCP tool list → Gemini FunctionDeclaration[]    │   │
│  │  - Executes tool calls via MCP session                      │   │
│  │  - Returns text results back to Gemini                      │   │
│  └─────────────────────────────┬────────────────────────────────┘   │
└─────────────────────────────────┼───────────────────────────────────┘
                                  │ npx mcp-remote (stdio → HTTPS)
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     Splunk MCP Server (HTTPS)                       │
│                                                                     │
│  Auth: Encrypted Bearer token  (RBAC-enforced)                     │
│                                                                     │
│  splunk_run_query        Execute SPL searches                       │
│  saia_generate_spl       NL → SPL via Splunk AI Assistant           │
│  splunk_get_indexes      List available indexes                     │
│  splunk_get_metadata     Hosts / sources / sourcetypes              │
│  splunk_get_knowledge_objects   Saved searches + alerts             │
│  splunk_run_saved_search        Run existing saved searches         │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │ Splunk REST API
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Splunk Platform                             │
│                                                                     │
│   index=app       application logs, HTTP status codes              │
│   index=infra     host metrics, CPU / memory / disk                │
│   index=security  auth logs, network events                         │
│   ... any index the token's role can access                         │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    IncidentReport  (models.py)                      │
│                                                                     │
│  title · severity · category · summary · root_cause                 │
│  affected_components  →  name, type, error_count, timespan          │
│  remediation_steps    →  action, description, spl_verify, priority  │
│  key_spl_queries      →  reproducible SPL for the team              │
│  full_analysis        →  Gemini's full narrative reasoning          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Component Responsibilities

| Component | File | Responsibility |
|---|---|---|
| CLI entry point | `splunkguard/cli.py` | Argument parsing, rich terminal output |
| Agent orchestrator | `splunkguard/agent.py` | Gemini tool-call loop, report parsing |
| MCP backend | `splunkguard/backends/mcp.py` | MCP session, tool schema conversion |
| Data models | `splunkguard/models.py` | Typed incident report dataclasses |
| Prompts | `splunkguard/prompts.py` | System prompt, investigation prompts |

---

## AI Integration

| AI Capability | How Used |
|---|---|
| **Gemini 2.0 Flash** | Primary reasoning — writes SPL, interprets results, identifies root cause |
| **Gemini function calling** | Drives the agentic loop against Splunk MCP tools |
| **Splunk AI Assistant (`saia_`)** | `saia_generate_spl` converts natural language intent → valid SPL |
| **Structured output enforcement** | System prompt requires JSON schema for machine-readable reports |

---

## Security Model

- Splunk MCP Server enforces **RBAC** — agent accesses only indexes the token's role permits
- Encrypted MCP token is **context-bound**, cannot be reused outside MCP sessions
- All queries go through Splunk's **built-in read-only guardrails**
- No Splunk data leaves the environment — the agent reads only, never writes

---

## Hackathon Track

**Observability** — SplunkGuard helps engineering teams detect anomalies earlier and automate operational responses using AI.
