"""Project (repository) management endpoints."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from app.core.database import get_db
from app.core.security import Roles, get_current_user, require_roles
from app.models.project import Project, ProjectCreate, ProjectPublic, ProjectUpdate
from app.services.repo_indexer import RepoIndexer

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("")
async def list_projects(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user=Depends(get_current_user),
):
    db = get_db()
    total = await db.projects.count_documents({})
    cursor = db.projects.find({}).skip(offset).limit(limit)
    docs = await cursor.to_list(length=limit)
    items = [ProjectPublic.from_doc(d).model_dump() for d in docs]
    return {
        "items": items,
        "limit": limit,
        "offset": offset,
        "total": total,
        "has_more": offset + len(items) < total,
    }


@router.post("", response_model=ProjectPublic)
async def create_project(payload: ProjectCreate, user=Depends(require_roles(Roles.ADMIN, Roles.DEVELOPER))):
    db = get_db()
    if await db.projects.find_one({"slug": payload.slug}):
        raise HTTPException(status_code=400, detail="slug already exists")
    member_ids = list(set(payload.member_ids) | {user["_id"]})
    project = Project(**{**payload.model_dump(), "member_ids": member_ids})
    await db.projects.insert_one(project.to_mongo())
    return ProjectPublic.from_doc(project.to_mongo())


@router.get("/{slug}", response_model=ProjectPublic)
async def get_project(slug: str, user=Depends(get_current_user)):
    db = get_db()
    doc = await db.projects.find_one({"slug": slug})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    return ProjectPublic.from_doc(doc)


@router.patch("/{slug}", response_model=ProjectPublic)
async def update_project(slug: str, payload: ProjectUpdate, user=Depends(require_roles(Roles.ADMIN, Roles.DEVELOPER))):
    db = get_db()
    doc = await db.projects.find_one({"slug": slug})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if updates:
        await db.projects.update_one({"_id": doc["_id"]}, {"$set": updates})
    doc = await db.projects.find_one({"_id": doc["_id"]})
    return ProjectPublic.from_doc(doc)


@router.delete("/{slug}")
async def delete_project(slug: str, user=Depends(require_roles(Roles.ADMIN))):
    db = get_db()
    res = await db.projects.delete_one({"slug": slug})
    return {"deleted": res.deleted_count}


@router.post("/{slug}/index")
async def reindex_project(slug: str, background: BackgroundTasks, user=Depends(require_roles(Roles.ADMIN, Roles.DEVELOPER))):
    db = get_db()
    doc = await db.projects.find_one({"slug": slug})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    indexer = RepoIndexer(
        project_id=doc["_id"],
        project_slug=doc["slug"],
        repo_url=doc["repository_url"],
        default_branch=doc.get("default_branch", "main"),
        github_token=doc.get("github_token"),
    )
    background.add_task(indexer.index)
    return {"queued": True}


@router.get("/{slug}/search")
async def search_project(slug: str, q: str, k: int = 8, user=Depends(get_current_user)):
    db = get_db()
    doc = await db.projects.find_one({"slug": slug})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    indexer = RepoIndexer(
        project_id=doc["_id"],
        project_slug=doc["slug"],
        repo_url=doc["repository_url"],
        default_branch=doc.get("default_branch", "main"),
        github_token=doc.get("github_token"),
    )
    results = await indexer.search(q, k=k)
    return {"results": results}
