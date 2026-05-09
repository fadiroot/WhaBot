"""WAHA webhook receiver.

WAHA sends events as JSON like:
{
  "event": "message",
  "session": "default",
  "payload": {
    "id": "true_xxxxx",
    "from": "1234567890@c.us",
    "fromMe": false,
    "body": "Fix login refresh bug",
    "hasMedia": false,
    "timestamp": 1731000000,
    "_data": {...}
  }
}
See: https://waha.devlike.pro/docs/how-to/webhooks/
"""

from __future__ import annotations

import re
import time
from collections import deque
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from app.config import get_settings
from app.core.database import get_db
from app.core.logger import logger
from app.models.approval import ApprovalStatus
from app.models.task import Task, TaskKind, TaskStatus
from app.services.approval_service import decide_approval
from app.services.audit_service import write_audit
from app.services.project_resolver import resolve_project
from app.services.whatsapp import get_whatsapp_client, is_recent_outbound_echo
from app.agents.orchestrator import run_agent

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


_APPROVE_RE = re.compile(r"^\s*(approve|reject)\s+([a-fA-F0-9\-]{6,})\s*$", re.IGNORECASE)
_RECENT_EVENT_TTL_SECONDS = 120.0
_RECENT_EVENT_MAX = 500
_recent_event_ids: deque[tuple[float, str]] = deque()
_recent_event_id_set: set[str] = set()


def _phone_from_chat_id(chat_id: str) -> str:
    # WAHA chat ids look like '1234567890@c.us' for users.
    if "@" in chat_id:
        return "+" + chat_id.split("@", 1)[0]
    return chat_id


def _extract_message_id(payload: Dict[str, Any]) -> Optional[str]:
    mid = payload.get("id")
    if isinstance(mid, str) and mid.strip():
        return mid.strip()
    if isinstance(mid, dict):
        s = mid.get("_serialized")
        if isinstance(s, str) and s.strip():
            return s.strip()
    data = payload.get("_data")
    if isinstance(data, dict):
        did = data.get("id")
        if isinstance(did, dict):
            s = did.get("_serialized")
            if isinstance(s, str) and s.strip():
                return s.strip()
    return None


def _seen_recent_message_id(message_id: Optional[str]) -> bool:
    if not message_id:
        return False
    now = time.monotonic()
    while _recent_event_ids and (now - _recent_event_ids[0][0] > _RECENT_EVENT_TTL_SECONDS):
        _, old_id = _recent_event_ids.popleft()
        _recent_event_id_set.discard(old_id)
    if message_id in _recent_event_id_set:
        return True
    _recent_event_ids.append((now, message_id))
    _recent_event_id_set.add(message_id)
    while len(_recent_event_ids) > _RECENT_EVENT_MAX:
        _, old_id = _recent_event_ids.popleft()
        _recent_event_id_set.discard(old_id)
    return False


@router.post("/waha")
async def waha_webhook(
    request: Request,
    background: BackgroundTasks,
    x_webhook_secret: Optional[str] = Header(default=None, alias="X-Webhook-Secret"),
):
    settings = get_settings()
    if settings.waha_webhook_secret and x_webhook_secret != settings.waha_webhook_secret:
        raise HTTPException(401, "Bad webhook secret")

    body: Dict[str, Any] = await request.json()
    event = body.get("event")
    payload = body.get("payload") or {}

    if event not in {"message", "message.any"}:
        # Ignore non-message events (status updates, etc.)
        return {"ignored": True, "event": event}

    chat_id = payload.get("from") or payload.get("chatId")
    text = (payload.get("body") or "").strip()
    if not chat_id or not text:
        return {"ignored": True, "reason": "missing chatId or body"}
    from_me = bool(payload.get("fromMe"))
    if from_me and not settings.waha_accept_from_me:
        return {"ignored": True, "reason": "fromMe"}
    if from_me and "@lid" in chat_id:
        # WEBJS can emit self echoes on LID chats; never treat those as user requests.
        return {"ignored": True, "reason": "self_lid_echo"}
    if _seen_recent_message_id(_extract_message_id(payload)):
        return {"ignored": True, "reason": "duplicate_message"}
    if from_me and is_recent_outbound_echo(chat_id, text):
        # Prevent feedback loops when WAHA re-emits bot outbound messages.
        return {"ignored": True, "reason": "bot_echo"}

    logger.info("WhatsApp <- {}: {}", chat_id, text[:100])
    background.add_task(_handle_incoming, chat_id=chat_id, text=text)
    return {"received": True}


