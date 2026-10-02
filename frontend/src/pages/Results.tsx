import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api/client";
import NetworkGraph from "../components/NetworkGraph";
import { MetricCard, fmt, fmtMoney, fmtPct } from "../components/MetricCard";
import {
  horizonFromTimeline,
  hotRouteIds,
  impactedIdsForDay,
  pointsForDay,
  statusMapForDay,
  subtitleForPoint,
} from "../timeline";
import type { DailyPoint, NetworkResponse, SimulateResponse } from "../types";

function series(daily: DailyPoint[], nodeType: string, field: keyof DailyPoint) {
  const byDay: Record<number, number> = {};
  for (const d of daily) {
    if (d.node_type !== nodeType) continue;
    const val = d[field];
    byDay[d.day] = (byDay[d.day] || 0) + (typeof val === "number" ? val : 0);
  }
  return Object.entries(byDay)
    .map(([day, value]) => ({ day: Number(day), value }))
    .sort((a, b) => a.day - b.day);
}

function inventorySeries(daily: DailyPoint[], sku: string) {
  const byDay: Record<number, number> = {};
  for (const d of daily) {
    if (d.node_type !== "warehouse") continue;
    byDay[d.day] = (byDay[d.day] || 0) + (d.inventory_by_sku?.[sku] || 0);
  }
  return Object.entries(byDay)
    .map(([day, value]) => ({ day: Number(day), value }))
    .sort((a, b) => a.day - b.day);
}

