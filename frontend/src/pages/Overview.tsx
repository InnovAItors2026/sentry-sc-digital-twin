import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import NetworkGraph from "../components/NetworkGraph";
import { MetricCard, fmt } from "../components/MetricCard";
import type { NetworkResponse } from "../types";

export default function Overview() {
  const [net, setNet] = useState<NetworkResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const nav = useNavigate();

  useEffect(() => {
    api.network().then(setNet).catch((e: Error) => setError(e.message));
  }, []);

  if (error) {
    return (
      <div className="p-8 text-rose-300">
        Cannot reach the simulation API. Start the backend on port 8000. {error}
      </div>
    );
  }
  if (!net) return <div className="p-8 text-slate-400">Loading twin…</div>;

  const selectedNode = net.graph_nodes.find((n) => n.id === selected);

  return (
    <div className="h-full flex flex-col">
      <header className="px-6 py-4 border-b border-white/10 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">{net.name}</h1>
          <p className="text-sm text-slate-400 mt-1">
            Interactive digital twin. Select a node to inspect it, then start a stress test without mutating this baseline.
          </p>
        </div>
        <button
          className="rounded-md bg-teal-600 hover:bg-teal-500 px-3 py-2 text-sm font-medium"
          onClick={() => nav(selected ? `/stress-test?node=${selected}` : "/stress-test")}
        >
          Configure stress test
        </button>
      </header>
      <div className="p-6 grid grid-cols-2 lg:grid-cols-5 gap-3">
        <MetricCard label="Suppliers" value={String(net.counts.suppliers)} />
        <MetricCard label="Factories" value={String(net.counts.factories)} />
        <MetricCard label="Warehouses" value={String(net.counts.warehouses)} />
        <MetricCard label="Routes" value={String(net.counts.routes)} />
        <MetricCard label="Customers" value={String(net.counts.customers)} />
      </div>
      <div className="px-6 pb-3 flex flex-wrap gap-4 text-xs text-slate-400">
        <Legend color="bg-sky-400" label="Supplier" />
        <Legend color="bg-violet-400" label="Factory" />
        <Legend color="bg-amber-400" label="Warehouse" />
        <Legend color="bg-emerald-400" label="Customer" />
        <Legend color="bg-rose-500" label="Disrupted / affected (after sim)" />
        <span>Overall status: {net.overall_status}</span>
      </div>
      <div className="flex-1 px-6 min-h-[420px] grid grid-cols-1 xl:grid-cols-[1fr_280px] gap-4">
        <NetworkGraph graphNodes={net.graph_nodes} graphEdges={net.graph_edges} selectedId={selected} onSelect={setSelected} />
        <div className="space-y-3">
          <div className="rounded-xl border border-white/10 bg-ink-800 p-4">
            <div className="text-xs uppercase tracking-wider text-slate-400">Selected node</div>
            {selectedNode ? (
              <div className="mt-2">
                <div className="font-medium">{selectedNode.label}</div>
                <div className="font-mono text-xs text-slate-400">{selectedNode.id}</div>
                <button className="mt-3 text-sm text-teal-300" onClick={() => nav(`/node?id=${selectedNode.id}`)}>
                  Open details
                </button>
              </div>
            ) : (
              <p className="text-sm text-slate-400 mt-2">Click a node on the map.</p>
            )}
          </div>
          <div className="rounded-xl border border-white/10 bg-ink-800 p-4">
            <div className="text-xs uppercase tracking-wider text-slate-400">Inventory overview</div>
            <ul className="mt-2 space-y-2 text-sm">
              {net.inventory_overview.map((w) => (
                <li key={w.warehouse_id}>
                  <div className="flex justify-between">
                    <span>{w.name}</span>
                    <span className="tabular-nums text-slate-300">{fmt(w.utilization_pct, 0)}%</span>
                  </div>
                  <div className="h-1.5 bg-ink-700 rounded mt-1">
                    <div className="h-1.5 rounded bg-amber-400" style={{ width: `${Math.min(100, w.utilization_pct)}%` }} />
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`w-2.5 h-2.5 rounded-sm ${color}`} />
      {label}
    </span>
  );
}
