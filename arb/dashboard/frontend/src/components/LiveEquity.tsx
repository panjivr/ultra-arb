"use client";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useLiveReal } from "../lib/useLiveReal";
import AnimatedNumber from "./AnimatedNumber";

interface Live {
  realized_equity: number; unrealized_usd: number; live_equity: number;
  start_capital: number; open_marked: number; is_real_wallet?: boolean;
}

const fmt2 = (n: number) => n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export default function LiveEquity() {
  const [d, setD] = useState<Live | null>(null);
  const { live, realMode } = useLiveReal(3000);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const j = await fetch(api("/api/equity/live")).then(r => r.json());
        if (alive) setD(j);
      } catch { /* ignore */ }
    };
    load();
    const id = setInterval(load, 1500);
    return () => { alive = false; clearInterval(id); };
  }, []);

  // ── REAL mode: show the actual Polymarket account, never the paper sim ──
  if (realMode) {
    const bal = live?.wallet_balance;
    const pnl = live?.realized_pnl ?? 0;
    const up = pnl >= 0;
    return (
      <div className="bg-gray-950 border-y border-gray-800 px-4 py-2 flex items-center justify-between font-mono flex-wrap gap-y-1">
        <div className="flex items-baseline gap-3">
          <span className="text-[10px] uppercase tracking-widest text-emerald-500">Real Balance</span>
          {bal == null ? (
            <span className="text-lg text-gray-500">menunggu saldo Polymarket…</span>
          ) : (
            <span className="text-2xl font-bold text-white">
              $<AnimatedNumber value={bal} duration={1000} format={fmt2} />
            </span>
          )}
          <span className={`text-sm font-bold ${up ? "text-green-400" : "text-red-400"}`}>
            realized {up ? "+" : ""}<AnimatedNumber value={pnl} duration={1000} format={(n) => "$" + fmt2(Math.abs(n))} />
          </span>
        </div>
        <div className="flex items-center gap-4 text-[11px]">
          <span className="text-gray-500">
            orders <span className="text-gray-300">{live?.orders_count ?? 0}</span> ·
            spent <span className="text-gray-300">${(live?.total_spend ?? 0).toFixed(2)}</span> ·
            open <span className="text-gray-300">{live?.open_count ?? 0}</span>
          </span>
          <span className="text-emerald-400 text-[10px]">● POLYMARKET · UANG ASLI</span>
        </div>
      </div>
    );
  }

  // ── DEMO/paper mode: the simulated equity curve (unchanged) ──
  const start = d?.start_capital ?? 10000;
  const eq = d?.live_equity ?? start;
  const pnl = eq - start;
  const pct = start ? (pnl / start) * 100 : 0;
  const up = pnl >= 0;
  const unreal = d?.unrealized_usd ?? 0;

  return (
    <div className="bg-gray-950 border-y border-gray-800 px-4 py-2 flex items-center justify-between font-mono">
      <div className="flex items-baseline gap-3">
        <span className="text-[10px] uppercase tracking-widest text-gray-500">Live Equity</span>
        <span className="text-[9px] uppercase tracking-wider text-amber-500/80 bg-amber-950/40 px-1.5 py-0.5 rounded">demo</span>
        <span className={`text-2xl font-bold ${up ? "text-green-400" : "text-red-400"}`}>
          $<AnimatedNumber value={eq} duration={1200} format={fmt2} />
        </span>
        <span className={`text-sm font-bold ${up ? "text-green-400" : "text-red-400"}`}>
          {up ? "▲" : "▼"} <AnimatedNumber value={pnl} duration={1200} format={(n) => (n >= 0 ? "+" : "") + n.toFixed(2)} />
          <span className="text-gray-500 text-xs ml-1">(<AnimatedNumber value={pct} format={(n) => (n >= 0 ? "+" : "") + n.toFixed(2)} />%)</span>
        </span>
      </div>
      <div className="flex items-center gap-4 text-[11px]">
        <span className="text-gray-500">
          unrealized <span className={unreal >= 0 ? "text-green-400" : "text-red-400"}>
            <AnimatedNumber value={unreal} format={(n) => (n >= 0 ? "+$" : "-$") + Math.abs(n).toFixed(2)} />
          </span>
          {d ? <span className="text-gray-600"> · {d.open_marked} open marked</span> : null}
        </span>
        <span className="text-green-400 text-[10px]">● LIVE MARK-TO-MARKET</span>
      </div>
    </div>
  );
}