export default function Results() {
  const [params] = useSearchParams();
  const [net, setNet] = useState<NetworkResponse | null>(null);
  const [data, setData] = useState<SimulateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [inspect, setInspect] = useState<string | null>(null);
  const [day, setDay] = useState(1);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    api.network().then(setNet).catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    const sid = params.get("scenario") || sessionStorage.getItem("sentryLastScenario");
    if (!sid) return;
    api
      .results(sid)
      .catch(() => api.simulate(sid))
      .then((body) => {
        setData(body);
        setDay(1);
      })
      .catch((e: Error) => setError(e.message));
  }, [params]);

  const horizon = data ? horizonFromTimeline(data.daily_timeline) : 1;

  useEffect(() => {
    if (!playing || !data) return;
    const id = window.setInterval(() => {
      setDay((cur) => (cur >= horizon ? 1 : cur + 1));
    }, 650);
    return () => window.clearInterval(id);
  }, [playing, data, horizon]);

  const statusByNode = useMemo(
    () => (data ? statusMapForDay(data.daily_timeline, day) : {}),
    [data, day]
  );

  const affectedIds = useMemo(
    () =>
      data
        ? impactedIdsForDay(data.daily_timeline, data.baseline_daily_timeline, day)
        : new Set<string>(),
    [data, day]
  );
  const affectedEdges = useMemo(
    () => (net ? hotRouteIds(net.graph_edges, affectedIds, data?.propagation_path || []) : new Set<string>()),
    [net, affectedIds, data]
  );

  const daySubtitles = useMemo(() => {
    const map: Record<string, string> = {};
    if (!data) return map;
    for (const p of pointsForDay(data.daily_timeline, day)) {
      const sub = subtitleForPoint(p, p.node_type);
      if (sub) map[p.node_id] = sub;
    }
    return map;
  }, [data, day]);

  const dayEvents = useMemo(() => {
    if (!data) return [];
    const unique: { node_id: string; category: string; message: string }[] = [];
    const seen = new Set<string>();
    for (const ev of data.events) {
      if (ev.day !== day) continue;
      const key = `${ev.node_id}|${ev.message}`;
      if (seen.has(key)) continue;
      seen.add(key);
      unique.push(ev);
    }
    return unique.slice(0, 12);
  }, [data, day]);

  const charts = useMemo(() => {
    if (!data) return [];
    const invA = inventorySeries(data.daily_timeline, "COMP-A");
    const invABase = inventorySeries(data.baseline_daily_timeline, "COMP-A");
    const prod = series(data.daily_timeline, "factory", "production");
    const prodB = series(data.baseline_daily_timeline, "factory", "production");
    const fill = series(data.daily_timeline, "customer", "fulfilled");
    const fillB = series(data.baseline_daily_timeline, "customer", "fulfilled");
    const days = invA.map((p) => p.day);
    return days.map((day, i) => ({
      day,
      invA: invA[i]?.value,
      invABase: invABase[i]?.value,
      prod: prod[i]?.value,
      prodBase: prodB[i]?.value,
      fill: fill[i]?.value,
      fillBase: fillB[i]?.value,
    }));
  }, [data]);

  const inspected = data?.affected_nodes.find((n) => n.node_id === inspect);

  if (error) return <div className="p-8 text-rose-300">{error}</div>;
  if (!data || !net) {
    return (
      <div className="p-8 text-slate-400">
        No simulation loaded. Run a stress test, or simulate the seeded demo scenarios from Compare.
      </div>
    );
  }

  const b = data.baseline_metrics;
  const s = data.scenario_metrics;

  return (
    <div className="p-6 space-y-6">
      <header>
        <h1 className="text-xl font-semibold">Simulation results — {data.scenario_id}</h1>
        <p className="text-sm text-slate-400 mt-1">
          Baseline and disrupted runs share the same initial inventories, demand, and routing rules. Explanations are
          generated from simulation events, not from an AI model.
        </p>
      </header>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <MetricCard label="Service level (baseline)" value={fmtPct(b.service_level_pct)} tone="good" />
        <MetricCard
          label="Service level (disrupted)"
          value={fmtPct(s.service_level_pct)}
          tone={(s.service_level_pct || 0) < (b.service_level_pct || 0) ? "bad" : "good"}
        />
        <MetricCard label="Production shortfall" value={fmt(s.production_shortfall, 0)} tone="bad" />
        <MetricCard label="Disruption cost" value={fmtMoney(s.estimated_disruption_cost)} hint="Incremental vs baseline" />
        <MetricCard label="Unfulfilled (closing backlog)" value={fmt(s.unfulfilled_demand, 0)} />
        <MetricCard label="Stockout node-days" value={fmt(s.stockout_days, 0)} />
        <MetricCard label="Avg delivery delay (days)" value={fmt(s.average_delivery_delay, 2)} />
        <MetricCard label="Recovery day" value={s.recovery_day != null ? String(s.recovery_day) : "n/a"} />
      </div>
      <div className="rounded-xl border border-white/10 bg-ink-800 p-4">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-sm font-medium">Disruption playback</h2>
          <span className="text-sm tabular-nums text-teal-200">Day {day} / {horizon}</span>
          <button
            type="button"
            className="rounded-md border border-white/15 px-3 py-1 text-xs"
            onClick={() => setPlaying((p) => !p)}
          >
            {playing ? "Pause" : "Play"}
          </button>
          <input
            className="flex-1 min-w-[180px] accent-teal-500"
            type="range"
            min={1}
            max={horizon}
            value={day}
            onChange={(e) => {
              setPlaying(false);
              setDay(Number(e.target.value));
            }}
          />
        </div>
        <p className="text-xs text-slate-400 mt-2">
          Node colors and highlights are that day&apos;s simulated status versus the paired baseline, not a static
          end-of-horizon snapshot.
        </p>
      </div>
      <div className="grid xl:grid-cols-2 gap-4" style={{ minHeight: 380 }}>
        <div>
          <h2 className="text-sm font-medium mb-2">Affected network — day {day}</h2>
          <div className="h-[360px]">
            <NetworkGraph
              graphNodes={net.graph_nodes}
              graphEdges={net.graph_edges}
              selectedId={inspect}
              onSelect={setInspect}
              statusByNode={statusByNode}
              affectedIds={affectedIds}
              affectedEdges={affectedEdges}
              daySubtitles={daySubtitles}
            />
          </div>
        </div>
        <div className="rounded-xl border border-white/10 bg-ink-800 p-4 overflow-auto max-h-[360px]">
          <h2 className="text-sm font-medium">Propagation path</h2>
          <p className="text-xs text-slate-400 mt-1">{data.propagation_path.join(" → ") || "No path"}</p>
          <ul className="mt-3 space-y-3">
            {data.affected_nodes.map((n) => (
              <li key={n.node_id}>
                <button className="text-left" onClick={() => setInspect(n.node_id)}>
                  <div className="text-sm font-medium text-teal-200">
                    {n.node_id}{" "}
                    <span className="text-slate-500 font-normal">{n.node_type}</span>
                  </div>
                  <div className="text-xs text-slate-300">{n.impact_summary}</div>
                </button>
              </li>
            ))}
          </ul>
          {dayEvents.length > 0 && (
            <div className="mt-4 border-t border-white/10 pt-3">
              <div className="text-xs uppercase text-slate-400">Events on day {day}</div>
              <ul className="mt-2 space-y-1 text-xs text-slate-300">
                {dayEvents.map((ev, i) => (
                  <li key={i}>
                    <span className="font-mono text-slate-500">{ev.node_id}</span> {ev.message}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {inspected && (
            <div className="mt-4 border-t border-white/10 pt-3 text-sm">
              <div className="text-xs uppercase text-slate-400">Why {inspected.node_id} was affected (horizon)</div>
              <ul className="mt-2 list-disc pl-4 space-y-1 text-slate-300">
                {inspected.reasons.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
      <div className="rounded-xl border border-white/10 bg-ink-800 p-4 h-[320px]">
        <h2 className="text-sm font-medium mb-2">Daily trends (baseline dashed)</h2>
        <ResponsiveContainer width="100%" height="90%">
          <LineChart data={charts}>
            <CartesianGrid stroke="#1e293b" />
            <XAxis dataKey="day" stroke="#94a3b8" />
            <YAxis stroke="#94a3b8" />
            <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #1e293b" }} />
            <Legend />
            <Line type="monotone" dataKey="invA" name="COMP-A inventory" stroke="#fbbf24" dot={false} />
            <Line type="monotone" dataKey="invABase" name="COMP-A baseline" stroke="#fbbf24" strokeDasharray="4 4" dot={false} />
            <Line type="monotone" dataKey="prod" name="Production" stroke="#a78bfa" dot={false} />
            <Line type="monotone" dataKey="prodBase" name="Production baseline" stroke="#a78bfa" strokeDasharray="4 4" dot={false} />
            <Line type="monotone" dataKey="fill" name="Fulfilled" stroke="#34d399" dot={false} />
            <Line type="monotone" dataKey="fillBase" name="Fulfilled baseline" stroke="#34d399" strokeDasharray="4 4" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      {data.feasibility.length > 0 && (
        <div className="text-xs text-slate-400">
          Recovery feasibility is model-checked only: {data.feasibility.map((f) => f.recovery_type).join(", ")}.{" "}
          {data.feasibility[0]?.claim}
        </div>
      )}
    </div>
  );
}