async def _handle_incoming(chat_id: str, text: str) -> None:
    db = get_db()
    wa = get_whatsapp_client()
    phone = _phone_from_chat_id(chat_id)

    # --- approval shortcut: "approve <id>" / "reject <id>" --------------
    m = _APPROVE_RE.match(text)
    if m:
        verb = m.group(1).lower()
        approval_id_partial = m.group(2)
        # Allow short prefix matching by lookup
        approval = await db.approvals.find_one(
            {"_id": {"$regex": f"^{re.escape(approval_id_partial)}"}},
        )
        if not approval:
            await wa.send_text(chat_id, f"Approval `{approval_id_partial}` not found.")
            return
        # Find the requester user (by phone) for audit
        user = await db.users.find_one({"whatsapp_number": phone})
        actor_id = user["_id"] if user else f"wa:{phone}"
        if user and "admin" not in user.get("roles", []):
            await wa.send_text(chat_id, "Only admins can decide approvals.")
            return
        decision = ApprovalStatus.APPROVED if verb == "approve" else ApprovalStatus.REJECTED
        updated = await decide_approval(approval["_id"], decision=decision, decided_by=actor_id, note="via whatsapp")
        await write_audit(
            action=f"approval.{verb}",
            actor_id=actor_id,
            actor_kind="user",
            project_id=approval.get("project_id"),
            task_id=approval.get("task_id"),
            payload={"approval_id": approval["_id"], "via": "whatsapp"},
        )
        if decision == ApprovalStatus.APPROVED:
            # Execute the approved action.
            from app.api.approvals import _execute_approved  # local import to avoid cycle

            result = await _execute_approved(updated or approval)
            await wa.send_text(chat_id, f"Approved `{approval['_id'][:8]}`. {result}")
        else:
            await wa.send_text(chat_id, f"Rejected `{approval['_id'][:8]}`.")
        return

    # --- normal request -> create task & run agent ----------------------
    project, cleaned = await resolve_project(text, chat_id, phone)
    user = await db.users.find_one({"whatsapp_number": phone})
    task = Task(
        request_text=cleaned or text,
        project_id=(project or {}).get("_id"),
        whatsapp_chat_id=chat_id,
        whatsapp_number=phone,
        requester_user_id=(user or {}).get("_id"),
        kind=TaskKind.CHAT,
        status=TaskStatus.PENDING,
    )
    await db.tasks.insert_one(task.to_mongo())
    await write_audit(
        action="whatsapp.message_received",
        actor_id=(user or {}).get("_id") or f"wa:{phone}",
        actor_kind="user",
        project_id=task.project_id,
        task_id=task.id,
        payload={"text": text[:500]},
    )

    try:
        await wa.start_typing(chat_id)
    except Exception:  # noqa: BLE001
        pass

    try:
        result = await run_agent(
            task_id=task.id,
            request_text=cleaned or text,
            project=project,
        )
        msg = result["final_message"]
    except Exception as exc:  # noqa: BLE001
        logger.exception("Agent failed: {}", exc)
        msg = f"Sorry, I hit an error: {exc}"
        await db.tasks.update_one(
            {"_id": task.id},
            {"$set": {"status": TaskStatus.FAILED.value, "error": str(exc), "result": msg}},
        )

    try:
        await wa.stop_typing(chat_id)
    except Exception:  # noqa: BLE001
        pass

    try:
        await wa.send_text(chat_id, msg)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to reply on WhatsApp: {}", exc)
