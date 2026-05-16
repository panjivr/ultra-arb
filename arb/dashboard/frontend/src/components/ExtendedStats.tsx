"use client";
import { API_URL, api, ws } from "../lib/api";
import { useEffect, useState } from "react";

interface Ext {
  sortino_ratio: number; calmar_ratio: number; recovery_factor: number;
  max_consec_wins: number; max_consec_losses: number;
  current_streak: number; current_streak_type: string;
  expectancy_per_dollar: number; kelly_optimal_pct: number;
  tail_ratio: number; var_95: number; var_99: number;
  avg_trade_size_usd: number; total_volume_usd: number;
}

function Card({ label, value, hint, color = "text-white" }: { label: string; value: string; hint?: string; color?: string }) {
  return (
    <div className="bg-gray-800 rounded p-2">
      <div className="text-[9px] uppercase tracking-wider text-gray-500">{label}</div>
      <div className={`font-mono text-lg font-bold ${color}`}>{value}</div>
      {hint && <div className="text-[9px] text-gray-600">{hint}</div>}
    </div>
  );
}

export default function ExtendedStats() {
  const [e, setE] = useState<Ext | null>(null);
  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(api("/api/stats/extended"));
        if (r.ok) setE(await r.json());
      } catch {}
    };
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);
  if (!e) return <div className="bg-gray-900 p-3 rounded-lg border border-gray-800 text-gray-500 text-xs">Loading...</div>;

  const streakColor = e.current_streak_type === "win" ? "text-green-400" :
                     e.current_streak_type === "loss" ? "text-red-400" : "text-gray-300";

  return (
    <div className="bg-gray-900 rounded-lg p-3 border border-gray-800">
      <h2 className="text-white font-bold text-base mb-2">Advanced Risk Metrics</h2>
      <div className="grid grid-cols-2 gap-1.5">
        <Card label="Sortino" value={e.sortino_ratio.toFixed(2)} hint="downside-only Sharpe"
          color={e.sortino_ratio >= 2 ? "text-green-400" : e.sortino_ratio >= 1 ? "text-yellow-400" : "text-red-400"} />
        <Card label="Calmar" value={e.calmar_ratio.toFixed(2)} hint="return / max DD"
          color={e.calmar_ratio >= 3 ? "text-green-400" : e.calmar_ratio >= 1 ? "text-yellow-400" : "text-red-400"} />
        <Card label="Recovery Factor" value={e.recovery_factor.toFixed(2)} hint="profit / DD$"
          color={e.recovery_factor >= 5 ? "text-green-400" : "text-yellow-400"} />
        <Card label="Kelly Optimal" value={e.kelly_optimal_pct.toFixed(2) + "%"} hint="position fraction"
          color="text-cyan-400" />
        <Card label="Max Wins Streak" value={e.max_consec_wins.toString()} hint="consecutive" color="text-green-400" />
        <Card label="Max Loss Streak" value={e.max_consec_losses.toString()} hint="consecutive" color="text-red-400" />
        <Card label="Current Streak" value={`${e.current_streak} ${e.current_streak_type.toUpperCase()}`}
          color={streakColor} />
        <Card label="Tail Ratio" value={e.tail_ratio.toFixed(2)} hint="P95 / P5"
          color={e.tail_ratio >= 1.5 ? "text-green-400" : "text-yellow-400"} />
        <Card label="VaR 95%" value={"$" + e.var_95.toFixed(2)} hint="worst-case 5%" color="text-orange-400" />
        <Card label="VaR 99%" value={"$" + e.var_99.toFixed(2)} hint="worst-case 1%" color="text-red-400" />
        <Card label="Avg Trade $" value={"$" + e.avg_trade_size_usd.toFixed(0)} color="text-gray-300" />
        <Card label="Total Volume" value={"$" + (e.total_volume_usd / 1000).toFixed(1) + "k"} color="text-blue-300" />
      </div>
    </div>
  );
}
