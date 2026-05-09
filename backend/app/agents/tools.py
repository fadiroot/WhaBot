"""Safe tool registry exposed to the AI agent.

Every tool returned to the LLM goes through this registry. The AI is **never**
given raw shell access. Each tool:
  * has a JSON schema (so OpenAI function-calling can validate args),
  * is explicitly listed in TOOL_SPECS / TOOL_DISPATCH,
  * runs against a per-project sandboxed workspace,
  * may require human approval before being executed (sensitive=True).
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from app.config import get_settings
from app.core.database import get_db
from app.core.logger import logger
from app.services.approval_service import request_approval
from app.services.git_service import GitService
from app.services.github_service import GitHubService
from app.services.repo_indexer import RepoIndexer


# --- Public tool specs (OpenAI tools schema) ----------------------------------
TOOL_SPECS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": (
                "Semantic + keyword search over the project's source code. "
                "Returns top file/line ranges relevant to the query."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural-language query, e.g. 'refresh token expiration logic'"},
                    "k": {"type": "integer", "default": 8, "minimum": 1, "maximum": 20},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List source files in the project (under an optional sub-path).",
            "parameters": {
                "type": "object",
                "properties": {
                    "sub_path": {"type": "string", "default": ""},
                    "max_files": {"type": "integer", "default": 200, "minimum": 1, "maximum": 2000},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file in the project workspace (utf-8, capped).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path under the repo workspace"},
                    "file_path": {"type": "string", "description": "Alias for path (same meaning)"},
                    "max_bytes": {"type": "integer", "default": 80000, "minimum": 100, "maximum": 200000},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Create or overwrite a file inside the project workspace. "
                "Only use after you've identified the right path. Paths are sandboxed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path under the repo workspace"},
                    "file_path": {"type": "string", "description": "Alias for path (many models use this)"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_branch",
            "description": "Create (or reset) a git branch off the project's default branch.",
            "parameters": {
                "type": "object",
                "properties": {
                    "branch": {"type": "string", "description": "e.g. 'ai/fix-login-refresh-bug'"},
                },
                "required": ["branch"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "commit_and_push",
            "description": (
                "Stage all changes, commit with the given message, and push the branch. "
                "Sensitive: may require human approval."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "branch": {"type": "string", "description": "Branch currently checked out (same as create_branch)."},
                    "branch_name": {"type": "string", "description": "Alias for branch."},
                    "message": {"type": "string", "description": "Commit message."},
                    "commit_message": {"type": "string", "description": "Alias for message."},
                },
                "required": ["branch", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_pull_request",
            "description": "Open a pull request on GitHub for the current project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "head": {
                        "type": "string",
                        "description": "Feature branch pushed to origin (same as create_branch). Not default/main.",
                    },
                    "branch_name": {
                        "type": "string",
                        "description": "Alternative to head if it is truly the pushed feature branch—not the base branch.",
                    },
                    "source_branch": {"type": "string", "description": "Alias for head."},
                    "base": {"type": "string", "default": "main"},
                    "draft": {"type": "boolean", "default": False},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_pull_request",
            "description": "Fetch and summarise the diff/details of an existing PR.",
            "parameters": {
                "type": "object",
                "properties": {"number": {"type": "integer"}},
                "required": ["number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_workflow_runs",
            "description": "List recent GitHub Actions runs for this project.",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 30}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "workflow_run_details",
            "description": "Get details and per-step status for a GitHub Actions run.",
            "parameters": {
                "type": "object",
                "properties": {"run_id": {"type": "integer"}},
                "required": ["run_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": (
                "Call this when you have a final answer for the user. "
                "Provide a concise WhatsApp-friendly message (markdown ok)."
            ),
            "parameters": {
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            },
        },
    },
]


SENSITIVE_TOOLS = {"commit_and_push", "create_pull_request"}


def _required_fields_for_tool(name: str) -> List[str]:
    for spec in TOOL_SPECS:
        fn = spec.get("function") or {}
        if fn.get("name") != name:
            continue
        params = fn.get("parameters") or {}
        required = params.get("required") or []
        return [str(r) for r in required if str(r).strip()]
    return []


def _validate_required_args(name: str, args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    missing: List[str] = []
    for field in _required_fields_for_tool(name):
        val = args.get(field)
        if val is None:
            missing.append(field)
        elif isinstance(val, str) and not val.strip():
            missing.append(field)
    if not missing:
        return None
    return {
        "error": f"Tool `{name}` missing required args: {', '.join(missing)}.",
        "tool": name,
        "missing_required": missing,
        "hint": "Call the tool again including all required arguments.",
    }


class ToolContext:
    """Bundle of resources passed into every tool invocation."""

    def __init__(
        self,
        *,
        project: Dict[str, Any],
        task_id: str,
        require_approval_for_push: bool = True,
    ):
        self.project = project
        self.task_id = task_id
        self.require_approval_for_push = require_approval_for_push
        self.git = GitService(
            project_slug=project["slug"],
            repo_url=project["repository_url"],
            default_branch=project.get("default_branch", "main"),
        )
        _settings = get_settings()
        self.github_token: Optional[str] = project.get("github_token") or _settings.github_token
        self.indexer = RepoIndexer(
            project_id=project["_id"],
            project_slug=project["slug"],
            repo_url=project["repository_url"],
            default_branch=project.get("default_branch", "main"),
            github_token=self.github_token,
        )
        # Branches we successfully pushed in this task. Lets create_pull_request
        # skip the GitHub round-trip when we already know the branch is live.
        self.pushed_branches: Set[str] = set()

    def _gh(self) -> GitHubService:
        return GitHubService(token=self.github_token)


# --- Implementations ---------------------------------------------------------
async def _t_search_code(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    results = await ctx.indexer.search(args["query"], k=int(args.get("k", 8)))
    return {"matches": results, "count": len(results)}


async def _t_list_files(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    files = ctx.git.list_files(sub_path=args.get("sub_path", ""), max_files=int(args.get("max_files", 200)))
    return {"files": files, "count": len(files)}


async def _t_read_file(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    path = args.get("path")
    if not path:
        return {"error": 'read_file requires "path" (aliases: file_path, relative_path).'}
    try:
        text = ctx.git.read_file(path, max_bytes=int(args.get("max_bytes", 80000)))
        return {"path": path, "content": text}
    except FileNotFoundError:
        # Let the agent continue and create the file instead of failing the whole run.
        return {"path": path, "content": "", "exists": False, "error": "file_not_found"}


async def _t_write_file(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    path = args.get("path")
    if not path:
        return {"error": 'write_file requires "path" (aliases: file_path, relative_path).'}
    content = args.get("content")
    if content is None:
        return {
            "error": (
                'write_file requires "content" (aliases: text, code, body). '
                "If you are creating a new file, pass the full file content."
            ),
            "path": path,
        }
    ctx.git.write_file(path, str(content))
    return {"path": path, "written": True}


async def _t_create_branch(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    b = args.get("branch")
    if not b:
        return {"error": 'create_branch expects "branch" (or alias "branch_name").'}
    ctx.git.clone_or_pull(token=ctx.github_token)
    branch = ctx.git.create_branch(b)
    return {"branch": branch}


async def _t_commit_and_push(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    branch = args.get("branch")
    message = args.get("message")
    if not branch or not message:
        missing = []
        if not branch:
            missing.append("branch (alias: branch_name)")
        if not message:
            missing.append("message (alias: commit_message)")
        return {"error": f'commit_and_push missing: {", ".join(missing)}.'}
    if ctx.require_approval_for_push:
        approval = await request_approval(
            action="git.push",
            summary=f"Push branch {branch}",
            project_id=ctx.project["_id"],
            task_id=ctx.task_id,
            payload={"branch": branch, "message": message},
        )
        return {
            "status": "awaiting_approval",
            "approval_id": approval.id,
            "message": "Push requires human approval. Reply 'approve <id>' on WhatsApp or use the dashboard.",
        }
    sha = ctx.git.commit_all(message)
    if not sha:
        return {"status": "no_changes"}
    ctx.git.push(branch, token=ctx.github_token)
    ctx.pushed_branches.add(branch)
    return {"status": "pushed", "sha": sha, "branch": branch}


async def _t_create_pull_request(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    base = args.get("base") or ctx.project.get("default_branch", "main")
    head = args.get("head") or _resolve_pr_head(ctx, args)
    if not head:
        return {
            "error": (
                "Missing feature branch for the PR (`head`). "
                'Use the branch you pushed (e.g. "ai/hello-md"), same as create_branch—not the default/base branch.'
            ),
        }
    if head == base:
        return {
            "error": (
                f"`head` and `base` are both `{base}`. PRs must compare a feature branch against the default branch."
            ),
            "hint": "Pass head=<your feature branch you pushed> (the same name you used in create_branch / commit_and_push).",
        }

    # Pre-flight: confirm the feature branch is actually on origin BEFORE asking
    # GitHub to open a PR. Otherwise we get a cryptic 422 "head invalid" and the
    # small LLMs (llama3.2 etc.) often don't recover from it. Small models also
    # frequently skip `commit_and_push` entirely; when push doesn't require human
    # approval we self-heal by running it now and continuing.
    gh = ctx._gh()
    pushed = ctx.pushed_branches if isinstance(ctx.pushed_branches, set) else set()
    if head not in pushed:
        existence = gh.branch_exists(ctx.project["repository_url"], head)
        if existence.get("error"):
            return existence
        if not existence.get("exists"):
            if ctx.require_approval_for_push:
                return {
                    "error": (
                        f"Cannot open PR: branch `{head}` is not on GitHub yet "
                        "(it was created locally but never pushed)."
                    ),
                    "missing_step": "commit_and_push",
                    "hint": (
                        "Call `commit_and_push` FIRST with this exact branch name and a commit message. "
                        "If it returns `awaiting_approval`, stop and wait — a human must approve before the "
                        "branch reaches GitHub. Only after the push has actually completed should you call "
                        "`create_pull_request` again."
                    ),
                    "next_tool": {
                        "name": "commit_and_push",
                        "args": {"branch": head, "message": f"Apply changes for {head}"},
                    },
                }
            logger.info(
                "create_pull_request: branch {} not on origin, auto-running commit_and_push",
                head,
            )
            push_result = await _t_commit_and_push(
                ctx,
                {"branch": head, "message": f"Apply changes for {head}"},
            )
            if push_result.get("status") != "pushed":
                return {
                    "error": (
                        f"Auto commit_and_push for `{head}` did not push (status="
                        f"{push_result.get('status') or push_result.get('error')}). "
                        "Make sure write_file ran with real content before opening the PR."
                    ),
                    "commit_and_push_result": push_result,
                }

    title = (args.get("title") or args.get("pr_title") or "").strip()
    if not title:
        readable = head.split("/")[-1].replace("-", " ").replace("_", " ").strip().capitalize()
        title = readable or f"Update from {head}"
    body = (args.get("body") or args.get("description") or "").strip()
    if not body:
        body = f"Automated PR from branch `{head}` against `{base}`."
    pr = gh.create_pull_request(
        repo_url=ctx.project["repository_url"],
        title=title,
        body=body,
        head=head,
        base=base,
        draft=bool(args.get("draft", False)),
    )
    if pr.get("error"):
        return pr
    db = get_db()
    await db.tasks.update_one(
        {"_id": ctx.task_id},
        {"$set": {"pr_url": pr["url"], "branch": head}},
    )
    return pr


async def _t_summarize_pull_request(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    raw_number = args.get("number") or args.get("pr_number") or args.get("pull_number")
    try:
        number = int(raw_number) if raw_number is not None else None
    except (TypeError, ValueError):
        number = None
    if not number:
        return {
            "error": 'summarize_pull_request requires "number" (the PR number).',
            "hint": "Pass the PR number you can see on the GitHub PR page (e.g. /pull/42 → 42).",
        }
    return ctx._gh().get_pr_summary(ctx.project["repository_url"], number)


async def _t_list_workflow_runs(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    return {"runs": ctx._gh().list_recent_workflow_runs(ctx.project["repository_url"], limit=int(args.get("limit", 10)))}


async def _t_workflow_run_details(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    return ctx._gh().get_workflow_run_logs_summary(ctx.project["repository_url"], int(args["run_id"]))


def _resolve_pr_head(ctx: ToolContext, args: Dict[str, Any]) -> Optional[str]:
    """Model often sends branch_name/repo_url/message aliases; infer head safely."""
    base = str(args.get("base") or ctx.project.get("default_branch") or "main").strip()

    def _want(s: str) -> Optional[str]:
        s = str(s).strip()
        return s if s and s != base else None

    head = (
        _want(args.get("head") or "")
        or _want(args.get("source_branch") or "")
        or _want(args.get("branch") or "")
    )
    if not head:
        bn = args.get("branch_name")
        if bn is not None:
            cand = _want(bn or "")
            if cand:
                head = cand
    if not head:
        cur = ctx.git.current_branch_name()
        cur = cur.strip() if cur else ""
        head = cur if cur and cur != base else ""

    return head or None


def _normalize_workspace_path(raw_path: str, file_name: Optional[str]) -> str:
    """Coerce model-provided paths into safe workspace-relative paths.

    Small models often invent absolute container paths (e.g. ``/home/user/...``)
    or pass the directory as ``path`` and the filename as ``file_name``. We
    accept both shapes by:
    - stripping leading slashes so absolute paths become relative;
    - if ``path`` looks like a directory (no extension or ends with ``/``)
      and ``file_name`` is present, joining them.
    """
    p = (raw_path or "").strip()
    fname = (file_name or "").strip()
    if not p and fname:
        return fname.lstrip("/")
    p_clean = p.lstrip("/")
    if fname and (p_clean.endswith("/") or "." not in p_clean.rsplit("/", 1)[-1]):
        if not p_clean.endswith("/"):
            p_clean = p_clean + "/"
        p_clean = p_clean + fname
    return p_clean


def _normalize_tool_args(name: str, ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    a = dict(args or {})
    if name in ("read_file", "write_file"):
        if not (a.get("path") or "").strip():
            for key in ("file_path", "filepath", "relative_path"):
                val = a.get(key)
                if val is not None and str(val).strip():
                    a["path"] = str(val).strip()
                    break
        # Sanitize after alias resolution so absolute paths and dir+file_name
        # combinations all turn into safe workspace-relative paths.
        if (a.get("path") or "").strip() or a.get("file_name"):
            a["path"] = _normalize_workspace_path(a.get("path") or "", a.get("file_name"))
    if name == "write_file":
        if a.get("content") is None:
            for key in ("text", "code", "body"):
                val = a.get(key)
                if val is not None:
                    a["content"] = val
                    break
    if name == "create_branch":
        if "branch" not in a and "branch_name" in a:
            a["branch"] = a["branch_name"]
    elif name == "commit_and_push":
        if "branch" not in a and "branch_name" in a:
            a["branch"] = a["branch_name"]
        if "message" not in a and "commit_message" in a:
            a["message"] = a["commit_message"]
    elif name == "create_pull_request":
        # Drop mistaken keys smaller models invent.
        a.pop("repo_url", None)
        head = _resolve_pr_head(ctx, a)
        if head and "head" not in a:
            a["head"] = head
        if (
            isinstance(a.get("base"), str)
            and not a["base"].strip()
        ):
            a["base"] = ctx.project.get("default_branch", "main")
    return a


TOOL_DISPATCH: Dict[str, Callable[[ToolContext, Dict[str, Any]], Awaitable[Dict[str, Any]]]] = {
    "search_code": _t_search_code,
    "list_files": _t_list_files,
    "read_file": _t_read_file,
    "write_file": _t_write_file,
    "create_branch": _t_create_branch,
    "commit_and_push": _t_commit_and_push,
    "create_pull_request": _t_create_pull_request,
    "summarize_pull_request": _t_summarize_pull_request,
    "list_workflow_runs": _t_list_workflow_runs,
    "workflow_run_details": _t_workflow_run_details,
}


async def run_tool(name: str, ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    fn = TOOL_DISPATCH.get(name)
    if not fn:
        return {"error": f"Unknown tool '{name}'"}
    try:
        args = _normalize_tool_args(name, ctx, args or {})
        validation_error = _validate_required_args(name, args)
        if validation_error:
            return validation_error
        result = await fn(ctx, args)
        return result
    except ValueError as exc:
        logger.warning("Tool {} rejected: {}", name, exc)
        return {
            "error": str(exc),
            "tool": name,
            "hint": "Use a workspace-relative path (e.g. `selection_sort.py`); absolute paths are not allowed.",
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Tool {} failed: {}", name, exc)
        return {"error": str(exc), "tool": name}
