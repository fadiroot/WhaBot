import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../store";
import clsx from "clsx";
import ThemeToggle from "./ThemeToggle";

const links = [
  { to: "/", label: "Overview" },
  { to: "/chat", label: "Try It" },
  { to: "/projects", label: "Projects" },
  { to: "/tasks", label: "Tasks" },
  { to: "/approvals", label: "Approvals" },
  { to: "/audit", label: "Audit" },
  { to: "/settings", label: "Settings" },
];

export default function Layout() {
  const { user, clear } = useAuth();
  const nav = useNavigate();

  return (
    <div className="min-h-screen flex app-shell">
      <aside className="w-64 shrink-0 border-r border-ink-700 bg-ink-800/40 flex flex-col app-sidebar">
        <div className="px-5 py-4 border-b border-ink-700">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <div className="h-9 w-9 rounded-md bg-wa-500 flex items-center justify-center text-black font-bold">
                EC
              </div>
              <div>
                <div className="font-semibold leading-tight text-sm">Engineering Console</div>
                <div className="text-[11px] text-slate-400">Operations Workspace</div>
              </div>
            </div>
            <ThemeToggle />
          </div>
        </div>
        <nav className="flex-1 p-3 space-y-1.5">
          {links.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.to === "/"}
              className={({ isActive }) =>
                clsx(
                  "flex items-center rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-wa-500/15 text-slate-100 ring-1 ring-wa-500/25"
                    : "text-slate-300 hover:bg-ink-700/60 hover:text-slate-100",
                )
              }
            >
              <span>{l.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="p-4 border-t border-ink-700 text-xs app-sidebar-footer">
          <div className="text-slate-400">Signed in as</div>
          <div className="font-medium text-slate-100 truncate">{user?.email}</div>
          <div className="mt-1 flex gap-1 flex-wrap">
            {user?.roles.map((r) => (
              <span key={r} className="badge bg-ink-700 text-slate-300">{r}</span>
            ))}
          </div>
          <button
            onClick={() => {
              clear();
              nav("/login");
            }}
            className="btn-ghost w-full mt-3"
          >
            Sign out
          </button>
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto scrollbar-thin">
        <div className="max-w-6xl mx-auto p-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
