import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { api, Task } from "../api";
import StatusBadge from "../components/StatusBadge";

export default function TaskDetail() {
  const { id = "" } = useParams();
  const task = useQuery<Task>({
    queryKey: ["task", id],
    queryFn: async () => (await api.get(`/tasks/${id}`)).data,
    refetchInterval: (q) => {
      const s = (q.state.data as Task | undefined)?.status;
      return s && ["succeeded", "failed", "cancelled"].includes(s) ? false : 2000;
    },
  });

  if (task.isLoading) return <div>Loading...</div>;
  if (!task.data) return <div>Not found</div>;

  const t = task.data;

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold break-words">{t.request_text}</h1>
          <div className="text-xs text-slate-400 mt-1">
            {new Date(t.created_at).toLocaleString()}
            {t.whatsapp_number && <span className="ml-2 font-mono">{t.whatsapp_number}</span>}
          </div>
        </div>
        <StatusBadge status={t.status} />
      </header>

      {t.pr_url && (
        <a href={t.pr_url} target="_blank" rel="noreferrer" className="card p-4 block hover:bg-ink-700/40">
          <div className="text-xs text-slate-400 uppercase">Pull request</div>
          <div className="text-wa-500 font-mono text-sm mt-1 break-all">{t.pr_url}</div>
        </a>
      )}

      {t.result && (
        <section className="card p-5">
          <h2 className="font-medium mb-2">Final result</h2>
          <div className="whitespace-pre-wrap text-sm">{t.result}</div>
        </section>
      )}

      {t.error && (
        <section className="card p-5 border-red-500/30">
          <h2 className="font-medium mb-2 text-red-300">Error</h2>
          <div className="whitespace-pre-wrap text-sm text-red-200">{t.error}</div>
        </section>
      )}

      <section>
        <h2 className="font-medium mb-2">Reasoning steps</h2>
        <div className="space-y-2">
          {t.steps.map((s, i) => (
            <div key={i} className="card p-3">
              <div className="flex items-center gap-2 mb-1">
                <span className="badge bg-ink-700 text-slate-300">{s.kind}</span>
                {s.name && <span className="text-xs font-mono text-wa-500">{s.name}</span>}
                <span className="text-xs text-slate-500 ml-auto">{s.created_at}</span>
              </div>
              {s.content && <div className="text-sm whitespace-pre-wrap">{s.content}</div>}
              {s.arguments && (
                <pre className="mt-1 text-xs font-mono text-slate-400 overflow-x-auto">
                  {JSON.stringify(s.arguments, null, 2)}
                </pre>
              )}
              {s.output && (
                <pre className="mt-1 text-xs font-mono text-slate-400 max-h-60 overflow-auto">
                  {s.output}
                </pre>
              )}
            </div>
          ))}
          {t.steps.length === 0 && <div className="text-sm text-slate-400">No steps yet.</div>}
        </div>
      </section>
    </div>
  );
}
