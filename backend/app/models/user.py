"""User model and DTOs."""

from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field

from app.core.security import Roles
from app.models.base import MongoBaseModel


class User(MongoBaseModel):
    email: EmailStr
    name: str
    password_hash: str
    roles: List[str] = Field(default_factory=lambda: [Roles.DEVELOPER])
    whatsapp_number: Optional[str] = None  # E.164, e.g. +491701234567
    is_active: bool = True


class UserPublic(BaseModel):
    id: str
    email: EmailStr
    name: str
    roles: List[str]
    whatsapp_number: Optional[str] = None
    is_active: bool

    @classmethod
    def from_doc(cls, doc: dict) -> "UserPublic":
        return cls(
            id=doc["_id"],
            email=doc["email"],
            name=doc["name"],
            roles=doc.get("roles", []),
            whatsapp_number=doc.get("whatsapp_number"),
            is_active=doc.get("is_active", True),
        )


class UserCreate(BaseModel):
    email: EmailStr
    name: str
    password: str
    roles: Optional[List[str]] = None
    whatsapp_number: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic
