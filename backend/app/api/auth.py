"""Authentication endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm

from app.core.database import get_db
from app.core.security import (
    Roles,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.models.user import TokenResponse, User, UserCreate, UserPublic

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserPublic)
async def register(payload: UserCreate):
    db = get_db()
    existing = await db.users.find_one({"email": payload.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    is_first = (await db.users.estimated_document_count()) == 0
    roles = payload.roles or ([Roles.ADMIN] if is_first else [Roles.DEVELOPER])

    user = User(
        email=payload.email,
        name=payload.name,
        password_hash=hash_password(payload.password),
        roles=roles,
        whatsapp_number=payload.whatsapp_number,
    )
    await db.users.insert_one(user.to_mongo())
    return UserPublic.from_doc(user.to_mongo())


@router.post("/login", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends()):
    db = get_db()
    user = await db.users.find_one({"email": form.username})
    if not user or not verify_password(form.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="User disabled")
    token = create_access_token(subject=user["_id"], extra={"roles": user.get("roles", [])})
    return TokenResponse(access_token=token, user=UserPublic.from_doc(user))


@router.get("/me", response_model=UserPublic)
async def me(user=Depends(get_current_user)):
    return UserPublic.from_doc(user)
