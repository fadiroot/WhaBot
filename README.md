# WhaBot

> An AI engineering operator accessible from WhatsApp.

A developer sends a message on WhatsApp such as **"Fix login refresh token bug"** or
**"Summarize PR #42"**. The platform understands the request, identifies the
right project & repository, analyses the code, generates or edits files,
runs validations, opens a Pull Request and reports back — all from chat.

This repo contains a working Phase-1 MVP that wires up:

- **WhatsApp ⇄ WAHA** for messaging ([WAHA docs](https://waha.devlike.pro/))
- **FastAPI + MongoDB + Redis** for the backend
- **OpenAI tool-calling agent** with a sandboxed, audited tool registry
- **GitHub** integration via PyGithub (PRs, workflow runs)
- **Repository indexing** (chunked + OpenAI embeddings) for RAG-style code search
- **React + Tailwind** dashboard (projects, tasks, approvals, audit, live chat)
- **Approval workflow** for sensitive actions (push, deploy)
- **Audit logs** for every tool call and human decision
- **Docker Compose** to spin up MongoDB, Redis, WAHA, backend, and frontend

It is structured to grow into Phase 2/3 (autonomous workflows, CI/CD ops,
multi-agent collaboration) without rewriting the foundation.

---

## Architecture

```
                ┌─────────────────────────┐
   WhatsApp ◀──▶│         WAHA            │ ◀── webhook ──▶ Backend
                │ (HTTP API + QR pairing) │
                └─────────────────────────┘                    │
                                                               ▼
                                                ┌──────────────────────────┐
                                                │         FastAPI           │
                                                │  ┌──────────────────────┐ │
                                                │  │ Webhook router       │ │
                                                │  │ AI Orchestrator      │ │
                                                │  │ Safe Tool Registry   │ │
                                                │  │ Approvals & Audit    │ │
                                                │  │ Project / Task APIs  │ │
                                                │  └──────────────────────┘ │
                                                └────────────┬──────────────┘
                                                             │
                              ┌──────────────────────────────┼─────────────────────────────────┐
                              ▼                              ▼                                 ▼
                   ┌───────────────────┐          ┌─────────────────────┐         ┌───────────────────────┐
                   │ MongoDB           │          │ Sandboxed workspace │         │ GitHub / Git remotes  │
                   │ (users, projects, │          │ /workspaces/<slug>  │         │ branches, PRs, runs   │
                   │  tasks, audit,    │          │ + clone/pull/diff   │         └───────────────────────┘
                   │  approvals,       │          └─────────────────────┘
                   │  code_chunks)     │
                   └───────────────────┘                ▲
                                                        │
                                                        │
                                                ┌────────────────┐
                                                │ React Dashboard│
                                                │  /  Vite + TW  │
                                                └────────────────┘
```

The AI **never** has shell access. Every action goes through one of the
explicitly registered tools in `backend/app/agents/tools.py`. Sensitive tools
(`commit_and_push`, `create_pull_request`) can require human approval, recorded
in MongoDB and revealable via WhatsApp ("approve `<id>`") or the dashboard.

---

## Quick start (Docker)

1. Copy the env file and fill in the secrets:

   ```bash
   cp .env.example .env
   # set OPENAI_API_KEY, GITHUB_TOKEN, SECRET_KEY at minimum
   ```

2. Bring everything up:

   ```bash
   docker compose up -d --build
   ```

3. Services:

   | URL                        | What                          |
   | -------------------------- | ----------------------------- |
   | http://localhost:8088      | React dashboard               |
   | http://localhost:8000/docs | FastAPI Swagger UI            |
   | http://localhost:3000      | WAHA dashboard (scan QR here) |
   | mongodb://localhost:27017  | MongoDB                       |

4. **Register the first user** at http://localhost:8088/register — the first
   user becomes admin.

5. **Pair WhatsApp**:
   - Open http://localhost:3000 (dashboard: `/dashboard/`). Credentials come from `.env`:
     `WAHA_DASHBOARD_USERNAME` / `WAHA_DASHBOARD_PASSWORD` (defaults: `admin` / `choose-a-strong-password`).
   - Start the `default` session and scan the QR with WhatsApp.
   - The webhook is preconfigured (`WHATSAPP_HOOK_URL=http://backend:8000/api/v1/webhooks/waha`).

6. **Add a project** in the dashboard with the GitHub repo URL and (optionally)
   a per-project token. Click "Re-index" to populate the embedding index.

7. **Map a chat** to that project — either by adding a chat id to
   `allowed_whatsapp_chats` or by setting your `whatsapp_number` on the user
   profile and being a member.

8. **Send a WhatsApp message** to the paired number using:

   ```text
   project: <slug> <your prompt>
   ```

   Example:

   ```text
   project: documind create file test4.js with console.log("hello")
   ```

   Other examples:

   - "project: documind summarize PR #12"
   - "project: documind find where refresh tokens are validated"
   - "project: documind add pagination to /users API"

   The bot replies in chat and records every step in the dashboard.

---

## Docker troubleshooting (Apple Silicon / M1–M3)

WAHA’s default **`latest`** image is often **amd64-only**, which leads to either **`no matching manifest for linux/arm64/v8`** or—if you force amd64 via **`platform:`**—Chromium under emulation that **times out** (`Timed out after 30000 ms while waiting for the WS endpoint URL`).

**Fix:** in `.env` set **`WAHA_IMAGE=devlikeapro/waha:arm`** (already in `.env.example`). Compose uses `WAHA_IMAGE` for the `waha` service so Chromium runs **natively** on Apple Silicon. On **Linux or Intel amd64**, leave `WAHA_IMAGE` unset (defaults to `latest`) or set `WAHA_IMAGE=devlikeapro/waha:latest`. See also [WAHA on Docker](https://waha.devlike.pro/blog/waha-on-docker/).

### `failed to stat parent ... overlayfs/snapshots/.../fs` (Mac, after restart)

That message means **Docker Desktop’s internal image/layer store is inconsistent**. Your **build finishes** (`docker compose up --build`); it **fails when creating containers**. Changing `docker-compose.yml` cannot fix this.

Run:

```bash
./scripts/docker-daemon-check.sh
```

If it fails with the same path, Docker Desktop itself must be repaired:

1. **Quit Docker Desktop** completely (menu bar whale → **Quit Docker Desktop**).
2. Open **Docker Desktop** again → **Settings** (gear) → **Troubleshoot** (or the bug icon).
3. Use **Clean / Purge data** or **Reset to factory defaults** (names vary by version). This wipes Docker’s images, containers, and **named volumes** (your project files on disk are unchanged).
4. After Docker is healthy: `docker compose up -d --build` from this repo (re-pull images; re-seed DB/WAHA if you rely on volumes).

**Workaround:** install **[OrbStack](https://orbstack.dev)** (or another Docker-compatible engine), start it instead of Docker Desktop, then run the same compose commands—it uses its own VM and avoids the corrupted Docker Desktop disk.

### WhatsApp webhook loop / duplicate replies

If you see repeated bot replies in a short burst, it is usually WAHA echoing outbound messages back to the webhook.

This repository includes guards to prevent that:

- ignore bot echo events for recent outbound messages
- ignore duplicate webhook message IDs
- ignore self-originated `@lid` echo events in WEBJS mode

If duplicates still happen, update to the latest `main` and rebuild:

```bash
docker compose up -d --build --force-recreate backend waha
```

### No backend logs when sending WhatsApp message

1. Confirm WAHA session is connected (`WORKING`) in dashboard.
2. Confirm webhook settings in `docker-compose.yml`:
   - `WHATSAPP_HOOK_URL=http://backend:8000/api/v1/webhooks/waha`
   - `WHATSAPP_HOOK_EVENTS=message,message.any`
3. Tail logs:

```bash
docker compose logs -f waha backend
```

4. Send a message and verify WAHA shows `WebhookSender ... POST request ... 200`.

---

## Ollama (local free LLM)

1. Install [Ollama](https://ollama.com) and pull models:

   ```bash
   ollama pull llama3.2
   ollama pull nomic-embed-text
   ```

   `nomic-embed-text` powers **code search / Re-index** (same OpenAI-compatible `/v1/embeddings` API).

2. In `.env` (use these values if the **backend runs in Docker** and Ollama runs on your machine):

   ```env
   LLM_PROVIDER=openai
   OPENAI_API_KEY=ollama
   OPENAI_BASE_URL=http://host.docker.internal:11434/v1
   OPENAI_MODEL=llama3.2
   OPENAI_EMBEDDINGS_MODEL=nomic-embed-text
   ```

   If `AZURE_OPENAI_*` is still set, either remove it or keep `LLM_PROVIDER=openai` so Azure is not selected by `auto`.

3. If you run the backend **on the host** (not Docker), use:

   ```env
   OPENAI_BASE_URL=http://127.0.0.1:11434/v1
   ```

4. Restart the stack: `docker compose up -d --build backend`.

`docker-compose.yml` adds `extra_hosts` so **Linux** Docker can resolve `host.docker.internal` to your host (Ollama’s default port **11434**).

**Tool calling:** Many local models (e.g. `llama3.2`) ignore OpenAI’s `tools=` parameter and print fake JSON in prose. With `OPENAI_BASE_URL` pointing at Ollama, the backend sets **`LLM_NATIVE_TOOLS=auto`** to **disable** native tools and use a strict **JSON tool protocol** instead. For OpenAI/Azure, native tools stay enabled. Override with `LLM_NATIVE_TOOLS=true` or `false` if needed.

---

## Development (without Docker)

Backend:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env  # then edit
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev   # → http://localhost:5173 (proxies /api to localhost:8000)
```

You'll still need MongoDB, Redis, and WAHA running locally (the easiest is
`docker compose up mongo redis waha`).

---

## Available AI tools (safe-listed)

Every tool has a JSON schema fed to the LLM via OpenAI function-calling.

| Tool                       | Purpose                                                | Sensitive? |
| -------------------------- | ------------------------------------------------------ | :--------: |
| `search_code`              | Semantic + keyword search over indexed code            |     —      |
| `list_files`               | List files in the project workspace                    |     —      |
| `read_file`                | Read a file (sandbox-checked path, capped size)        |     —      |
| `write_file`               | Create/overwrite a file in the project workspace       |     —      |
| `create_branch`            | Create a branch off `default_branch`                   |     —      |
| `commit_and_push`          | Stage, commit, push the branch                         |    **✓**   |
| `create_pull_request`      | Open a GitHub PR                                       |    **✓**   |
| `summarize_pull_request`   | Fetch PR title/body/files                              |     —      |
| `list_workflow_runs`       | Recent GitHub Actions runs                             |     —      |
| `workflow_run_details`     | Per-job/step status for a run                          |     —      |
| `finish`                   | Return the user-facing message and stop the loop       |     —      |

Add your own in `backend/app/agents/tools.py` — declare the spec, write the
implementation, and register it in `TOOL_DISPATCH`.

---

## Security notes

- The AI is given **no shell, no eval, no arbitrary HTTP**.
- File access is sandboxed to `WORKSPACE_ROOT/<project_slug>` with path-traversal checks.
- `commit_and_push` and `create_pull_request` are flagged sensitive; a row is
  written to the `approvals` collection and the agent pauses. Admins approve
  via dashboard or by replying `approve <id>` on WhatsApp.
- All tool invocations + approvals are written to `audit_logs`.
- Per-project GitHub tokens are stored in MongoDB. **In production, encrypt
  them at rest** (e.g. via AWS KMS / sops / a secrets manager) — a TODO marker.
- Do not commit real tokens or secrets to this repository. Rotate leaked credentials immediately.
- WAHA webhook calls can be authenticated via `WAHA_WEBHOOK_SECRET`
  (set both in backend env and as `WHATSAPP_HOOK_HMAC_KEY` on WAHA).

---

## Contributing

Contributions are welcome.

1. Fork the repository.
2. Create a feature branch.
3. Run the stack and test your change locally.
4. Open a pull request with:
   - clear problem statement
   - what changed and why
   - test evidence (logs, screenshots, or curl output)

---

## Project layout

```
backend/
  app/
    main.py                  FastAPI factory + lifespan
    config.py                Pydantic settings
    core/                    db, logger, security (JWT, RBAC)
    models/                  user, project, task, approval, audit, code_chunk
    services/                whatsapp, git_service, github_service, repo_indexer,
                             approval_service, audit_service, project_resolver
    agents/                  tools.py, orchestrator.py
    api/                     auth, users, projects, tasks, approvals, audit, webhooks
  Dockerfile
  requirements.txt

frontend/
  src/
    pages/                   Login, Register, Dashboard, Chat, Projects,
                             ProjectDetail, Tasks, TaskDetail, Approvals,
                             Audit, Settings
    components/              Layout, StatusBadge
    api.ts, store.ts, App.tsx, main.tsx
  Dockerfile, nginx.conf, vite.config.ts, tailwind.config.js

docker-compose.yml           mongo + redis + waha + backend + frontend
.env.example
README.md
```

---

## Roadmap

- **Phase 1 (this MVP)** — chat, code search, PR summaries, simple PR generation,
  approvals, audit, dashboard.
- **Phase 2** — running tests/builds in a sandboxed runner before push, richer
  diffs, CI failure root-cause analysis, multi-step task graphs.
- **Phase 3** — multi-agent collaboration (planner ↔ coder ↔ reviewer),
  Kubernetes / Jenkins / Azure DevOps integration, autonomous deploys with
  guardrails, cross-repo refactors.

---

## Credits

Inspired by the WAHA project ([waha.devlike.pro](https://waha.devlike.pro/))
for the WhatsApp HTTP API layer.
