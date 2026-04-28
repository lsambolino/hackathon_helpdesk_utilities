"""
Core evaluation loop.

Two Claude roles:
  1. CUSTOMER  — drives the conversation as a realistic Italian water-utility customer
  2. EVALUATOR — scores quality and timing after the conversation ends

Use no_llm=True in run_scenario() to bypass all Claude API calls (pipeline smoke-test).
"""
import json
import time
import uuid
import anthropic
from config import ANTHROPIC_API_KEY, MODEL, MAX_TURNS, TIMING_THRESHOLDS
from chatbot_client import ChatbotClient

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

# ── prompts ──────────────────────────────────────────────────────────────────

_CUSTOMER_SYSTEM = """\
Sei un cliente di AcquaLombardia, l'azienda idrica pubblica della Lombardia (Italia).
Stai usando il chatbot di supporto per risolvere un problema reale.

PROFILO:
{profile}

PROBLEMA:
{complaint}

REGOLE DI COMPORTAMENTO:
- Scrivi SOLO come cliente: risposte brevi (2-4 frasi), tono colloquiale italiano.
- Inizia subito descrivendo il problema, senza saluti prolissi.
- Se il bot ti chiede informazioni che hai nel profilo, forniscile.
- Se una risposta è vaga o non utile, insisti o chiedi spiegazioni.
- Se dopo 3 risposte non ottieni progressi concreti, chiedi di parlare con un operatore umano.
- Quando il problema è risolto (o escalato a umano), scrivi esattamente: [FINE CONVERSAZIONE]
- Non fingere di essere il bot. Non uscire mai dal personaggio.
"""

_EVALUATOR_SYSTEM = """\
Sei un esperto valutatore di chatbot per aziende di servizi pubblici idrici.
Analizza la conversazione completa tra cliente e chatbot e assegna due punteggi.

CRITERI QUALITÀ (1-5):
5 = Problema capito e risolto completamente, tono professionale, nessuna informazione sbagliata
4 = Buona comprensione, risoluzione quasi completa o correttamente escalata
3 = Risposta accettabile ma con lacune o imprecisioni minori
2 = Comprensione parziale, mancano informazioni chiave, non risolto
1 = Risposta irrilevante, sbagliata o il bot ha peggiorato la situazione

CRITERI TIMING (1-5) — basati sulla latenza media per turno:
5 = < 1 secondo
4 = 1–2.5 secondi
3 = 2.5–5 secondi
2 = 5–9 secondi
1 = > 9 secondi

Rispondi ESCLUSIVAMENTE con JSON valido (nessun testo extra):
{
  "quality_score": <int 1-5>,
  "quality_reasoning": "<max 2 frasi>",
  "timing_score": <int 1-5>,
  "timing_reasoning": "<max 1 frase con latenza media>"
}
"""

# ── helpers ───────────────────────────────────────────────────────────────────

def _timing_score(avg_latency: float) -> int:
    for i, threshold in enumerate(TIMING_THRESHOLDS):
        if avg_latency < threshold:
            return 5 - i
    return 1


def _format_profile(persona: dict) -> str:
    fields = ["customer_id", "name", "email", "phone", "address",
              "billed_amount", "expected_amount"]
    return "\n".join(f"  {k}: {persona[k]}" for k in fields if persona.get(k))


_SCRIPTED_FOLLOW_UPS = [
    "Non ho ancora ricevuto risposta. Può aggiornarmi sullo stato?",
    "Capisco, ma ho bisogno di una soluzione concreta il prima possibile.",
    "Grazie. Posso avere una conferma scritta via email?",
]

def _generate_customer_turn(system: str, history: list[dict]) -> str:
    if not _client:
        raise RuntimeError("ANTHROPIC_API_KEY non impostato. Usa --no-llm per la modalità senza API.")
    resp = _client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=system,
        messages=history,
    )
    return resp.content[0].text.strip()


def _scripted_customer_turn(complaint_text: str, turn_index: int) -> str:
    if turn_index == 0:
        return complaint_text
    idx = (turn_index - 1) % len(_SCRIPTED_FOLLOW_UPS)
    return _SCRIPTED_FOLLOW_UPS[idx]


def _evaluate(conversation: list[dict], avg_latency: float) -> dict:
    if not _client:
        raise RuntimeError("ANTHROPIC_API_KEY non impostato.")
    turns_text = "\n".join(
        f"CLIENTE: {t['customer']}\nBOT ({t['latency_s']:.1f}s): {t['bot']}"
        for t in conversation
    )
    prompt = f"CONVERSAZIONE:\n{turns_text}\n\nLatenza media: {avg_latency:.2f}s"
    resp = _client.messages.create(
        model=MODEL,
        max_tokens=400,
        system=_EVALUATOR_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].lstrip("json").strip()
    return json.loads(raw)


def _scripted_evaluate(avg_latency: float) -> dict:
    return {
        "quality_score": 3,
        "quality_reasoning": "[no-llm mode] Valutazione automatica non disponibile. Punteggio neutro assegnato.",
        "timing_score": _timing_score(avg_latency),
        "timing_reasoning": f"Latenza media misurata: {avg_latency:.2f}s",
    }


