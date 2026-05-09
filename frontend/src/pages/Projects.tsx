import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, Project, PaginatedResponse } from "../api";

export default function Projects() {
  const qc = useQueryClient();
  const pageSize = 12;
  const [page, setPage] = useState(1);
  const offset = (page - 1) * pageSize;
  const projects = useQuery<PaginatedResponse<Project>>({
    queryKey: ["projects", page, pageSize],
    queryFn: async () => (await api.get(`/projects?limit=${pageSize}&offset=${offset}`)).data,
  });
  const totalPages = Math.max(1, Math.ceil((projects.data?.total ?? 0) / pageSize));

  const [show, setShow] = useState(false);
  const [form, setForm] = useState({
    slug: "",
    name: "",
    repository_url: "",
    default_branch: "main",
    description: "",
    github_token: "",
    allowed_whatsapp_chats: "",
  });

  const create = useMutation({
    mutationFn: async () => {
      const payload: any = {
        slug: form.slug,
        name: form.name,
        repository_url: form.repository_url,
        default_branch: form.default_branch || "main",
        description: form.description || undefined,
        github_token: form.github_token || undefined,
        allowed_whatsapp_chats: form.allowed_whatsapp_chats
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      };
      return (await api.post("/projects", payload)).data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      setShow(false);
      setPage(1);
      setForm({
        slug: "",
        name: "",
        repository_url: "",
        default_branch: "main",
        description: "",
        github_token: "",
        allowed_whatsapp_chats: "",
      });
    },
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Projects</h1>
        <button className="btn-primary" onClick={() => setShow((v) => !v)}>
          {show ? "Cancel" : "+ New project"}
        </button>
      </div>

      {show && (
        <form
          className="card p-5 grid grid-cols-1 md:grid-cols-2 gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <div>
            <label className="label">Slug *</label>
            <input className="input" required value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} />
          </div>
          <div>
            <label className="label">Name *</label>
            <input className="input" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          <div className="md:col-span-2">
            <label className="label">Repository URL *</label>
            <input className="input" placeholder="https://github.com/org/repo.git" required value={form.repository_url} onChange={(e) => setForm({ ...form, repository_url: e.target.value })} />
          </div>
          <div>
            <label className="label">Default branch</label>
            <input className="input" value={form.default_branch} onChange={(e) => setForm({ ...form, default_branch: e.target.value })} />
          </div>
          <div>
            <label className="label">GitHub token (per-project)</label>
            <input className="input" type="password" value={form.github_token} onChange={(e) => setForm({ ...form, github_token: e.target.value })} />
          </div>
          <div className="md:col-span-2">
            <label className="label">Description</label>
            <textarea className="input" rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </div>
          <div className="md:col-span-2">
            <label className="label">Allowed WhatsApp chat IDs (comma-separated)</label>
            <input className="input" placeholder="1234567890@c.us, 9999@g.us" value={form.allowed_whatsapp_chats} onChange={(e) => setForm({ ...form, allowed_whatsapp_chats: e.target.value })} />
          </div>
          <div className="md:col-span-2">
            <button className="btn-primary" disabled={create.isPending}>
              {create.isPending ? "Creating..." : "Create project"}
            </button>
            {create.error && <span className="ml-3 text-sm text-red-300">{(create.error as any)?.response?.data?.detail || (create.error as Error).message}</span>}
          </div>
        </form>
      )}

      <div className="card divide-y divide-ink-700">
        {projects.data?.items.map((p) => (
          <Link to={`/projects/${p.slug}`} key={p.id} className="block px-5 py-4 hover:bg-ink-700/40">
            <div className="flex items-center justify-between">
              <div>
                <div className="font-medium">{p.name} <span className="text-xs text-slate-400">({p.slug})</span></div>
                <div className="text-xs text-slate-400">{p.repository_url}</div>
              </div>
              <div className="text-xs text-slate-400">
                {p.indexed_files} indexed files
              </div>
            </div>
          </Link>
        ))}
        {projects.data && projects.data.items.length === 0 && (
          <div className="px-5 py-8 text-center text-sm text-slate-400">No projects yet.</div>
        )}
      </div>
      <div className="flex items-center justify-between">
        <div className="text-xs text-slate-400">
          {projects.data ? `${offset + 1}-${Math.min(offset + pageSize, projects.data.total)} of ${projects.data.total}` : "Loading..."}
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-ghost" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>
            Previous
          </button>
          <div className="text-sm text-slate-300">
            Page {page} / {totalPages}
          </div>
          <button className="btn-ghost" onClick={() => setPage((p) => (projects.data?.has_more ? p + 1 : p))} disabled={!projects.data?.has_more}>
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
