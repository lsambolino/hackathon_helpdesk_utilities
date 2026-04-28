"""Heuristic spike-risk forecast over historical tickets.

This is intentionally rule-based, not ML. The production version would
plug in Prophet/ARIMA against a year of complaint volume; here we ship
the API surface and a defensible heuristic.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.db import conn_ctx


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def forecast_zones(window_days: int = 30) -> list[dict[str, Any]]:
    """Compare the last `window_days/2` against the prior `window_days/2`
    per zone. If volume grew >25% and absolute count > threshold, flag."""
    half = window_days // 2
    now = datetime.utcnow()
    recent_start = now - timedelta(days=half)
    prior_start = now - timedelta(days=window_days)

    with conn_ctx() as c:
        rows = c.execute(
            "SELECT t.opened_at AS opened_at, c.zone AS zone, t.category AS category "
            "FROM tickets t JOIN customers c ON c.id = t.customer_id "
            "WHERE t.opened_at >= ?",
            (prior_start.isoformat(timespec="seconds"),),
        ).fetchall()

    by_zone_recent: dict[str, int] = {}
    by_zone_prior: dict[str, int] = {}
    for r in rows:
        ts = _parse(r["opened_at"])
        z = r["zone"]
        if ts >= recent_start:
            by_zone_recent[z] = by_zone_recent.get(z, 0) + 1
        else:
            by_zone_prior[z] = by_zone_prior.get(z, 0) + 1

    out: list[dict[str, Any]] = []
    for zone in sorted(set(by_zone_recent) | set(by_zone_prior)):
        rec = by_zone_recent.get(zone, 0)
        pri = by_zone_prior.get(zone, 0)
        growth = ((rec - pri) / pri * 100.0) if pri > 0 else (100.0 if rec > 0 else 0.0)
        risk = "low"
        if rec >= 3 and growth >= 50:
            risk = "high"
        elif rec >= 2 and growth >= 25:
            risk = "medium"
        out.append({
            "zone": zone,
            "recent_count": rec,
            "prior_count": pri,
            "growth_pct": round(growth, 1),
            "risk": risk,
        })
    out.sort(key=lambda x: ({"high": 0, "medium": 1, "low": 2}[x["risk"]], -x["recent_count"]))
    return out
