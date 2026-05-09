"""Base Pydantic models with common helpers (timestamps, ids, etc.)."""

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid4().hex


class MongoBaseModel(BaseModel):
    """Base for documents stored in Mongo. Uses string ids (uuid4 hex)."""

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    id: str = Field(default_factory=_new_id, alias="_id")
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: Optional[datetime] = None

    def to_mongo(self) -> dict:
        return self.model_dump(by_alias=True, exclude_none=False)
