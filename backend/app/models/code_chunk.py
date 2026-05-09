"""Indexed source-code chunks used for retrieval (RAG)."""

from typing import List, Optional

from pydantic import Field

from app.models.base import MongoBaseModel


class CodeChunk(MongoBaseModel):
    project_id: str
    path: str
    language: Optional[str] = None
    start_line: int = 1
    end_line: int = 1
    content: str
    embedding: List[float] = Field(default_factory=list)
    sha: Optional[str] = None
