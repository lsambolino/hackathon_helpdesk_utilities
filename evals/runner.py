"""Eval harness — runs the coordinator over the synthetic + adversarial sets
and produces a report with classification accuracy, action accuracy, false-
confidence rate, adversarial-pass rate, and a simulated handle-time delta.

Usage:
    python -m evals.runner            # mock mode (no API key)
    python -m evals.runner --live     # uses Claude Agent SDK with ANTHROPIC_API_KEY

Writes evals/report.json and prints a summary table.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app.agents.coordinator import triage_ticket
from app.db import conn_ctx, init_db, now_iso

EVAL_DIR = Path(__file__).resolve().parent
ROOT = EVAL_DIR.parent
REPORT_PATH = EVAL_DIR / "report.json"

EVAL_SET_PATH = EVAL_DIR / "eval_set.json"
ADVERSARIAL_PATH = EVAL_DIR / "adversarial.json"


def load_cases() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    eval_cases = json.loads(EVAL_SET_PATH.read_text(encoding="utf-8"))
    adv_cases = json.loads(ADVERSARIAL_PATH.read_text(encoding="utf-8"))
    return eval_cases, adv_cases


def _ensure_customer(c, name: str, *, vulnerable: int = 0, b2b: bool = False) -> int:
    row = c.execute("SELECT id FROM customers WHERE name=?", (name,)).fetchone()
    if row:
        return row["id"]
    if b2b:
        cur = c.execute(
            "INSERT INTO customers (type,name,vat_id,zone,email) VALUES ('B2B',?,?,?,?)",
            (name, "IT00000000000", "Milano-Centro", "b2b@example.it"),
        )
    else:
        cur = c.execute(
            "INSERT INTO customers (type,name,address,zone,email,vulnerable) "
            "VALUES ('B2C',?,?,?,?,?)",
            (name, "Synthetic eval", "Milano-Centro", "eval@example.it", vulnerable),
        )
    return cur.lastrowid


def _insert_case(c, case: dict[str, Any]) -> int:
    if case.get("expected_escalation_reason") == "vulnerable_customer":
        cust_id = _ensure_customer(c, "__EVAL_VULNERABLE__", vulnerable=1)
    elif case.get("customer_type") == "B2B":
        cust_id = _ensure_customer(c, "__EVAL_B2B__", b2b=True)
    else:
        cust_id = _ensure_customer(c, "__EVAL_CUSTOMER__")
    cur = c.execute(
        "INSERT INTO tickets (customer_id,channel,subject,body,status,priority,opened_at) "
        "VALUES (?,?,?,?,'open','medium',?)",
        (cust_id, case["channel"], case["subject"], case["body"], now_iso()),
    )
    return cur.lastrowid


async def run(live: bool = False) -> dict[str, Any]:
    eval_cases, adv_cases = load_cases()
    init_db()

    case_tickets: list[tuple[dict[str, Any], int, str]] = []
    with conn_ctx() as c:
        for case in eval_cases:
            tid = _insert_case(c, case)
            case_tickets.append((case, tid, "eval"))
        for case in adv_cases:
            tid = _insert_case(c, case)
            case_tickets.append((case, tid, "adversarial"))

    results: list[dict[str, Any]] = []
    for case, tid, kind in case_tickets:
        t0 = time.time()
        try:
            tr = await triage_ticket(tid, mock=not live)
            elapsed = time.time() - t0
            predicted_action = (
                "escalate" if tr.action == "escalated"
                else "auto_resolve" if tr.action == "resolved"
                else "in_progress"
            )
            results.append({
                "case_id": case["id"],
                "kind": kind,
                "ticket_id": tid,
                "true_category": case.get("true_category"),
                "predicted_category": tr.category,
                "expected_action": case.get("expected_action"),
                "predicted_action": predicted_action,
                "expected_escalation_reason": case.get("expected_escalation_reason"),
                "predicted_escalation_reason": tr.escalation_reason,
                "confidence": tr.confidence,
                "elapsed_seconds": round(elapsed, 3),
                "tools_used": tr.tools_used,
                "attack_type": case.get("attack_type"),
            })
        except Exception as e:
            results.append({
                "case_id": case["id"], "kind": kind, "ticket_id": tid,
                "error": str(e), "elapsed_seconds": round(time.time() - t0, 3),
            })

    return _summarize(results, live=live)


def _summarize(results: list[dict[str, Any]], *, live: bool) -> dict[str, Any]:
    eval_results = [r for r in results if r.get("kind") == "eval" and "error" not in r]
    adv_results = [r for r in results if r.get("kind") == "adversarial" and "error" not in r]

    cls_correct = sum(1 for r in eval_results if r["true_category"] == r["predicted_category"])
    cls_total = len(eval_results)
    cls_accuracy = round(100.0 * cls_correct / max(cls_total, 1), 1)

    act_correct = sum(1 for r in eval_results if r["expected_action"] == r["predicted_action"])
    act_accuracy = round(100.0 * act_correct / max(cls_total, 1), 1)

    false_conf = sum(
        1 for r in eval_results
        if r["expected_action"] == "escalate" and r["predicted_action"] == "auto_resolve"
    )
    fc_denom = sum(1 for r in eval_results if r["expected_action"] == "escalate")
    false_conf_rate = round(100.0 * false_conf / max(fc_denom, 1), 1)

    over_esc = sum(
        1 for r in eval_results
        if r["expected_action"] == "auto_resolve" and r["predicted_action"] == "escalate"
    )
    oe_denom = sum(1 for r in eval_results if r["expected_action"] == "auto_resolve")
    over_esc_rate = round(100.0 * over_esc / max(oe_denom, 1), 1)

    adv_caught = sum(1 for r in adv_results if r["predicted_action"] == "escalate")
    adv_total = len(adv_results)
    adv_pass_rate = round(100.0 * adv_caught / max(adv_total, 1), 1)

    eval_latencies = [r["elapsed_seconds"] for r in eval_results]
    avg_latency = round(statistics.mean(eval_latencies), 3) if eval_latencies else 0.0

    HUMAN_MIN = 8.0
    auto_share = (
        sum(1 for r in eval_results if r["predicted_action"] == "auto_resolve") / max(cls_total, 1)
    )
    avg_agent_min = auto_share * 0.4 + (1 - auto_share) * (HUMAN_MIN * 0.5)
    handle_delta_pct = round(100.0 * (HUMAN_MIN - avg_agent_min) / HUMAN_MIN, 1)

    return {
        "mode": "live" if live else "mock",
        "generated_at": datetime.utcnow().isoformat(timespec="seconds"),
        "totals": {"eval_cases": cls_total, "adversarial_cases": adv_total},
        "metrics": {
            "classification_accuracy_pct": cls_accuracy,
            "action_accuracy_pct": act_accuracy,
            "false_confidence_rate_pct": false_conf_rate,
            "over_escalation_rate_pct": over_esc_rate,
            "adversarial_pass_rate_pct": adv_pass_rate,
            "avg_latency_seconds": avg_latency,
            "auto_resolution_share_pct": round(100.0 * auto_share, 1),
            "simulated_human_handle_min": HUMAN_MIN,
            "simulated_agent_handle_min": round(avg_agent_min, 2),
            "handle_time_reduction_pct": handle_delta_pct,
        },
        "details": results,
    }


def _print_summary(summary: dict[str, Any]) -> None:
    m = summary["metrics"]
    t = summary["totals"]
    print()
    print("─" * 64)
    print(f" Eval mode: {summary['mode']}    cases: {t['eval_cases']} eval / {t['adversarial_cases']} adv")
    print("─" * 64)
    print(f"  Classification accuracy : {m['classification_accuracy_pct']:6.1f}%")
    print(f"  Action accuracy         : {m['action_accuracy_pct']:6.1f}%")
    print(f"  False-confidence rate   : {m['false_confidence_rate_pct']:6.1f}%   (lower is better)")
    print(f"  Over-escalation rate    : {m['over_escalation_rate_pct']:6.1f}%   (lower is better)")
    print(f"  Adversarial pass rate   : {m['adversarial_pass_rate_pct']:6.1f}%   (target 100%)")
    print(f"  Avg latency / ticket    : {m['avg_latency_seconds']:6.3f}s")
    print(f"  Auto-resolution share   : {m['auto_resolution_share_pct']:6.1f}%")
    print()
    print(f"  Simulated handle time   : human {m['simulated_human_handle_min']} min  →  "
          f"agent {m['simulated_agent_handle_min']} min")
    print(f"                            reduction: {m['handle_time_reduction_pct']}%")
    print("─" * 64)
    print(f"  Report written to {REPORT_PATH.relative_to(ROOT)}")
    print()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--live", action="store_true",
                   help="Use the real Claude Agent SDK (requires ANTHROPIC_API_KEY).")
    args = p.parse_args()

    if args.live and not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: --live requires ANTHROPIC_API_KEY in env. Falling back to mock.")
        args.live = False

    summary = asyncio.run(run(live=args.live))
    REPORT_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    _print_summary(summary)


if __name__ == "__main__":
    main()
