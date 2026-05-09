"""AI orchestration: turn a WhatsApp request into engineering actions.

The orchestrator runs an OpenAI tool-calling loop against the safe tool registry
defined in `app.agents.tools`. It records every step into the Task document so
the dashboard / WhatsApp summary can show what happened.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import (
    get_async_openai_client,
    get_settings,
    llm_chat_model,
    llm_is_configured,
    should_use_native_openai_tools,
)
from app.core.database import get_db
from app.core.logger import logger
from app.models.task import Task, TaskStatus
from app.services.audit_service import write_audit
from app.services.github_service import GitHubService
from app.agents.json_tool_protocol import JSON_TOOL_INSTRUCTION, parse_tool_json_response
from app.agents.tools import (
    TOOL_SPECS,
    ToolContext,
    run_tool,
)


SYSTEM_PROMPT = """\
You are "AI Engineer", an autonomous junior/mid-level software engineer accessible \
through WhatsApp. You receive concise natural-language requests from developers \
and must complete them safely using the provided tools.

Operating rules:
- ALWAYS reason about what file/module is involved before editing.
- Prefer `search_code` and `read_file` to gather context before changing anything —
  but if the user gives an explicit path plus a trivial change (new file named X, typo fix), skip long exploration unless needed; each round counts toward the step budget.
- Make minimal, focused edits. Keep diffs small and explainable.
- For code changes, follow this flow STRICTLY in order — never skip a step:
    1) explore (search_code / read_file)
    2) create_branch with a short, kebab-case name like 'ai/<topic>'
    3) write_file for each modified file
    4) commit_and_push — REQUIRED. The branch only reaches GitHub after THIS tool succeeds.
       * If it returns {"status":"pushed"} you may proceed to step 5.
       * If it returns {"status":"awaiting_approval"} STOP — call `finish` and tell the user a human must approve. Do NOT call create_pull_request now; the branch is not on GitHub yet.
       * If it returns {"status":"no_changes"} you have nothing to PR — investigate.
    5) create_pull_request — only AFTER step 4 returned "pushed". If you call it before, it will fail with `head invalid` because the branch does not exist on origin.
    6) finish with a short WhatsApp-friendly summary including the PR URL
- If the request is informational (e.g. "summarize PR #42", "why did deploy fail?"), \
do not modify code; just gather data and call `finish`.
- NEVER fabricate file paths, line numbers, PR numbers, or commit SHAs. \
If unsure, use a tool to verify.
- WhatsApp messages should be SHORT. Use bullets, no large code blocks.
- When you are done, you MUST call the `finish` tool with the user-facing message.
"""

_TRIVIAL_GREETING_RE = re.compile(
    r"^(hi|hello|hey|yo|sup|good\s+(morning|afternoon|evening)|مرحبا|salut)\b[!?.]*\s*$",
    re.IGNORECASE,
)

_GREETING_JSON_HINT = """

