import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { fmt, fmtMoney, fmtPct } from "../components/MetricCard";
import type { CompareResponse, ScenarioSummary } from "../types";

const DEMO = ["SCN-BASELINE", "SCN-ALPHA-OUTAGE", "SCN-ALPHA-RECOVERY"];

export default function Compare() {
  const [list, setList] = useState<ScenarioSummary[]>([]);
  const [selected, setSelected] = useState<string[]>(DEMO);
  const [cmp, setCmp] = useState<CompareResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.scenarios().then(setList).catch((e: Error) => setError(e.message));
  }, []);

  function toggle(id: string) {
    setSelected((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));
  }

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const body = await api.compare(selected);
      setCmp(body);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Compare failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold">Scenario comparison</h1>
      <p className="text-sm text-slate-400 mt-1">
        Seeded demo: 30-day baseline, Alpha 10-day outage from day 3, and the same outage with Supplier Beta activated on
        day 5. Unsimulated scenarios are run on demand. KPIs are calculated, not hardcoded.
      </p>
      {error && <div className="mt-3 text-rose-300 text-sm">{error}</div>}
      <div className="mt-4 grid md:grid-cols-2 gap-3">
        {list.map((s) => (
          <label key={s.scenario_id} className="flex gap-3 rounded-xl border border-white/10 bg-ink-800 p-3 text-sm">
            <input type="checkbox" checked={selected.includes(s.scenario_id)} onChange={() => toggle(s.scenario_id)} />
            <span>
              <div className="font-medium">{s.name}</div>
              <div className="text-xs text-slate-400">
                {s.scenario_id} · {s.horizon_days}d · {s.disruption_count} disruption(s) · {s.recovery_count} recovery
              </div>
            </span>
          </label>
        ))}
      </div>
      <button
        className="mt-4 rounded-md bg-teal-600 hover:bg-teal-500 disabled:opacity-50 px-4 py-2 text-sm"
        disabled={busy || selected.length === 0}
        onClick={run}
      >
        {busy ? "Simulating & comparing…" : "Compare selected"}
      </button>
      {cmp && (
        <div className="mt-6 overflow-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-slate-400">
              <tr>
                <th className="p-2">Scenario</th>
                <th className="p-2">Service</th>
                <th className="p-2">Disruption cost</th>
                <th className="p-2">Shortfall</th>
                <th className="p-2">Unfulfilled</th>
                <th className="p-2">Delay</th>
                <th className="p-2">Recovery day</th>
              </tr>
            </thead>
            <tbody>
              {cmp.scenarios.map((row) => (
                <tr key={String(row.scenario_id)} className="border-t border-white/10">
                  <td className="p-2">
                    <Link className="text-teal-300 hover:underline" to={`/results?scenario=${row.scenario_id}`}>
                      {String(row.name)}
                    </Link>
                  </td>
                  <td className="p-2 tabular-nums">{fmtPct(row.service_level_pct as number)}</td>
                  <td className="p-2 tabular-nums">{fmtMoney(row.estimated_disruption_cost as number)}</td>
                  <td className="p-2 tabular-nums">{fmt(row.production_shortfall as number, 0)}</td>
                  <td className="p-2 tabular-nums">{fmt(row.unfulfilled_demand as number, 0)}</td>
                  <td className="p-2 tabular-nums">{fmt(row.average_delivery_delay as number, 2)}</td>
                  <td className="p-2 tabular-nums">{row.recovery_day == null ? "n/a" : String(row.recovery_day)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <ul className="mt-4 space-y-2 text-sm text-slate-300 list-disc pl-5">
            {cmp.trade_offs.map((t, i) => (
              <li key={i}>{t}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
