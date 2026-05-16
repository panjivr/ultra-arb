"use client";
import { API_URL, api, ws } from "../lib/api";
import { useEffect, useState } from "react";

interface Coin {
  name: string; symbol: string;
  rank: number | null;
  score: number;
  price_btc: number;
}

export default function TrendingCoins() {
  const [coins, setCoins] = useState<Coin[]>([]);

  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(api("/api/bloomberg/trending"));
        if (r.ok) setCoins((await r.json()).coins || []);
      } catch {}
    };
    load();
    const id = setInterval(load, 300_000); // 5min
    return () => clearInterval(id);
  }, []);

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-3 h-full">
      <h2 className="text-white font-bold text-sm flex items-center gap-2 mb-1">
        <span className="text-amber-400">🔥</span> Trending Now
      </h2>
      <p className="text-[10px] text-gray-500 mb-3">most searched coins (last 24h)</p>
      <div className="space-y-1">
        {coins.length === 0 && (
          <div className="text-gray-600 text-xs p-2 text-center">Loading trending…</div>
        )}
        {coins.slice(0, 10).map((c, i) => (
          <div key={i} className="flex items-center justify-between text-xs py-1 px-1.5 hover:bg-gray-800/50 rounded">
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-[10px] text-gray-500 font-mono w-4">#{i+1}</span>
              <span className="font-bold text-white truncate">{c.name}</span>
              <span className="text-[10px] text-gray-500 font-mono">{c.symbol}</span>
            </div>
            <div className="text-right">
              {c.rank && <span className="text-[10px] text-gray-500">rank {c.rank}</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
