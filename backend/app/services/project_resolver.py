"""Resolve which project a WhatsApp message refers to.

Resolution order:
 1. Explicit "project: <slug>" prefix in the message text.
 2. Whole message or first word matches a project's `slug` or `name` (case-insensitive),
    e.g. "documind" or "documind summarize PR #3".
 3. The chat id is in `allowed_whatsapp_chats` of exactly one project.
 4. The user's whatsapp number is mapped to exactly one project (member).
 5. None — caller must ask the user.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from app.core.database import get_db

_SLUG_PREFIX_RE = re.compile(r"^\s*project\s*:\s*([a-zA-Z0-9_\-]+)\s*\n?", re.IGNORECASE)
# Slug-like token (avoids treating "Fix the bug" as slug "Fix")
_SLUGLIKE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}$")


async def _project_by_slug_or_name(db, token: str) -> Optional[Dict[str, Any]]:
    t = (token or "").strip()
    if not t:
        return None
    esc = re.escape(t)
    proj = await db.projects.find_one({"slug": {"$regex": f"^{esc}$", "$options": "i"}})
    if proj:
        return proj
    return await db.projects.find_one({"name": {"$regex": f"^{esc}$", "$options": "i"}})


async def resolve_project(text: str, chat_id: Optional[str], whatsapp_number: Optional[str]) -> Tuple[Optional[Dict[str, Any]], str]:
    db = get_db()
    cleaned = text or ""

    m = _SLUG_PREFIX_RE.match(cleaned)
    if m:
        slug = m.group(1)
        project = await db.projects.find_one({"slug": slug})
        cleaned = _SLUG_PREFIX_RE.sub("", cleaned, count=1).strip()
        return project, cleaned

    raw = cleaned.strip()
    if raw:
        # Whole message is exactly a project slug or display name (dashboard / WhatsApp).
        proj = await _project_by_slug_or_name(db, raw)
        if proj:
            return proj, ""

        # "my-slug the rest of the request" — first token must look like a slug
        parts = raw.split(None, 1)
        if len(parts) == 2 and _SLUGLIKE.match(parts[0]):
            proj = await _project_by_slug_or_name(db, parts[0])
            if proj:
                return proj, parts[1].strip()

    if chat_id:
        cursor = db.projects.find({"allowed_whatsapp_chats": chat_id})
        projects = await cursor.to_list(length=2)
        if len(projects) == 1:
            return projects[0], cleaned.strip()

    if whatsapp_number:
        # Look up users with that whatsapp number, find their projects.
        user = await db.users.find_one({"whatsapp_number": whatsapp_number})
        if user:
            cursor = db.projects.find({"member_ids": user["_id"]})
            projects = await cursor.to_list(length=2)
            if len(projects) == 1:
                return projects[0], cleaned.strip()

    return None, cleaned.strip()
