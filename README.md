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

# 1. seed the demo database
python -m app.seed

# 2. start the backend
uvicorn app.main:app --reload --port 8080

# 3. open http://localhost:8080  (ticket list + dashboard + chatbot)

# 4. run the eval harness against the synthetic eval set
python -m evals.runner            # mock mode (no credentials needed)
python -m evals.runner --live     # uses the SDK against the configured provider
```

### Picking a model provider

The Agent SDK is provider-agnostic. Pick one of:

**A) Anthropic API**
```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

**B) AWS Bedrock** (verified working in this hackathon — `us.anthropic.claude-sonnet-4-6` in `us-east-1`)
```bash
export CLAUDE_CODE_USE_BEDROCK=1
export AWS_REGION=us-east-1
export AWS_PROFILE=<profile-with-bedrock-access>     # any profile from ~/.aws/credentials
# (optional) override the model:
# export HELPDESK_MODEL=us.anthropic.claude-sonnet-4-6
```

Bedrock prerequisites: model access must be enabled once in the AWS console
(Bedrock → Model access → Anthropic Claude Sonnet 4.6) and the IAM role must
allow `bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream`.

For a quick sanity check before running the full eval:
```bash
AWS_PROFILE=... AWS_REGION=us-east-1 CLAUDE_CODE_USE_BEDROCK=1 \
  python -m scripts.probe_bedrock
```

Quick health check before running the full eval:
```bash
python -m scripts.probe_bedrock
```

If neither provider is configured, the demo still runs end-to-end in **mock mode**: a deterministic keyword-based classifier short-circuits the SDK call so the dashboard, chatbot, and eval all produce realistic numbers.

## Status

| Waypoint | Status |
|---|---|
| The Mandate (scope + escalation rules) | ✅ done — see `docs/adr/0001-architecture.md` |
| The Bones (architecture ADR) | ✅ done |
| The Tools (4–5 per specialist) | ✅ done — 20 MCP tools across coordinator + 3 specialists |
| The Triage (coordinator + classification) | ✅ done — classify → route → resolve/escalate |
| The Brake (human-in-the-loop) | ✅ done — `can_use_tool` callback + 6 escalation rules |
| The Attack (adversarial set) | ✅ done — 10 adversarial cases, 100% pass rate |
| The Scorecard (eval metrics) | ✅ done — `evals/runner.py`, writes `evals/report.json` |
| The Loop (feedback retraining) | ⏭️ skipped — listed as future work |

## Eval results (mock mode)

```
Classification accuracy : 77.5%
Action accuracy         : 75.0%
False-confidence rate   :  6.7%   (lower is better)
Adversarial pass rate   : 100.0%  (target 100%)
Auto-resolution share   : 42.5%
Handle-time reduction   : 69.1%   (human 8.0 min → agent 2.47 min)
```

Mock mode runs without an Anthropic API key; live mode (`python -m evals.runner --live`) uses the real Agent SDK and is expected to match or exceed the mock floor on adversarial detection thanks to model judgment.

## Economic impact (annualized)

Conservative assumption: 100,000 tickets/year (≈10% of 1M customers, lower bound for the Italian water sector).

| Item | Value |
|---|---|
| Cost / ticket — human path | **€3.33** (8 min × €25/h fully loaded) |
| Cost / ticket — agent path | **€1.58** (mix of auto-resolved + agent-pre-triaged escalation) |
| Saving / ticket | **€1.76** |
| **Annual direct opex saving** | **≈ €175,500/year** |
| For a public regulated utility | flows into **tariff headroom** under ARERA |

Assumptions are exposed live by `GET /api/dashboard` so the dashboard, presentation, and README always cite the same numbers.

## Honest disclosures

- The DB is SQLite with synthetic Italian-flavored data. No real customer data is used.
- The "forecast / prevention" feature is rule-based (threshold over historical ticket counts), not ML. Pluggable: production version would use Prophet/ARIMA over a year of real complaint volume.
- The handle-time KPI is a simulation: human baseline is a fixed assumption (8 min/ticket) compared against measured agent path latency. Disclosed in the dashboard.
- The chatbot is a synchronous CLI/REST loop, not streaming.

## Historical backlog (parallel data work)

A 1,000-entry synthetic complaints dataset (`hydric_complaints_backlog.json`) was contributed in parallel by another team member and merged into this branch. It powers a separate "historical insights" panel on the dashboard and gives the presentation defensible baseline numbers:

| Metric (1,000 closed complaints) | Value |
|---|---|
| Average time to resolution | **189 days** |
| Average CSAT | **3.45 / 5** |
| Total disputed amount | **€233,686** |
| Top category | Provider Switch — error / incomplete transfer (124 cases) |

The agentic solution moves "average time to resolution" from 189 days to <1 day for auto-resolved categories and reduces backlog buildup for the rest. This is the *narrative* benefit on top of the €175K direct opex saving.

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
