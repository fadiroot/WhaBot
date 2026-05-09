"""Project (repository) model."""

from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.base import MongoBaseModel


class Project(MongoBaseModel):
    slug: str
    name: str
    description: Optional[str] = None
    repository_url: str  # e.g. https://github.com/org/repo.git
    provider: str = "github"  # github | gitlab | bitbucket
    default_branch: str = "main"

    # Mapping: which whatsapp chat IDs / numbers can talk to this project.
    allowed_whatsapp_chats: List[str] = Field(default_factory=list)
    # Members granted access to this project (user ids).
    member_ids: List[str] = Field(default_factory=list)

    # Per-project secrets (encrypted in production; here for MVP).
    github_token: Optional[str] = None

    # Indexing state
    last_indexed_at: Optional[str] = None
    indexed_files: int = 0


class ProjectCreate(BaseModel):
    slug: str
    name: str
    description: Optional[str] = None
    repository_url: str
    provider: str = "github"
    default_branch: str = "main"
    allowed_whatsapp_chats: List[str] = Field(default_factory=list)
    member_ids: List[str] = Field(default_factory=list)
    github_token: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    default_branch: Optional[str] = None
    allowed_whatsapp_chats: Optional[List[str]] = None
    member_ids: Optional[List[str]] = None
    github_token: Optional[str] = None


class ProjectPublic(BaseModel):
    id: str
    slug: str
    name: str
    description: Optional[str] = None
    repository_url: str
    provider: str
    default_branch: str
    allowed_whatsapp_chats: List[str]
    member_ids: List[str]
    indexed_files: int
    last_indexed_at: Optional[str] = None

    @classmethod
    def from_doc(cls, doc: dict) -> "ProjectPublic":
        return cls(
            id=doc["_id"],
            slug=doc["slug"],
            name=doc["name"],
            description=doc.get("description"),
            repository_url=doc["repository_url"],
            provider=doc.get("provider", "github"),
            default_branch=doc.get("default_branch", "main"),
            allowed_whatsapp_chats=doc.get("allowed_whatsapp_chats", []),
            member_ids=doc.get("member_ids", []),
            indexed_files=doc.get("indexed_files", 0),
            last_indexed_at=doc.get("last_indexed_at"),
        )
