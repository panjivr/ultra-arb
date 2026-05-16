"use client";
import { API_URL, api, ws } from "../lib/api";
import { useEffect, useState } from "react";

interface CorrData { strategies: string[]; matrix: number[][]; }

export default function CorrelationMatrix() {
  const [d, setD] = useState<CorrData | null>(null);
  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(api("/api/stats/correlation"));
        if (r.ok) setD(await r.json());
      } catch {}
    };
    load();
    const id = setInterval(load, 15_000);
    return () => clearInterval(id);
  }, []);
  if (!d || d.strategies.length < 2) {
    return (
      <div className="bg-gray-900 rounded-lg p-3 border border-gray-800">
        <h2 className="text-white font-bold text-base mb-1">Strategy Correlation</h2>
        <p className="text-gray-500 text-xs text-center py-4">Need at least 2 active strategies</p>
      </div>
    );
  }
  const cellColor = (v: number) => {
    if (v >= 0.7) return "bg-red-700/80 text-white";
    if (v >= 0.3) return "bg-orange-600/70 text-white";
    if (v >= -0.3) return "bg-gray-700 text-gray-300";
    if (v >= -0.7) return "bg-cyan-700/60 text-white";
    return "bg-blue-700/80 text-white";
  };
  return (
    <div className="bg-gray-900 rounded-lg p-3 border border-gray-800">
      <h2 className="text-white font-bold text-base mb-1">Strategy Correlation</h2>
      <p className="text-[10px] text-gray-500 mb-2">low correl = good diversification</p>
      <div className="overflow-x-auto">
        <table className="text-[10px] font-mono">
          <thead>
            <tr>
              <th className="p-1"></th>
              {d.strategies.map(s => (
                <th key={s} className="p-1 text-gray-400 -rotate-45 origin-left whitespace-nowrap pl-3 pb-3">{s.slice(0, 8)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {d.matrix.map((row, i) => (
              <tr key={i}>
                <td className="p-1 text-gray-400 text-right pr-2">{d.strategies[i].slice(0, 12)}</td>
                {row.map((v, j) => (
                  <td key={j} className={`p-1 text-center w-12 h-8 ${cellColor(v)}`} title={`${d.strategies[i]} ↔ ${d.strategies[j]}: ${v}`}>
                    {v.toFixed(2)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex justify-between text-[9px] text-gray-500 mt-2">
        <span>← negative (hedged)</span>
        <span>0 (independent)</span>
        <span>positive (redundant) →</span>
      </div>
    </div>
  );
}
