"""WAHA (WhatsApp HTTP API) client.

Reference: https://waha.devlike.pro/
The Core (free) version provides REST endpoints under /api/* such as:

    POST /api/sendText                  { session, chatId, text }
    POST /api/sendImage                 { session, chatId, file: {...}, caption }
    GET  /api/sessions                  list sessions
    POST /api/sessions/{name}/start     start a session

We only use a small subset for sending messages and exposing a webhook listener.
"""

import time
from collections import defaultdict, deque
from typing import Any, Deque, Dict, Optional, Tuple

import httpx

from app.config import get_settings
from app.core.logger import logger

_RECENT_OUTBOUND_TTL_SECONDS = 90.0
_RECENT_OUTBOUND_MAX_PER_CHAT = 30
_recent_outbound_by_chat: dict[str, Deque[Tuple[float, str]]] = defaultdict(deque)


def _normalize_text(text: str) -> str:
    return (text or "").strip()


def remember_outbound_text(chat_id: str, text: str) -> None:
    """Remember outbound bot messages so webhook echo can be ignored safely."""
    if not chat_id:
        return
    now = time.monotonic()
    q = _recent_outbound_by_chat[chat_id]
    q.append((now, _normalize_text(text)))
    # Trim old entries and keep bounded memory.
    while q and (now - q[0][0] > _RECENT_OUTBOUND_TTL_SECONDS or len(q) > _RECENT_OUTBOUND_MAX_PER_CHAT):
        q.popleft()


def is_recent_outbound_echo(chat_id: str, text: str) -> bool:
    """True when webhook message text matches a recent outbound bot message."""
    q = _recent_outbound_by_chat.get(chat_id)
    if not q:
        return False
    now = time.monotonic()
    normalized = _normalize_text(text)
    # Drop expired entries first.
    while q and (now - q[0][0] > _RECENT_OUTBOUND_TTL_SECONDS):
        q.popleft()
    for _, sent_text in q:
        if sent_text and sent_text == normalized:
            return True
    return False


class WhatsAppClient:
    """Thin async client around the WAHA HTTP API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        session: Optional[str] = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.waha_base_url).rstrip("/")
        self.api_key = api_key or settings.waha_api_key
        self.session = session or settings.waha_session

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        return headers

    async def send_text(self, chat_id: str, text: str) -> Dict[str, Any]:
        """Send a plain-text WhatsApp message."""
        if not chat_id:
            raise ValueError("chat_id is required")
        url = f"{self.base_url}/api/sendText"
        payload = {"session": self.session, "chatId": chat_id, "text": text}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload, headers=self._headers())
        if resp.status_code >= 400:
            logger.error("WAHA sendText failed [{}]: {}", resp.status_code, resp.text)
            resp.raise_for_status()
        remember_outbound_text(chat_id, text)
        logger.info("WAHA -> {} | {} chars", chat_id, len(text))
        return resp.json() if resp.content else {}

    async def send_seen(self, chat_id: str) -> None:
        """Mark a chat as seen (best-effort)."""
        try:
            url = f"{self.base_url}/api/sendSeen"
            payload = {"session": self.session, "chatId": chat_id}
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(url, json=payload, headers=self._headers())
        except Exception as exc:  # noqa: BLE001
            logger.warning("WAHA sendSeen failed: {}", exc)

    async def start_typing(self, chat_id: str) -> None:
        try:
            url = f"{self.base_url}/api/startTyping"
            payload = {"session": self.session, "chatId": chat_id}
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(url, json=payload, headers=self._headers())
        except Exception as exc:  # noqa: BLE001
            logger.debug("WAHA startTyping failed: {}", exc)

    async def stop_typing(self, chat_id: str) -> None:
        try:
            url = f"{self.base_url}/api/stopTyping"
            payload = {"session": self.session, "chatId": chat_id}
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(url, json=payload, headers=self._headers())
        except Exception as exc:  # noqa: BLE001
            logger.debug("WAHA stopTyping failed: {}", exc)

    async def list_sessions(self) -> Any:
        url = f"{self.base_url}/api/sessions"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=self._headers())
        resp.raise_for_status()
        return resp.json()


_default_client: Optional[WhatsAppClient] = None


def get_whatsapp_client() -> WhatsAppClient:
    global _default_client
    if _default_client is None:
        _default_client = WhatsAppClient()
    return _default_client
