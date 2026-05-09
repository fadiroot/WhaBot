"""Audit log endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.core.database import get_db
from app.core.security import Roles, require_roles

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
async def list_audit(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    project_id: Optional[str] = None,
    action: Optional[str] = None,
    user=Depends(require_roles(Roles.ADMIN, Roles.DEVELOPER)),
):
    db = get_db()
    q: dict = {}
    if project_id:
        q["project_id"] = project_id
    if action:
        q["action"] = action
    total = await db.audit_logs.count_documents(q)
    cursor = db.audit_logs.find(q).sort("created_at", -1).skip(offset).limit(limit)
    docs = await cursor.to_list(length=limit)
    for d in docs:
        d["id"] = d.pop("_id")
    return {
        "items": docs,
        "limit": limit,
        "offset": offset,
        "total": total,
        "has_more": offset + len(docs) < total,
    }
