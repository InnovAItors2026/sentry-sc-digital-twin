import { NavLink, Outlet } from "react-router-dom";

const links = [
  { to: "/", label: "Overview" },
  { to: "/stress-test", label: "Stress test" },
  { to: "/results", label: "Results" },
  { to: "/compare", label: "Compare" },
  { to: "/node", label: "Node details" },
];

export default function Layout() {
  return (
    <div className="min-h-full flex">
      <aside className="w-60 shrink-0 border-r border-white/10 bg-ink-900 flex flex-col">
        <div className="px-5 py-6 border-b border-white/10">
          <div className="text-[11px] tracking-[0.2em] text-teal-400 font-medium">SAP HACKFEST 2026</div>
          <div className="mt-1 text-lg font-semibold">SENTRY-SC</div>
          <div className="text-xs text-slate-400">Digital twin & disruption sim</div>
        </div>
        <nav className="p-3 flex-1 space-y-1">
          {links.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.to === "/"}
              className={({ isActive }) =>
                `block rounded-md px-3 py-2 text-sm ${
                  isActive ? "bg-teal-500/15 text-teal-200" : "text-slate-300 hover:bg-white/5"
                }`
              }
            >
              {l.label}
            </NavLink>
          ))}
        </nav>
        <div className="p-4 text-[11px] text-slate-500 border-t border-white/10">
          Simulation engine only. No live SAP. Explanations are rule-based.
        </div>
      </aside>
      <main className="flex-1 min-w-0">
        <Outlet />
      </main>
    </div>
  );
}
