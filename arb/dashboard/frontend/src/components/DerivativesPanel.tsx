"use client";
import { API_URL, api, ws } from "../lib/api";
import { useEffect, useState } from "react";

interface Deriv {
  symbol: string;
  funding_rate: number;
  funding_rate_pct: number;
  open_interest: number;
  apr: number;
  ts: number;
}

export default function DerivativesPanel() {
  const [items, setItems] = useState<Deriv[]>([]);

  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(api("/api/bloomberg/derivatives"));
        if (r.ok) setItems((await r.json()).derivatives || []);
      } catch {}
    };
    load();
    const id = setInterval(load, 60_000);
    return () => clearInterval(id);
  }, []);

  const fmtOI = (oi: number) => {
    if (oi >= 1e9) return `${(oi/1e9).toFixed(2)}B`;
    if (oi >= 1e6) return `${(oi/1e6).toFixed(2)}M`;
    if (oi >= 1e3) return `${(oi/1e3).toFixed(2)}K`;
    return oi.toFixed(0);
  };

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-3 h-full">
      <h2 className="text-white font-bold text-sm flex items-center gap-2 mb-1">
        <span className="text-pink-400">📊</span> Derivatives Sentiment
      </h2>
      <p className="text-[10px] text-gray-500 mb-3">funding · open interest · annualized rate</p>
      <div className="space-y-2">
        {items.length === 0 && (
          <div className="text-gray-600 text-xs p-2 text-center">Loading derivatives data…</div>
        )}
        {items.map((d) => {
          const isLong = d.funding_rate > 0;
          return (
            <div key={d.symbol} className="bg-gray-950 rounded p-2 border border-gray-800">
              <div className="flex justify-between items-center mb-1">
                <span className="font-mono text-white font-bold text-sm">{d.symbol}</span>
                <span className={`text-[10px] uppercase font-bold ${isLong ? "text-green-400" : "text-red-400"}`}>
                  {isLong ? "LONGS PAY" : "SHORTS PAY"}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2 text-[11px]">
                <div>
                  <div className="text-[9px] text-gray-500 uppercase">Funding</div>
                  <div className={`font-mono font-bold ${isLong ? "text-green-400" : "text-red-400"}`}>
                    {d.funding_rate_pct >= 0 ? "+" : ""}{d.funding_rate_pct.toFixed(4)}%
                  </div>
                </div>
                <div>
                  <div className="text-[9px] text-gray-500 uppercase">APR</div>
                  <div className={`font-mono font-bold ${d.apr >= 0 ? "text-green-400" : "text-red-400"}`}>
                    {d.apr >= 0 ? "+" : ""}{d.apr.toFixed(2)}%
                  </div>
                </div>
                <div>
                  <div className="text-[9px] text-gray-500 uppercase">OI</div>
                  <div className="font-mono font-bold text-blue-300">{fmtOI(d.open_interest)}</div>
                </div>
              </div>
              <div className="text-[9px] text-gray-600 mt-1">
                {isLong ? "Bullish bias — longs paying funding" : "Bearish bias — shorts paying funding"}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
