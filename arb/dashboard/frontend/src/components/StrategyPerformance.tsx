"use client";
import { API_URL, api, ws } from "../lib/api";
import { useEffect, useState } from "react";

interface Strategy {
  strategy: string; trades: number;
  pnl_usd: number; win_rate: number;
  avg_pnl: number; best: number; worst: number;
}

export default function StrategyPerformance() {
  const [list, setList] = useState<Strategy[]>([]);

  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(api("/api/strategies"));
        if (r.ok) {
          const j = await r.json();
          setList(j.strategies || []);
        }
      } catch {}
    };
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  const maxAbs = Math.max(1, ...list.map(s => Math.abs(s.pnl_usd)));

  return (
    <div className="bg-gray-900 rounded-lg p-4 border border-gray-800 h-full">
      <h2 className="text-white font-bold text-base mb-3">Strategy Performance</h2>
      {list.length === 0 ? (
        <p className="text-gray-500 text-xs text-center py-6">No strategy data yet</p>
      ) : (
        <div className="space-y-2">
          {list.map((s) => {
            const positive = s.pnl_usd >= 0;
            const barPct = Math.abs(s.pnl_usd) / maxAbs * 100;
            return (
              <div key={s.strategy} className="text-xs">
                <div className="flex justify-between items-center mb-0.5">
                  <span className="text-blue-300 font-bold">{s.strategy}</span>
                  <span className={`font-mono ${positive ? "text-green-400" : "text-red-400"}`}>
                    {positive ? "+" : ""}${s.pnl_usd.toFixed(2)}
                  </span>
                </div>
                <div className="relative h-1.5 bg-gray-800 rounded overflow-hidden">
                  <div className={`absolute top-0 left-0 h-full ${positive ? "bg-green-500" : "bg-red-500"}`}
                    style={{ width: `${barPct}%` }} />
                </div>
                <div className="flex justify-between text-[10px] text-gray-500 mt-0.5">
                  <span>{s.trades}t · WR {s.win_rate}%</span>
                  <span>best +${s.best} / worst ${s.worst}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
