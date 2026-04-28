"""MCP tools — thin wrappers over SQLite for the Coordinator + specialists.

All tools follow the SDK contract: async, return
    {"content": [{"type": "text", "text": "..."}], "is_error": bool}

State changes go through `db.audit(...)` so the eval harness and the UI's
audit-log view can attribute every action to an actor.
"""
from __future__ import annotations

import json
from typing import Any

from claude_agent_sdk import tool, create_sdk_mcp_server

from app.db import audit, conn_ctx, now_iso


# ---------- helpers ----------

def _ok(payload: Any) -> dict[str, Any]:
    text = json.dumps(payload, ensure_ascii=False, default=str)
    return {"content": [{"type": "text", "text": text}], "is_error": False}


def _err(msg: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": f"ERROR: {msg}"}], "is_error": True}


# ============================================================
# COORDINATOR TOOLS
# ============================================================

@tool("tk_get_ticket", "Fetch a ticket with its customer and comments.", {"ticket_id": int})
async def tk_get_ticket(args: dict[str, Any]) -> dict[str, Any]:
    tid = args["ticket_id"]
    with conn_ctx() as c:
        t = c.execute("SELECT * FROM tickets WHERE id=?", (tid,)).fetchone()
        if not t:
            return _err(f"ticket {tid} not found")
        cust = c.execute("SELECT * FROM customers WHERE id=?", (t["customer_id"],)).fetchone()
        comments = c.execute(
            "SELECT author, body, created_at FROM comments WHERE ticket_id=? ORDER BY id", (tid,)
        ).fetchall()
        return _ok({
            "ticket": dict(t),
            "customer": dict(cust) if cust else None,
            "comments": [dict(x) for x in comments],
        })


@tool("tk_classify", "Record the coordinator's classification of a ticket.",
      {"ticket_id": int, "category": str, "confidence": float})
async def tk_classify(args: dict[str, Any]) -> dict[str, Any]:
    tid, cat, conf = args["ticket_id"], args["category"], float(args["confidence"])
    if cat not in ("billing", "switching", "outage", "general"):
        return _err(f"invalid category: {cat}")
    with conn_ctx() as c:
        c.execute("UPDATE tickets SET category=?, confidence=?, status='agent_handling' WHERE id=?",
                  (cat, conf, tid))
        audit(c, ticket_id=tid, actor="coordinator", action="classify",
              detail=f"category={cat} confidence={conf}")
    return _ok({"ticket_id": tid, "category": cat, "confidence": conf})


@tool("tk_escalate", "Escalate the ticket to a human reviewer with a reason.",
      {"ticket_id": int, "reason": str})
async def tk_escalate(args: dict[str, Any]) -> dict[str, Any]:
    tid, reason = args["ticket_id"], args["reason"]
    valid = ("low_confidence", "high_amount", "vulnerable_customer",
             "policy_exception", "adversarial", "specialist_failure")
    if reason not in valid:
        return _err(f"invalid escalation reason; expected one of {valid}")
    with conn_ctx() as c:
        c.execute("UPDATE tickets SET status='escalated', escalation_reason=? WHERE id=?",
                  (reason, tid))
        audit(c, ticket_id=tid, actor="coordinator", action="escalate", detail=reason)
    return _ok({"ticket_id": tid, "escalated": True, "reason": reason})


@tool("tk_mark_resolved", "Close a ticket as auto-resolved by the agent.",
      {"ticket_id": int, "summary": str})
async def tk_mark_resolved(args: dict[str, Any]) -> dict[str, Any]:
    tid, summary = args["ticket_id"], args["summary"]
    with conn_ctx() as c:
        c.execute(
            "UPDATE tickets SET status='resolved', closed_at=?, agent_handled=1, "
            "resolution_summary=? WHERE id=?",
            (now_iso(), summary, tid),
        )
        audit(c, ticket_id=tid, actor="coordinator", action="mark_resolved", detail=summary[:120])
    return _ok({"ticket_id": tid, "resolved": True})


@tool("tk_post_comment", "Post a comment on a ticket as a given actor.",
      {"ticket_id": int, "author": str, "body": str})
async def tk_post_comment(args: dict[str, Any]) -> dict[str, Any]:
    tid, author, body = args["ticket_id"], args["author"], args["body"]
    with conn_ctx() as c:
        c.execute(
            "INSERT INTO comments (ticket_id,author,body,created_at) VALUES (?,?,?,?)",
            (tid, author, body, now_iso()),
        )
    return _ok({"ticket_id": tid, "comment_posted": True})


COORDINATOR_TOOLS = [tk_get_ticket, tk_classify, tk_escalate, tk_mark_resolved, tk_post_comment]


# ============================================================
# BILLING SPECIALIST TOOLS
# ============================================================

@tool("bill_invoice_history", "List a customer's invoices, newest first.", {"customer_id": int})
async def bill_invoice_history(args: dict[str, Any]) -> dict[str, Any]:
    cid = args["customer_id"]
    with conn_ctx() as c:
        rows = c.execute(
            "SELECT id,period,amount_eur,status,issued_date,due_date "
            "FROM invoices WHERE customer_id=? ORDER BY issued_date DESC", (cid,)
        ).fetchall()
    return _ok([dict(r) for r in rows])


@tool("bill_find_disputed", "Find the customer's most relevant disputed/overdue invoice.",
      {"customer_id": int})
async def bill_find_disputed(args: dict[str, Any]) -> dict[str, Any]:
    cid = args["customer_id"]
    with conn_ctx() as c:
        row = c.execute(
            "SELECT * FROM invoices WHERE customer_id=? AND status IN ('disputed','overdue') "
            "ORDER BY issued_date DESC LIMIT 1", (cid,)
        ).fetchone()
    return _ok(dict(row) if row else None)


@tool("bill_check_payment", "Check current payment status of an invoice.", {"invoice_id": int})
async def bill_check_payment(args: dict[str, Any]) -> dict[str, Any]:
    iid = args["invoice_id"]
    with conn_ctx() as c:
        row = c.execute("SELECT id,status,amount_eur,due_date FROM invoices WHERE id=?", (iid,)).fetchone()
    if not row:
        return _err(f"invoice {iid} not found")
    return _ok(dict(row))


@tool("bill_request_rateizzazione",
      "Request an installment plan for an invoice (creates an audit entry; needs human approval if amount > 500).",
      {"customer_id": int, "invoice_id": int, "n_months": int})
async def bill_request_rateizzazione(args: dict[str, Any]) -> dict[str, Any]:
    cid, iid, n = args["customer_id"], args["invoice_id"], args["n_months"]
    if n < 2 or n > 24:
        return _err("n_months must be between 2 and 24")
    with conn_ctx() as c:
        inv = c.execute("SELECT amount_eur FROM invoices WHERE id=?", (iid,)).fetchone()
        if not inv:
            return _err("invoice not found")
        audit(c, ticket_id=None, actor="billing_agent", action="request_rateizzazione",
              detail=f"customer={cid} invoice={iid} n_months={n} amount={inv['amount_eur']}")
    return _ok({"requested": True, "amount_eur": inv["amount_eur"], "n_months": n,
                "needs_human_approval": inv["amount_eur"] > 500})


@tool("bill_draft_reply",
      "Draft an Italian customer reply for a billing ticket. Posts it as a comment.",
      {"ticket_id": int, "template": str, "params_json": str})
async def bill_draft_reply(args: dict[str, Any]) -> dict[str, Any]:
    tid = args["ticket_id"]
    tmpl = args["template"]
    try:
        params = json.loads(args.get("params_json") or "{}")
    except json.JSONDecodeError as e:
        return _err(f"params_json invalid: {e}")
    body = tmpl.format(**params) if params else tmpl
    with conn_ctx() as c:
        c.execute("INSERT INTO comments (ticket_id,author,body,created_at) VALUES (?,?,?,?)",
                  (tid, "billing_agent", body, now_iso()))
        audit(c, ticket_id=tid, actor="billing_agent", action="draft_reply", detail=body[:120])
    return _ok({"ticket_id": tid, "reply_posted": True})


BILLING_TOOLS = [bill_invoice_history, bill_find_disputed, bill_check_payment,
                 bill_request_rateizzazione, bill_draft_reply]


# ============================================================
# SWITCHING SPECIALIST TOOLS
# ============================================================

@tool("sw_get_request", "Get the customer's current/most-recent switch request.", {"customer_id": int})
async def sw_get_request(args: dict[str, Any]) -> dict[str, Any]:
    cid = args["customer_id"]
    with conn_ctx() as c:
        row = c.execute(
            "SELECT * FROM switches WHERE customer_id=? ORDER BY opened_at DESC LIMIT 1", (cid,)
        ).fetchone()
    return _ok(dict(row) if row else None)


@tool("sw_check_blockers",
      "Check which switch blockers apply to a customer (overdue invoices, contract lock, address mismatch).",
      {"customer_id": int})
async def sw_check_blockers(args: dict[str, Any]) -> dict[str, Any]:
    cid = args["customer_id"]
    blockers: list[dict[str, Any]] = []
    with conn_ctx() as c:
        overdue = c.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(amount_eur),0) AS total "
            "FROM invoices WHERE customer_id=? AND status='overdue'", (cid,)
        ).fetchone()
        if overdue and overdue["n"] > 0:
            blockers.append({"type": "unpaid_balance",
                             "detail": f"{overdue['n']} overdue invoices totalling €{overdue['total']:.2f}"})
        sw = c.execute(
            "SELECT * FROM switches WHERE customer_id=? AND status='blocked' ORDER BY opened_at DESC LIMIT 1",
            (cid,),
        ).fetchone()
        if sw and sw["blocker"] and sw["blocker"] not in [b["type"] for b in blockers]:
            blockers.append({"type": sw["blocker"], "detail": "registered on switch request"})
    return _ok({"customer_id": cid, "blockers": blockers, "blocked": len(blockers) > 0})


