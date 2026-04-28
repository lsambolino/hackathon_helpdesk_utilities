import json
import random
import httpx
from config import DATASET_URL


def load_dataset() -> list[dict]:
    """Download and return the complaints list from the shared dataset."""
    response = httpx.get(DATASET_URL, timeout=15)
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict):
        for key in ("complaints", "data", "records"):
            if key in data:
                return data[key]
        return list(data.values())[0] if data else []
    return data


def pick_scenario(dataset: list[dict], category: str | None = None) -> dict:
    pool = [s for s in dataset if s.get("category_label") == category] if category else dataset
    return random.choice(pool or dataset)


def build_persona(scenario: dict) -> dict:
    customer = scenario.get("customer", {})
    financials = scenario.get("financials", {})
    return {
        "customer_id": customer.get("customer_id", "USR-00001"),
        "name": customer.get("full_name", "Mario Rossi"),
        "email": customer.get("email", "mario.rossi@email.it"),
        "phone": customer.get("phone", "+39 02 12345678"),
        "address": customer.get("address", "Via Roma 1, Milano (MI)"),
        "complaint_id": scenario.get("complaint_id", "CMP-00001"),
        "category": scenario.get("category_label", "billing_issue"),
        "priority": scenario.get("priority", "medium"),
        "complaint_text": scenario.get("complaint_text", "Ho un problema con la bolletta."),
        "billed_amount": financials.get("billed_amount", None),
        "expected_amount": financials.get("expected_amount", None),
        "channel": scenario.get("channel", "chatbot"),
    }
