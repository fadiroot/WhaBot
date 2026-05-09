"""Audit log entries for sensitive operations."""

from typing import Any, Dict, Optional

from pydantic import Field

from app.models.base import MongoBaseModel


class AuditLog(MongoBaseModel):
    actor_id: Optional[str] = None  # user id, "system", or "ai-agent"
    actor_kind: str = "user"  # user | system | ai-agent
    action: str  # e.g. "git.push", "github.create_pr", "whatsapp.send"
    project_id: Optional[str] = None
    task_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    success: bool = True
    message: Optional[str] = None
