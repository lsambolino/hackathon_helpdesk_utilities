"""FastAPI app — REST endpoints for the helpdesk demo + static frontend."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.agents.coordinator import ChatReply, TriageResult, chat_turn, triage_ticket
from app.agents.forecast import forecast_zones
from app.db import conn_ctx, init_db, rows_to_list

# ---------- KPI assumptions (disclosed in the dashboard) ----------
HUMAN_AGENT_HOURLY_EUR = 25.0
HUMAN_HANDLE_TIME_MIN = 8.0
ESCALATED_TICKET_HUMAN_TIME_MIN = 5.0   # human time after agent triage
ANNUAL_TICKETS_ASSUMED = 100_000        # ~10% of customer base; conservative
COST_PER_AGENT_TICKET_EUR = 0.20        # API + infra amortized

ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT / "frontend"

app = FastAPI(title="Helpdesk Utilities — Agentic", version="0.1.0")


@app.on_event("startup")
def _ensure_db() -> None:
    init_db()


# ---------- request/response models ----------

class TicketSummary(BaseModel):
    id: int
    customer_id: int
    customer_name: str | None = None
    channel: str
    category: str | None
    subject: str
    status: str
    priority: str
    opened_at: str
    closed_at: str | None
    agent_handled: int
    confidence: float | None
    escalation_reason: str | None


class TicketDetail(TicketSummary):
    body: str
    resolution_summary: str | None
    comments: list[dict[str, Any]] = []
    audit_log: list[dict[str, Any]] = []


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    customer_id: int | None = None


# ---------- ticket endpoints ----------

@app.get("/api/tickets", response_model=list[TicketSummary])
def list_tickets(status: str | None = None, limit: int = 100):
    where = "WHERE t.status = ?" if status else ""
    params = (status,) if status else ()
    with conn_ctx() as c:
        rows = c.execute(
            "SELECT t.*, c.name AS customer_name FROM tickets t "
            "JOIN customers c ON c.id = t.customer_id "
            f"{where} ORDER BY t.opened_at DESC LIMIT ?",
            params + (limit,),
        ).fetchall()
    return rows_to_list(rows)


@app.get("/api/tickets/{ticket_id}", response_model=TicketDetail)
def get_ticket(ticket_id: int):
    with conn_ctx() as c:
        t = c.execute(
            "SELECT t.*, c.name AS customer_name FROM tickets t "
            "JOIN customers c ON c.id = t.customer_id WHERE t.id = ?",
            (ticket_id,),
        ).fetchone()
        if not t:
            raise HTTPException(404, f"ticket {ticket_id} not found")
        comments = c.execute(
            "SELECT id,author,body,created_at FROM comments WHERE ticket_id=? ORDER BY id",
            (ticket_id,),
        ).fetchall()
        audit = c.execute(
            "SELECT id,actor,action,detail,ts FROM audit_log WHERE ticket_id=? ORDER BY id",
            (ticket_id,),
        ).fetchall()
    out = dict(t)
    out["comments"] = rows_to_list(comments)
    out["audit_log"] = rows_to_list(audit)
    return out


@app.post("/api/tickets/{ticket_id}/triage", response_model=TriageResult)
async def triage(ticket_id: int):
    return await triage_ticket(ticket_id)


# ---------- chatbot endpoint ----------

@app.post("/api/chat", response_model=ChatReply)
async def chat(req: ChatRequest):
    return await chat_turn(req.message, req.session_id, req.customer_id)


# ---------- dashboard ----------

@app.get("/api/dashboard")
def dashboard():
    with conn_ctx() as c:
        # Counts
        total = c.execute("SELECT COUNT(*) AS n FROM tickets").fetchone()["n"]
        resolved = c.execute(
            "SELECT COUNT(*) AS n FROM tickets WHERE status IN ('resolved','closed')"
        ).fetchone()["n"]
        agent_handled = c.execute(
            "SELECT COUNT(*) AS n FROM tickets WHERE agent_handled=1"
        ).fetchone()["n"]
        escalated = c.execute(
            "SELECT COUNT(*) AS n FROM tickets WHERE status='escalated'"
        ).fetchone()["n"]

        # Last 7d
        last7 = (datetime.utcnow() - timedelta(days=7)).isoformat(timespec="seconds")
        last7d = c.execute(
            "SELECT COUNT(*) AS n FROM tickets WHERE opened_at >= ?", (last7,)
        ).fetchone()["n"]

        # By category last 30d
        last30 = (datetime.utcnow() - timedelta(days=30)).isoformat(timespec="seconds")
        by_cat_rows = c.execute(
            "SELECT COALESCE(category,'unclassified') AS category, COUNT(*) AS n "
            "FROM tickets WHERE opened_at >= ? GROUP BY category ORDER BY n DESC",
            (last30,),
        ).fetchall()

    # Derived KPIs
    auto_res_rate = round(100.0 * agent_handled / max(total, 1), 1)
    escalation_rate = round(100.0 * escalated / max(total, 1), 1)

    # Handle-time simulation: human baseline vs agent path
    # human full path = HUMAN_HANDLE_TIME_MIN per ticket
    # agent path: 0.4 min per auto-resolve + (HUMAN_HANDLE_TIME_MIN with -50% pre-triage discount) per escalation
    avg_human_min = HUMAN_HANDLE_TIME_MIN
    auto_share = agent_handled / max(total, 1)
    avg_agent_min = auto_share * 0.4 + (1 - auto_share) * (HUMAN_HANDLE_TIME_MIN * 0.5)
    handle_time_delta_pct = round(100.0 * (avg_human_min - avg_agent_min) / avg_human_min, 1)

    # Annualized economic savings (assumptions disclosed)
    cost_human_per_ticket = HUMAN_AGENT_HOURLY_EUR * (HUMAN_HANDLE_TIME_MIN / 60.0)
    cost_agent_per_ticket = (
        auto_share * COST_PER_AGENT_TICKET_EUR
        + (1 - auto_share) * (HUMAN_AGENT_HOURLY_EUR * (ESCALATED_TICKET_HUMAN_TIME_MIN / 60.0)
                              + COST_PER_AGENT_TICKET_EUR)
    )
    saving_per_ticket = cost_human_per_ticket - cost_agent_per_ticket
    annual_saving_eur = saving_per_ticket * ANNUAL_TICKETS_ASSUMED

    return {
        "kpis": {
            "total_tickets": total,
            "tickets_last_7d": last7d,
            "auto_resolution_rate_pct": auto_res_rate,
            "escalation_rate_pct": escalation_rate,
            "avg_human_handle_min": round(avg_human_min, 2),
            "avg_agent_handle_min": round(avg_agent_min, 2),
            "handle_time_reduction_pct": handle_time_delta_pct,
        },
        "savings": {
            "annual_tickets_assumed": ANNUAL_TICKETS_ASSUMED,
            "cost_per_ticket_human_eur": round(cost_human_per_ticket, 2),
            "cost_per_ticket_agent_eur": round(cost_agent_per_ticket, 2),
            "saving_per_ticket_eur": round(saving_per_ticket, 2),
            "annual_saving_eur": round(annual_saving_eur, 0),
            "annual_saving_eur_human_readable": f"€{annual_saving_eur:,.0f}",
            "assumptions": {
                "human_hourly_eur": HUMAN_AGENT_HOURLY_EUR,
                "human_handle_time_min": HUMAN_HANDLE_TIME_MIN,
                "escalated_human_time_min": ESCALATED_TICKET_HUMAN_TIME_MIN,
                "agent_cost_per_ticket_eur": COST_PER_AGENT_TICKET_EUR,
            },
        },
        "by_category": rows_to_list(by_cat_rows),
        "spike_forecast": forecast_zones(window_days=30),
    }


# ---------- static frontend ----------

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    def index():
        idx = FRONTEND_DIR / "index.html"
        if idx.exists():
            return FileResponse(idx)
        return {"status": "ok", "frontend": "missing"}

    @app.get("/{page}.html")
    def page(page: str):
        f = FRONTEND_DIR / f"{page}.html"
        if f.exists():
            return FileResponse(f)
        raise HTTPException(404, "page not found")
