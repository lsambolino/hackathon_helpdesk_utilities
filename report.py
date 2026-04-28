import json
import os
from datetime import datetime
from config import OUTPUT_DIR


def _stars(score: int, max_score: int = 5) -> str:
    return "★" * score + "☆" * (max_score - score)


def print_summary(results: list[dict]) -> None:
    if not results:
        print("Nessun risultato disponibile.")
        return

    quality_scores = [r["scores"]["quality_score"] for r in results]
    timing_scores = [r["scores"]["timing_score"] for r in results]
    avg_q = sum(quality_scores) / len(quality_scores)
    avg_t = sum(timing_scores) / len(timing_scores)

    print("\n" + "═" * 60)
    print("  RIEPILOGO VALUTAZIONE CHATBOT — AcquaLombardia")
    print("═" * 60)
    print(f"  Scenari testati : {len(results)}")
    print(f"  Qualità media   : {_stars(round(avg_q))}  ({avg_q:.2f}/5)")
    print(f"  Timing medio    : {_stars(round(avg_t))}  ({avg_t:.2f}/5)")
    print()

    for r in results:
        q = r["scores"]["quality_score"]
        t = r["scores"]["timing_score"]
        print(f"  [{r['scenario_id']}]  {r['category']}")
        print(f"    Qualità: {_stars(q)} ({q}/5)  |  Timing: {_stars(t)} ({t}/5)"
              f"  |  Turni: {r['total_turns']}  |  Latenza media: {r['avg_latency_s']:.1f}s")
        print(f"    {r['scores']['quality_reasoning']}")
        print()
    print("═" * 60)


def save_json(results: list[dict], label: str = "eval") -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(OUTPUT_DIR, f"{label}_{timestamp}.json")
    summary = {
        "generated_at": timestamp,
        "num_scenarios": len(results),
        "avg_quality_score": round(
            sum(r["scores"]["quality_score"] for r in results) / len(results), 2
        ) if results else 0,
        "avg_timing_score": round(
            sum(r["scores"]["timing_score"] for r in results) / len(results), 2
        ) if results else 0,
        "results": results,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n  Report salvato in: {path}")
    return path
