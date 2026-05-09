"""Approval workflow: a sensitive action is paused until a human approves."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.core.database import get_db
from app.models.approval import Approval, ApprovalStatus


async def request_approval(
    *,
    action: str,
    summary: str,
    project_id: Optional[str] = None,
    task_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Approval:
    db = get_db()
    approval = Approval(
        action=action,
        summary=summary,
        project_id=project_id,
        task_id=task_id,
        payload=payload or {},
    )
    await db.approvals.insert_one(approval.to_mongo())
    return approval


async def decide_approval(
    approval_id: str,
    *,
    decision: ApprovalStatus,
    decided_by: str,
    note: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    db = get_db()
    res = await db.approvals.find_one_and_update(
        {"_id": approval_id, "status": ApprovalStatus.PENDING.value},
        {
            "$set": {
                "status": decision.value,
                "decided_by": decided_by,
                "decided_at": datetime.now(timezone.utc).isoformat(),
                "note": note,
            }
        },
        return_document=True,
    )
    return res
