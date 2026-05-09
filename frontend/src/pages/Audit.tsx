import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, AuditEntry, PaginatedResponse } from "../api";

export default function Audit() {
  const pageSize = 25;
  const [page, setPage] = useState(1);
  const offset = (page - 1) * pageSize;

  const audit = useQuery<PaginatedResponse<AuditEntry>>({
    queryKey: ["audit", page, pageSize],
    queryFn: async () => (await api.get(`/audit?limit=${pageSize}&offset=${offset}`)).data,
    refetchInterval: 5000,
  });

  const totalPages = Math.max(1, Math.ceil((audit.data?.total ?? 0) / pageSize));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Audit log</h1>
        <div className="text-xs text-slate-400">
          {audit.data ? `${offset + 1}-${Math.min(offset + pageSize, audit.data.total)} of ${audit.data.total}` : "Loading..."}
        </div>
      </div>
      <div className="card divide-y divide-ink-700">
        {audit.data?.items.map((a) => (
          <div key={a.id} className="px-5 py-3 grid grid-cols-12 gap-3 text-sm">
            <div className="col-span-3 text-xs text-slate-400 font-mono">{new Date(a.created_at).toLocaleString()}</div>
            <div className="col-span-3 font-mono text-wa-500">{a.action}</div>
            <div className="col-span-2 text-xs text-slate-300">{a.actor_kind}{a.actor_id ? `:${a.actor_id.slice(0, 8)}` : ""}</div>
            <div className="col-span-3 text-xs text-slate-400 truncate">{Object.entries(a.payload || {}).map(([k, v]) => `${k}=${typeof v === "object" ? "…" : String(v)}`).join(" ")}</div>
            <div className="col-span-1 text-right">
              <span className={`badge ${a.success ? "bg-emerald-500/20 text-emerald-300" : "bg-red-500/20 text-red-300"}`}>
                {a.success ? "ok" : "fail"}
              </span>
            </div>
          </div>
        ))}
        {audit.data?.items.length === 0 && (
          <div className="px-5 py-8 text-center text-sm text-slate-400">No entries.</div>
        )}
      </div>
      <div className="flex items-center justify-end gap-2">
        <button
          className="btn-ghost"
          onClick={() => setPage((p) => Math.max(1, p - 1))}
          disabled={page === 1}
        >
          Previous
        </button>
        <div className="text-sm text-slate-300">
          Page {page} / {totalPages}
        </div>
        <button
          className="btn-ghost"
          onClick={() => setPage((p) => (audit.data?.has_more ? p + 1 : p))}
          disabled={!audit.data?.has_more}
        >
          Next
        </button>
      </div>
    </div>
  );
}