@tool("sw_query_provider", "Look up a provider by name. Returns canonical name + status.", {"provider_name": str})
async def sw_query_provider(args: dict[str, Any]) -> dict[str, Any]:
    name = (args["provider_name"] or "").strip().lower()
    known = {
        "acquasrl": ("AcquaSrl", "active"),
        "idroplus": ("IdroPlus SPA", "active"),
        "idroplus spa": ("IdroPlus SPA", "active"),
        "bluewater": ("BlueWater Italia", "active"),
        "bluewater italia": ("BlueWater Italia", "active"),
        "ecoidrica": ("EcoIdrica", "active"),
    }
    canonical = next((v for k, v in known.items() if k in name), None)
    if not canonical:
        return _ok({"found": False, "name": args["provider_name"]})
    return _ok({"found": True, "canonical": canonical[0], "status": canonical[1]})


@tool("sw_unblock_request",
      "Mark a blocked switch as ready-for-resubmit (records audit entry; human signs off).",
      {"switch_id": int, "reason": str})
async def sw_unblock_request(args: dict[str, Any]) -> dict[str, Any]:
    sid, reason = args["switch_id"], args["reason"]
    with conn_ctx() as c:
        sw = c.execute("SELECT id,status FROM switches WHERE id=?", (sid,)).fetchone()
        if not sw:
            return _err(f"switch {sid} not found")
        if sw["status"] != "blocked":
            return _err(f"switch {sid} status is {sw['status']}, not blocked")
        audit(c, ticket_id=None, actor="switching_agent", action="unblock_request_proposed",
              detail=f"switch={sid} reason={reason}")
    return _ok({"switch_id": sid, "needs_human_approval": True, "reason": reason})


