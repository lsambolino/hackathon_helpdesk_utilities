"""
Adapter layer for calling the hackathon chatbot.

Set CHATBOT_ENDPOINT in .env to point at the real chatbot.
Use MockChatbotClient during development / CI to test the evaluator itself.
"""
import time
import uuid
import httpx
from config import CHATBOT_ENDPOINT


class ChatbotClient:
    def send(self, message: str, session_id: str) -> tuple[str, float]:
        """Return (reply_text, latency_seconds)."""
        raise NotImplementedError


class HttpChatbotClient(ChatbotClient):
    """
    Calls a REST endpoint.

    Expected request:  POST /chat  { "message": "...", "session_id": "..." }
    Expected response: { "reply": "..." }   (or plain text)

    Adapt the payload/response parsing below if the hackathon team uses a
    different contract.
    """

    def __init__(self, endpoint: str = CHATBOT_ENDPOINT, timeout: float = 30.0):
        self.endpoint = endpoint
        self.timeout = timeout

    def send(self, message: str, session_id: str) -> tuple[str, float]:
        payload = {"message": message, "session_id": session_id}
        t0 = time.perf_counter()
        resp = httpx.post(self.endpoint, json=payload, timeout=self.timeout)
        latency = time.perf_counter() - t0
        resp.raise_for_status()
        body = resp.json()
        if isinstance(body, dict):
            reply = body.get("reply") or body.get("message") or body.get("response") or str(body)
        else:
            reply = str(body)
        return reply, latency


class MockChatbotClient(ChatbotClient):
    """Deterministic stub — use when the real chatbot is not yet available."""

    CANNED = [
        "Grazie per averci contattato. Può fornirmi il suo codice cliente?",
        "Ho verificato il suo account. Risulta un'anomalia sulla lettura del contatore del mese scorso.",
        "Il problema è stato registrato nel sistema. Riceverà una conferma via email entro 24 ore.",
        "Se il problema persiste, la metterò in contatto con un operatore umano specializzato.",
        "Posso aprire un ticket di assistenza prioritaria per lei. Conferma?",
    ]

    def __init__(self, latency: float = 1.2):
        self._latency = latency
        self._counter: dict[str, int] = {}

    def send(self, message: str, session_id: str) -> tuple[str, float]:
        idx = self._counter.get(session_id, 0)
        reply = self.CANNED[idx % len(self.CANNED)]
        self._counter[session_id] = idx + 1
        time.sleep(self._latency)
        return reply, self._latency


def get_client(mock: bool = False) -> ChatbotClient:
    return MockChatbotClient() if mock else HttpChatbotClient()
