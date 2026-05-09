"""Approval workflow endpoints."""

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from git.exc import GitCommandError
from pydantic import BaseModel

from app.config import get_settings
from app.core.database import get_db
from app.core.logger import logger
from app.core.security import Roles, require_roles
from app.models.approval import ApprovalStatus
from app.services.approval_service import decide_approval
from app.services.audit_service import write_audit
from app.services.git_service import GitService
from app.services.github_service import GitHubService
from app.services.whatsapp import get_whatsapp_client

router = APIRouter(prefix="/approvals", tags=["approvals"])


class DecisionPayload(BaseModel):
    note: Optional[str] = None


@router.get("")
async def list_approvals(
    status: Optional[ApprovalStatus] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user=Depends(require_roles(Roles.ADMIN, Roles.DEVELOPER)),
):
    db = get_db()
    q: dict = {}
    if status:
        q["status"] = status.value
    total = await db.approvals.count_documents(q)
    cursor = db.approvals.find(q).sort("created_at", -1).skip(offset).limit(limit)
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


async def _execute_approved(approval: dict) -> str:
    """Carry out the action a now-approved approval represents."""
    db = get_db()
    project = await db.projects.find_one({"_id": approval.get("project_id")})
    if not project:
        return "Project no longer exists; cannot execute."
    if approval["action"] == "git.push":
        branch = approval["payload"]["branch"]
        message = approval["payload"]["message"]
        settings = get_settings()
        token = project.get("github_token") or settings.github_token
        if not token:
            return (
                "Cannot push: no GitHub credentials. Set `GITHUB_TOKEN` in the server `.env` "
                "or store `github_token` on the project, then approve again."
            )
        git = GitService(project["slug"], project["repository_url"], project.get("default_branch", "main"))
        try:
            sha = git.commit_all(message)
            if sha:
                git.push(branch, token=token)
                return f"Pushed branch `{branch}` with commit {sha[:7]}."
            return f"Branch `{branch}` had no changes to commit."
        except GitCommandError as exc:
            err = (exc.stderr or exc.stdout or str(exc)).strip()
            logger.warning("Approval git.push failed: {}", err)
            msg = f"Push failed (git): {err}"
            if "403" in err or "denied" in err.lower():
                msg += (
                    " Fine-grained PAT: enable **Contents: Read and write** for this repository "
                    "(write on Pull requests alone does not authorize `git push`)."
                )
            return msg
    return f"No executor registered for action {approval['action']}"


@router.post("/{approval_id}/approve")
async def approve(approval_id: str, payload: DecisionPayload, background: BackgroundTasks, user=Depends(require_roles(Roles.ADMIN))):
    updated = await decide_approval(
        approval_id,
        decision=ApprovalStatus.APPROVED,
        decided_by=user["_id"],
        note=payload.note,
    )
    if not updated:
        raise HTTPException(404, "Approval not found or already decided")

    async def _run():
        try:
            result = await _execute_approved(updated)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Approval execution crashed: {}", exc)
            result = f"Internal error while executing approval: {exc}"
        await write_audit(
            action=f"approval.execute.{updated['action']}",
            actor_id=user["_id"],
            actor_kind="user",
            project_id=updated.get("project_id"),
            task_id=updated.get("task_id"),
            payload={"approval_id": approval_id, "result": result},
        )
        # Notify on whatsapp if we know the chat
        db = get_db()
        if updated.get("task_id"):
            task = await db.tasks.find_one({"_id": updated["task_id"]})
            if task and task.get("whatsapp_chat_id"):
                try:
                    await get_whatsapp_client().send_text(task["whatsapp_chat_id"], f"Approval {approval_id[:8]}: {result}")
                except Exception:  # noqa: BLE001
                    pass

    background.add_task(_run)
    return {"status": "approved", "approval_id": approval_id}


@router.post("/{approval_id}/reject")
async def reject(approval_id: str, payload: DecisionPayload, user=Depends(require_roles(Roles.ADMIN, Roles.DEVELOPER))):
    updated = await decide_approval(
        approval_id,
        decision=ApprovalStatus.REJECTED,
        decided_by=user["_id"],
        note=payload.note,
    )
    if not updated:
        raise HTTPException(404, "Approval not found or already decided")
    await write_audit(
        action="approval.reject",
        actor_id=user["_id"],
        actor_kind="user",
        project_id=updated.get("project_id"),
        task_id=updated.get("task_id"),
        payload={"approval_id": approval_id},
    )
    return {"status": "rejected", "approval_id": approval_id}