@tool("sw_draft_reply",
      "Draft an Italian reply for a switching ticket. Posts it as a comment.",
      {"ticket_id": int, "template": str, "params_json": str})
async def sw_draft_reply(args: dict[str, Any]) -> dict[str, Any]:
    tid = args["ticket_id"]
    tmpl = args["template"]
    try:
        params = json.loads(args.get("params_json") or "{}")
    except json.JSONDecodeError as e:
        return _err(f"params_json invalid: {e}")
    body = tmpl.format(**params) if params else tmpl
    with conn_ctx() as c:
        c.execute("INSERT INTO comments (ticket_id,author,body,created_at) VALUES (?,?,?,?)",
                  (tid, "switching_agent", body, now_iso()))
        audit(c, ticket_id=tid, actor="switching_agent", action="draft_reply", detail=body[:120])
    return _ok({"ticket_id": tid, "reply_posted": True})


SWITCHING_TOOLS = [sw_get_request, sw_check_blockers, sw_query_provider,
                   sw_unblock_request, sw_draft_reply]


# ============================================================
# CHATBOT (END-USER) TOOLS
# ============================================================

@tool("kb_search", "Full-text-ish search of the knowledge base. Returns up to 3 matching articles.",
      {"query": str})
async def kb_search(args: dict[str, Any]) -> dict[str, Any]:
    q = (args["query"] or "").strip().lower()
    if not q:
        return _ok([])
    with conn_ctx() as c:
        rows = c.execute("SELECT id,title,body,tags FROM kb_articles").fetchall()
    scored = []
    for r in rows:
        hay = (r["title"] + " " + r["body"] + " " + (r["tags"] or "")).lower()
        score = sum(1 for tok in q.split() if tok in hay)
        if score > 0:
            scored.append((score, dict(r)))
    scored.sort(key=lambda x: -x[0])
    return _ok([s[1] for s in scored[:3]])


