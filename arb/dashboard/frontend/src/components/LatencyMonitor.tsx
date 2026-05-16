"use client";
import { API_URL, api, ws } from "../lib/api";
import { useEffect, useState } from "react";

interface Stage {
  stage: string;
  label: string;
  samples: number;
  p50_ns: number; p95_ns: number; p99_ns: number; max_ns: number; avg_ns: number;
  p50_fmt: string; p95_fmt: string; p99_fmt: string; max_fmt: string;
  synthetic: boolean;
}
interface LatencyData {
  stages: Stage[];
  summary: { tick_to_signal_p50_us: number; decision_speed_label: string };
  ts: number;
}

export default function LatencyMonitor() {
  const [data, setData] = useState<LatencyData | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(api("/api/latency"));
        if (r.ok) setData(await r.json());
      } catch {}
    };
    load();
    const id = setInterval(load, 2_000);
    return () => clearInterval(id);
  }, []);

  const speedColor = (label?: string) =>
    label === "ULTRA-LOW" ? "text-green-400" :
    label === "LOW" ? "text-lime-400" :
    "text-amber-400";

  const stageColor = (ns: number) => {
    if (ns < 1_000) return "text-green-400";       // <1μs
    if (ns < 10_000) return "text-lime-400";        // <10μs
    if (ns < 100_000) return "text-yellow-400";    // <100μs
    if (ns < 1_000_000) return "text-orange-400";  // <1ms
    return "text-red-400";
  };

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-3 h-full">
      <div className="flex justify-between items-start mb-3">
        <div>
          <h2 className="text-white font-bold text-sm flex items-center gap-2">
            <span className="text-cyan-400">⚡</span> Decision Latency
          </h2>
          <p className="text-[10px] text-gray-500">tick → decision pipeline (ns precision)</p>
        </div>
        <div className="text-right">
          <div className="text-[10px] text-gray-500 uppercase">Speed</div>
          <div className={`font-mono text-sm font-bold ${speedColor(data?.summary.decision_speed_label)}`}>
            {data?.summary.decision_speed_label || "—"}
          </div>
        </div>
      </div>

      <div className="bg-gray-950 rounded p-2 mb-3 border border-cyan-900/40">
        <div className="flex items-baseline gap-2">
          <span className="text-[10px] text-gray-500 uppercase">Tick → Signal p50</span>
          <span className="font-mono text-2xl font-bold text-cyan-300">
            {data?.summary.tick_to_signal_p50_us ?? "—"}
          </span>
          <span className="text-xs text-gray-400">μs</span>
        </div>
        <div className="text-[10px] text-gray-500 mt-0.5">
          ≈ {data ? Math.round(1_000_000 / Math.max(data.summary.tick_to_signal_p50_us, 1)) : "—"} decisions/sec theoretical max
        </div>
      </div>

      <div className="space-y-1 text-xs">
        {(data?.stages ?? []).map((s) => {
          const pctBar = Math.min(100, Math.log10(Math.max(s.p50_ns, 1)) * 10); // log scale visualization
          return (
            <div key={s.stage} className="bg-gray-950/50 rounded px-2 py-1.5 border border-gray-800">
              <div className="flex justify-between items-center mb-0.5">
                <span className="text-[11px] text-gray-300 font-medium">{s.label}</span>
                <div className="flex items-center gap-2 text-[10px] font-mono">
                  <span className={stageColor(s.p50_ns)}>p50 {s.p50_fmt}</span>
                  <span className="text-gray-600">·</span>
                  <span className={stageColor(s.p95_ns)}>p95 {s.p95_fmt}</span>
                  <span className="text-gray-600">·</span>
                  <span className={stageColor(s.max_ns)}>max {s.max_fmt}</span>
                </div>
              </div>
              <div className="h-1 bg-gray-800 rounded overflow-hidden">
                <div className="h-full bg-gradient-to-r from-cyan-500 to-purple-500"
                  style={{ width: `${pctBar}%` }} />
              </div>
              {s.synthetic && (
                <div className="text-[9px] text-amber-500/70 mt-0.5">simulated · awaiting live data</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
