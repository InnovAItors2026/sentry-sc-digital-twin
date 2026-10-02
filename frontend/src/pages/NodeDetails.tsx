import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { NetworkResponse } from "../types";

type NodePayload = Record<string, unknown>;

const ENTITY_FIELDS: Record<string, string[]> = {
  supplier: ["supplier_id", "name", "sku", "capacity_per_day", "lead_time_days", "unit_cost", "reliability_score", "risk_level", "preferred_for_sku", "available"],
  factory: ["factory_id", "name", "output_sku", "production_capacity_per_day", "current_production_per_day", "available"],
  warehouse: ["warehouse_id", "name", "maximum_capacity", "available"],
  customer: ["customer_id", "name", "demand_sku", "daily_demand", "priority", "outstanding_orders", "unit_revenue"],
};

function pretty(key: string) {
  return key.replace(/_/g, " ");
}

function display(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  if (Array.isArray(value)) return value.map((v) => (typeof v === "object" ? JSON.stringify(v) : String(v))).join(", ");
  if (typeof value === "object") return Object.entries(value as Record<string, unknown>)
    .map(([k, v]) => `${k}: ${v}`)
    .join(" · ");
  return String(value);
}

export default function NodeDetails() {
  const [params] = useSearchParams();
  const [net, setNet] = useState<NetworkResponse | null>(null);
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null);
  const [id, setId] = useState(params.get("id") || "SUP-001");
  const [error, setError] = useState<string | null>(null);
  const last = sessionStorage.getItem("sentryLastResults");
  const reasons: string[] = [];
  if (last) {
    try {
      const parsed = JSON.parse(last);
      const hit = parsed.affected_nodes?.find((n: { node_id: string }) => n.node_id === id);
      if (hit?.reasons) reasons.push(...hit.reasons);
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    api.network().then(setNet).catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    api.node(id).then(setDetail).catch((e: Error) => setError(e.message));
  }, [id]);

  const ids = net?.graph_nodes.map((n) => n.id) || [];
  const node = (detail?.node || {}) as NodePayload;
  const nodeType = String(detail?.node_type || "");
  const fields = ENTITY_FIELDS[nodeType] || Object.keys(node).filter((k) => typeof node[k] !== "object");

  return (
    <div className="p-6 max-w-4xl">
      <h1 className="text-xl font-semibold">Node details</h1>
      <select
        className="mt-3 rounded-md bg-ink-900 border border-white/10 px-3 py-2 text-sm"
        value={id}
        onChange={(e) => setId(e.target.value)}
      >
        {ids.map((nid) => (
          <option key={nid}>{nid}</option>
        ))}
      </select>
      {error && <p className="mt-3 text-rose-300 text-sm">{error}</p>}
      {detail && (
        <div className="mt-4 grid md:grid-cols-2 gap-4">
          <Panel title={String(node.name || id)}>
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
              <dt className="text-slate-500">Type</dt>
              <dd className="text-slate-200">{nodeType || "—"}</dd>
              {fields.map((key) => (
                <FragmentRow key={key} label={pretty(key)} value={display(node[key])} />
              ))}
            </dl>
            {nodeType === "factory" && Array.isArray(node.required_materials) && (
              <div className="mt-3">
                <div className="text-xs uppercase text-slate-400">Bill of materials</div>
                <ul className="mt-1 text-sm text-slate-300">
                  {(node.required_materials as { sku: string; qty_per_unit: number }[]).map((m) => (
                    <li key={m.sku}>
                      {m.qty_per_unit} × {m.sku}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {nodeType === "warehouse" && node.current_inventory && (
              <div className="mt-3">
                <div className="text-xs uppercase text-slate-400">On-hand inventory</div>
                <ul className="mt-1 text-sm text-slate-300">
                  {Object.entries(node.current_inventory as Record<string, number>).map(([sku, qty]) => (
                    <li key={sku}>
                      {sku}: {qty}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Panel>
          <div className="space-y-4">
            <RouteList title="Incoming routes" routes={(detail.incoming as NodePayload[]) || []} />
            <RouteList title="Outgoing routes" routes={(detail.outgoing as NodePayload[]) || []} />
          </div>
        </div>
      )}
      {reasons.length > 0 && (
        <div className="mt-4 rounded-xl border border-white/10 bg-ink-800 p-4">
          <div className="text-xs uppercase text-slate-400">Rule-based impact reasons (last simulation)</div>
          <ul className="mt-2 list-disc pl-4 text-sm text-slate-300 space-y-1">
            {reasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function FragmentRow({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="text-slate-500 capitalize">{label}</dt>
      <dd className="text-slate-200">{value}</dd>
    </>
  );
}

function RouteList({ title, routes }: { title: string; routes: NodePayload[] }) {
  return (
    <Panel title={title}>
      {routes.length === 0 ? (
        <p className="text-sm text-slate-500">None</p>
      ) : (
        <ul className="space-y-2 text-sm">
          {routes.map((r) => (
            <li key={String(r.route_id)} className="border-b border-white/5 pb-2 last:border-0">
              <div className="font-medium text-teal-200">{String(r.route_id)}</div>
              <div className="text-slate-300">{String(r.name)}</div>
              <div className="text-xs text-slate-500">
                {String(r.source_node_id)} → {String(r.destination_node_id)} · transit {display(r.transit_time_days)}d ·
                cap {display(r.capacity_per_day)}/d · ${display(r.cost_per_unit)}/u
              </div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-white/10 bg-ink-800 p-4">
      <h2 className="text-sm font-medium mb-2">{title}</h2>
      {children}
    </section>
  );
}
