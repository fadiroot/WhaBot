"""Audit log helper."""

from typing import Any, Dict, Optional

from app.core.database import get_db
from app.models.audit import AuditLog


async def write_audit(
    *,
    action: str,
    actor_id: Optional[str] = None,
    actor_kind: str = "system",
    project_id: Optional[str] = None,
    task_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    success: bool = True,
    message: Optional[str] = None,
) -> str:
    db = get_db()
    entry = AuditLog(
        action=action,
        actor_id=actor_id,
        actor_kind=actor_kind,
        project_id=project_id,
        task_id=task_id,
        payload=payload or {},
        success=success,
        message=message,
    )
    await db.audit_logs.insert_one(entry.to_mongo())
    return entry.id
