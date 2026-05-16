"use client";
import { API_URL, api, ws } from "../lib/api";
import { useEffect, useState } from "react";

interface Spread {
  symbol: string; exchanges: string[];
  buy_at: number; buy_ex?: string;
  sell_at: number; sell_ex?: string;
  spread_bps: number; edge_usd: number;
}

export default function SpreadsMonitor() {
  const [spreads, setSpreads] = useState<Spread[]>([]);

  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(api("/api/spreads"));
        if (r.ok) {
          const j = await r.json();
          setSpreads(j.spreads || []);
        }
      } catch {}
    };
    load();
    const id = setInterval(load, 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
      <div className="mb-3">
        <h2 className="text-white font-bold text-base">Cross-Exchange Spreads</h2>
        <p className="text-xs text-gray-500">live bid/ask gap across venues — arb opportunity when bps {">"} 14</p>
      </div>

      {spreads.length === 0 ? (
        <p className="text-gray-500 text-xs text-center py-6">No live tick data — start feeds</p>
      ) : (
        <div className="space-y-1.5">
          {spreads.slice(0, 6).map((s, i) => {
            const arb = s.spread_bps > 14;  // 14 bps = covers maker+taker fees
            return (
              <div key={i} className={`p-2 rounded text-xs ${arb ? "bg-green-950/40 border border-green-800" : "bg-gray-800/60"}`}>
                <div className="flex justify-between items-center mb-1">
                  <span className="text-white font-mono font-bold">{s.symbol}</span>
                  <span className={`font-mono font-bold ${arb ? "text-green-400" : s.spread_bps > 5 ? "text-yellow-400" : "text-gray-400"}`}>
                    {s.spread_bps >= 0 ? "+" : ""}{s.spread_bps.toFixed(2)} bps
                  </span>
                </div>
                <div className="flex justify-between gap-2 text-[10px] font-mono">
                  <div className="bg-red-950/40 px-1.5 py-0.5 rounded flex-1">
                    <span className="text-gray-500">BUY </span>
                    <span className="text-red-400">{s.buy_ex}</span>
                    <span className="text-white ml-1">{s.buy_at.toFixed(2)}</span>
                  </div>
                  <div className="bg-green-950/40 px-1.5 py-0.5 rounded flex-1">
                    <span className="text-gray-500">SELL </span>
                    <span className="text-green-400">{s.sell_ex}</span>
                    <span className="text-white ml-1">{s.sell_at.toFixed(2)}</span>
                  </div>
                </div>
                {arb && (
                  <div className="text-[10px] text-green-400 mt-1">
                    ⚡ edge ${s.edge_usd.toFixed(2)} per unit
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
