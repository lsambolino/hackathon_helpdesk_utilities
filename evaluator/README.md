# End-User Evaluator Agent

Standalone agent that simulates a real AcquaLombardia customer interacting with the hackathon chatbot and scores every conversation on **quality** and **timing**.

This component is completely independent of the main ticketing/agentic solution — it only needs an HTTP endpoint to call.

---

## What it does

1. Picks a random complaint from `hydric_complaints_backlog.json` (1 000 real scenarios)
2. Builds an Italian customer persona (name, address, customer ID, billing details)
3. Drives a multi-turn conversation against the chatbot endpoint
4. After the conversation ends, scores it:

| Dimension | Scale | Evaluated by |
|---|---|---|
| Quality | 1 (useless) → 5 (perfect resolution) | Claude LLM |
| Timing | 1 (>9 s/turn) → 5 (<1 s/turn) | measured HTTP latency |

5. Saves a JSON report in `results/`

---

## Quick start

```bash
cd evaluator
pip install -r requirements.txt
cp .env.example .env          # add your ANTHROPIC_API_KEY
```

### Run without API key (pipeline smoke-test)

```bash
PYTHONIOENCODING=utf-8 python main.py --mock --no-llm --n 3
```

### Run with Claude evaluation against mock chatbot

```bash
# .env must contain ANTHROPIC_API_KEY
PYTHONIOENCODING=utf-8 python main.py --mock --n 5
```

### Run against the real hackathon chatbot

```bash
# .env: set CHATBOT_ENDPOINT=http://<host>:<port>/chat
PYTHONIOENCODING=utf-8 python main.py --n 10
```

---

## CLI options

| Flag | Default | Description |
|---|---|---|
| `--mock` | off | Use built-in mock chatbot instead of real endpoint |
| `--no-llm` | off | Scripted customer turns, no API key needed |
| `--n N` | 5 | Number of scenarios to run |
| `--category CAT` | random | Filter by complaint category |
| `--quiet` | off | Suppress per-turn output |
| `--no-save` | off | Skip saving JSON report |

---

## Chatbot API contract

The evaluator sends:

```
POST /chat
Content-Type: application/json

{ "message": "...", "session_id": "uuid" }
```

And expects:

```json
{ "reply": "..." }
```

If the hackathon chatbot uses different field names, edit the two lines in `chatbot_client.py → HttpChatbotClient.send()`.

---

## File structure

```
evaluator/
├── main.py           # CLI entry point
├── agent.py          # Customer simulator (Claude) + quality evaluator (Claude)
├── chatbot_client.py # HTTP adapter + MockChatbotClient
├── scenarios.py      # Dataset loader + persona builder
├── report.py         # Terminal summary + JSON report
├── config.py         # All env-var config
├── requirements.txt
└── .env.example
```

---

## Output example

```
────────────────────────────────────────────────────────────
  Scenario: CMP-00124 | Refund Not Received
  Cliente:  Michelle Flores  (CUST-742108)
────────────────────────────────────────────────────────────
[CLIENTE] After switching provider I am owed a final credit...
[BOT]     (0.8s) Buongiorno, può fornirmi il codice cliente?
...
  QUALITÀ: ★★★★☆ (4/5)  |  TIMING: ★★★★★ (5/5)

════════════════════════════════════════════════════════════
  RIEPILOGO VALUTAZIONE CHATBOT — AcquaLombardia
  Scenari testati : 5
  Qualità media   : ★★★★☆  (3.80/5)
  Timing medio    : ★★★★★  (5.00/5)
════════════════════════════════════════════════════════════
```