SPECIAL CASE — The user only sent a short greeting (hi/hello). Do **not** run search_code, git, or other tools.
Reply with **exactly one** JSON object only:
{"tool":"finish","args":{"message":"Hi! I'm ready — what should we work on? (e.g. summarize PR #2, fix a bug, check CI)"}}
"""


def _is_trivial_greeting(text: str) -> bool:
    return bool(text and _TRIVIAL_GREETING_RE.match(text.strip()))


def _looks_like_json_tool_blob(text: str) -> bool:
    """True if assistant output is probably tool JSON, not a natural reply."""
    t = text.strip()
    if len(t) > 1200:
        return True
    if t.startswith("{") and ("tool" in t or '"name"' in t or "'name'" in t):
        return True
    return False


def _quick_project_metadata_reply(request_text: str, project: Dict[str, Any]) -> Optional[str]:
    """Answer simple questions about the active project without involving the LLM (Ollama-friendly)."""
    if not (request_text or "").strip():
        return None
    url = (project.get("repository_url") or "").strip()
    if not url:
        return None
    t = request_text.lower().strip()
    # Skip likely engineering tasks — let the agent run
    if re.search(r"\b(fix|implement|add|change|delete|refactor|migrate|deploy|test|run|build)\b", t):
        return None

    asks_meta = bool(
        re.search(r"\b(url|uri|link|clone|remote|web\s*address)\b", t)
        or re.search(r"\b(repo|repository|rep)\b", t)
        or re.search(r"\b(branch|default\s*branch)\b", t)
    )
    asks_question = bool(re.search(r"\b(what|where|which|give|show|send|tell|need|get)\b", t) or "?" in t)
    # "give me the url of rep", "repo url", "what's the repository"
    if asks_meta and (asks_question or "url" in t or "link" in t or "clone" in t):
        branch = project.get("default_branch", "main")
        name = project.get("name") or project.get("slug") or "project"
        slug = project.get("slug", "")
        return (
            f"**Repository URL:** `{url}`\n"
            f"**Default branch:** `{branch}`\n"
            f"**Project:** {name} (`{slug}`)"
        )
    return None


def _quick_github_pr_summary(request_text: str, project: Dict[str, Any]) -> Optional[str]:
    """Fetch PR #N from GitHub when user asks to summarize/describe — no LLM required."""
    if not re.search(r"\b(summarize|summary|describe|overview)\b", request_text, re.I):
        return None
    m = re.search(r"\b(?:pr|pull\s*request)\s*#?\s*(\d+)\b", request_text, re.I)
    if not m:
        m = re.search(r"\bsummarize\s+.*?\#?\s*(\d+)\b", request_text, re.I)
    if not m:
        return None
    num = int(m.group(1))
    url = (project.get("repository_url") or "").strip()
    if not url or "github.com" not in url.lower():
        return None
    settings = get_settings()
    token = project.get("github_token") or settings.github_token
    if not token:
        return None
    try:
        gh = GitHubService(token=token)
        data = gh.get_pr_summary(url, num)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Quick PR summary failed: {}", exc)
        return None
    if data.get("error"):
        hint = data.get("hint")
        msg = data["error"]
        return f"{msg}\n\n{hint}" if hint else msg
    files = data.get("files") or []
    file_lines = "\n".join(f"- {f.get('filename', '')}" for f in files[:20])
    body = (data.get("body") or "")[:2000]
    return (
        f"**PR #{data.get('number', num)}** — {data.get('title', '')}\n"
        f"**State:** {data.get('state', '')} · {data.get('url', '')}\n"
        f"**+{data.get('additions', 0)} / -{data.get('deletions', 0)}** · {data.get('changed_files', 0)} files\n"
        f"**Author:** {data.get('author') or '—'}\n\n"
        f"**Description:**\n{body or '_(empty)_'}\n\n"
        f"**Changed files (sample):**\n{file_lines or '—'}"
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _append_step(task_id: str, step: Dict[str, Any]) -> None:
    db = get_db()
    step["created_at"] = _now_iso()
    await db.tasks.update_one({"_id": task_id}, {"$push": {"steps": step}})


async def _set_task(task_id: str, **fields: Any) -> None:
    db = get_db()
    fields["updated_at"] = datetime.now(timezone.utc)
    await db.tasks.update_one({"_id": task_id}, {"$set": fields})


def _build_messages(
    request_text: str,
    project: Optional[Dict[str, Any]],
    *,
    json_protocol: bool = False,
    extra_system_suffix: str = "",
) -> List[Dict[str, Any]]:
    project_block = ""
    if project:
        project_block = (
            f"\n\nActive project (already known — no need to search the codebase for this):\n"
            f"- name: {project.get('name')}\n"
            f"- slug: {project.get('slug')}\n"
            f"- repository_url: {project.get('repository_url')}\n"
            f"- default_branch: {project.get('default_branch', 'main')}\n"
            "If the user only asks for the repo URL, branch, or project name, call `finish` with that info.\n"
        )
    sys_content = SYSTEM_PROMPT + project_block
    if json_protocol:
        sys_content += JSON_TOOL_INSTRUCTION
    sys_content += extra_system_suffix
    return [
        {"role": "system", "content": sys_content},
        {"role": "user", "content": request_text},
    ]


async def run_agent(
    *,
    task_id: str,
    request_text: str,
    project: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run the tool-calling loop for a single Task.

    Returns a dict like {"final_message": str, "status": TaskStatus}.
    """
    settings = get_settings()
    await _set_task(task_id, status=TaskStatus.PLANNING.value)

    if project is None:
        msg = (
            "I couldn't identify which project this request belongs to. "
            "Use the project dropdown, send the project **slug** alone (e.g. `documind`), "
            "or prefix with `project: my-slug` plus your request.\n"
            "Or have an admin map your WhatsApp number/group to a project."
        )
        await _set_task(task_id, status=TaskStatus.FAILED.value, result=msg)
        return {"final_message": msg, "status": TaskStatus.FAILED}

    # User only selected a project (slug/name) with no engineering question yet
    if not (request_text or "").strip():
        pname = project.get("name") or project.get("slug")
        pslug = project.get("slug", "")
        msg = (
            f"Project **{pname}** (`{pslug}`) is set. What should I do next?\n"
            "Examples: summarize PR #12, why did CI fail, add pagination to users API."
        )
        await _set_task(task_id, status=TaskStatus.SUCCEEDED.value, result=msg)
        return {"final_message": msg, "status": TaskStatus.SUCCEEDED}

    if not llm_is_configured(settings):
        msg = (
            "AI is not configured. Options: (1) OPENAI_API_KEY for OpenAI or LLM_PROVIDER=openai + "
            "Groq/Ollama keys; (2) Azure: AZURE_OPENAI_* + LLM_PROVIDER=azure or auto."
        )
        await _set_task(task_id, status=TaskStatus.FAILED.value, error="missing LLM credentials", result=msg)
        return {"final_message": msg, "status": TaskStatus.FAILED}

    quick = _quick_project_metadata_reply(request_text, project)
    if quick:
        await _append_step(task_id, {"kind": "assistant", "content": quick})
        await _set_task(task_id, status=TaskStatus.SUCCEEDED.value, result=quick)
        return {"final_message": quick, "status": TaskStatus.SUCCEEDED}

    pr_quick = _quick_github_pr_summary(request_text, project)
    if pr_quick:
        await _append_step(task_id, {"kind": "assistant", "content": pr_quick})
        await _set_task(task_id, status=TaskStatus.SUCCEEDED.value, result=pr_quick)
        return {"final_message": pr_quick, "status": TaskStatus.SUCCEEDED}

    client = get_async_openai_client()
    ctx = ToolContext(
        project=project,
        task_id=task_id,
        require_approval_for_push=settings.require_approval_for_push,
    )

    use_native_tools = should_use_native_openai_tools(settings)
    greeting_extra = ""
    if not use_native_tools and _is_trivial_greeting(request_text):
        greeting_extra = _GREETING_JSON_HINT
    messages = _build_messages(
        request_text,
        project,
        json_protocol=not use_native_tools,
        extra_system_suffix=greeting_extra,
    )
    await _set_task(task_id, status=TaskStatus.EXECUTING.value)

    final_message: Optional[str] = None
    last_assistant: Optional[str] = None

    for iteration in range(settings.ai_max_tool_iterations):
        try:
            completion_kw: Dict[str, Any] = {
                "model": llm_chat_model(settings),
                "messages": messages,
                "temperature": 0.1,
            }
            if use_native_tools:
                completion_kw["tools"] = TOOL_SPECS
                completion_kw["tool_choice"] = "auto"
            response = await client.chat.completions.create(**completion_kw)
        except Exception as exc:  # noqa: BLE001
            logger.exception("LLM call failed: {}", exc)
            detail = str(exc)
            hint = ""
            if "protocol" in detail.lower() and ("http" in detail.lower() or "missing" in detail.lower()):
                hint = " Check OPENAI_BASE_URL: use a full URL (e.g. https://api.openai.com/v1) or leave it empty for the default API."
            elif "404" in detail or "not found" in detail.lower():
                hint = (
                    " For Azure: set AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, and AZURE_OPENAI_DEPLOYMENT "
                    "to the exact deployment name in Azure AI Studio (404 = wrong endpoint or deployment name)."
                )
            await _append_step(task_id, {"kind": "system", "content": f"LLM error: {exc}"})
            await _set_task(task_id, status=TaskStatus.FAILED.value, error=detail)
            return {"final_message": f"AI error: {exc}{hint}", "status": TaskStatus.FAILED}

        choice = response.choices[0]
        msg = choice.message
        content = msg.content or ""

        if use_native_tools:
            assistant_msg: Dict[str, Any] = {"role": "assistant", "content": content}
            if msg.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ]
            messages.append(assistant_msg)

            if content:
                last_assistant = content
                await _append_step(task_id, {"kind": "assistant", "content": content})

            if not msg.tool_calls:
                final_message = content or last_assistant or "Done."
                break

            awaiting_approval = False
            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}

                await _append_step(task_id, {"kind": "tool_call", "name": name, "arguments": args})

                if name == "finish":
                    final_message = args.get("message") or last_assistant or "Done."
                    break

                result = await run_tool(name, ctx, args)
                await _append_step(
                    task_id,
                    {"kind": "tool_result", "name": name, "output": json.dumps(result)[:4000]},
                )
                await write_audit(
                    action=f"tool.{name}",
                    actor_kind="ai-agent",
                    project_id=project["_id"],
                    task_id=task_id,
                    payload={"args": args, "ok": "error" not in result},
                    success="error" not in result,
                )
                if result.get("status") == "awaiting_approval":
                    awaiting_approval = True

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": name,
                        "content": json.dumps(result)[:8000],
                    }
                )

            if final_message is not None:
                break
            if awaiting_approval:
                await _set_task(task_id, status=TaskStatus.AWAITING_APPROVAL.value)
                final_message = (
                    "I prepared the changes and they're awaiting human approval before push. "
                    "An admin can approve via WhatsApp ('approve <id>') or the dashboard."
                )
                break
        else:
            # Ollama / small models: JSON tool protocol (no OpenAI tools=)
            messages.append({"role": "assistant", "content": content})
            if content:
                last_assistant = content
                await _append_step(task_id, {"kind": "assistant", "content": content})

            parsed = parse_tool_json_response(content)
            if not parsed:
                final_message = (
                    content.strip()
                    or "The model did not return valid tool JSON. "
                    "Try again or use LLM_NATIVE_TOOLS=true with OpenAI/Azure."
                )
                break

            name, args = parsed
            await _append_step(task_id, {"kind": "tool_call", "name": name, "arguments": args})

            if name == "finish":
                final_message = args.get("message") or last_assistant or "Done."
                break

            result = await run_tool(name, ctx, args)
            await _append_step(
                task_id,
                {"kind": "tool_result", "name": name, "output": json.dumps(result)[:4000]},
            )
            await write_audit(
                action=f"tool.{name}",
                actor_kind="ai-agent",
                project_id=project["_id"],
                task_id=task_id,
                payload={"args": args, "ok": "error" not in result},
                success="error" not in result,
            )
            if result.get("status") == "awaiting_approval":
                await _set_task(task_id, status=TaskStatus.AWAITING_APPROVAL.value)
                final_message = (
                    "I prepared the changes and they're awaiting human approval before push. "
                    "An admin can approve via WhatsApp ('approve <id>') or the dashboard."
                )
                break

            followup = (
                f"Tool `{name}` completed. Result JSON:\n{json.dumps(result)[:7500]}\n\n"
                "Reply with your next single JSON tool call, or finish."
            )
            if iteration >= settings.ai_max_tool_iterations - 2:
                followup += (
                    "\n\nIMPORTANT: You are almost out of steps — you **must** respond with only:\n"
                    '{"tool":"finish","args":{"message":"<short summary for the user>"}}\n'
                )
            messages.append({"role": "user", "content": followup})

    if final_message is None:
        tail = (last_assistant or "").strip()
        if tail and not _looks_like_json_tool_blob(tail):
            final_message = tail
            await _set_task(task_id, status=TaskStatus.SUCCEEDED.value, result=final_message)
            return {"final_message": final_message, "status": TaskStatus.SUCCEEDED}
        final_message = (
            "I hit the step limit before finishing this run. "
            "Increase `AI_MAX_TOOL_ITERATIONS` in your `.env` (try 28–40) if you use local/Ollama JSON tools; "
            "each tool call uses one round. Or retry asking for fewer exploratory steps "
            '(e.g. “create branch …, add hello.md with …, open PR”).'
        )
        await _set_task(task_id, status=TaskStatus.FAILED.value, error="max_iterations", result=final_message)
        return {"final_message": final_message, "status": TaskStatus.FAILED}

    if (await _get_task_status(task_id)) != TaskStatus.AWAITING_APPROVAL.value:
        await _set_task(task_id, status=TaskStatus.SUCCEEDED.value, result=final_message)
    else:
        await _set_task(task_id, result=final_message)

    return {"final_message": final_message, "status": TaskStatus.SUCCEEDED}


async def _get_task_status(task_id: str) -> str:
    db = get_db()
    doc = await db.tasks.find_one({"_id": task_id}, {"status": 1})
    return (doc or {}).get("status", "")
