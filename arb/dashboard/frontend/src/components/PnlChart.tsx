"use client";
import { API_URL, api, ws } from "../lib/api";
import { useEffect, useState } from "react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";

interface PnlPoint { time: string; pnl: number; trades: number; }

export default function PnlChart() {
  const [data, setData] = useState<PnlPoint[]>([]);
  const [totalPnl, setTotalPnl] = useState(0);
  const [window, setWindow] = useState("24h");

  const fetch_pnl = async () => {
    try {
      const res = await fetch(api(`/api/pnl?window=${window}`));
      if (res.ok) {
        const json = await res.json();
        setData(json.data || []);
        setTotalPnl(json.total_pnl || 0);
      }
    } catch {}
  };

  useEffect(() => { fetch_pnl(); const id = setInterval(fetch_pnl, 5000); return () => clearInterval(id); }, [window]);

  const color = totalPnl >= 0 ? "#22c55e" : "#ef4444";

  return (
    <div className="bg-gray-900 rounded-xl p-4 border border-gray-700">
      <div className="flex justify-between items-center mb-3">
        <h2 className="text-white font-bold text-lg">PnL Curve</h2>
        <div className="flex gap-2">
          {["1h","6h","24h","7d"].map(w => (
            <button key={w} onClick={() => setWindow(w)}
              className={`px-2 py-1 text-xs rounded ${window===w ? "bg-blue-600 text-white" : "bg-gray-700 text-gray-300"}`}>
              {w}
            </button>
          ))}
        </div>
      </div>
      <div className="text-2xl font-mono mb-3" style={{ color }}>
        {totalPnl >= 0 ? "+" : ""}{totalPnl.toFixed(4)} USDT
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={data}>
          <defs>
            <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={color} stopOpacity={0.3} />
              <stop offset="95%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis dataKey="time" tick={{ fill: "#9ca3af", fontSize: 10 }}
            tickFormatter={v => v.split("T")[1]?.slice(0,5) || v.slice(-5)} />
          <YAxis tick={{ fill: "#9ca3af", fontSize: 10 }} />
          <Tooltip contentStyle={{ background: "#111827", border: "1px solid #374151" }}
            labelStyle={{ color: "#9ca3af" }} itemStyle={{ color }} />
          <Area type="monotone" dataKey="pnl" stroke={color} fill="url(#pnlGrad)" strokeWidth={2} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