@tool("cust_account_summary",
      "Compact account snapshot for chatbot personalization: profile + bill status + open tickets.",
      {"customer_id": int})
async def cust_account_summary(args: dict[str, Any]) -> dict[str, Any]:
    cid = args["customer_id"]
    with conn_ctx() as c:
        cust = c.execute("SELECT id,type,name,zone,vulnerable FROM customers WHERE id=?", (cid,)).fetchone()
        if not cust:
            return _err(f"customer {cid} not found")
        bills = c.execute(
            "SELECT status, COUNT(*) AS n FROM invoices WHERE customer_id=? GROUP BY status", (cid,)
        ).fetchall()
        opens = c.execute(
            "SELECT id,subject,status FROM tickets WHERE customer_id=? AND status IN ('open','escalated','agent_handling') ORDER BY opened_at DESC LIMIT 5",
            (cid,),
        ).fetchall()
    return _ok({
        "customer": dict(cust),
        "bill_summary": {r["status"]: r["n"] for r in bills},
        "open_tickets": [dict(t) for t in opens],
    })


@tool("outage_check_zone", "Active outage info for a zone, if any.", {"zone": str})
async def outage_check_zone(args: dict[str, Any]) -> dict[str, Any]:
    zone = args["zone"]
    with conn_ctx() as c:
        row = c.execute(
            "SELECT zone,severity,description,started_at,ended_at FROM outages "
            "WHERE zone=? AND ended_at IS NULL ORDER BY started_at DESC LIMIT 1",
            (zone,),
        ).fetchone()
    return _ok(dict(row) if row else {"zone": zone, "active_outage": False})


@tool("chat_create_ticket",
      "Open a new ticket on behalf of a customer (escalation path from chatbot).",
      {"customer_id": int, "subject": str, "body": str, "channel": str, "priority": str})
async def chat_create_ticket(args: dict[str, Any]) -> dict[str, Any]:
    if args["channel"] not in ("email", "phone", "chat", "web"):
        return _err("invalid channel")
    if args["priority"] not in ("low", "medium", "high", "urgent"):
        return _err("invalid priority")
    with conn_ctx() as c:
        cur = c.execute(
            "INSERT INTO tickets (customer_id,channel,subject,body,status,priority,opened_at) "
            "VALUES (?,?,?,?,'open',?,?)",
            (args["customer_id"], args["channel"], args["subject"], args["body"],
             args["priority"], now_iso()),
        )
        tid = cur.lastrowid
        audit(c, ticket_id=tid, actor="chatbot", action="open_ticket",
              detail=f"customer={args['customer_id']} priority={args['priority']}")
    return _ok({"ticket_id": tid, "opened": True})


@tool("chat_suggest_self_service", "Return the body of a KB article to suggest as a self-service path.",
      {"article_id": int})
async def chat_suggest_self_service(args: dict[str, Any]) -> dict[str, Any]:
    aid = args["article_id"]
    with conn_ctx() as c:
        row = c.execute("SELECT id,title,body FROM kb_articles WHERE id=?", (aid,)).fetchone()
    if not row:
        return _err(f"article {aid} not found")
    return _ok(dict(row))


CHATBOT_TOOLS = [kb_search, cust_account_summary, outage_check_zone,
                 chat_create_ticket, chat_suggest_self_service]


# ============================================================
# MCP SERVERS (one per concern keeps tool names readable)
# ============================================================

ALL_TOOLS = COORDINATOR_TOOLS + BILLING_TOOLS + SWITCHING_TOOLS + CHATBOT_TOOLS

helpdesk_server = create_sdk_mcp_server(
    name="helpdesk",
    version="0.1.0",
    tools=ALL_TOOLS,
)


def tool_names(tools: list) -> list[str]:
    """Return the SDK-prefixed names (mcp__helpdesk__<name>) for allowed_tools listing."""
    return [f"mcp__helpdesk__{t.name if hasattr(t, 'name') else t.__name__}" for t in tools]
