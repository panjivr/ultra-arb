"use client";
import { useEffect, useState } from "react";
import { api } from "../lib/api";

interface Row {
  asset: string; symbol: string; avg: number | null; price: number | null;
  returns: Record<string, number | null>;
}
interface Matrix { timeframes: string[]; rows: Row[]; ts: number; }

function cellColor(v: number | null): string {
  if (v === null || v === undefined) return "bg-gray-900 text-gray-700";
  const a = Math.min(Math.abs(v) / 8, 1); // scale: ±8% = full color
  if (v > 0) return "text-green-300";
  if (v < 0) return "text-red-300";
  return "text-gray-400";
  void a;
}
function cellBg(v: number | null): string {
  if (v === null || v === undefined) return "rgba(30,41,59,0.3)";
  const a = Math.min(Math.abs(v) / 8, 0.85);
  return v >= 0 ? `rgba(16,185,129,${a})` : `rgba(239,68,68,${a})`;
}

export default function RobustnessMatrix() {
  const [m, setM] = useState<Matrix | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const d = await fetch(api("/api/matrix")).then(r => r.json());
        if (alive) setM(d);
      } catch { /* ignore */ }
    };
    load();
    const id = setInterval(load, 15000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const tfs = m?.timeframes || ["5m", "15m", "30m", "1h", "4h", "1d"];

  return (
    <div className="bg-gray-950 rounded-xl p-4 border border-gray-800 font-mono">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-white font-bold text-sm tracking-wider">◧ ROBUSTNESS MATRIX</h2>
          <p className="text-[10px] text-gray-500">7 assets × 6 timeframes · real Gate.io returns</p>
        </div>
        <span className="text-[10px] text-green-400">● LIVE</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-[11px] border-separate" style={{ borderSpacing: "2px" }}>
          <thead>
            <tr className="text-gray-500">
              <th className="text-left font-normal px-2">ASSET</th>
              {tfs.map(tf => <th key={tf} className="font-normal px-2 text-center">{tf.toUpperCase()}</th>)}
              <th className="font-normal px-2 text-center text-amber-400">AVG</th>
            </tr>
          </thead>
          <tbody>
            {(m?.rows || []).map(row => (
              <tr key={row.asset}>
                <td className="px-2 text-white whitespace-nowrap">
                  {row.asset}
                  {row.price != null && <span className="text-gray-600 ml-1">${row.price?.toLocaleString()}</span>}
                </td>
                {tfs.map(tf => {
                  const v = row.returns?.[tf];
                  return (
                    <td key={tf} className={`px-2 py-1 text-center rounded ${cellColor(v ?? null)}`}
                        style={{ background: cellBg(v ?? null) }}>
                      {v == null ? "·" : `${v > 0 ? "+" : ""}${v.toFixed(1)}%`}
                    </td>
                  );
                })}
                <td className="px-2 py-1 text-center rounded font-bold"
                    style={{ background: cellBg(row.avg) }}>
                  {row.avg == null ? "·" : `${row.avg > 0 ? "+" : ""}${row.avg.toFixed(1)}%`}
                </td>
              </tr>
            ))}
            {(!m || m.rows.length === 0) && (
              <tr><td colSpan={tfs.length + 2} className="text-gray-600 text-center py-6">Loading matrix…</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
