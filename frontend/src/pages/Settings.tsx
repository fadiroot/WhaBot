import { useAuth } from "../store";

export default function Settings() {
  const user = useAuth((s) => s.user);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Settings</h1>

      <section className="card p-5">
        <h2 className="font-medium mb-3">Account</h2>
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div className="text-slate-400">Name</div>
          <div>{user?.name}</div>
          <div className="text-slate-400">Email</div>
          <div>{user?.email}</div>
          <div className="text-slate-400">Roles</div>
          <div>{user?.roles.join(", ")}</div>
          <div className="text-slate-400">WhatsApp</div>
          <div className="font-mono">{user?.whatsapp_number || "—"}</div>
        </div>
      </section>

      <section className="card p-5">
        <h2 className="font-medium mb-2">Connecting WhatsApp via WAHA</h2>
        <ol className="list-decimal pl-5 space-y-2 text-sm text-slate-300">
          <li>
            Run WAHA next to this app (the bundled <code className="font-mono">docker-compose.yml</code> already does it).
            It will be available at <code className="font-mono">http://localhost:3000</code>.
          </li>
          <li>
            Open the WAHA dashboard and start the <code className="font-mono">default</code> session, then scan the QR with WhatsApp.
          </li>
          <li>
            Configure the WAHA webhook to point at:{" "}
            <code className="font-mono">{`${location.origin}/api/v1/webhooks/waha`}</code>.
            If you set a webhook secret, send it as the <code className="font-mono">X-Webhook-Secret</code> header.
          </li>
          <li>
            On the project page, list the chat ids that should be allowed to talk to it
            (e.g. <code className="font-mono">15551234567@c.us</code> for individuals,{" "}
            <code className="font-mono">…@g.us</code> for groups). Or map your user's WhatsApp number under your account.
          </li>
          <li>
            From WhatsApp, send a message such as: <em>"project: my-app fix login refresh bug"</em>.
            The AI reads, edits, commits, opens a PR, and replies in chat. Sensitive actions wait for your approval.
          </li>
        </ol>
      </section>

      <section className="card p-5">
        <h2 className="font-medium mb-2">Environment</h2>
        <p className="text-sm text-slate-300 mb-2">
          The backend reads its configuration from environment variables (see <code className="font-mono">.env.example</code>).
          Required:
        </p>
        <ul className="text-sm list-disc pl-5 space-y-1 text-slate-300">
          <li><code className="font-mono">OPENAI_API_KEY</code> – LLM + embeddings</li>
          <li><code className="font-mono">GITHUB_TOKEN</code> – default token for git/PR operations (or per-project)</li>
          <li><code className="font-mono">WAHA_BASE_URL</code> / <code className="font-mono">WAHA_API_KEY</code> – WAHA host</li>
          <li><code className="font-mono">SECRET_KEY</code> – JWT signing key (rotate in production)</li>
        </ul>
      </section>
    </div>
  );
}
