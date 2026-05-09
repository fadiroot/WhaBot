"""GitHub integration: PRs, issues, CI status. Uses PyGithub."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from github import Auth, Github

from app.config import get_settings
from app.core.logger import logger


def _github_request_error_dict(operation: str, exc: Any) -> Dict[str, Any]:
    """Turn PyGithub errors into something the agent and users can act on (no stack traces)."""
    status = getattr(exc, "status", None)
    if status is None:
        raise TypeError("expected a GitHub API exception with .status")
    raw = getattr(exc, "data", None)
    data = raw if isinstance(raw, dict) else {}
    top_msg = (data.get("message") or str(exc)).strip()
    msg = top_msg
    # GitHub often leaves top-level message as "Validation Failed" and puts the real reason in `errors[]`.
    detail_lines: list[str] = []
    raw_errors = data.get("errors")
    if isinstance(raw_errors, list):
        for e in raw_errors:
            if isinstance(e, dict):
                m = (e.get("message") or "").strip()
                if not m:
                    fld = (e.get("field") or "").strip()
                    code = (e.get("code") or "").strip()
                    if fld == "head" and code == "invalid":
                        m = (
                            "head is invalid — that branch is not on GitHub yet (push to origin first), "
                            "or the branch name does not match."
                        )
                    elif fld and code:
                        m = f"{fld} ({code})"
                if m and m not in detail_lines:
                    detail_lines.append(m)
    if detail_lines and (status == 422 or top_msg == "Validation Failed" or "failed" in top_msg.lower()):
        msg = f"{top_msg} — {detail_lines[0]}"
    hint = ""
    low = top_msg.lower()
    if status == 403 and (
        "not accessible" in low
        or "resource not accessible" in low
        or "insufficient" in low
    ):
        hint = (
            "This token is not allowed to open pull requests on that repository. "
            "Classic PAT: enable the `repo` scope (private repos need full `repo`). "
            "Fine-grained PAT: under Repository permissions set "
            "**Pull requests** and **Contents** to Read and write (not Read-only). "
            "**Actions** (CI/workflows) is a separate permission — Read access to Actions does **not** allow creating PRs. "
            "If Pull requests is Read-only, POST /pulls returns 403. "
            "If the org uses SSO, authorize the token for the org. "
            "Update `GITHUB_TOKEN` / project `github_token` and restart the backend."
        )
    elif status == 404:
        if "get_pull" in operation.lower() or "summarize" in operation.lower():
            hint = (
                "No such pull request in this repo, or the token cannot access it — "
                "confirm the PR number on GitHub (the first opened PR might not be #1)."
            )
        else:
            hint = (
                "Repository or ref not found, or the token cannot see the repo. "
                "Confirm `repository_url`, branch names, "
                "and that the token has access to this repo."
            )
    elif status == 422:
        head_invalid = bool(
            isinstance(raw_errors, list)
            and any(
                isinstance(e, dict) and e.get("field") == "head" and e.get("code") == "invalid"
                for e in raw_errors
            )
        )
        specific = ""
        if detail_lines:
            specific = f" GitHub said: {'; '.join(detail_lines[:3])}."
        elif isinstance(raw_errors, list) and raw_errors:
            specific = f" Raw: {raw_errors[:3]!r}."
        if head_invalid:
            hint = (
                "`head` must already exist on GitHub (origin). Push the branch first (`commit_and_push`), "
                "and approve the push if your app requires it — rejecting approval means nothing is pushed, "
                "so opening a PR will fail with head invalid."
                + specific
            )
        else:
            hint = (
                "GitHub rejected the PR (validation). Typical causes: feature branch not pushed, "
                "`head` is the same as `base`, no new commits on `head`, or a PR for that branch already exists."
                + specific
            )
    elif status in (401, 403) and "bad credentials" in low:
        hint = "Token rejected — verify `GITHUB_TOKEN` / project token is valid and not expired."
    out: Dict[str, Any] = {
        "error": f"GitHub {operation} failed ({status}): {msg}",
        "github_status": status,
    }
    if hint:
        out["hint"] = hint
    if detail_lines:
        out["github_errors"] = detail_lines
    return out


class GitHubService:
    def __init__(self, token: Optional[str] = None):
        settings = get_settings()
        self.token = token or settings.github_token
        if not self.token:
            raise RuntimeError("GitHub token is not configured")
        self.client = Github(auth=Auth.Token(self.token))

    @staticmethod
    def parse_repo(url: str) -> str:
        """Convert https://github.com/org/repo(.git) → 'org/repo'."""
        parsed = urlparse(url)
        path = parsed.path.lstrip("/").removesuffix(".git")
        return path

    def repo(self, repo_url: str):
        return self.client.get_repo(self.parse_repo(repo_url))

    def branch_exists(self, repo_url: str, branch: str) -> Dict[str, Any]:
        """Check whether `branch` exists on origin.

        Returns one of:
          {"exists": True}
          {"exists": False}
          {"error": "...", "github_status": <int>}  — when the lookup itself failed
            (e.g. token can't see the repo). We deliberately surface this so the
            caller doesn't silently treat an auth/API failure as "branch missing".
        """
        try:
            r = self.repo(repo_url)
            r.get_branch(branch)
            return {"exists": True}
        except Exception as exc:  # noqa: BLE001
            status = getattr(exc, "status", None)
            if status == 404:
                return {"exists": False}
            if status is not None:
                try:
                    err = _github_request_error_dict("branch_exists", exc)
                except TypeError:
                    err = {
                        "error": f"GitHub branch_exists failed: {exc}",
                        "github_status": status,
                    }
                return err
            logger.warning("branch_exists failed (non-API): {}", exc)
            return {
                "error": f"GitHub branch_exists failed: {exc}",
                "hint": "Network or unexpected error before GitHub returned an HTTP status.",
            }

    def create_pull_request(
        self,
        repo_url: str,
        title: str,
        body: str,
        head: str,
        base: str = "main",
        draft: bool = False,
    ) -> Dict[str, Any]:
        try:
            r = self.repo(repo_url)
            pr = r.create_pull(title=title, body=body, head=head, base=base, draft=draft)
            return {"number": pr.number, "url": pr.html_url, "state": pr.state}
        except Exception as exc:
            # Include GitHub API errors (403/422/…) without relying on isinstance — avoids noisy tracebacks in tools.run_tool.
            if getattr(exc, "status", None) is not None:
                try:
                    err = _github_request_error_dict("create_pull_request", exc)
                except TypeError:
                    err = {
                        "error": f"GitHub create_pull_request failed: {exc}",
                        "github_status": getattr(exc, "status", None),
                    }
                if err.get("github_status") == 422 and isinstance(getattr(exc, "data", None), dict):
                    logger.warning("create_pull_request 422 full body: {}", exc.data)
                else:
                    logger.warning("create_pull_request GitHub API error: {}", err.get("error", exc))
                return err
            logger.warning("create_pull_request failed: {}", exc)
            return {
                "error": f"GitHub create_pull_request failed: {exc}",
                "hint": "Network error or unexpected failure before GitHub returned HTTP status; retry after checking connectivity.",
            }

    def get_pr_summary(self, repo_url: str, number: int) -> Dict[str, Any]:
        try:
            r = self.repo(repo_url)
            pr = r.get_pull(number)
            files = [
                {"filename": f.filename, "status": f.status, "additions": f.additions, "deletions": f.deletions}
                for f in pr.get_files()[:50]
            ]
            return {
                "number": pr.number,
                "title": pr.title,
                "state": pr.state,
                "url": pr.html_url,
                "author": pr.user.login if pr.user else None,
                "body": pr.body or "",
                "additions": pr.additions,
                "deletions": pr.deletions,
                "changed_files": pr.changed_files,
                "files": files,
            }
        except Exception as exc:
            if getattr(exc, "status", None) is not None:
                try:
                    err = _github_request_error_dict("summarize_pull_request#get_pull_request", exc)
                except TypeError:
                    err = {
                        "error": f"GitHub get_pull_request failed: {exc}",
                        "github_status": getattr(exc, "status", None),
                    }
                err["requested_pr_number"] = number
                logger.warning("summarize_pull_request/get_pr_summary: {}", err.get("error", exc))
                return err
            logger.warning("get_pr_summary failed: {}", exc)
            return {
                "error": f"GitHub get_pr_summary failed: {exc}",
                "requested_pr_number": number,
                "hint": "Network or unexpected error before GitHub returned an HTTP status.",
            }

    def list_recent_workflow_runs(self, repo_url: str, limit: int = 10) -> List[Dict[str, Any]]:
        r = self.repo(repo_url)
        runs = r.get_workflow_runs()
        out: List[Dict[str, Any]] = []
        for i, run in enumerate(runs):
            if i >= limit:
                break
            out.append(
                {
                    "id": run.id,
                    "name": run.name,
                    "status": run.status,
                    "conclusion": run.conclusion,
                    "branch": run.head_branch,
                    "created_at": run.created_at.isoformat() if run.created_at else None,
                    "url": run.html_url,
                }
            )
        return out

    def get_workflow_run_logs_summary(self, repo_url: str, run_id: int) -> Dict[str, Any]:
        r = self.repo(repo_url)
        run = r.get_workflow_run(run_id)
        jobs = []
        for job in run.jobs():
            steps = [
                {"name": s.name, "status": s.status, "conclusion": s.conclusion}
                for s in job.steps
            ]
            jobs.append(
                {
                    "name": job.name,
                    "status": job.status,
                    "conclusion": job.conclusion,
                    "url": job.html_url,
                    "steps": steps,
                }
            )
        return {
            "id": run.id,
            "name": run.name,
            "status": run.status,
            "conclusion": run.conclusion,
            "url": run.html_url,
            "jobs": jobs,
        }
