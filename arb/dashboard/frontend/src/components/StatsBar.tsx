"use client";
import { api } from "../lib/api";
import { useLiveReal } from "../lib/useLiveReal";
import { useEffect, useState, ReactNode } from "react";
import AnimatedNumber from "./AnimatedNumber";

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

const sign = (n: number) => (n >= 0 ? "+" : "");

function KPI({ label, value, unit = "", trend = "neutral", subtitle = "" }:
  { label: string; value: ReactNode; unit?: string; trend?: "good" | "bad" | "neutral"; subtitle?: string }) {
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
  const { live, realMode } = useLiveReal(3000);

  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(api("/api/stats"));
        if (r.ok) setS(await r.json());
      } catch {}
    };
    load();
    const id = setInterval(load, 2000);
    return () => clearInterval(id);
  }, []);

  // ── REAL mode: only the actual Polymarket account — no paper figures ──
  if (realMode) {
    const bal = live?.wallet_balance;
    const pnl = live?.realized_pnl ?? 0;
    const caps = live?.caps;
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-2">
        <div className="bg-gray-900 border border-emerald-800/50 rounded-lg px-3 py-2 min-w-[120px] relative">
          <span className="absolute top-1 right-1 text-[8px] bg-emerald-700 text-white px-1 rounded font-bold">REAL</span>
          <div className="text-[10px] text-gray-500 uppercase tracking-wider">Real Balance</div>
          <div className="font-mono text-lg font-bold text-white">
            {bal == null ? <span className="text-gray-500 text-sm">—</span> :
              <>$<AnimatedNumber value={bal} format={(n) => n.toFixed(2)} /></>}
          </div>
          <div className="text-[10px] text-emerald-300">Polymarket</div>
        </div>
        <KPI label="Realized PnL" unit="USD" trend={pnl >= 0 ? "good" : "bad"}
          value={<AnimatedNumber value={pnl} format={(n) => sign(n) + n.toFixed(2)} />}
          subtitle="order resolved" />
        <KPI label="Orders" value={live?.orders_count ?? 0} subtitle="real ditaruh" />
        <KPI label="Open" value={live?.open_count ?? 0} subtitle={`/ ${caps?.max_open ?? 5} maks`} />
        <KPI label="Spent Today" unit="USD"
          value={<AnimatedNumber value={live?.daily_spend ?? 0} format={(n) => n.toFixed(2)} />}
          subtitle={`/ $${caps?.daily ?? 5} cap`} />
        <KPI label="Total Spent" unit="USD"
          value={<AnimatedNumber value={live?.total_spend ?? 0} format={(n) => n.toFixed(2)} />}
          subtitle={`/ $${caps?.total ?? 25} cap`} />
        <KPI label="Per-bet Cap" unit="USD" value={(caps?.bet ?? 2).toFixed(2)} subtitle="maks / taruhan" />
        <KPI label="Status"
          trend={live?.halted ? "bad" : live?.armed ? "good" : "neutral"}
          value={live?.halted ? "HALTED" : live?.armed ? "ARMED" : "STANDBY"}
          subtitle={live?.armed ? "eksekusi aktif" : "menunggu arm"} />
      </div>
    );
  }

  if (!s) return <div className="text-gray-500 text-sm">Loading stats...</div>;

  const startCap = s.start_capital ?? 10000;
  const isReal = !!s.is_real_wallet;
  const startLabel = isReal ? `wallet $${startCap.toFixed(2)}` : `demo $${startCap.toLocaleString()}`;

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-2">
      <div className="bg-gray-900 border border-gray-800 rounded-lg px-3 py-2 min-w-[120px] relative">
        {isReal && <span className="absolute top-1 right-1 text-[8px] bg-purple-700 text-white px-1 rounded font-bold">LIVE</span>}
        <div className="text-[10px] text-gray-500 uppercase tracking-wider">Equity</div>
        <div className={`font-mono text-lg font-bold ${s.current_equity >= startCap ? "text-green-400" : "text-red-400"}`}>
          $<AnimatedNumber value={s.current_equity} format={(n) => n.toFixed(2)} />
        </div>
        <div className={`text-[10px] ${isReal ? "text-purple-300" : "text-gray-500"}`}>{startLabel}</div>
      </div>
      <KPI label="Total PnL" unit="USD" trend={s.total_pnl_usd >= 0 ? "good" : "bad"}
        value={<AnimatedNumber value={s.total_pnl_usd} format={(n) => sign(n) + n.toFixed(2)} />}
        subtitle={sign(s.total_pnl_pct) + s.total_pnl_pct.toFixed(2) + "%"} />
      <KPI label="Win Rate" unit="%"
        trend={s.win_rate >= 55 ? "good" : s.win_rate >= 45 ? "neutral" : "bad"}
        value={<AnimatedNumber value={s.win_rate} format={(n) => n.toFixed(1)} />}
        subtitle={`${s.total_trades} trades`} />
      <KPI label="Sharpe"
        trend={s.sharpe_ratio >= 1.5 ? "good" : s.sharpe_ratio >= 0.5 ? "neutral" : "bad"}
        value={<AnimatedNumber value={s.sharpe_ratio} format={(n) => n.toFixed(2)} />} subtitle="annualized" />
      <KPI label="Profit Factor"
        trend={s.profit_factor >= 1.5 ? "good" : s.profit_factor >= 1.0 ? "neutral" : "bad"}
        value={<AnimatedNumber value={s.profit_factor} format={(n) => n.toFixed(2)} />} subtitle="wins / losses" />
      <KPI label="Max DD" unit="%"
        trend={s.max_drawdown_pct < 2 ? "good" : s.max_drawdown_pct < 5 ? "neutral" : "bad"}
        value={<AnimatedNumber value={s.max_drawdown_pct} format={(n) => "-" + n.toFixed(2)} />} subtitle="peak-to-trough" />
      <KPI label="Avg Win / Loss" trend="neutral"
        value={<><AnimatedNumber value={s.avg_win} format={(n) => "+" + n.toFixed(2)} /> / <AnimatedNumber value={s.avg_loss} format={(n) => n.toFixed(2)} /></>}
        subtitle={`exp ${sign(s.expectancy) + s.expectancy.toFixed(3)}`} />
      <KPI label="Best / Worst" trend="neutral"
        value={<><AnimatedNumber value={s.best_trade} format={(n) => sign(n) + n.toFixed(2)} /> / <AnimatedNumber value={s.worst_trade} format={(n) => sign(n) + n.toFixed(2)} /></>}
        subtitle="USD" />
    </div>
  );
}
