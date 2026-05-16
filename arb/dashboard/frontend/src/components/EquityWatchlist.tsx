"use client";
import { API_URL, api, ws } from "../lib/api";
import { useEffect, useState } from "react";

interface Item {
  ticker: string;
  price: number;
  change: number;
  change_pct: number;
  time: string;
  is_pro: boolean;
}

interface Correlation {
  equity_avg_change_pct: number;
  btc_price_now: number;
  sentiment: "RISK-ON" | "RISK-OFF" | "NEUTRAL";
  signal: string;
}

export default function EquityWatchlist() {
  const [items, setItems] = useState<Item[]>([]);
  const [corr, setCorr] = useState<Correlation | null>(null);
  const [apiKeyLoaded, setApiKeyLoaded] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const [r1, r2] = await Promise.all([
          fetch(api("/api/financial/watchlist")),
          fetch(api("/api/financial/correlation")),
        ]);
        if (r1.ok) {
          const j = await r1.json();
          setItems(j.watchlist || []);
          setApiKeyLoaded(!!j.api_key_loaded);
        }
        if (r2.ok) setCorr(await r2.json());
      } catch {}
    };
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, []);

  const sentColor = (s?: string) =>
    s === "RISK-ON" ? "text-green-400 bg-green-900/30 border-green-700/50" :
    s === "RISK-OFF" ? "text-red-400 bg-red-900/30 border-red-700/50" :
    "text-gray-400 bg-gray-800 border-gray-700";

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-3 h-full">
      <div className="flex justify-between items-start mb-2">
        <div>
          <h2 className="text-white font-bold text-sm flex items-center gap-2">
            <span className="text-emerald-400">📈</span> Equities Watchlist
          </h2>
          <p className="text-[10px] text-gray-500">
            financialdatasets.ai · {apiKeyLoaded ? "PRO" : "FREE TIER"}
          </p>
        </div>
        {corr && (
          <div className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded border ${sentColor(corr.sentiment)}`}>
            {corr.sentiment}
          </div>
        )}
      </div>

      {corr && (
        <div className="bg-gray-950 rounded p-2 mb-2 border border-gray-800">
          <div className="text-[10px] text-gray-500 uppercase mb-1">Macro → Crypto signal</div>
          <div className="flex items-baseline justify-between">
            <span className={`font-mono text-base font-bold ${
              corr.equity_avg_change_pct >= 0 ? "text-green-400" : "text-red-400"
            }`}>
              {corr.equity_avg_change_pct >= 0 ? "+" : ""}{corr.equity_avg_change_pct.toFixed(2)}%
            </span>
            <span className="text-[10px] text-gray-400">Avg equity Δ</span>
          </div>
          <div className="text-[10px] text-amber-300 mt-1">{corr.signal}</div>
        </div>
      )}

      <div className="space-y-1">
        {items.length === 0 && (
          <div className="text-gray-600 text-xs p-2 text-center">Loading equities…</div>
        )}
        {items.map((it) => {
          const up = (it.change_pct ?? 0) >= 0;
          return (
            <div key={it.ticker} className="flex items-center justify-between bg-gray-950/60 px-2 py-1.5 rounded text-xs border border-gray-800">
              <div className="flex items-center gap-2">
                <span className="font-bold font-mono text-white w-12">{it.ticker}</span>
                {it.is_pro && <span className="text-[8px] bg-purple-700 text-white px-1 rounded">PRO</span>}
              </div>
              <div className="flex items-center gap-3">
                <span className="font-mono text-white">${(it.price ?? 0).toFixed(2)}</span>
                <span className={`font-mono text-xs ${up ? "text-green-400" : "text-red-400"} min-w-[60px] text-right`}>
                  {up ? "▲" : "▼"} {Math.abs(it.change_pct ?? 0).toFixed(2)}%
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {!apiKeyLoaded && (
        <div className="mt-2 text-[9px] text-gray-600 bg-gray-950/40 p-1.5 rounded">
          Add <code className="text-amber-400">FINANCIAL_DATASETS_API_KEY</code> to .env for 17,000+ tickers + earnings + filings
        </div>
      )}
    </div>
  );
}
