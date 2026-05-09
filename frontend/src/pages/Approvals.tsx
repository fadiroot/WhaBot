import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, Approval, PaginatedResponse } from "../api";
import StatusBadge from "../components/StatusBadge";

export default function Approvals() {
  const qc = useQueryClient();
  const pageSize = 15;
  const [page, setPage] = useState(1);
  const offset = (page - 1) * pageSize;

  const approvals = useQuery<PaginatedResponse<Approval>>({
    queryKey: ["approvals", page, pageSize],
    queryFn: async () => (await api.get(`/approvals?limit=${pageSize}&offset=${offset}`)).data,
    refetchInterval: 5000,
  });
  const totalPages = Math.max(1, Math.ceil((approvals.data?.total ?? 0) / pageSize));

  const decide = useMutation({
    mutationFn: async ({ id, decision }: { id: string; decision: "approve" | "reject" }) =>
      (await api.post(`/approvals/${id}/${decision}`, {})).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["approvals"] }),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <h1 className="text-2xl font-semibold">Approvals</h1>
        <div className="text-xs text-slate-400">
          {approvals.data ? `${offset + 1}-${Math.min(offset + pageSize, approvals.data.total)} of ${approvals.data.total}` : "Loading..."}
        </div>
      </div>
      <div className="card divide-y divide-ink-700">
        {approvals.data?.items.map((a) => (
          <div key={a.id} className="px-5 py-4">
            <div className="flex items-center justify-between gap-4">
              <div className="min-w-0">
                <div className="font-medium">{a.summary}</div>
                <div className="text-xs text-slate-400 mt-0.5 font-mono">{a.action}</div>
                <div className="text-xs text-slate-500">{new Date(a.created_at).toLocaleString()}</div>
              </div>
              <div className="flex items-center gap-2">
                <StatusBadge status={a.status} />
                {a.status === "pending" && (
                  <>
                    <button className="btn-primary" onClick={() => decide.mutate({ id: a.id, decision: "approve" })}>
                      Approve
                    </button>
                    <button className="btn-danger" onClick={() => decide.mutate({ id: a.id, decision: "reject" })}>
                      Reject
                    </button>
                  </>
                )}
              </div>
            </div>
            {a.payload && Object.keys(a.payload).length > 0 && (
              <pre className="mt-2 text-xs font-mono text-slate-400 overflow-x-auto">
                {JSON.stringify(a.payload, null, 2)}
              </pre>
            )}
          </div>
        ))}
        {approvals.data?.items.length === 0 && (
          <div className="px-5 py-8 text-center text-sm text-slate-400">No approvals.</div>
        )}
      </div>
      <div className="flex items-center justify-end gap-2">
        <button className="btn-ghost" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>
          Previous
        </button>
        <div className="text-sm text-slate-300">
          Page {page} / {totalPages}
        </div>
        <button className="btn-ghost" onClick={() => setPage((p) => (approvals.data?.has_more ? p + 1 : p))} disabled={!approvals.data?.has_more}>
          Next
        </button>
      </div>
    </div>
  );
}
