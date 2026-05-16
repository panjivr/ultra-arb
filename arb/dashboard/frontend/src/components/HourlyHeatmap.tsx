"use client";
import { API_URL, api, ws } from "../lib/api";
import { useEffect, useState } from "react";

interface Hour { hour: number; trades: number; pnl: number; win_rate: number; }

export default function HourlyHeatmap() {
  const [hours, setHours] = useState<Hour[]>([]);
  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(api("/api/stats/hourly"));
        if (r.ok) {
          const j = await r.json();
          setHours(j.hourly || []);
        }
      } catch {}
    };
    load();
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, []);

  const maxAbs = Math.max(1, ...hours.map(h => Math.abs(h.pnl)));

  return (
    <div className="bg-gray-900 rounded-lg p-3 border border-gray-800">
      <h2 className="text-white font-bold text-base mb-1">PnL by Hour of Day</h2>
      <p className="text-[10px] text-gray-500 mb-2">find your best trading windows · UTC</p>
      <div className="grid grid-cols-12 gap-0.5">
        {hours.map(h => {
          const intensity = Math.min(1, Math.abs(h.pnl) / maxAbs);
          const bg = h.pnl >= 0
            ? `rgba(34, 197, 94, ${0.15 + intensity * 0.75})`
            : `rgba(239, 68, 68, ${0.15 + intensity * 0.75})`;
          return (
            <div key={h.hour} className="aspect-square rounded text-center p-0.5 flex flex-col justify-between hover:ring-1 hover:ring-white/40 cursor-default"
              style={{ background: bg }} title={`${h.hour}:00 - ${h.trades} trades, ${h.win_rate}% WR, ${h.pnl >= 0 ? "+" : ""}$${h.pnl.toFixed(2)}`}>
              <div className="text-[8px] text-white font-mono">{h.hour}</div>
              <div className="text-[8px] text-white font-mono font-bold">{h.trades}</div>
            </div>
          );
        })}
      </div>
      <div className="flex items-center justify-between mt-2 text-[10px] text-gray-500">
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded" style={{ background: "rgba(239,68,68,0.9)" }} />
          <span>loss</span>
        </div>
        <div>hour-of-day · trades count</div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded" style={{ background: "rgba(34,197,94,0.9)" }} />
          <span>win</span>
        </div>
      </div>
    </div>
  );
}
