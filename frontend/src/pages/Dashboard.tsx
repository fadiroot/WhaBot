import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, Project, Task, Approval, PaginatedResponse } from "../api";
import StatusBadge from "../components/StatusBadge";

export default function Dashboard() {
  const projects = useQuery<PaginatedResponse<Project>>({
    queryKey: ["projects"],
    queryFn: async () => (await api.get("/projects?limit=50&offset=0")).data,
  });
  const tasks = useQuery<PaginatedResponse<Task>>({
    queryKey: ["tasks"],
    queryFn: async () => (await api.get("/tasks?limit=10&offset=0")).data,
  });
  const approvals = useQuery<PaginatedResponse<Approval>>({
    queryKey: ["approvals", "pending"],
    queryFn: async () => (await api.get("/approvals?status=pending&limit=20&offset=0")).data,
  });

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold">Overview</h1>
        <p className="text-slate-400 text-sm">Central workspace for project operations and delivery workflows.</p>
      </header>

      <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="card p-5">
          <div className="text-xs uppercase text-slate-400">Projects</div>
          <div className="text-3xl font-semibold mt-1">{projects.data?.total ?? "·"}</div>
          <Link to="/projects" className="text-wa-500 text-sm">manage →</Link>
        </div>
        <div className="card p-5">
          <div className="text-xs uppercase text-slate-400">Recent tasks</div>
          <div className="text-3xl font-semibold mt-1">{tasks.data?.total ?? "·"}</div>
          <Link to="/tasks" className="text-wa-500 text-sm">view →</Link>
        </div>
        <div className="card p-5">
          <div className="text-xs uppercase text-slate-400">Pending approvals</div>
          <div className="text-3xl font-semibold mt-1">{approvals.data?.total ?? "·"}</div>
          <Link to="/approvals" className="text-wa-500 text-sm">review →</Link>
        </div>
      </section>

      <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-medium">Recent tasks</h2>
            <Link to="/tasks" className="text-xs text-wa-500">all →</Link>
          </div>
          <div className="space-y-2">
            {tasks.data?.items.slice(0, 8).map((t) => (
              <Link
                to={`/tasks/${t.id}`}
                key={t.id}
                className="block rounded-lg border border-ink-700 p-3 hover:bg-ink-700/40"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm truncate">{t.request_text}</div>
                  <StatusBadge status={t.status} />
                </div>
                <div className="mt-1 text-xs text-slate-400">
                  {new Date(t.created_at).toLocaleString()}
                  {t.pr_url && (
                    <a className="ml-2 text-wa-500" href={t.pr_url} target="_blank" rel="noreferrer">PR</a>
                  )}
                </div>
              </Link>
            ))}
            {!tasks.data?.items.length && <div className="text-sm text-slate-400">No tasks yet.</div>}
          </div>
        </div>

        <div className="card p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="font-medium">Projects</h2>
            <Link to="/projects" className="text-xs text-wa-500">manage →</Link>
          </div>
          <div className="space-y-2">
            {projects.data?.items.map((p) => (
              <Link key={p.id} to={`/projects/${p.slug}`} className="block rounded-lg border border-ink-700 p-3 hover:bg-ink-700/40">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-medium">{p.name}</div>
                    <div className="text-xs text-slate-400">{p.repository_url}</div>
                  </div>
                  <span className="badge bg-ink-700 text-slate-300">{p.indexed_files} files</span>
                </div>
              </Link>
            ))}
            {!projects.data?.items.length && (
              <div className="text-sm text-slate-400">
                No projects yet. <Link to="/projects" className="text-wa-500">Add one →</Link>
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
