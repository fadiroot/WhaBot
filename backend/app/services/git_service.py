"""Git operations using GitPython, scoped to a per-project workspace dir.

Every project gets its own directory under WORKSPACE_ROOT/<project_slug>.
We never accept arbitrary paths from the AI — paths are always validated to
stay within the project workspace (see _safe_path).
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse, urlunparse

from git import GitCommandError, Repo

from app.config import get_settings
from app.core.logger import logger


class GitService:
    def __init__(self, project_slug: str, repo_url: str, default_branch: str = "main"):
        self.settings = get_settings()
        self.project_slug = project_slug
        self.repo_url = repo_url
        self.default_branch = default_branch
        self.workspace = Path(self.settings.workspace_root) / project_slug
        self.workspace.mkdir(parents=True, exist_ok=True)

    # --- helpers --------------------------------------------------------
    @staticmethod
    def _with_token(url: str, token: Optional[str]) -> str:
        if not token:
            return url
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return url
        netloc = f"x-access-token:{token}@{parsed.hostname}"
        if parsed.port:
            netloc += f":{parsed.port}"
        return urlunparse(parsed._replace(netloc=netloc))

    def _safe_path(self, rel_path: str) -> Path:
        # Strip leading slashes so absolute-looking paths from the model
        # (e.g. "/home/user/projects/foo.py") are treated as relative.
        # We still reject any `..` traversal that would escape the workspace.
        cleaned = (rel_path or "").strip().lstrip("/")
        if not cleaned:
            raise ValueError("Refusing to access empty path")
        candidate = (self.workspace / cleaned).resolve()
        ws = self.workspace.resolve()
        if not str(candidate).startswith(str(ws) + os.sep) and candidate != ws:
            raise ValueError(f"Refusing to access path outside workspace: {rel_path}")
        return candidate

    # --- repo lifecycle -------------------------------------------------
    def is_cloned(self) -> bool:
        return (self.workspace / ".git").exists()

    def _workspace_has_content(self) -> bool:
        try:
            next(self.workspace.iterdir())
            return True
        except StopIteration:
            return False

    def _reset_workspace_for_clone(self) -> None:
        shutil.rmtree(self.workspace, ignore_errors=True)
        self.workspace.mkdir(parents=True, exist_ok=True)

    def _stash_workspace_if_dirty(self, repo: Repo) -> bool:
        """Avoid checkout/pull aborting on dirty tree; returns True if a stash entry was created."""
        if repo.is_dirty(index=True, working_tree=True, untracked_files=True):
            try:
                repo.git.stash("push", "-u", "-m", "ai-wa-engineer sync")
                return True
            except GitCommandError as exc:
                # New/unborn repos can error with "You do not have the initial commit yet".
                logger.warning("Skipping stash for {}: {}", self.project_slug, exc)
                return False
        return False

    def clone_or_pull(self, token: Optional[str] = None) -> Repo:
        url = self._with_token(self.repo_url, token)
        if self.is_cloned():
            repo = Repo(self.workspace)
            stash_created = False
            try:
                repo.remotes.origin.set_url(url)
                repo.remotes.origin.fetch()
                stash_created = self._stash_workspace_if_dirty(repo)
                repo.git.checkout(self.default_branch)
                repo.remotes.origin.pull(self.default_branch)
                if stash_created:
                    try:
                        repo.git.stash("pop")
                    except GitCommandError as pop_exc:
                        logger.warning(
                            "After syncing {}, stash pop conflicted — your edits are saved in stash. {}",
                            self.project_slug,
                            pop_exc,
                        )
                logger.info("Pulled latest for {}", self.project_slug)
            except GitCommandError as exc:
                if stash_created:
                    try:
                        repo.git.stash("pop")
                    except GitCommandError:
                        logger.warning("Left stash intact after failed sync for {}", self.project_slug)
                err = str(exc)
                if "would be overwritten by checkout" in err or ("local changes" in err and "Aborting" in err):
                    logger.warning(
                        "Sync failed for {} (workspace state); try approving push or resetting workspace: {}",
                        self.project_slug,
                        exc,
                    )
                    raise
                logger.warning("Pull failed hard, recloning {}: {}", self.project_slug, exc)
                self._reset_workspace_for_clone()
                repo = Repo.clone_from(url, self.workspace)
        else:
            if self._workspace_has_content():
                logger.warning(
                    "Workspace {} exists but is not a git repo; resetting and recloning.",
                    self.workspace,
                )
                self._reset_workspace_for_clone()
            logger.info("Cloning {} into {}", self.repo_url, self.workspace)
            repo = Repo.clone_from(url, self.workspace)
        return repo

    # --- branching ------------------------------------------------------
    def current_branch_name(self) -> Optional[str]:
        """Branch checked out locally, if any."""
        if not self.is_cloned():
            return None
        try:
            return str(Repo(self.workspace).active_branch.name)
        except TypeError:
            return None  # detached HEAD

    def create_branch(self, branch_name: str) -> str:
        repo = Repo(self.workspace)
        stash_created = self._stash_workspace_if_dirty(repo)
        try:
            repo.git.checkout(self.default_branch)
            repo.git.checkout("-B", branch_name)
        finally:
            if stash_created:
                try:
                    repo.git.stash("pop")
                except GitCommandError as pop_exc:
                    logger.warning(
                        "create_branch: could not restore stashed edits on {} ({}) — check git stash.",
                        branch_name,
                        pop_exc,
                    )
        return branch_name

    def commit_all(self, message: str, author_name: str = "AI Engineer", author_email: str = "ai@example.com") -> Optional[str]:
        repo = Repo(self.workspace)
        repo.git.add(A=True)
        if not repo.is_dirty(index=True, working_tree=False, untracked_files=True):
            return None
        with repo.config_writer() as cw:
            cw.set_value("user", "name", author_name)
            cw.set_value("user", "email", author_email)
        commit = repo.index.commit(message)
        return commit.hexsha

    def push(self, branch: str, token: Optional[str] = None) -> None:
        repo = Repo(self.workspace)
        url = self._with_token(self.repo_url, token)
        repo.remotes.origin.set_url(url)
        repo.git.push("--set-upstream", "origin", branch)

    # --- file ops -------------------------------------------------------
    def read_file(self, rel_path: str, max_bytes: int = 200_000) -> str:
        path = self._safe_path(rel_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(rel_path)
        data = path.read_bytes()[:max_bytes]
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data.decode("utf-8", errors="replace")

    def write_file(self, rel_path: str, content: str) -> None:
        path = self._safe_path(rel_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def delete_file(self, rel_path: str) -> None:
        path = self._safe_path(rel_path)
        if path.exists():
            path.unlink()

    def list_files(self, sub_path: str = "", max_files: int = 5000) -> List[str]:
        base = self._safe_path(sub_path) if sub_path else self.workspace
        results: List[str] = []
        ignored = {".git", "node_modules", "__pycache__", ".venv", "dist", "build", ".next"}
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in ignored]
            for fn in files:
                p = Path(root) / fn
                rel = p.relative_to(self.workspace).as_posix()
                results.append(rel)
                if len(results) >= max_files:
                    return results
        return results

    def diff(self, branch: Optional[str] = None) -> str:
        repo = Repo(self.workspace)
        if branch:
            return repo.git.diff(self.default_branch, branch)
        return repo.git.diff()
