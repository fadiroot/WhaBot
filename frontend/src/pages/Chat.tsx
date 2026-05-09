import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, Project, Task, PaginatedResponse } from "../api";
import StatusBadge from "../components/StatusBadge";

interface Bubble {
  role: "user" | "assistant" | "system";
  text: string;
  task_id?: string;
}

export default function Chat() {
  const [text, setText] = useState("");
  const [slug, setSlug] = useState("");
  const [bubbles, setBubbles] = useState<Bubble[]>([
    {
      role: "assistant",
      text:
        "Hi 👋 — Pick a project from the menu above, **or** type your project **slug** (e.g. `documind`) before your request. Then describe what to do: fix a bug, summarize a PR, etc.",
    },
  ]);
  const [pollId, setPollId] = useState<string | null>(null);
  const scroller = useRef<HTMLDivElement>(null);

  const projects = useQuery<PaginatedResponse<Project>>({
    queryKey: ["projects"],
    queryFn: async () => (await api.get("/projects?limit=100&offset=0")).data,
  });

  useEffect(() => {
    if (!slug && projects.data?.items.length) setSlug(projects.data.items[0].slug);
  }, [projects.data, slug]);

  const create = useMutation({
    mutationFn: async () => {
      const res = await api.post("/tasks", { request_text: text, project_slug: slug || undefined });
      return res.data as { id: string; status: string };
    },
    onSuccess: (data) => {
      setBubbles((b) => [...b, { role: "user", text }, { role: "assistant", text: "Thinking…", task_id: data.id }]);
      setText("");
      setPollId(data.id);
    },
  });

  const poll = useQuery<Task>({
    queryKey: ["chat-task", pollId],
    queryFn: async () => (await api.get(`/tasks/${pollId}`)).data,
    enabled: !!pollId,
    refetchInterval: 1500,
  });

  useEffect(() => {
    if (!poll.data) return;
    const t = poll.data;
    if (["succeeded", "failed", "awaiting_approval", "cancelled"].includes(t.status)) {
      setBubbles((b) => {
        const arr = [...b];
        let idx = -1;
        for (let i = arr.length - 1; i >= 0; i--) {
          if (arr[i].task_id === t.id) {
            idx = i;
            break;
          }
        }
        if (idx >= 0) arr[idx] = { role: "assistant", text: t.result || t.error || "Done.", task_id: t.id };
        return arr;
      });
      setPollId(null);
    }
  }, [poll.data]);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [bubbles]);

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Try it</h1>
        <select
          className="input max-w-xs min-w-[12rem]"
          value={slug}
          onChange={(e) => setSlug(e.target.value)}
          title="Optional if your message starts with the project slug"
        >
          <option value="">— pick a project (optional) —</option>
          {projects.data?.items.map((p) => (
            <option key={p.id} value={p.slug}>
              {p.name} ({p.slug})
            </option>
          ))}
        </select>
      </header>

      <div className="card flex flex-col h-[70vh]">
        <div ref={scroller} className="flex-1 overflow-y-auto scrollbar-thin p-5 space-y-3">
          {bubbles.map((b, i) => (
            <div key={i} className={`max-w-[80%] ${b.role === "user" ? "ml-auto" : ""}`}>
              <div className={`rounded-2xl px-4 py-2 text-sm whitespace-pre-wrap ${
                b.role === "user" ? "bg-wa-500 text-black" : "bg-ink-700"
              }`}>
                {b.text}
              </div>
              {b.task_id && poll.data?.id === b.task_id && (
                <div className="text-xs mt-1 text-slate-400 flex items-center gap-2">
                  <StatusBadge status={poll.data.status} />
                  <Link to={`/tasks/${b.task_id}`} className="text-wa-500">view steps →</Link>
                </div>
              )}
            </div>
          ))}
        </div>
        <form
          className="border-t border-ink-700 p-3 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!text.trim()) return;
            create.mutate();
          }}
        >
          <input
            className="input flex-1"
            placeholder="e.g. Fix login refresh token bug"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <button className="btn-primary" disabled={create.isPending || !text.trim()}>
            {create.isPending ? "Sending..." : "Send"}
          </button>
        </form>
      </div>
    </div>
  );
}