# ── public API ────────────────────────────────────────────────────────────────

def run_scenario(persona: dict, chatbot: ChatbotClient,
                 verbose: bool = True, no_llm: bool = False) -> dict:
    """
    Run one end-to-end evaluation for a single persona/complaint.

    no_llm=True  → scripted customer turns + fixed neutral quality score.
                   Use this to smoke-test the pipeline without an API key.
    """
    session_id = str(uuid.uuid4())
    system = _CUSTOMER_SYSTEM.format(
        profile=_format_profile(persona),
        complaint=persona["complaint_text"],
    )

    history: list[dict] = []
    conversation: list[dict] = []
    latencies: list[float] = []

    if verbose:
        mode_tag = " [no-llm]" if no_llm else ""
        print(f"\n{'─'*60}")
        print(f"  Scenario: {persona['complaint_id']} | {persona['category']}{mode_tag}")
        print(f"  Cliente:  {persona['name']}  ({persona['customer_id']})")
        print(f"{'─'*60}")

    scripted_turns = min(MAX_TURNS, len(_SCRIPTED_FOLLOW_UPS) + 1)
    turn_limit = scripted_turns if no_llm else MAX_TURNS

    for turn in range(turn_limit):
        # Customer speaks
        if no_llm:
            customer_msg = _scripted_customer_turn(persona["complaint_text"], turn)
        else:
            customer_msg = _generate_customer_turn(system, history)

        history.append({"role": "assistant", "content": customer_msg})
        if verbose:
            print(f"[CLIENTE] {customer_msg}")

        if "[FINE CONVERSAZIONE]" in customer_msg:
            break

        # Bot responds
        bot_reply, latency = chatbot.send(customer_msg, session_id)
        latencies.append(latency)
        history.append({"role": "user", "content": bot_reply})
        if verbose:
            print(f"[BOT]     ({latency:.1f}s) {bot_reply}")

        conversation.append({
            "turn": turn + 1,
            "customer": customer_msg,
            "bot": bot_reply,
            "latency_s": latency,
        })

    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

    scores = _scripted_evaluate(avg_latency) if no_llm else _evaluate(conversation, avg_latency)
    scores["timing_score"] = _timing_score(avg_latency)
    scores["avg_latency_s"] = round(avg_latency, 2)

    if verbose:
        q = scores["quality_score"]
        t = scores["timing_score"]
        print(f"\n  QUALITÀ: {'★' * q}{'☆' * (5-q)} ({q}/5)  |  TIMING: {'★' * t}{'☆' * (5-t)} ({t}/5)")
        print(f"  {scores['quality_reasoning']}")

    return {
        "scenario_id": persona["complaint_id"],
        "category": persona["category"],
        "persona_name": persona["name"],
        "total_turns": len(conversation),
        "avg_latency_s": avg_latency,
        "conversation": conversation,
        "scores": scores,
    }


def run_scenario_steps(persona: dict, chatbot: ChatbotClient, no_llm: bool = False):
    """
    Generator version of run_scenario for streaming UIs.

    Yields dicts:
      {"type": "customer", "text": ..., "turn": N}
      {"type": "bot",      "text": ..., "latency": float, "turn": N}
      {"type": "scores",   "scores": {...}, "conversation": [...]}
    """
    session_id = str(uuid.uuid4())
    system = _CUSTOMER_SYSTEM.format(
        profile=_format_profile(persona),
        complaint=persona["complaint_text"],
    )

    history: list[dict] = []
    conversation: list[dict] = []
    latencies: list[float] = []

    scripted_turns = min(MAX_TURNS, len(_SCRIPTED_FOLLOW_UPS) + 1)
    turn_limit = scripted_turns if no_llm else MAX_TURNS

    for turn in range(turn_limit):
        if no_llm:
            customer_msg = _scripted_customer_turn(persona["complaint_text"], turn)
        else:
            customer_msg = _generate_customer_turn(system, history)

        history.append({"role": "assistant", "content": customer_msg})
        yield {"type": "customer", "text": customer_msg, "turn": turn + 1}

        if "[FINE CONVERSAZIONE]" in customer_msg:
            break

        bot_reply, latency = chatbot.send(customer_msg, session_id)
        latencies.append(latency)
        history.append({"role": "user", "content": bot_reply})
        yield {"type": "bot", "text": bot_reply, "latency": latency, "turn": turn + 1}

        conversation.append({
            "turn": turn + 1,
            "customer": customer_msg,
            "bot": bot_reply,
            "latency_s": latency,
        })

    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    scores = _scripted_evaluate(avg_latency) if no_llm else _evaluate(conversation, avg_latency)
    scores["timing_score"] = _timing_score(avg_latency)
    scores["avg_latency_s"] = round(avg_latency, 2)

    yield {"type": "scores", "scores": scores, "conversation": conversation}
