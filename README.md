# Helpdesk Utilities — Agentic Ticketing for an Italian Public Water Utility

> Hackathon submission, Scenario 5 (Agentic Solution).
> Built with the Claude Agent SDK. Status: in active development.

## Customer context (assumed)

A public-services water utility serving Lombardy, ~1M customers, B2C + B2B. The
existing IT ticketing system handles complaints across channels (email, phone,
chat, web): missing/incorrect bills, failed switches between providers, voltura
issues, leaks and outages, billing disputes.

## Goals

1. **Reduce ticket handle time** — measurable, double-digit improvement.
2. **Reduce cost** — fewer human-minutes per ticket → tariff headroom for the public utility.
3. **Forecast / prevention** — historical complaints surface spike risk by zone & category.
4. **Customer-facing chatbot** — resolves L1 issues, opens a ticket only when escalation is warranted.

## Architecture (one-liner)

A FastAPI backend serves a small ticketing UI and exposes REST endpoints. A
Coordinator agent (Claude Agent SDK) classifies each new ticket, hands off to a
specialist subagent (billing / switching / chatbot), which uses MCP tools that
read & write a SQLite database. Escalation to a human is gated by an explicit
policy (confidence, amount, vulnerable-customer, adversarial signals).

ADR with diagram: [`docs/adr/0001-architecture.md`](docs/adr/0001-architecture.md).

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-...

# 1. seed the demo database
python -m app.seed

# 2. start the backend
uvicorn app.main:app --reload --port 8080

# 3. open http://localhost:8080  (ticket list + dashboard + chatbot)

# 4. run the eval harness against the synthetic eval set
python -m evals.runner
```

## Status

| Waypoint | Status |
|---|---|
| The Mandate (scope + escalation rules) | _in progress_ |
| The Bones (architecture ADR) | _in progress_ |
| The Tools (4–5 per specialist) | _in progress_ |
| The Triage (coordinator + classification) | _in progress_ |
| The Brake (human-in-the-loop) | _in progress_ |
| The Attack (adversarial set) | _in progress_ |
| The Scorecard (eval metrics) | _in progress_ |
| The Loop (feedback retraining) | _skipped — out of scope for this timebox_ |

## Honest disclosures

- The DB is SQLite with synthetic Italian-flavored data. No real customer data is used.
- The "forecast / prevention" feature is rule-based (threshold over historical ticket counts), not ML. Pluggable: production version would use Prophet/ARIMA over a year of real complaint volume.
- The handle-time KPI is a simulation: human baseline is a fixed assumption (8 min/ticket) compared against measured agent path latency. Disclosed in the dashboard.
- The chatbot is a synchronous CLI/REST loop, not streaming.

## Team & roles

This README, the code, and the deliverables were built collaboratively — two
PCs, two human operators, Claude Code as the implementation partner. Roles
were not fixed; each operator drove direction interactively while Claude
implemented in parallel branches.

(Names of participants will be added before submission.)

## How Claude Code accelerated the work

- Generated the entire scaffold (FastAPI, SQLite schema, seed data) from a single design discussion.
- Spawned subagents in parallel for independent files (frontend, eval set, presentation), avoiding merge collisions on a 2-PC repo.
- Researched the Claude Agent SDK Python API (imports, tool/permission/structured-output patterns) and produced a working coordinator+specialist loop.
- Drafted the adversarial eval cases (prompt injection, false confidence) without manual brainstorming.
