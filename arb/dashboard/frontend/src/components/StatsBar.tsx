"use client";
import { API_URL, api, ws } from "../lib/api";
import { useEffect, useState } from "react";

interface Stats {
  total_trades: number; win_rate: number;
  total_pnl_usd: number; total_pnl_pct: number;
  avg_win: number; avg_loss: number;
  profit_factor: number; sharpe_ratio: number;
  max_drawdown_pct: number; expectancy: number;
  best_trade: number; worst_trade: number;
  current_equity: number;
  start_capital?: number;
  is_real_wallet?: boolean;
  wallet_addr?: string;
}

const fmt = (n: number, dp = 2) => (n >= 0 ? "+" : "") + n.toFixed(dp);

function KPI({ label, value, unit = "", trend = "neutral", subtitle = "" }:
  { label: string; value: string; unit?: string; trend?: "good" | "bad" | "neutral"; subtitle?: string }) {
  const color =
    trend === "good" ? "text-green-400" :
    trend === "bad" ? "text-red-400" : "text-white";
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg px-3 py-2 min-w-[120px]">
      <div className="text-[10px] text-gray-500 uppercase tracking-wider">{label}</div>
      <div className={`font-mono text-lg font-bold ${color}`}>{value}<span className="text-xs text-gray-400 ml-0.5">{unit}</span></div>
      {subtitle && <div className="text-[10px] text-gray-500">{subtitle}</div>}
    </div>
  );
}

export default function StatsBar() {
  const [s, setS] = useState<Stats | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(api("/api/stats"));
        if (r.ok) setS(await r.json());
      } catch {}
    };
    load();
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, []);

  if (!s) return <div className="text-gray-500 text-sm">Loading stats...</div>;

  const startCap = s.start_capital ?? 10000;
  const isReal = !!s.is_real_wallet;
  const startLabel = isReal
    ? `wallet $${startCap.toFixed(2)}`
    : `demo $${startCap.toLocaleString()}`;

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-2">
      <div className="bg-gray-900 border border-gray-800 rounded-lg px-3 py-2 min-w-[120px] relative">
        {isReal && (
          <span className="absolute top-1 right-1 text-[8px] bg-purple-700 text-white px-1 rounded font-bold">LIVE</span>
        )}
        <div className="text-[10px] text-gray-500 uppercase tracking-wider">Equity</div>
        <div className={`font-mono text-lg font-bold ${s.current_equity >= startCap ? "text-green-400" : "text-red-400"}`}>
          ${s.current_equity.toFixed(2)}
        </div>
        <div className={`text-[10px] ${isReal ? "text-purple-300" : "text-gray-500"}`}>{startLabel}</div>
      </div>
      <KPI label="Total PnL" value={fmt(s.total_pnl_usd)} unit="USD"
        trend={s.total_pnl_usd >= 0 ? "good" : "bad"} subtitle={fmt(s.total_pnl_pct, 2) + "%"} />
      <KPI label="Win Rate" value={s.win_rate.toFixed(1)} unit="%"
        trend={s.win_rate >= 55 ? "good" : s.win_rate >= 45 ? "neutral" : "bad"}
        subtitle={`${s.total_trades} trades`} />
      <KPI label="Sharpe" value={s.sharpe_ratio.toFixed(2)}
        trend={s.sharpe_ratio >= 1.5 ? "good" : s.sharpe_ratio >= 0.5 ? "neutral" : "bad"}
        subtitle="annualized" />
      <KPI label="Profit Factor" value={s.profit_factor.toFixed(2)}
        trend={s.profit_factor >= 1.5 ? "good" : s.profit_factor >= 1.0 ? "neutral" : "bad"}
        subtitle="wins / losses" />
      <KPI label="Max DD" value={"-" + s.max_drawdown_pct.toFixed(2)} unit="%"
        trend={s.max_drawdown_pct < 2 ? "good" : s.max_drawdown_pct < 5 ? "neutral" : "bad"}
        subtitle="peak-to-trough" />
      <KPI label="Avg Win / Loss" value={`+${s.avg_win.toFixed(2)} / ${s.avg_loss.toFixed(2)}`}
        trend="neutral" subtitle={`exp ${fmt(s.expectancy, 3)}`} />
      <KPI label="Best / Worst" value={`${fmt(s.best_trade)} / ${fmt(s.worst_trade)}`}
        trend="neutral" subtitle="USD" />
    </div>
  );
}
