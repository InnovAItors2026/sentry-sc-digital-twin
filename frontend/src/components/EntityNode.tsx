import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";

const accents: Record<string, string> = {
  supplier: "border-sky-400/70 bg-sky-950/70",
  factory: "border-violet-400/70 bg-violet-950/70",
  warehouse: "border-amber-400/70 bg-amber-950/60",
  customer: "border-emerald-400/70 bg-emerald-950/60",
};

const statusRing: Record<string, string> = {
  normal: "",
  warning: "ring-2 ring-amber-400",
  critical: "ring-2 ring-rose-500",
  unavailable: "ring-2 ring-rose-600 opacity-70",
};

function EntityNode({ data, selected }: NodeProps) {
  const kind = String(data.kind || "supplier");
  const status = String(data.status || "normal");
  const affected = Boolean(data.affected);
  return (
    <div
      className={`min-w-[160px] rounded-lg border px-3 py-2 shadow-lg ${accents[kind] || accents.supplier} ${
        statusRing[status] || ""
      } ${selected ? "outline outline-2 outline-white/70" : ""} ${affected ? "brightness-110" : ""}`}
    >
      <Handle type="target" position={Position.Left} className="!bg-slate-300" />
      <div className="text-[10px] uppercase tracking-wider text-slate-400">{kind}</div>
      <div className="text-sm font-medium leading-tight">{String(data.label)}</div>
      <div className="text-[11px] font-mono text-slate-400 mt-0.5">{String(data.id)}</div>
      {data.subtitle ? <div className="text-[11px] text-slate-300 mt-1">{String(data.subtitle)}</div> : null}
      <Handle type="source" position={Position.Right} className="!bg-slate-300" />
    </div>
  );
}

export default memo(EntityNode);
