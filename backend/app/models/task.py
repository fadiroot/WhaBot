"""Engineering task model. Each WhatsApp request becomes a Task."""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.models.base import MongoBaseModel


class TaskStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    EXECUTING = "executing"
    AWAITING_APPROVAL = "awaiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskKind(str, Enum):
    CHAT = "chat"
    BUG_FIX = "bug_fix"
    FEATURE = "feature"
    SUMMARY = "summary"
    DEPLOY_DIAG = "deploy_diag"
    OTHER = "other"


class TaskStep(BaseModel):
    """Single tool invocation or assistant message step."""

    kind: str  # "assistant" | "tool_call" | "tool_result" | "system"
    name: Optional[str] = None
    content: Optional[str] = None
    arguments: Optional[Dict[str, Any]] = None
    output: Optional[str] = None
    created_at: str


class Task(MongoBaseModel):
    project_id: Optional[str] = None  # Resolved project (if any)
    requester_user_id: Optional[str] = None
    whatsapp_chat_id: Optional[str] = None
    whatsapp_number: Optional[str] = None
    request_text: str
    kind: TaskKind = TaskKind.CHAT
    status: TaskStatus = TaskStatus.PENDING
    steps: List[TaskStep] = Field(default_factory=list)
    result: Optional[str] = None
    error: Optional[str] = None
    pr_url: Optional[str] = None
    branch: Optional[str] = None
