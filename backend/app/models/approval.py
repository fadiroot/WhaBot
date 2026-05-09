"""Approval requests for sensitive operations (push, deploy, etc.)."""

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import Field

from app.models.base import MongoBaseModel


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class Approval(MongoBaseModel):
    project_id: Optional[str] = None
    task_id: Optional[str] = None
    requested_by: str = "ai-agent"
    action: str  # e.g. "git.push", "github.create_pr"
    summary: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    status: ApprovalStatus = ApprovalStatus.PENDING
    decided_by: Optional[str] = None
    decided_at: Optional[str] = None
    note: Optional[str] = None
