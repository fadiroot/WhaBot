"""Lightweight repository indexer.

For the MVP we keep things simple and dependency-light:
- Walk the workspace skipping vendor / build dirs and binary files.
- Split each file into ~80-line chunks (or by top-level blocks for some languages).
- Compute embeddings via OpenAI (text-embedding-3-small) and store in Mongo.
- Search via cosine similarity in Python (Mongo can also do $vectorSearch on Atlas).

When pgvector / a vector DB is plugged in later, swap `vector_search` to use it.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from app.config import get_async_openai_client, get_settings, llm_embeddings_model, llm_is_configured
from app.core.database import get_db
from app.core.logger import logger
from app.services.git_service import GitService

# File extensions we will index. Keep this conservative.
INDEXABLE_EXTS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rb", ".php",
    ".cs", ".cpp", ".c", ".h", ".hpp", ".rs", ".swift", ".kt",
    ".sql", ".md", ".yml", ".yaml", ".json", ".toml",
    ".html", ".css", ".scss",
}
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
    ".next", ".turbo", "target", "out", "coverage",
}
MAX_FILE_BYTES = 200_000
CHUNK_LINES = 80
CHUNK_OVERLAP = 10


def _iter_indexable_files(root: Path) -> Iterable[Path]:
    for cur, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in INDEXABLE_EXTS:
                continue
            p = Path(cur) / fn
            try:
                if p.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield p


def _chunk_lines(lines: List[str]) -> List[Tuple[int, int, str]]:
    """Return list of (start_line, end_line, content) tuples, 1-indexed inclusive."""
    if not lines:
        return []
    chunks: List[Tuple[int, int, str]] = []
    n = len(lines)
    i = 0
    while i < n:
        end = min(i + CHUNK_LINES, n)
        content = "\n".join(lines[i:end])
        chunks.append((i + 1, end, content))
        if end == n:
            break
        i = end - CHUNK_OVERLAP
        if i < 0:
            i = 0
    return chunks


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0 or nb == 0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


class RepoIndexer:
    """Embeds repo files and supports semantic search."""

    def __init__(self, project_id: str, project_slug: str, repo_url: str, default_branch: str = "main", github_token: Optional[str] = None):
        self.project_id = project_id
        self.git = GitService(project_slug, repo_url, default_branch)
        self.github_token = github_token
        self.settings = get_settings()

    async def _embed(self, texts: List[str]) -> List[List[float]]:
        if not llm_is_configured(self.settings):
            return [[0.0] * 8 for _ in texts]
        client = get_async_openai_client()
        # Batch in groups of 64
        out: List[List[float]] = []
        BATCH = 64
        emb_model = llm_embeddings_model(self.settings)
        for i in range(0, len(texts), BATCH):
            batch = texts[i : i + BATCH]
            try:
                resp = await client.embeddings.create(
                    model=emb_model,
                    input=batch,
                )
                out.extend([d.embedding for d in resp.data])
            except Exception as exc:  # noqa: BLE001 — OpenAI/Ollama/network
                logger.warning(
                    "Embeddings failed for model {} (RAG/search degrades to keyword match): {}",
                    emb_model,
                    exc,
                )
                out.extend([[0.0] * 8 for _ in batch])
        return out

    async def index(self) -> Dict[str, int]:
        """Clone/pull and re-index. Returns {files, chunks}."""
        self.git.clone_or_pull(token=self.github_token)
        db = get_db()
        await db.code_chunks.delete_many({"project_id": self.project_id})

        files = list(_iter_indexable_files(self.git.workspace))
        logger.info("Indexing {} files for project {}", len(files), self.project_id)

        all_chunks: List[Dict] = []
        for p in files:
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = p.relative_to(self.git.workspace).as_posix()
            sha = hashlib.sha1(text.encode("utf-8")).hexdigest()
            for start, end, content in _chunk_lines(text.splitlines()):
                all_chunks.append(
                    {
                        "project_id": self.project_id,
                        "path": rel,
                        "language": p.suffix.lstrip("."),
                        "start_line": start,
                        "end_line": end,
                        "content": content,
                        "sha": sha,
                    }
                )

        # Embeddings
        texts = [f"{c['path']}\n{c['content']}" for c in all_chunks]
        if texts:
            embeddings = await self._embed(texts)
            for c, emb in zip(all_chunks, embeddings):
                c["embedding"] = emb

        if all_chunks:
            await db.code_chunks.insert_many(all_chunks)

        await db.projects.update_one(
            {"_id": self.project_id},
            {"$set": {"indexed_files": len(files), "last_indexed_at": _now_iso()}},
        )
        logger.success("Indexed {} files / {} chunks", len(files), len(all_chunks))
        return {"files": len(files), "chunks": len(all_chunks)}

    async def search(self, query: str, k: int = 8) -> List[Dict]:
        db = get_db()
        # Try embedding-based search first
        emb_list = await self._embed([query])
        q_emb = emb_list[0] if emb_list else []
        cursor = db.code_chunks.find({"project_id": self.project_id})
        scored: List[Tuple[float, Dict]] = []
        async for doc in cursor:
            score = _cosine(q_emb, doc.get("embedding", [])) if q_emb else 0.0
            if score == 0.0:
                # Lightweight fallback: substring contains
                ql = query.lower()
                if ql in doc.get("content", "").lower() or ql in doc.get("path", "").lower():
                    score = 0.1
            if score > 0:
                scored.append((score, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "path": d["path"],
                "start_line": d["start_line"],
                "end_line": d["end_line"],
                "score": round(s, 4),
                "preview": d["content"][:600],
            }
            for s, d in scored[:k]
        ]


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
