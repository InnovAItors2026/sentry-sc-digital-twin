import { FormEvent, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { buildRecoveryPayload, recoveriesForEvent } from "../recoveryTargets";
import type { NetworkResponse } from "../types";

const TYPES = [
  { id: "supplier_outage", label: "Supplier failure" },
  { id: "factory_shutdown", label: "Factory shutdown" },
  { id: "transportation_delay", label: "Transportation delay" },
  { id: "warehouse_disruption", label: "Warehouse disruption" },
  { id: "demand_spike", label: "Demand spike" },
];

export default function StressTest() {
  const [net, setNet] = useState<NetworkResponse | null>(null);
  const [params] = useSearchParams();
  const nav = useNavigate();
  const [eventType, setEventType] = useState("supplier_outage");
  const [target, setTarget] = useState(params.get("node") || "SUP-001");
  const [startDay, setStartDay] = useState(3);
  const [duration, setDuration] = useState(10);
  const [horizon, setHorizon] = useState(30);
  const [capacityFactor, setCapacityFactor] = useState(0);
  const [extraTransit, setExtraTransit] = useState(2);
  const [unavailPct, setUnavailPct] = useState(40);
  const [demandPct, setDemandPct] = useState(25);
  const [recovery, setRecovery] = useState("activate_alternative_supplier");
  const [recoveryDay, setRecoveryDay] = useState(5);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.network().then(setNet).catch((e: Error) => setError(e.message));
  }, []);

  const targets = useMemo(() => {
    if (!net) return [];
    if (eventType === "supplier_outage") return net.graph_nodes.filter((n) => n.type === "supplier");
    if (eventType === "factory_shutdown") return net.graph_nodes.filter((n) => n.type === "factory");
    if (eventType === "warehouse_disruption") return net.graph_nodes.filter((n) => n.type === "warehouse");
    if (eventType === "demand_spike") return net.graph_nodes.filter((n) => n.type === "customer");
    return net.graph_edges.map((e) => ({ id: e.id, label: e.label, type: "route" as const }));
  }, [net, eventType]);

  const recoveryChoices = useMemo(() => recoveriesForEvent(eventType), [eventType]);

  const recoveryPlan = useMemo(() => {
    if (!net || !recovery) return { payload: null, error: null, summary: null };
    return buildRecoveryPayload({ recovery, recoveryDay, target, eventType, net });
  }, [net, recovery, recoveryDay, target, eventType]);

  useEffect(() => {
    if (targets.length && !targets.some((t) => t.id === target)) {
      setTarget(targets[0].id);
    }
  }, [targets, target]);

  useEffect(() => {
    if (!recoveryChoices.some((r) => r.id === recovery)) {
      setRecovery("");
    }
  }, [recoveryChoices, recovery]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (startDay < 1 || duration < 1 || horizon < 1) {
      setError("Start day, duration, and horizon must be at least 1.");
      return;
    }
    if (startDay > horizon) {
      setError("Disruption start day must fall within the simulation horizon.");
      return;
    }
    const disruption: Record<string, unknown> = {
      event_type: eventType,
      target_node_id: target,
      start_day: startDay,
      duration_days: duration,
      source: "user_configured",
    };
    if (eventType === "supplier_outage" || eventType === "factory_shutdown") {
      disruption.capacity_factor = capacityFactor;
    }
    if (eventType === "transportation_delay") {
      disruption.extra_transit_days = extraTransit;
      disruption.capacity_factor = capacityFactor;
    }
    if (eventType === "warehouse_disruption") {
      disruption.unavailable_inventory_pct = unavailPct;
      disruption.capacity_factor = 0;
    }
    if (eventType === "demand_spike") {
      disruption.demand_increase_pct = demandPct;
    }
    if (recovery && recoveryPlan.error) {
      setError(recoveryPlan.error);
      return;
    }
    const recoveries: Record<string, unknown>[] = recoveryPlan.payload ? [recoveryPlan.payload] : [];

    setBusy(true);
    try {
      const created = await api.createScenario({
        name: `${TYPES.find((t) => t.id === eventType)?.label} on ${target}`,
        horizon_days: horizon,
        disruptions: [disruption],
        recoveries,
        notes: "Configured from the stress-test console. Baseline twin is not modified.",
      });
      const results = await api.simulate(created.scenario_id);
      sessionStorage.setItem("sentryLastScenario", created.scenario_id);
      sessionStorage.setItem("sentryLastResults", JSON.stringify(results));
      nav(`/results?scenario=${created.scenario_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Simulation failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="p-6 max-w-3xl">
      <h1 className="text-xl font-semibold">Stress-test configuration</h1>
      <p className="text-sm text-slate-400 mt-1">
        Disruptions apply only to the scenario being simulated. The baseline network stays intact for comparison.
      </p>
      <form onSubmit={onSubmit} className="mt-6 space-y-4">
        <Field label="Simulation horizon (days)">
          <select className={input} value={horizon} onChange={(e) => setHorizon(Number(e.target.value))}>
            {[7, 14, 30, 60].map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Disruption type">
          <select className={input} value={eventType} onChange={(e) => setEventType(e.target.value)}>
            {TYPES.map((t) => (
              <option key={t.id} value={t.id}>
                {t.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Target">
          <select className={input} value={target} onChange={(e) => setTarget(e.target.value)}>
            {targets.map((t) => (
              <option key={t.id} value={t.id}>
                {t.id} — {"label" in t ? String(t.label) : t.id}
              </option>
            ))}
          </select>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Start day">
            <input className={input} type="number" min={1} value={startDay} onChange={(e) => setStartDay(Number(e.target.value))} />
          </Field>
          <Field label="Duration (days)">
            <input className={input} type="number" min={1} value={duration} onChange={(e) => setDuration(Number(e.target.value))} />
          </Field>
        </div>
        {(eventType === "supplier_outage" || eventType === "factory_shutdown" || eventType === "transportation_delay") && (
          <Field label="Capacity factor (0 = full outage, 0.5 = half capacity)">
            <input
              className={input}
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={capacityFactor}
              onChange={(e) => setCapacityFactor(Number(e.target.value))}
            />
          </Field>
        )}
        {eventType === "transportation_delay" && (
          <Field label="Additional transit days">
            <input className={input} type="number" min={0} value={extraTransit} onChange={(e) => setExtraTransit(Number(e.target.value))} />
          </Field>
        )}
        {eventType === "warehouse_disruption" && (
          <Field label="Unavailable inventory %">
            <input className={input} type="number" min={0} max={100} value={unavailPct} onChange={(e) => setUnavailPct(Number(e.target.value))} />
          </Field>
        )}
        {eventType === "demand_spike" && (
          <Field label="Demand increase %">
            <input className={input} type="number" min={0} value={demandPct} onChange={(e) => setDemandPct(Number(e.target.value))} />
          </Field>
        )}
        <Field label="Recovery intervention (optional, this scenario only)">
          <select className={input} value={recovery} onChange={(e) => setRecovery(e.target.value)}>
            {recoveryChoices.map((r) => (
              <option key={r.id} value={r.id}>
                {r.label}
              </option>
            ))}
          </select>
        </Field>
        {recovery && (
          <Field label="Recovery start day">
            <input className={input} type="number" min={1} value={recoveryDay} onChange={(e) => setRecoveryDay(Number(e.target.value))} />
          </Field>
        )}
        {recoveryPlan.summary && <p className="text-xs text-teal-300">{recoveryPlan.summary}</p>}
        {recoveryPlan.error && <p className="text-xs text-rose-300">{recoveryPlan.error}</p>}
        {error && <div className="text-sm text-rose-300">{error}</div>}
        <div className="flex gap-3">
          <button disabled={busy} className="rounded-md bg-teal-600 hover:bg-teal-500 disabled:opacity-50 px-4 py-2 text-sm font-medium">
            {busy ? "Simulating…" : "Run baseline + disrupted simulation"}
          </button>
          <button
            type="button"
            className="rounded-md border border-white/15 px-4 py-2 text-sm"
            onClick={() => {
              setEventType("supplier_outage");
              setTarget("SUP-001");
              setStartDay(3);
              setDuration(10);
              setHorizon(30);
              setCapacityFactor(0);
              setRecovery("activate_alternative_supplier");
              setRecoveryDay(5);
            }}
          >
            Load demo (Alpha outage)
          </button>
        </div>
      </form>
    </div>
  );
}

const input =
  "w-full rounded-md bg-ink-900 border border-white/10 px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-1 focus:ring-teal-500";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-xs uppercase tracking-wider text-slate-400">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  );
}
