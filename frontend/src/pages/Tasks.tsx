import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, Task, PaginatedResponse } from "../api";
import StatusBadge from "../components/StatusBadge";

export default function Tasks() {
  const pageSize = 20;
  const [page, setPage] = useState(1);
  const offset = (page - 1) * pageSize;

  const tasks = useQuery<PaginatedResponse<Task>>({
    queryKey: ["tasks", "all", page, pageSize],
    queryFn: async () => (await api.get(`/tasks?limit=${pageSize}&offset=${offset}`)).data,
    refetchInterval: 5000,
  });

  const totalPages = Math.max(1, Math.ceil((tasks.data?.total ?? 0) / pageSize));

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Tasks</h1>
        <div className="text-xs text-slate-400">
          {tasks.data ? `${offset + 1}-${Math.min(offset + pageSize, tasks.data.total)} of ${tasks.data.total}` : "Loading..."}
        </div>
      </div>
      <div className="card divide-y divide-ink-700">
        {tasks.data?.items.map((t) => (
          <Link to={`/tasks/${t.id}`} key={t.id} className="block px-5 py-4 transition-colors hover:bg-ink-700/40">
            <div className="flex items-center justify-between gap-4">
              <div className="min-w-0">
                <div className="truncate font-medium text-[15px]">{t.request_text}</div>
                <div className="text-xs text-slate-400 mt-0.5">
                  {new Date(t.created_at).toLocaleString()}
                  {t.whatsapp_number && <span className="ml-2 font-mono">{t.whatsapp_number}</span>}
                </div>
              </div>
              <div className="flex items-center gap-2">
                {t.pr_url && <a className="text-xs text-wa-500" href={t.pr_url} target="_blank" rel="noreferrer">PR</a>}
                <StatusBadge status={t.status} />
              </div>
            </div>
          </Link>
        ))}
        {tasks.data?.items.length === 0 && (
          <div className="px-5 py-8 text-center text-sm text-slate-400">No tasks yet.</div>
        )}
      </div>
      <div className="flex items-center justify-end gap-2">
        <button className="btn-ghost" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>
          Previous
        </button>
        <div className="text-sm text-slate-300">
          Page {page} / {totalPages}
        </div>
        <button className="btn-ghost" onClick={() => setPage((p) => (tasks.data?.has_more ? p + 1 : p))} disabled={!tasks.data?.has_more}>
          Next
        </button>
      </div>
    </div>
  );
}
