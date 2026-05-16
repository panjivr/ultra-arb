"use client";
import { API_URL, api, ws } from "../lib/api";
import { useEffect, useState } from "react";

interface Data {
  start_capital: number; current_equity: number;
  is_real_wallet: boolean; wallet_addr: string | null;
  spot_perp_pnl: number; polymarket_pnl: number;
  polymarket_open_bets: number; polymarket_open_stake_usd: number;
  polymarket_wins: number; polymarket_losses: number;
  total_pnl: number; total_return_pct: number;
  elapsed_hours: number; elapsed_days: number; trade_count: number;
  hourly_return_capped_pct: number;
  daily_return_pct: number;
  monthly_return_pct: number;
  annual_return_pct: number;
  projection_capped: {
    next_24h: number; next_7d: number; next_30d: number;
    next_90d: number; next_1y: number;
  };
  note: string;
}

export default function CompoundingTracker() {
  const [d, setD] = useState<Data | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(api("/api/compounding"));
        if (r.ok) setD(await r.json());
      } catch {}
    };
    load();
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, []);

  if (!d) return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-4 h-full flex items-center justify-center">
      <span className="text-gray-500 text-xs">Loading compounding projection…</span>
    </div>
  );

  const fmt = (n: number) => "$" + n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-3 h-full overflow-hidden">
      <div className="flex justify-between items-start mb-3">
        <div>
          <h2 className="text-white font-bold text-sm flex items-center gap-2">
            <span className="text-emerald-400">📈</span> Compounding Projection
            {d.is_real_wallet && (
              <span className="text-[9px] bg-purple-700 text-white px-1.5 py-0.5 rounded uppercase">LIVE WALLET</span>
            )}
          </h2>
          <p className="text-[10px] text-gray-500">
            starting {fmt(d.start_capital)} · {d.elapsed_days.toFixed(2)}d · {d.trade_count.toLocaleString()} trades
          </p>
        </div>
        <div className="text-right">
          <div className="text-[10px] text-gray-500 uppercase">Equity Now</div>
          <div className={`font-mono text-lg font-bold ${d.total_pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
            {fmt(d.current_equity)}
          </div>
          <div className={`text-[10px] ${d.total_pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
            {d.total_return_pct >= 0 ? "+" : ""}{d.total_return_pct.toFixed(2)}%
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-1.5 mb-3">
        <div className="bg-gray-950 rounded p-2 border border-gray-800">
          <div className="text-[9px] text-gray-500 uppercase">Spot/Perp PnL</div>
          <div className={`font-mono text-sm font-bold ${d.spot_perp_pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
            {d.spot_perp_pnl >= 0 ? "+" : ""}${d.spot_perp_pnl.toFixed(2)}
          </div>
        </div>
        <div className="bg-gray-950 rounded p-2 border border-gray-800">
          <div className="text-[9px] text-gray-500 uppercase">Polymarket PnL</div>
          <div className={`font-mono text-sm font-bold ${d.polymarket_pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
            {d.polymarket_pnl >= 0 ? "+" : ""}${d.polymarket_pnl.toFixed(2)}
          </div>
          <div className="text-[9px] text-gray-500">
            {d.polymarket_open_bets} open · ${d.polymarket_open_stake_usd.toFixed(0)} staked
          </div>
        </div>
      </div>

      <div className="bg-gray-950/80 rounded p-2 border border-emerald-900/50 mb-3">
        <div className="text-[10px] text-gray-500 uppercase mb-1">Live Compounding Rate (capped at 50% APR)</div>
        <div className="grid grid-cols-3 gap-2">
          <div>
            <div className="text-[9px] text-gray-600">Hourly</div>
            <div className="font-mono text-xs text-emerald-300 font-bold">+{d.hourly_return_capped_pct.toFixed(4)}%</div>
          </div>
          <div>
            <div className="text-[9px] text-gray-600">Daily</div>
            <div className="font-mono text-sm text-emerald-300 font-bold">+{d.daily_return_pct.toFixed(3)}%</div>
          </div>
          <div>
            <div className="text-[9px] text-gray-600">Annual</div>
            <div className="font-mono text-base text-emerald-400 font-bold">+{d.annual_return_pct.toFixed(2)}%</div>
          </div>
        </div>
      </div>

      <div className="space-y-1.5">
        <div className="text-[10px] text-gray-500 uppercase">If bot keeps compounding…</div>
        {[
          ["24 hours", d.projection_capped.next_24h, "blue"],
          ["7 days", d.projection_capped.next_7d, "cyan"],
          ["30 days", d.projection_capped.next_30d, "emerald"],
          ["90 days", d.projection_capped.next_90d, "amber"],
          ["1 year", d.projection_capped.next_1y, "purple"],
        ].map(([label, val, color]: any) => (
          <div key={label} className="flex justify-between items-center bg-gray-950/40 rounded px-2 py-1 border border-gray-800">
            <span className="text-[11px] text-gray-400">{label}</span>
            <span className={`font-mono text-sm font-bold text-${color}-300`}>{fmt(val)}</span>
          </div>
        ))}
      </div>

      <div className="mt-2 text-[9px] text-gray-600">{d.note}</div>
    </div>
  );
}
