"use client";
import { API_URL, api, ws } from "../lib/api";
import { useEffect, useState } from "react";

interface Rate { symbol: string; exchange: string; rate: number; next_funding_ts: number; ts: number; }
interface Opp { symbol: string; long_at: string; long_rate: number; short_at: string; short_rate: number; spread_pct: number; annualized_pct: number; }

export default function FundingRates() {
  const [rates, setRates] = useState<Rate[]>([]);
  const [opps, setOpps] = useState<Opp[]>([]);

  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(api("/api/funding"));
        if (r.ok) {
          const j = await r.json();
          setRates(j.rates || []);
          setOpps(j.opportunities || []);
        }
      } catch {}
    };
    load();
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
      <h2 className="text-white font-bold text-base mb-3">Funding Rate Arbitrage</h2>

      {opps.length > 0 && (
        <div className="mb-3">
          <div className="text-[10px] uppercase text-gray-500 mb-1">Live Opportunities</div>
          <div className="space-y-1">
            {opps.slice(0, 3).map((o, i) => (
              <div key={i} className="bg-green-950/30 border border-green-800/50 p-2 rounded text-xs">
                <div className="flex justify-between items-center mb-1">
                  <span className="font-mono text-white font-bold">{o.symbol}</span>
                  <span className="font-mono text-green-400">+{o.annualized_pct.toFixed(2)}% APR</span>
                </div>
                <div className="grid grid-cols-2 gap-1 text-[10px] font-mono">
                  <div className="text-green-400">LONG @ {o.long_at}: {o.long_rate.toFixed(4)}%</div>
                  <div className="text-red-400">SHORT @ {o.short_at}: {o.short_rate.toFixed(4)}%</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div>
        <div className="text-[10px] uppercase text-gray-500 mb-1">Current Rates (per 8h)</div>
        {rates.length === 0 ? (
          <p className="text-gray-600 text-xs">No funding data</p>
        ) : (
          <table className="w-full text-xs">
            <thead className="text-gray-500 text-[10px] uppercase">
              <tr>
                <th className="text-left py-1">Symbol</th>
                <th className="text-left">Exchange</th>
                <th className="text-right">Rate (%)</th>
                <th className="text-right">APR</th>
              </tr>
            </thead>
            <tbody>
              {rates.map((r, i) => {
                const apr = r.rate * 3 * 365;  // 3 fundings/day × 365
                return (
                  <tr key={i} className="border-t border-gray-800/50">
                    <td className="py-1 font-mono text-white">{r.symbol}</td>
                    <td className="text-gray-300">{r.exchange}</td>
                    <td className={`text-right font-mono ${r.rate >= 0 ? "text-green-400" : "text-red-400"}`}>
                      {r.rate >= 0 ? "+" : ""}{r.rate.toFixed(4)}
                    </td>
                    <td className={`text-right font-mono ${apr >= 0 ? "text-green-400" : "text-red-400"}`}>
                      {apr >= 0 ? "+" : ""}{apr.toFixed(1)}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
