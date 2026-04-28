"""
End-User Simulator & Evaluator for AcquaLombardia Chatbot

Usage:
    python main.py --mock --no-llm         # full pipeline, no API key needed
    python main.py --mock                  # mock chatbot + Claude evaluation
    python main.py                         # real chatbot + Claude evaluation
    python main.py --n 10 --category billing_issue
    python main.py --mock --no-save --quiet
"""
import argparse
import sys

# Force UTF-8 output on Windows to handle Italian accented characters
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from scenarios import load_dataset, pick_scenario, build_persona
from chatbot_client import get_client
from agent import run_scenario
from report import print_summary, save_json
from config import NUM_SCENARIOS, ANTHROPIC_API_KEY


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AcquaLombardia chatbot evaluator")
    p.add_argument("--mock", action="store_true",
                   help="Use mock chatbot instead of real endpoint")
    p.add_argument("--no-llm", action="store_true",
                   help="Scripted customer turns + fixed scoring (no API key needed)")
    p.add_argument("--n", type=int, default=NUM_SCENARIOS,
                   help="Number of scenarios to run")
    p.add_argument("--category", type=str, default=None,
                   help="Filter scenarios by category (e.g. billing_issue)")
    p.add_argument("--no-save", action="store_true",
                   help="Skip saving JSON report")
    p.add_argument("--quiet", action="store_true",
                   help="Suppress per-turn output")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if not args.no_llm and not ANTHROPIC_API_KEY:
        print("ERRORE: ANTHROPIC_API_KEY non impostato.")
        print("  → Aggiungi la chiave nel file .env  oppure usa --no-llm per la modalità senza API.")
        sys.exit(1)

    print("Caricamento dataset scenari...")
    try:
        dataset = load_dataset()
    except Exception as e:
        print(f"Errore nel caricamento del dataset: {e}")
        sys.exit(1)
    print(f"  {len(dataset)} scenari disponibili.")

    chatbot = get_client(mock=args.mock)
    mode_parts = []
    if args.mock:
        mode_parts.append("chatbot MOCK")
    if args.no_llm:
        mode_parts.append("cliente SCRIPTED (no API)")
    if not mode_parts:
        mode_parts.append("chatbot REALE + Claude")
    print(f"  Modalità: {' | '.join(mode_parts)}")

    results = []
    for i in range(args.n):
        print(f"\n[{i+1}/{args.n}] Seleziono scenario...")
        scenario = pick_scenario(dataset, category=args.category)
        persona = build_persona(scenario)
        try:
            result = run_scenario(persona, chatbot,
                                  verbose=not args.quiet,
                                  no_llm=args.no_llm)
            results.append(result)
        except Exception as e:
            print(f"  Errore nello scenario {persona['complaint_id']}: {e}")

    print_summary(results)

    if not args.no_save and results:
        save_json(results)


if __name__ == "__main__":
    main()
