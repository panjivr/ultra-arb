"use client";
import { API_URL, api, ws } from "../lib/api";
import { useEffect, useState } from "react";
import {
  ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts";

interface Point { time: string; equity: number; drawdown_pct: number; }
interface EquityData {
  window: string; current_equity: number;
  total_pnl_pct: number; max_drawdown_pct: number; curve: Point[];
  start_capital?: number;
  is_real_wallet?: boolean;
  wallet_addr?: string;
  trades_in_window?: number;
}

export default function EquityChart() {
  const [data, setData] = useState<EquityData | null>(null);
  const [win, setWin] = useState("7d");

  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(api(`/api/equity?window=${win}`));
        if (r.ok) setData(await r.json());
      } catch {}
    };
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [win]);

  const color = (data?.total_pnl_pct ?? 0) >= 0 ? "#22c55e" : "#ef4444";

  // Compute trade analytics from curve
  const curveLen = data?.curve?.length ?? 0;
  const winningSpan = curveLen > 1 && data ? (data.total_pnl_pct >= 0) : false;
  // Average daily/hourly PnL estimate
  const avgPnlPerPoint = curveLen > 1 && data
    ? (data.curve[curveLen - 1].equity - data.curve[0].equity) / curveLen
    : 0;
  // Volatility (stddev of equity changes)
  const volatility = (() => {
    if (curveLen < 2 || !data) return 0;
    const diffs = [];
    for (let i = 1; i < data.curve.length; i++) {
      diffs.push(data.curve[i].equity - data.curve[i - 1].equity);
    }
    const mean = diffs.reduce((a, b) => a + b, 0) / diffs.length;
    const variance = diffs.reduce((s, d) => s + (d - mean) ** 2, 0) / diffs.length;
    return Math.sqrt(variance);
  })();

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 min-h-[420px] flex flex-col overflow-hidden">
      <div className="px-4 pt-4 pb-2">
        <div className="flex justify-between items-center mb-3">
          <div>
            <h2 className="text-white font-bold text-base flex items-center gap-2">
              <span className="text-green-400">📈</span> Equity Curve
              {data?.is_real_wallet && (
                <span className="text-[9px] bg-purple-700 text-white px-1.5 py-0.5 rounded font-bold uppercase tracking-wide">
                  WALLET LIVE
                </span>
              )}
            </h2>
            <p className="text-xs text-gray-500">
              cumulative PnL · starting capital{" "}
              <span className={data?.is_real_wallet ? "text-purple-300 font-mono" : ""}>
                ${(data?.start_capital ?? 10000).toLocaleString(undefined, { maximumFractionDigits: 2 })}
              </span>
              {data?.is_real_wallet && data?.wallet_addr && (
                <span className="text-purple-400 ml-1">· {data.wallet_addr.slice(0,6)}…{data.wallet_addr.slice(-4)}</span>
              )}
            </p>
          </div>
          <div className="flex gap-1">
            {["1h","24h","7d","30d"].map(w => (
              <button key={w} onClick={() => setWin(w)}
                className={`px-2.5 py-1 text-[11px] rounded font-semibold transition-colors ${
                  win===w ? "bg-blue-600 text-white shadow-lg shadow-blue-900/40" :
                  "bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white"
                }`}>
                {w}
              </button>
            ))}
          </div>
        </div>

        {/* KPI grid — 4 stats inline */}
        <div className="grid grid-cols-4 gap-2 mb-3">
          <div className="bg-gray-950/60 rounded px-3 py-2 border border-gray-800">
            <div className="text-gray-500 uppercase text-[9px] mb-0.5">Equity</div>
            <div className="font-mono text-lg font-bold" style={{ color }}>
              ${data?.current_equity?.toLocaleString(undefined, { maximumFractionDigits: 2 }) ?? "—"}
            </div>
          </div>
          <div className="bg-gray-950/60 rounded px-3 py-2 border border-gray-800">
            <div className="text-gray-500 uppercase text-[9px] mb-0.5">Return</div>
            <div className="font-mono text-lg font-bold" style={{ color }}>
              {(data?.total_pnl_pct ?? 0) >= 0 ? "+" : ""}{(data?.total_pnl_pct ?? 0).toFixed(2)}%
            </div>
          </div>
          <div className="bg-gray-950/60 rounded px-3 py-2 border border-gray-800">
            <div className="text-gray-500 uppercase text-[9px] mb-0.5">Max DD</div>
            <div className="font-mono text-lg font-bold text-red-400">
              -{(data?.max_drawdown_pct ?? 0).toFixed(2)}%
            </div>
          </div>
          <div className="bg-gray-950/60 rounded px-3 py-2 border border-gray-800">
            <div className="text-gray-500 uppercase text-[9px] mb-0.5">Volatility</div>
            <div className="font-mono text-lg font-bold text-purple-400">
              ${volatility.toFixed(2)}
            </div>
          </div>
        </div>
      </div>

      <div className="px-2">
        <ResponsiveContainer width="100%" height={280}>
          <ComposedChart data={data?.curve ?? []} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
            <defs>
              <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.45} />
                <stop offset="100%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="time" tick={{ fill: "#6b7280", fontSize: 9 }}
              tickFormatter={(v) => {
                const d = new Date(typeof v === "number" ? v : v);
                return isNaN(d.getTime()) ? v : `${d.getHours()}:${String(d.getMinutes()).padStart(2,'0')}`;
              }} />
            <YAxis yAxisId="left" tick={{ fill: "#6b7280", fontSize: 10 }} domain={['auto', 'auto']} />
            <YAxis yAxisId="right" orientation="right" tick={{ fill: "#ef4444", fontSize: 10 }}
              domain={[0, 'dataMax + 1']} />
            <ReferenceLine yAxisId="left" y={data?.start_capital ?? data?.curve?.[0]?.equity ?? 10000}
              stroke="#a855f7" strokeDasharray="3 3"
              label={{ value: data?.is_real_wallet ? "wallet" : "start", position: "right", fill: "#a855f7", fontSize: 9 }} />
            <Tooltip
              contentStyle={{ background: "#111827", border: "1px solid #374151", fontSize: 11 }}
              labelStyle={{ color: "#9ca3af" }} />
            <Area yAxisId="left" type="monotone" dataKey="equity" stroke={color}
              fill="url(#eqGrad)" strokeWidth={2} />
            <Line yAxisId="right" type="monotone" dataKey="drawdown_pct" stroke="#ef4444"
              strokeWidth={1.2} dot={false} strokeDasharray="2 2" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="px-4 py-2 border-t border-gray-800 bg-gray-950/40 grid grid-cols-3 gap-2 text-[10px]">
        <div className="text-gray-500">
          Points: <span className="font-mono text-white">{curveLen}</span>
        </div>
        <div className="text-gray-500 text-center">
          Trend: <span className={`font-mono font-bold ${winningSpan ? "text-green-400" : "text-red-400"}`}>
            {winningSpan ? "▲ UP" : "▼ DOWN"}
          </span>
        </div>
        <div className="text-gray-500 text-right">
          Avg PnL/bar: <span className="font-mono text-white">${avgPnlPerPoint.toFixed(3)}</span>
        </div>
      </div>
    </div>
  );
}
