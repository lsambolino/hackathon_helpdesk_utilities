# ADR 0001 — Architecture

**Status:** Accepted (hackathon scope). 2026-04-28.

## Context

Italian public water utility, Lombardy, ~1M customers, mixed B2C + B2B. Daily
ticket volume in production is in the hundreds; complaints cluster around
billing (missed/incorrect bills, IVA errors, conguagli), provider switch
(voltura, switch blocked by morosità), and operational disservizi (leaks,
pressure, outages). Current process is fully human and the customer wants a
double-digit reduction in handle time, plus a chatbot that absorbs L1 traffic.

## Decision

Build a single FastAPI process that:

1. Stores tickets, customers, invoices, switches, KB articles, outages, and an
   audit log in a local SQLite database.
2. Serves a minimal HTML/JS UI with three views: ticket list/detail, dashboard
   (KPIs + spike forecast), chatbot.
3. Embeds a **Coordinator** agent (Claude Agent SDK) that classifies each new
   ticket, decides whether to delegate, escalate, or auto-close.
4. Delegates to one of three **specialist subagents** — `billing`, `switching`,
   `chatbot` — each with 4–5 narrow MCP tools backed by SQLite.
5. Gates dangerous tools (refunds, contract changes, large amounts) behind a
   permission callback that enforces explicit escalation rules.
6. Ships an **eval harness** with a synthetic ground-truth set + adversarial
   cases, reporting accuracy / auto-resolution rate / handle-time delta /
   adversarial-pass / false-confidence rate.

```
┌──────────────────────────────────────┐
│  Browser (vanilla HTML+JS, no deps)  │
│  /tickets   /chat   /dash            │
└─────────────────┬────────────────────┘
                  │ fetch
┌─────────────────▼────────────────────┐
│  FastAPI app  (app/main.py)          │
│  - REST: /api/tickets, /api/chat ... │
│  - Static mount /frontend            │
│  - Calls Agent SDK in-process        │
└──────┬──────────────────────┬────────┘
       │                      │
┌──────▼──────┐   ┌───────────▼─────────────┐
│  SQLite     │   │  Claude Agent SDK       │
│  helpdesk.db│   │  ┌──────────────────┐   │
│             │   │  │   COORDINATOR    │   │
│ customers   │   │  │  classify+route  │   │
│ invoices    │   │  └─┬─────┬────┬─────┘   │
│ switches    │   │    │     │    │         │
│ tickets     │   │  ┌─▼─┐ ┌─▼─┐ ┌▼─────┐   │
│ comments    │   │  │BIL│ │SW │ │CHATBOT│  │
│ kb_articles │   │  └───┘ └───┘ └──────┘   │
│ outages     │   │   ↑ tools = SQLite + KB │
│ audit_log   │   └─────────────────────────┘
└─────────────┘
```

## Why these choices

**SQLite over JSON files.** Real schema, real indexes, real transactions —
buys credibility on the "could ops deploy this Monday?" rubric for ~10 lines
more code. Production swap-target is Postgres with the same DDL.

**FastAPI over Flask.** Native async means the Agent SDK (also async) integrates
without thread-pool awkwardness. Pydantic models double as SDK structured-output
schemas.

**Plain HTML + fetch over a frontend framework.** A judge can `git clone && pip install && uvicorn` in 60 seconds. Adding a build step would burn time we don't have without changing the demo's substance.

**1 coordinator + 3 specialists** instead of one giant prompt. Each specialist
has narrow context, narrow tools, and a small system prompt — easier to evaluate
in isolation, and matches the brief's "coordinator + specialist split" rubric.

**Rule-based forecasting, not ML.** A trained model isn't deployable in two
hours and a heuristic over historical ticket counts gives a defensible MVP.
Documented as pluggable.

## Escalation rules (enforced in coordinator's permission callback)

Escalate to human if any of:

- `confidence < 0.75`
- monetary action > €500
- customer flagged `vulnerable = 1`
- adversarial pattern detected (prompt injection, instruction override, role-play attack)
- specialist returned `is_error: True` twice in a row on the same ticket

## Out of scope (deliberate non-automation)

- Anything touching real customer data or production systems.
- Authentication / multi-tenancy / RBAC.
- Streaming chatbot UX (websockets); request/response is enough for the demo.
- "The Loop" — feedback retraining mechanism. Listed as future work.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Two PCs writing to same files → merge conflicts | Disjoint subtrees; frequent commits; this branch is `feat/agentic-scaffold` until merge. |
| `ANTHROPIC_API_KEY` not provisioned in time | Eval harness has a `--mock` flag that returns canned model outputs so the architecture is demonstrable offline. |
| Synthetic data makes the KPI claim feel constructed | We disclose the assumption (8 min/ticket human baseline) explicitly in README and dashboard. |
