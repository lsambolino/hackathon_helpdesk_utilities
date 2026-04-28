"""Summary stats over the 1000-entry historical complaints backlog.

The dataset (`hydric_complaints_backlog.json`) is contributed by the parallel
data work; we treat it as a read-only knowledge corpus that powers richer
forecasting and a "historical insights" panel on the dashboard.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
HISTORICAL_PATH = ROOT / "hydric_complaints_backlog.json"


@lru_cache(maxsize=1)
def _load() -> list[dict[str, Any]]:
    if not HISTORICAL_PATH.exists():
        return []
    blob = json.loads(HISTORICAL_PATH.read_text(encoding="utf-8"))
    return blob.get("complaints", []) if isinstance(blob, dict) else []


def _zone_from_address(addr: str | None) -> str | None:
    if not addr:
        return None
    parts = addr.rsplit(",", 1)
    return parts[1].strip() if len(parts) == 2 else None


def _resolution_days(c: dict[str, Any]) -> int | None:
    try:
        created = datetime.fromisoformat(c["created_date"])
        updated = datetime.fromisoformat(c["last_updated_date"])
        return max(0, (updated - created).days)
    except (KeyError, ValueError, TypeError):
        return None


def summarize() -> dict[str, Any]:
    """Compute headline KPIs for the historical backlog. Returns an empty
    summary if the dataset is not present (file optional)."""
    rows = _load()
    if not rows:
        return {"available": False}

    cat_counter = Counter(c.get("category_label") for c in rows)
    chan_counter = Counter(c.get("channel") for c in rows)
    zones = [_zone_from_address(c.get("customer", {}).get("address")) for c in rows]
    zone_counter = Counter(z for z in zones if z)

    csat_scores = [c["satisfaction_score"] for c in rows
                   if isinstance(c.get("satisfaction_score"), (int, float))]
    avg_csat = round(mean(csat_scores), 2) if csat_scores else None

    disputed_total = sum(
        (c.get("financials") or {}).get("disputed_amount", 0) or 0 for c in rows
    )
    billed_total = sum(
        (c.get("financials") or {}).get("billed_amount", 0) or 0 for c in rows
    )

    res_days = [d for d in (_resolution_days(c) for c in rows) if d is not None]
    avg_res_days = round(mean(res_days), 1) if res_days else None

    return {
        "available": True,
        "total_complaints": len(rows),
        "avg_csat_score": avg_csat,                # 1-5 scale
        "avg_resolution_days": avg_res_days,
        "disputed_amount_eur_total": round(disputed_total, 2),
        "billed_amount_eur_total": round(billed_total, 2),
        "top_categories": [
            {"category": k, "count": v} for k, v in cat_counter.most_common(5)
        ],
        "channels": [
            {"channel": k, "count": v} for k, v in chan_counter.most_common()
        ],
        "top_zones": [
            {"zone": k, "count": v} for k, v in zone_counter.most_common(8)
        ],
    }
