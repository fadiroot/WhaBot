import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import ThemeToggle from "../components/ThemeToggle";

export default function Register() {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [whatsapp, setWhatsapp] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const nav = useNavigate();

  async function submit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setLoading(true);
    try {
      await api.post("/auth/register", {
        email,
        name,
        password,
        whatsapp_number: whatsapp || undefined,
      });
      nav("/login");
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
        <div className="text-lg font-semibold mb-1">Create account</div>
        <div className="text-xs text-slate-400 mb-6">The first registered user becomes admin.</div>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="label">Name</label>
            <input className="input" required value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div>
            <label className="label">Email</label>
            <input className="input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div>
            <label className="label">Password</label>
            <input className="input" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          <div>
            <label className="label">WhatsApp number (E.164, optional)</label>
            <input className="input" placeholder="+15551234567" value={whatsapp} onChange={(e) => setWhatsapp(e.target.value)} />
          </div>
          {err && <div className="rounded-lg bg-red-500/10 border border-red-500/30 px-3 py-2 text-sm text-red-300">{err}</div>}
          <button className="btn-primary w-full" disabled={loading}>{loading ? "..." : "Create account"}</button>
        </form>
        <div className="text-xs text-slate-400 mt-4">
          Already have one? <Link className="text-wa-500" to="/login">Sign in</Link>
        </div>
      </div>
      </div>
    </div>
  );
}
