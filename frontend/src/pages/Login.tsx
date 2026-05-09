import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../store";
import ThemeToggle from "../components/ThemeToggle";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const setAuth = useAuth((s) => s.setAuth);
  const nav = useNavigate();

  async function submit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setLoading(true);
    try {
      const form = new URLSearchParams();
      form.set("username", email);
      form.set("password", password);
      const { data } = await api.post("/auth/login", form, {
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
      });
      setAuth(data.access_token, data.user);
      nav("/");
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen grid place-items-center p-6">
      <div className="w-full max-w-md space-y-3">
        <div className="flex justify-end">
          <ThemeToggle />
        </div>
        <div className="card p-8">
        <div className="flex items-center gap-3 mb-6">
          <div className="h-10 w-10 rounded-lg bg-wa-500 grid place-items-center text-black font-bold">EC</div>
          <div>
            <div className="text-lg font-semibold">Engineering Console</div>
            <div className="text-xs text-slate-400">Sign in to manage projects</div>
          </div>
        </div>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="label">Email</label>
            <input className="input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div>
            <label className="label">Password</label>
            <input className="input" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          {err && <div className="rounded-lg bg-red-500/10 border border-red-500/30 px-3 py-2 text-sm text-red-300">{err}</div>}
          <button className="btn-primary w-full" disabled={loading}>{loading ? "..." : "Sign in"}</button>
        </form>
        <div className="text-xs text-slate-400 mt-4">
          No account? <Link className="text-wa-500" to="/register">Create one</Link>
          <span className="text-slate-500"> · the first user becomes admin.</span>
        </div>
      </div>
      </div>
    </div>
  );
}
