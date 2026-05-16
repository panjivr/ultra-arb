"use client";
import { API_URL, api, ws } from "../lib/api";
import { useEffect, useState } from "react";

interface Signal {
  ts: number; strategy: string; symbol: string; direction?: string;
  probability_score?: number; expected_value?: number;
  confidence_interval?: [number, number]; risk_reward_ratio?: number;
  liquidity_score?: number; volatility_score?: number;
  slippage_estimate_bps?: number; correlation_impact?: number;
  execution_feasibility?: number; failure_probability?: number;
  regime?: number; tradeable?: boolean;
}

const REGIME_LABEL: Record<number, string> = { 0: "LOW VOL", 1: "MED VOL", 2: "HIGH VOL" };
const REGIME_COLOR: Record<number, string> = { 0: "text-green-400", 1: "text-yellow-400", 2: "text-red-400" };

function Bar({ value, color = "bg-blue-500", max = 1 }: { value: number; color?: string; max?: number }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="h-1 bg-gray-800 rounded overflow-hidden">
      <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export default function DetailedSignals() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [filter, setFilter] = useState<"all" | "tradeable">("tradeable");

  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(api("/api/signals?limit=50"));
        if (r.ok) {
          const j = await r.json();
          setSignals(j.signals || []);
        }
      } catch {}
    };
    load();
    const id = setInterval(load, 2000);
    return () => clearInterval(id);
  }, []);

  const filtered = filter === "tradeable" ? signals.filter(s => s.tradeable) : signals;

  return (
    <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
      <div className="flex justify-between items-center mb-3">
        <div>
          <h2 className="text-white font-bold text-base">Signal Feed</h2>
          <p className="text-xs text-gray-500">11-factor AI decision metadata · {filtered.length} signals</p>
        </div>
        <div className="flex gap-1 text-[11px]">
          <button onClick={() => setFilter("tradeable")}
            className={`px-2 py-0.5 rounded ${filter === "tradeable" ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-400"}`}>
            Tradeable
          </button>
          <button onClick={() => setFilter("all")}
            className={`px-2 py-0.5 rounded ${filter === "all" ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-400"}`}>
            All
          </button>
        </div>
      </div>

      <div className="space-y-2 max-h-[480px] overflow-y-auto pr-1">
        {filtered.length === 0 && (
          <p className="text-gray-500 text-xs text-center py-6">No signals match filter</p>
        )}
        {filtered.map((s, i) => {
          const prob = s.probability_score ?? 0;
          const ev = s.expected_value ?? 0;
          const liq = s.liquidity_score ?? 0;
          const vol = s.volatility_score ?? 0;
          const slip = s.slippage_estimate_bps ?? 0;
          const corr = s.correlation_impact ?? 0;
          const feas = s.execution_feasibility ?? 0;
          const fail = s.failure_probability ?? 0;
          const rr = s.risk_reward_ratio ?? 0;
          const ci = s.confidence_interval ?? [prob - 0.05, prob + 0.05];

          return (
            <div key={i} className={`p-2.5 rounded border ${s.tradeable ? "bg-blue-950/40 border-blue-800" : "bg-gray-800/50 border-gray-700"}`}>
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-2">
                  <span className="text-blue-300 font-bold text-sm">{s.strategy}</span>
                  <span className="text-white font-mono text-sm">{s.symbol}</span>
                  {s.direction && (
                    <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${s.direction === "long" ? "bg-green-900 text-green-400" : "bg-red-900 text-red-400"}`}>
                      {s.direction.toUpperCase()}
                    </span>
                  )}
                  {s.regime !== undefined && (
                    <span className={`text-[10px] ${REGIME_COLOR[s.regime]}`}>{REGIME_LABEL[s.regime]}</span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {s.tradeable && <span className="text-green-400 text-xs">⚡ TRADE</span>}
                  <span className="text-gray-500 text-[10px] font-mono">
                    {new Date(s.ts).toLocaleTimeString()}
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-x-3 gap-y-1 text-[11px]">
                <div>
                  <div className="flex justify-between"><span className="text-gray-500">Prob</span>
                    <span className={prob > 0.7 ? "text-green-400" : "text-yellow-400"}>{(prob*100).toFixed(0)}%</span></div>
                  <Bar value={prob} color={prob > 0.7 ? "bg-green-500" : "bg-yellow-500"} />
                  <div className="text-[9px] text-gray-600">CI [{(ci[0]*100).toFixed(0)}-{(ci[1]*100).toFixed(0)}]</div>
                </div>
                <div>
                  <div className="flex justify-between"><span className="text-gray-500">EV</span>
                    <span className="text-cyan-400 font-mono">{ev.toFixed(4)}</span></div>
                  <Bar value={Math.min(ev * 10, 1)} color="bg-cyan-500" />
                  <div className="text-[9px] text-gray-600">R/R {rr.toFixed(2)}x</div>
                </div>
                <div>
                  <div className="flex justify-between"><span className="text-gray-500">Liquidity</span>
                    <span className="text-blue-300">{(liq*100).toFixed(0)}%</span></div>
                  <Bar value={liq} color="bg-blue-500" />
                  <div className="text-[9px] text-gray-600">slip {slip.toFixed(1)}bps</div>
                </div>
                <div>
                  <div className="flex justify-between"><span className="text-gray-500">Exec Feas</span>
                    <span className={feas > 0.8 ? "text-green-400" : "text-yellow-400"}>{(feas*100).toFixed(0)}%</span></div>
                  <Bar value={feas} color={feas > 0.8 ? "bg-green-500" : "bg-yellow-500"} />
                  <div className="text-[9px] text-gray-600">fail {(fail*100).toFixed(0)}%</div>
                </div>
                <div>
                  <div className="flex justify-between"><span className="text-gray-500">Volatility</span>
                    <span className={vol > 0.6 ? "text-red-400" : "text-yellow-400"}>{(vol*100).toFixed(0)}%</span></div>
                  <Bar value={vol} color={vol > 0.6 ? "bg-red-500" : "bg-yellow-500"} />
                </div>
                <div>
                  <div className="flex justify-between"><span className="text-gray-500">Correlation</span>
                    <span className={Math.abs(corr) > 0.2 ? "text-orange-400" : "text-gray-300"}>{corr >= 0 ? "+" : ""}{corr.toFixed(2)}</span></div>
                  <Bar value={Math.abs(corr) * 2} color="bg-orange-500" />
                </div>
                <div>
                  <div className="flex justify-between"><span className="text-gray-500">Slippage</span>
                    <span className={slip < 3 ? "text-green-400" : slip < 8 ? "text-yellow-400" : "text-red-400"}>{slip.toFixed(1)}bps</span></div>
                  <Bar value={Math.min(slip / 15, 1)} color={slip < 3 ? "bg-green-500" : slip < 8 ? "bg-yellow-500" : "bg-red-500"} />
                </div>
                <div>
                  <div className="flex justify-between"><span className="text-gray-500">Fail Prob</span>
                    <span className={fail < 0.15 ? "text-green-400" : fail < 0.3 ? "text-yellow-400" : "text-red-400"}>{(fail*100).toFixed(0)}%</span></div>
                  <Bar value={fail} color={fail < 0.15 ? "bg-green-500" : fail < 0.3 ? "bg-yellow-500" : "bg-red-500"} />
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
