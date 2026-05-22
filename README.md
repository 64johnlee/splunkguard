# SplunkGuard

> AI-powered Splunk incident investigation using Gemini 2.0 Flash + Splunk MCP Server

SplunkGuard connects Gemini to your Splunk environment. When an incident occurs, it:

1. **Explores** available indexes and metadata via Splunk MCP tools
2. **Queries** Splunk autonomously — writing and executing SPL to surface patterns
3. **Correlates** across observability, security, and app indexes
4. **Reports** root cause, affected components, and prioritized remediation steps

Built for the [Splunk Agentic Ops Hackathon](https://splunk.devpost.com) — Observability track.

---

## Architecture

```
User / Alert Webhook
        │
        ▼
┌───────────────────────────────────────────────────────┐
│  SplunkGuardAgent  (splunkguard/agent.py)             │
│                                                       │
│  ┌────────────────────┐    ┌─────────────────────┐    │
│  │  Gemini 2.0 Flash  │◄──►│  Tool Call Loop     │    │
│  │  (google-genai)    │    │  (up to 20 iters)   │    │
│  └────────────────────┘    └──────────┬──────────┘    │
└─────────────────────────────────────── │ ─────────────┘
                                         │ MCP function calls
                                         ▼
                         ┌───────────────────────────┐
                         │  mcp-remote (npx proxy)   │
                         └──────────────┬────────────┘
                                        │ HTTPS
                                        ▼
                         ┌───────────────────────────┐
                         │  Splunk MCP Server        │
                         │                           │
                         │  splunk_run_query  (SPL)  │
                         │  saia_generate_spl        │
                         │  splunk_get_indexes       │
                         │  splunk_get_metadata      │
                         │  splunk_get_knowledge_    │
                         │    objects                │
                         │  splunk_run_saved_search  │
                         └───────────────────────────┘
                                        │
                                        ▼
                                 Splunk Platform
```

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/64johnlee/splunkguard
cd splunkguard
pip install -e .
```

Requires Node.js >=18 (for `mcp-remote`).

### 2. Configure

```bash
cp .env.example .env
# Fill in:
#   GEMINI_API_KEY         — https://aistudio.google.com/
#   SPLUNK_MCP_ENDPOINT    — from your Splunk MCP Server app
#   SPLUNK_MCP_TOKEN       — encrypted token from Splunk MCP Server app
```

**Getting your Splunk MCP endpoint and token:**
1. Install the Splunk MCP Server app on your Splunk instance
2. Navigate to the MCP Server app and copy the endpoint URL
3. Generate an encrypted token (requires `mcp_tool_admin` capability)

### 3. Investigate

```bash
# Natural language investigation
splunkguard investigate "high error rate on payment service in the last hour"

# Custom time range
splunkguard investigate "failed SSH logins from unusual IPs" --time-range -24h

# Investigate a triggered alert
splunkguard alert "High 5xx Rate" \
  "index=web status>=500 | stats count by host | where count > 100"
```

---

## Example Output

```
╭─ SplunkGuard · investigating: high error rate on payment service ─╮
│ instance: prod-splunk                                              │
╰────────────────────────────────────────────────────────────────────╯
  → splunk_get_indexes({})
  → splunk_get_metadata({"index": "app", "type": "sourcetype"})
  → splunk_run_query({"query": "index=app sourcetype=payment-api..."})
  → splunk_run_query({"query": "index=infra host=db-01 | stats..."})

╭─ SplunkGuard Incident Report ──────────────────────────────────────╮
│ DB Connection Pool Exhaustion — Payment API                        │
│                                                                    │
│ Severity: HIGH  Category: resource_exhaustion  Ongoing: yes        │
│                                                                    │
│ Root Cause: payment-api on web-02/web-03 exhausted the PostgreSQL  │
│ connection pool (max=100) due to a slow query introduced in        │
│ deploy v2.4.1 at 14:28 UTC.                                        │
╰────────────────────────────────────────────────────────────────────╯

Remediation Steps:
  1. Restart payment-api with DB_POOL_MAX=250 (high confidence)
  2. Kill long-running queries on db-01 (high confidence)
  3. Roll back deploy v2.4.1 (medium confidence)
```

---

## How It Works

**Gemini as the SPL author**: Instead of hardcoded queries, Gemini uses `saia_generate_spl` to write SPL from natural language and `splunk_run_query` to execute it, then decides what to query next. This gives it genuine investigative ability rather than template-matching.

**Multi-index correlation**: A real incident rarely lives in one index. SplunkGuard automatically correlates app logs, infrastructure metrics, and security events to distinguish application bugs from infrastructure failures from security threats.

**Structured output**: Every report is machine-readable — severity, category, affected components, ordered remediation steps — ready to feed into ticketing or Slack.

---

## Incident Categories

| Category | Example |
|---|---|
| `error_spike` | HTTP 5xx rate exceeded threshold |
| `latency_degradation` | p99 response time > 2s |
| `service_down` | Health check failures on all hosts |
| `security_threat` | Brute force, unusual access patterns |
| `resource_exhaustion` | OOM, disk full, connection pool |
| `data_pipeline_failure` | Indexing lag, forwarder down |
| `authentication_failure` | Repeated failed logins, token expiry |
| `network_anomaly` | Unexpected traffic patterns |

---

## Tech Stack

| Component | Library |
|---|---|
| LLM | Gemini 2.0 Flash via `google-genai` |
| Splunk tools | Splunk MCP Server + `mcp-remote` |
| MCP client | `mcp` (official Python SDK) |
| CLI | `click` + `rich` |

---

## License

MIT
