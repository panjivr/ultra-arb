"use client";
import { API_URL, api, ws } from "../lib/api";
import { useEffect, useState } from "react";

interface Breaker { triggered: boolean; value: number; threshold: number; }
interface Risk {
  halted: boolean;
  alerts: Array<{ event: string; reason: string; halted?: boolean; ts: number }>;
  open_positions: number; max_positions: number;
  exposure_usd: number;
  daily_pnl_pct: number; max_drawdown_pct: number;
  vol_multiplier: number; vol_threshold: number;
  drawdown_breaker: Breaker;
  vol_breaker: Breaker;
}

function Gauge({ label, value, max, min, danger, format, unit = "" }: {
  label: string; value: number; max: number; min?: number; danger: number;
  format: (n: number) => string; unit?: string;
}) {
  const lo = min ?? 0;
  const pct = ((value - lo) / (max - lo)) * 100;
  const triggered = value <= danger || value >= danger * (danger < 0 ? 1 : 1);
  const dangerSide = danger < 0 ? value <= danger : value >= danger;
  const color = dangerSide ? "bg-red-500" : pct > 70 ? "bg-yellow-500" : "bg-green-500";
  return (
    <div className="bg-gray-800 p-2 rounded">
      <div className="flex justify-between text-[10px] mb-1">
        <span className="text-gray-400 uppercase">{label}</span>
        <span className={`font-mono ${dangerSide ? "text-red-400" : "text-white"}`}>{format(value)}{unit}</span>
      </div>
      <div className="relative h-1.5 bg-gray-900 rounded overflow-hidden">
        <div className={`absolute top-0 left-0 h-full ${color}`} style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} />
        {/* threshold marker */}
        <div className="absolute top-0 h-full w-px bg-red-400"
          style={{ left: `${((danger - lo) / (max - lo)) * 100}%` }} />
      </div>
      <div className="flex justify-between text-[9px] text-gray-600 mt-0.5">
        <span>{format(lo)}</span>
        <span className="text-red-400">{format(danger)}</span>
        <span>{format(max)}</span>
      </div>
    </div>
  );
}

export default function RiskPanel() {
  const [r, setR] = useState<Risk | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch(api("/api/risk/state"));
        if (res.ok) setR(await res.json());
      } catch {}
    };
    load();
    const id = setInterval(load, 2000);
    return () => clearInterval(id);
  }, []);

  if (!r) return <div className="bg-gray-900 p-4 rounded-lg border border-gray-800 text-gray-500 text-xs">Loading risk...</div>;

  return (
    <div className={`bg-gray-900 rounded-lg p-4 border ${r.halted ? "border-red-700" : "border-gray-800"}`}>
      <div className="flex justify-between items-center mb-3">
        <div>
          <h2 className="text-white font-bold text-base">Risk Engine</h2>
          <p className="text-xs text-gray-500">circuit breakers + exposure limits</p>
        </div>
        <div className={`text-xs px-2 py-1 rounded font-bold ${r.halted ? "bg-red-900 text-red-400 animate-pulse" : "bg-green-900 text-green-400"}`}>
          {r.halted ? "⚠ HALTED" : "● ACTIVE"}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 mb-3">
        <Gauge label="Daily PnL" value={r.daily_pnl_pct} min={-3} max={3} danger={-2}
          format={(n) => (n >= 0 ? "+" : "") + n.toFixed(2)} unit="%" />
        <Gauge label="Vol Multiplier" value={r.vol_multiplier} max={4} min={0} danger={r.vol_threshold}
          format={(n) => n.toFixed(2)} unit="x" />
        <Gauge label="Positions" value={r.open_positions} max={r.max_positions} min={0} danger={r.max_positions}
          format={(n) => n.toFixed(0)} unit={`/${r.max_positions}`} />
        <Gauge label="Drawdown" value={r.max_drawdown_pct} max={3} min={0} danger={2}
          format={(n) => "-" + n.toFixed(2)} unit="%" />
      </div>

      <div className="grid grid-cols-2 gap-2 mb-3">
        <div className={`p-2 rounded text-center text-xs ${r.drawdown_breaker.triggered ? "bg-red-950 border border-red-700" : "bg-gray-800"}`}>
          <div className="text-[10px] text-gray-400 uppercase">Drawdown Breaker</div>
          <div className={r.drawdown_breaker.triggered ? "text-red-400 font-bold" : "text-green-400"}>
            {r.drawdown_breaker.triggered ? "TRIPPED" : "OK"}
          </div>
        </div>
        <div className={`p-2 rounded text-center text-xs ${r.vol_breaker.triggered ? "bg-red-950 border border-red-700" : "bg-gray-800"}`}>
          <div className="text-[10px] text-gray-400 uppercase">Vol Breaker</div>
          <div className={r.vol_breaker.triggered ? "text-red-400 font-bold" : "text-green-400"}>
            {r.vol_breaker.triggered ? "TRIPPED" : "OK"}
          </div>
        </div>
      </div>

      <div>
        <div className="text-[10px] uppercase text-gray-500 mb-1">Total Exposure</div>
        <div className="text-lg font-mono text-white">${r.exposure_usd.toFixed(2)}</div>
      </div>

      <div className="mt-3">
        <div className="text-[10px] uppercase text-gray-500 mb-1">Recent Alerts</div>
        <div className="space-y-1 max-h-32 overflow-y-auto">
          {r.alerts.length === 0 && <p className="text-gray-600 text-xs">No alerts</p>}
          {r.alerts.slice(0, 5).map((a, i) => (
            <div key={i} className="bg-gray-800 p-1.5 rounded text-[11px]">
              <div className="flex justify-between">
                <span className={a.halted ? "text-red-400 font-bold" : "text-yellow-400"}>{a.event}</span>
                <span className="text-gray-500">{new Date(a.ts).toLocaleTimeString()}</span>
              </div>
              <div className="text-gray-400 text-[10px]">{a.reason}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
