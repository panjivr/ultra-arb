"use client";
import { useEffect, useState } from "react";
import { api } from "../lib/api";

interface CopyTrade {
  ts: number; asset?: string; side?: string; leader_rank?: number;
  leader_name?: string; entry_price?: number; question?: string;
}

export default function AlertTicker() {
  const [items, setItems] = useState<string[]>([]);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const d = await fetch(api("/api/edges/copy-trades?limit=20")).then(r => r.json());
        if (!alive) return;
        const trades: CopyTrade[] = d.items || [];
        const lines = trades.slice(0, 15).map(t =>
          `⚡ COPY #${t.leader_rank ?? "?"} ${t.leader_name || ""} · ${t.asset} ${t.side} @ ${t.entry_price} · ${(t.question || "").slice(0, 40)}`
        );
        setItems(lines);
      } catch { /* ignore */ }
    };
    load();
    const id = setInterval(load, 10000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const text = items.length
    ? items.join("      •      ")
    : "SCANNING TOP 1-10 POLYMARKET CHAMPIONS · waiting for a leader to place a crypto bet · copy-trade armed";

  return (
    <div className="bg-black border-y border-amber-900/40 overflow-hidden">
      <div className="flex items-center">
        <span className="bg-amber-500 text-black text-[10px] font-bold px-2 py-1 shrink-0">● LIVE</span>
        <div className="relative flex-1 overflow-hidden whitespace-nowrap">
          <div className="inline-block py-1 text-[11px] font-mono text-amber-300 animate-[marquee_40s_linear_infinite]">
            {text}      •      {text}
          </div>
        </div>
      </div>
      <style>{`@keyframes marquee { 0%{transform:translateX(0)} 100%{transform:translateX(-50%)} }`}</style>
    </div>
  );
}
