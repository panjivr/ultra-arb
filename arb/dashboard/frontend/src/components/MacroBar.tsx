"use client";
import { API_URL, api, ws } from "../lib/api";
import { useEffect, useState } from "react";

interface MacroIndicator {
  symbol: string; label: string;
  price: number; change: number; change_pct: number;
  currency: string;
}

interface FearGreed {
  value: number; classification: string; timestamp: number;
}

interface Global {
  total_market_cap_usd: number;
  total_volume_24h_usd: number;
  btc_dominance: number;
  eth_dominance: number;
  mcap_change_24h_pct: number;
}

export default function MacroBar() {
  const [macro, setMacro] = useState<MacroIndicator[]>([]);
  const [fg, setFg] = useState<FearGreed | null>(null);
  const [glob, setGlob] = useState<Global | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const [r1, r2, r3] = await Promise.all([
          fetch(api("/api/bloomberg/macro")),
          fetch(api("/api/bloomberg/fear-greed")),
          fetch(api("/api/bloomberg/global")),
        ]);
        // These upstreams (CoinGecko / fear-greed) can return a degraded
        // {"error": ...} body with a 200. Only accept a payload that actually
        // has the numeric fields we render, else keep the empty/loading state.
        if (r1.ok) { const j = await r1.json(); setMacro(Array.isArray(j?.indicators) ? j.indicators : []); }
        if (r2.ok) { const j = await r2.json(); setFg(j && typeof j.value === "number" ? j : null); }
        if (r3.ok) { const j = await r3.json(); setGlob(j && typeof j.total_market_cap_usd === "number" ? j : null); }
      } catch {}
    };
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, []);

  const fgColor = (v?: number) => {
    if (v == null) return "bg-gray-600";
    if (v < 25) return "bg-red-600";
    if (v < 45) return "bg-orange-500";
    if (v < 55) return "bg-yellow-500";
    if (v < 75) return "bg-lime-500";
    return "bg-green-500";
  };

  const fmtNum = (n: number, prec = 2) =>
    n.toLocaleString(undefined, { minimumFractionDigits: prec, maximumFractionDigits: prec });
  const fmtCompact = (n: number) => {
    if (n >= 1e12) return `$${(n/1e12).toFixed(2)}T`;
    if (n >= 1e9) return `$${(n/1e9).toFixed(2)}B`;
    if (n >= 1e6) return `$${(n/1e6).toFixed(2)}M`;
    return `$${fmtNum(n, 0)}`;
  };

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
      <div className="bg-black/60 px-3 py-1.5 flex items-center justify-between">
        <span className="text-[10px] text-gray-500 uppercase tracking-widest">Macro Intelligence</span>
        <span className="text-[10px] text-amber-400 animate-pulse">● live</span>
      </div>
      <div className="overflow-x-auto whitespace-nowrap py-2 px-2 flex gap-2 items-stretch">
        {fg && (
          <div className="flex items-center gap-2 bg-gray-800 rounded px-2.5 py-1.5 flex-shrink-0 border-l-2 border-orange-500">
            <div>
              <div className="text-[8px] text-gray-500 uppercase">Fear & Greed</div>
              <div className="flex items-baseline gap-1.5">
                <span className={`font-mono font-bold text-base ${
                  fg.value < 25 ? "text-red-400" :
                  fg.value < 45 ? "text-orange-400" :
                  fg.value < 55 ? "text-yellow-400" :
                  fg.value < 75 ? "text-lime-400" : "text-green-400"
                }`}>{fg.value}</span>
                <span className="text-[10px] text-gray-400 uppercase">{fg.classification}</span>
              </div>
            </div>
            <div className="w-16 h-1.5 bg-gray-700 rounded relative">
              <div className={`h-full rounded ${fgColor(fg.value)}`} style={{ width: `${fg.value}%` }} />
            </div>
          </div>
        )}

        {glob && (
          <>
            <div className="flex flex-col bg-gray-800 rounded px-2.5 py-1.5 flex-shrink-0">
              <div className="text-[8px] text-gray-500 uppercase">Total Mcap</div>
              <div className="font-mono font-bold text-sm text-white">{fmtCompact(glob.total_market_cap_usd)}</div>
              <div className={`text-[9px] font-mono ${glob.mcap_change_24h_pct >= 0 ? "text-green-400" : "text-red-400"}`}>
                {glob.mcap_change_24h_pct >= 0 ? "+" : ""}{glob.mcap_change_24h_pct.toFixed(2)}%
              </div>
            </div>
            <div className="flex flex-col bg-gray-800 rounded px-2.5 py-1.5 flex-shrink-0">
              <div className="text-[8px] text-gray-500 uppercase">24h Volume</div>
              <div className="font-mono font-bold text-sm text-white">{fmtCompact(glob.total_volume_24h_usd)}</div>
            </div>
            <div className="flex flex-col bg-gray-800 rounded px-2.5 py-1.5 flex-shrink-0">
              <div className="text-[8px] text-gray-500 uppercase">BTC Dom</div>
              <div className="font-mono font-bold text-sm text-orange-300">{glob.btc_dominance.toFixed(2)}%</div>
              <div className="text-[9px] text-gray-500">ETH {glob.eth_dominance.toFixed(2)}%</div>
            </div>
          </>
        )}

        {macro.map((m) => (
          <div key={m.symbol} className="flex flex-col bg-gray-800 rounded px-2.5 py-1.5 flex-shrink-0 min-w-[110px]">
            <div className="text-[8px] text-gray-500 uppercase truncate" title={m.label}>{m.label.replace(/\([^)]*\)/g, "").trim()}</div>
            <div className="font-mono font-bold text-sm text-white">{fmtNum(m.price, m.price > 100 ? 2 : 4)}</div>
            <div className={`text-[9px] font-mono ${m.change_pct >= 0 ? "text-green-400" : "text-red-400"}`}>
              {m.change_pct >= 0 ? "▲" : "▼"} {m.change_pct.toFixed(2)}%
            </div>
          </div>
        ))}

        {macro.length === 0 && !glob && !fg && (
          <span className="text-gray-600 text-xs px-2">Loading macro indicators…</span>
        )}
      </div>
    </div>
  );
}
