import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { api, Project } from "../api";

export default function ProjectDetail() {
  const { slug = "" } = useParams();
  const qc = useQueryClient();
  const [q, setQ] = useState("");

  const project = useQuery<Project>({
    queryKey: ["project", slug],
    queryFn: async () => (await api.get(`/projects/${slug}`)).data,
  });

  const reindex = useMutation({
    mutationFn: async () => (await api.post(`/projects/${slug}/index`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["project", slug] }),
  });

  const search = useQuery({
    queryKey: ["search", slug, q],
    queryFn: async () =>
      (await api.get(`/projects/${slug}/search`, { params: { q, k: 12 } })).data,
    enabled: q.length > 2,
  });

  if (project.isLoading) return <div>Loading...</div>;
  if (!project.data) return <div>Not found</div>;

  const p = project.data;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">{p.name}</h1>
        <div className="text-sm text-slate-400">{p.repository_url}</div>
      </header>

      <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="card p-4">
          <div className="text-xs text-slate-400 uppercase">Indexed files</div>
          <div className="text-2xl font-semibold mt-1">{p.indexed_files}</div>
          <div className="text-xs text-slate-500">{p.last_indexed_at ?? "never"}</div>
        </div>
        <div className="card p-4">
          <div className="text-xs text-slate-400 uppercase">Default branch</div>
          <div className="text-2xl font-semibold mt-1">{p.default_branch}</div>
        </div>
        <div className="card p-4">
          <div className="text-xs text-slate-400 uppercase">WhatsApp chats</div>
          <div className="text-sm mt-1 font-mono break-all">
            {p.allowed_whatsapp_chats.join(", ") || "—"}
          </div>
        </div>
      </section>

      <section className="card p-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-medium">Code search (RAG)</h2>
          <button onClick={() => reindex.mutate()} className="btn-ghost" disabled={reindex.isPending}>
            {reindex.isPending ? "Queued..." : "Re-index"}
          </button>
        </div>
        <input
          className="input"
          placeholder="What are you looking for? e.g. 'refresh token expiration'"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        {search.data?.results?.length ? (
          <div className="mt-4 space-y-3">
            {search.data.results.map((r: any, i: number) => (
              <div key={i} className="rounded-lg border border-ink-700 p-3">
                <div className="text-sm font-mono text-wa-500">
                  {r.path}:{r.start_line}-{r.end_line}{" "}
                  <span className="text-xs text-slate-400">score {r.score}</span>
                </div>
                <pre className="mt-2 text-xs whitespace-pre-wrap text-slate-300 font-mono">{r.preview}</pre>
              </div>
            ))}
          </div>
        ) : q.length > 2 ? (
          <div className="mt-4 text-sm text-slate-400">{search.isLoading ? "Searching..." : "No results."}</div>
        ) : null}
      </section>
    </div>
  );
}
