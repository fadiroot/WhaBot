"""Task endpoints — list/inspect AI engineering tasks."""

from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.task import Task, TaskKind, TaskStatus
from app.services.project_resolver import resolve_project
from app.agents.orchestrator import run_agent

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskCreate(BaseModel):
    request_text: str
    project_slug: Optional[str] = None


@router.get("")
async def list_tasks(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: Optional[TaskStatus] = None,
    user=Depends(get_current_user),
):
    db = get_db()
    q: dict = {}
    if status:
        q["status"] = status.value
    total = await db.tasks.count_documents(q)
    cursor = db.tasks.find(q).sort("created_at", -1).skip(offset).limit(limit)
    docs = await cursor.to_list(length=limit)
    for d in docs:
        d["id"] = d.pop("_id")
    return {
        "items": docs,
        "limit": limit,
        "offset": offset,
        "total": total,
        "has_more": offset + len(docs) < total,
    }


@router.get("/{task_id}")
async def get_task(task_id: str, user=Depends(get_current_user)):
    db = get_db()
    doc = await db.tasks.find_one({"_id": task_id})
    if not doc:
        raise HTTPException(404, "Not found")
    doc["id"] = doc.pop("_id")
    return doc


async def _run_task_bg(task_id: str, request_text: str, project: Optional[dict]):
    await run_agent(task_id=task_id, request_text=request_text, project=project)


@router.post("")
async def create_task(payload: TaskCreate, background: BackgroundTasks, user=Depends(get_current_user)):
    db = get_db()
    project = None
    cleaned_text = payload.request_text
    if payload.project_slug:
        project = await db.projects.find_one({"slug": payload.project_slug})
    else:
        project, cleaned_text = await resolve_project(payload.request_text, None, user.get("whatsapp_number"))

    task = Task(
        request_text=cleaned_text,
        project_id=(project or {}).get("_id"),
        requester_user_id=user["_id"],
        kind=TaskKind.CHAT,
        status=TaskStatus.PENDING,
    )
    await db.tasks.insert_one(task.to_mongo())
    background.add_task(_run_task_bg, task.id, cleaned_text, project)
    return {"id": task.id, "status": task.status}
