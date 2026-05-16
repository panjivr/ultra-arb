"use client";
import { API_URL, api, ws } from "../lib/api";
import { useEffect, useState } from "react";

interface PositionData {
  recent_orders: Array<{ strategy: string; symbol: string; direction: string; size_usd: number; event: string; pnl?: number; ts: number }>;
  risk_alerts: Array<{ event: string; reason: string; halted?: boolean; ts: number }>;
}

export default function RiskMonitor() {
  const [data, setData] = useState<PositionData>({ recent_orders: [], risk_alerts: [] });

  useEffect(() => {
    const fetch_data = async () => {
      try {
        const res = await fetch(api("/api/positions"));
        if (res.ok) setData(await res.json());
      } catch {}
    };
    fetch_data();
    const id = setInterval(fetch_data, 3000);
    return () => clearInterval(id);
  }, []);

  const isHalted = data.risk_alerts.some(a => a.halted);

  return (
    <div className="bg-gray-900 rounded-xl p-4 border border-gray-700">
      <div className="flex justify-between items-center mb-3">
        <h2 className="text-white font-bold text-lg">Risk Monitor</h2>
        <div className={`text-xs px-2 py-1 rounded font-bold ${isHalted ? "bg-red-900 text-red-400 animate-pulse" : "bg-green-900 text-green-400"}`}>
          {isHalted ? "⚠ HALTED" : "● TRADING"}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="bg-gray-800 p-3 rounded">
          <div className="text-gray-400 text-xs">Recent Orders</div>
          <div className="text-white text-2xl font-mono">{data.recent_orders.length}</div>
        </div>
        <div className="bg-gray-800 p-3 rounded">
          <div className="text-gray-400 text-xs">Risk Alerts</div>
          <div className={`text-2xl font-mono ${data.risk_alerts.length > 0 ? "text-red-400" : "text-white"}`}>
            {data.risk_alerts.length}
          </div>
        </div>
      </div>

      <div className="space-y-1 max-h-40 overflow-y-auto">
        {data.recent_orders.slice(0, 10).map((o, i) => (
          <div key={i} className="flex text-xs gap-2 py-1 border-b border-gray-800">
            <span className="text-gray-500 w-16">{new Date(o.ts).toLocaleTimeString()}</span>
            <span className={`w-12 ${o.event === "CLOSE" ? "text-yellow-400" : "text-green-400"}`}>{o.event}</span>
            <span className="text-white">{o.strategy}</span>
            {o.pnl !== undefined && (
              <span className={`ml-auto ${o.pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                {o.pnl >= 0 ? "+" : ""}{o.pnl.toFixed(2)}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
