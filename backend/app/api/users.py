"""User management."""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.database import get_db
from app.core.security import Roles, get_current_user, hash_password, require_roles
from app.models.user import User, UserCreate, UserPublic

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
async def list_users(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user=Depends(require_roles(Roles.ADMIN)),
):
    db = get_db()
    total = await db.users.count_documents({})
    docs = await db.users.find({}).skip(offset).limit(limit).to_list(length=limit)
    items = [UserPublic.from_doc(d).model_dump() for d in docs]
    return {
        "items": items,
        "limit": limit,
        "offset": offset,
        "total": total,
        "has_more": offset + len(items) < total,
    }


@router.post("", response_model=UserPublic)
async def create_user(payload: UserCreate, user=Depends(require_roles(Roles.ADMIN))):
    db = get_db()
    if await db.users.find_one({"email": payload.email}):
        raise HTTPException(400, "email already exists")
    new_user = User(
        email=payload.email,
        name=payload.name,
        password_hash=hash_password(payload.password),
        roles=payload.roles or [Roles.DEVELOPER],
        whatsapp_number=payload.whatsapp_number,
    )
    await db.users.insert_one(new_user.to_mongo())
    return UserPublic.from_doc(new_user.to_mongo())


@router.delete("/{user_id}")
async def delete_user(user_id: str, user=Depends(require_roles(Roles.ADMIN))):
    db = get_db()
    if user_id == user["_id"]:
        raise HTTPException(400, "cannot delete yourself")
    res = await db.users.delete_one({"_id": user_id})
    return {"deleted": res.deleted_count}
