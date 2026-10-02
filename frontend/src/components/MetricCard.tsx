export function MetricCard({
  label,
  value,
  hint,
  tone = "neutral",
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "neutral" | "good" | "bad";
}) {
  const color = tone === "good" ? "text-emerald-300" : tone === "bad" ? "text-rose-300" : "text-white";
  return (
    <div className="rounded-xl border border-white/10 bg-ink-800/80 p-4">
      <div className="text-[11px] uppercase tracking-wider text-slate-400">{label}</div>
      <div className={`mt-1 text-2xl font-semibold tabular-nums ${color}`}>{value}</div>
      {hint ? <div className="mt-1 text-xs text-slate-500">{hint}</div> : null}
    </div>
  );
}

export function fmt(n: number | null | undefined, digits = 1) {
  if (n == null || Number.isNaN(n)) return "n/a";
  return n.toLocaleString(undefined, { maximumFractionDigits: digits });
}

export function fmtPct(n: number | null | undefined) {
  if (n == null) return "n/a";
  return `${n.toFixed(1)}%`;
}

export function fmtMoney(n: number | null | undefined) {
  if (n == null) return "n/a";
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}
