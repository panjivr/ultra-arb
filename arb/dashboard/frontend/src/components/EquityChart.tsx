"use client";
import { api } from "../lib/api";
import { useEffect, useState } from "react";
import { useLiveReal } from "../lib/useLiveReal";
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
  const { live, realMode } = useLiveReal(3000);

  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(api(`/api/equity?window=${win}`));
        if (r.ok) setData(await r.json());
      } catch { /* ignore */ }
    };
    load();
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, [win]);

  // ── REAL mode: derive the curve from the actual Polymarket balance +
  // realized PnL. No paper $10k. (A full time-series needs history we don't
  // keep, so we draw the honest start→now line from real figures.) ──
  const realView: EquityData | null = (realMode && live?.wallet_balance != null) ? (() => {
    const bal = live.wallet_balance as number;
    const realized = live.realized_pnl ?? 0;
    const start = bal - realized;
    const now = Date.now();
    return {
      window: win, current_equity: bal,
      total_pnl_pct: start ? (realized / start) * 100 : 0,
      max_drawdown_pct: 0,
      start_capital: start,
      is_real_wallet: true,
      curve: [
        { time: String(now - 3_600_000), equity: start, drawdown_pct: 0 },
        { time: String(now), equity: bal, drawdown_pct: 0 },
      ],
    };
  })() : null;

  const d = realMode ? realView : data;
  const color = (d?.total_pnl_pct ?? 0) >= 0 ? "#22c55e" : "#ef4444";

  const curveLen = d?.curve?.length ?? 0;
  const winningSpan = curveLen > 1 && d ? (d.total_pnl_pct >= 0) : false;
  const avgPnlPerPoint = curveLen > 1 && d
    ? (d.curve[curveLen - 1].equity - d.curve[0].equity) / curveLen
    : 0;
  const volatility = (() => {
    if (curveLen < 2 || !d) return 0;
    const diffs = [];
    for (let i = 1; i < d.curve.length; i++) diffs.push(d.curve[i].equity - d.curve[i - 1].equity);
    const mean = diffs.reduce((a, b) => a + b, 0) / diffs.length;
    const variance = diffs.reduce((s, x) => s + (x - mean) ** 2, 0) / diffs.length;
    return Math.sqrt(variance);
  })();

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 min-h-[420px] flex flex-col overflow-hidden">
      <div className="px-4 pt-4 pb-2">
        <div className="flex justify-between items-center mb-3">
          <div>
            <h2 className="text-white font-bold text-base flex items-center gap-2">
              <span className="text-green-400">📈</span> Equity Curve
              {realMode ? (
                <span className="text-[9px] bg-emerald-700 text-white px-1.5 py-0.5 rounded font-bold uppercase tracking-wide">UANG ASLI</span>
              ) : (
                <span className="text-[9px] bg-amber-800/70 text-amber-200 px-1.5 py-0.5 rounded font-bold uppercase tracking-wide">DEMO</span>
              )}
            </h2>
            <p className="text-xs text-gray-500">
              {realMode ? "saldo Polymarket · modal awal " : "cumulative PnL · starting capital "}
              <span className={realMode ? "text-emerald-300 font-mono" : ""}>
                ${(d?.start_capital ?? (realMode ? 0 : 10000)).toLocaleString(undefined, { maximumFractionDigits: 2 })}
              </span>
            </p>
          </div>
          <div className="flex gap-1">
            {["1h", "24h", "7d", "30d"].map(w => (
              <button key={w} onClick={() => setWin(w)}
                className={`px-2.5 py-1 text-[11px] rounded font-semibold transition-colors ${
                  win === w ? "bg-blue-600 text-white shadow-lg shadow-blue-900/40" :
                  "bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white"}`}>
                {w}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-4 gap-2 mb-3">
          <div className="bg-gray-950/60 rounded px-3 py-2 border border-gray-800">
            <div className="text-gray-500 uppercase text-[9px] mb-0.5">Equity</div>
            <div className="font-mono text-lg font-bold" style={{ color }}>
              ${d?.current_equity?.toLocaleString(undefined, { maximumFractionDigits: 2 }) ?? "—"}
            </div>
          </div>
          <div className="bg-gray-950/60 rounded px-3 py-2 border border-gray-800">
            <div className="text-gray-500 uppercase text-[9px] mb-0.5">Return</div>
            <div className="font-mono text-lg font-bold" style={{ color }}>
              {(d?.total_pnl_pct ?? 0) >= 0 ? "+" : ""}{(d?.total_pnl_pct ?? 0).toFixed(2)}%
            </div>
          </div>
          <div className="bg-gray-950/60 rounded px-3 py-2 border border-gray-800">
            <div className="text-gray-500 uppercase text-[9px] mb-0.5">Max DD</div>
            <div className="font-mono text-lg font-bold text-red-400">-{(d?.max_drawdown_pct ?? 0).toFixed(2)}%</div>
          </div>
          <div className="bg-gray-950/60 rounded px-3 py-2 border border-gray-800">
            <div className="text-gray-500 uppercase text-[9px] mb-0.5">Volatility</div>
            <div className="font-mono text-lg font-bold text-purple-400">${volatility.toFixed(2)}</div>
          </div>
        </div>
      </div>

      <div className="px-2">
        <ResponsiveContainer width="100%" height={280}>
          <ComposedChart data={d?.curve ?? []} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
            <defs>
              <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.45} />
                <stop offset="100%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="time" tick={{ fill: "#6b7280", fontSize: 9 }}
              tickFormatter={(v) => {
                const dt = new Date(typeof v === "number" ? v : Number(v) || v);
                return isNaN(dt.getTime()) ? v : `${dt.getHours()}:${String(dt.getMinutes()).padStart(2, "0")}`;
              }} />
            <YAxis yAxisId="left" tick={{ fill: "#6b7280", fontSize: 10 }} domain={["auto", "auto"]} />
            <YAxis yAxisId="right" orientation="right" tick={{ fill: "#ef4444", fontSize: 10 }} domain={[0, "dataMax + 1"]} />
            <ReferenceLine yAxisId="left" y={d?.start_capital ?? d?.curve?.[0]?.equity ?? 0}
              stroke="#a855f7" strokeDasharray="3 3"
              label={{ value: realMode ? "modal" : "start", position: "right", fill: "#a855f7", fontSize: 9 }} />
            <Tooltip contentStyle={{ background: "#111827", border: "1px solid #374151", fontSize: 11 }} labelStyle={{ color: "#9ca3af" }} />
            <Area yAxisId="left" type="monotone" dataKey="equity" stroke={color} fill="url(#eqGrad)" strokeWidth={2} />
            <Line yAxisId="right" type="monotone" dataKey="drawdown_pct" stroke="#ef4444" strokeWidth={1.2} dot={false} strokeDasharray="2 2" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="px-4 py-2 border-t border-gray-800 bg-gray-950/40 grid grid-cols-3 gap-2 text-[10px]">
        <div className="text-gray-500">Points: <span className="font-mono text-white">{curveLen}</span></div>
        <div className="text-gray-500 text-center">
          Trend: <span className={`font-mono font-bold ${winningSpan ? "text-green-400" : "text-red-400"}`}>{winningSpan ? "▲ UP" : "▼ DOWN"}</span>
        </div>
        <div className="text-gray-500 text-right">Avg PnL/bar: <span className="font-mono text-white">${avgPnlPerPoint.toFixed(3)}</span></div>
      </div>
    </div>
  );
}
