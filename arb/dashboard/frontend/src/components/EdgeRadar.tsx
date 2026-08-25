"use client";
import { API_URL, api, ws } from "../lib/api";
import { useEffect, useState } from "react";

interface AllEdges {
  yesno_arb: any[];
  smart_money: any[];
  time_decay: any[];
  related: any[];
  news_signal: any[];
  basis_carry: any[];
  counts: Record<string, number>;
}

const TABS = [
  { key: "all", label: "All", emoji: "🎯", color: "purple" },
  { key: "yesno_arb", label: "Math Arb", emoji: "💎", color: "green" },
  { key: "smart_money", label: "Smart Money", emoji: "🐋", color: "blue" },
  { key: "time_decay", label: "Time Decay", emoji: "⏰", color: "amber" },
  { key: "related", label: "Related", emoji: "🔗", color: "pink" },
  { key: "news_signal", label: "News", emoji: "📰", color: "orange" },
  { key: "basis_carry", label: "Carry", emoji: "💰", color: "cyan" },
] as const;

export default function EdgeRadar() {
  const [data, setData] = useState<AllEdges | null>(null);
  const [tab, setTab] = useState<string>("all");

  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(api("/api/edges/all?limit=15"));
        if (r.ok) setData(await r.json());
      } catch {}
    };
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  if (!data) return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-4 h-full flex items-center justify-center">
      <span className="text-gray-500 text-xs">Scanning for edges…</span>
    </div>
  );

  const fmt = (n: number, d = 2) => Number(n).toFixed(d);

  // Render specific edge cards based on kind
  const renderEdge = (e: any, kind: string, i: number) => {
    switch (kind) {
      case "yesno_arb":
        return (
          <a key={i} href={e.url} target="_blank" rel="noopener noreferrer"
            className="block bg-green-950/30 border border-green-800/40 hover:border-green-600 rounded p-2 transition-all">
            <div className="flex justify-between items-start gap-2">
              <p className="text-xs text-white line-clamp-1 flex-1">{e.question}</p>
              <span className="text-[10px] bg-green-700 text-white px-1.5 py-0.5 rounded font-bold">
                {fmt(e.guaranteed_roi_pct)}% GUARANTEED
              </span>
            </div>
            <div className="flex items-center gap-2 mt-1 text-[10px]">
              <span className="text-green-300">YES {fmt(e.yes_price * 100, 1)}¢</span>
              <span className="text-red-300">NO {fmt(e.no_price * 100, 1)}¢</span>
              <span className="text-gray-500">sum {fmt(e.sum)}</span>
              <span className="text-emerald-400 font-bold">+{fmt(e.profit_bps, 0)} bps</span>
            </div>
          </a>
        );

      case "smart_money":
        return (
          <div key={i} className="bg-blue-950/30 border border-blue-800/40 rounded p-2">
            <div className="flex justify-between items-start gap-2">
              <p className="text-xs text-white line-clamp-1 flex-1">{e.question || "(no title)"}</p>
              <span className={`text-[9px] px-1.5 rounded font-bold ${
                e.side === "BUY" ? "bg-green-700" : "bg-red-700"
              } text-white`}>{e.side} {e.outcome || ""}</span>
            </div>
            <div className="flex items-center gap-2 mt-1 text-[10px]">
              <span className="text-blue-300 font-mono">
                🐋 {(e.wallet_name || e.wallet)?.slice(0, 10) || "wallet"}
              </span>
              <span className="text-purple-300">${fmt(e.size_usd, 0)}</span>
              <span className="text-gray-500">@{fmt(e.price * 100, 1)}¢</span>
              <span className="text-amber-300">Day +${fmt(e.wallet_day_pnl, 0)}</span>
            </div>
          </div>
        );

      case "time_decay":
        return (
          <a key={i} href={e.url} target="_blank" rel="noopener noreferrer"
            className="block bg-amber-950/30 border border-amber-800/40 hover:border-amber-600 rounded p-2">
            <div className="flex justify-between items-start gap-2">
              <p className="text-xs text-white line-clamp-1 flex-1">{e.question}</p>
              <span className="text-[9px] bg-amber-700 text-white px-1.5 rounded font-bold">
                {fmt(e.minutes_to_resolve, 0)}m left
              </span>
            </div>
            <div className="flex items-center gap-2 mt-1 text-[10px]">
              <span className={`px-1 rounded ${e.side === "Yes" ? "bg-green-900 text-green-200" : "bg-red-900 text-red-200"}`}>
                {e.side}
              </span>
              <span className="text-amber-300">@{fmt(e.entry_price * 100, 1)}¢</span>
              <span className="text-emerald-400 font-bold">EV +{fmt(e.ev_per_dollar * 100, 1)}%</span>
              <span className="text-gray-500">our {fmt(e.our_prob * 100, 0)}% vs market {fmt(e.implied_prob * 100, 0)}%</span>
            </div>
          </a>
        );

      case "related":
        return (
          <div key={i} className="bg-pink-950/30 border border-pink-800/40 rounded p-2">
            <div className="text-[10px] text-pink-300 uppercase font-bold mb-1">
              Probability Ordering Violation · +{fmt(e.edge_bps, 0)} bps edge
            </div>
            <div className="text-[10px] text-white">
              CHEAP: <span className="text-green-400">{e.cheap_market?.slice(0, 50)}…</span> at {fmt(e.cheap_yes_price * 100, 1)}¢
            </div>
            <div className="text-[10px] text-white">
              EXPENSIVE: <span className="text-red-400">{e.expensive_market?.slice(0, 50)}…</span> at {fmt(e.expensive_yes_price * 100, 1)}¢
            </div>
          </div>
        );

      case "news_signal":
        return (
          <a key={i} href={e.url} target="_blank" rel="noopener noreferrer"
            className="block bg-orange-950/30 border border-orange-800/40 hover:border-orange-600 rounded p-2">
            <div className="flex justify-between items-start gap-2">
              <p className="text-xs text-white line-clamp-2 flex-1">{e.title}</p>
              <span className={`text-[9px] px-1.5 rounded font-bold whitespace-nowrap ${
                e.direction === "BULLISH" ? "bg-green-700" : "bg-red-700"
              } text-white`}>{e.direction}</span>
            </div>
            <div className="flex items-center gap-2 mt-1 text-[10px]">
              <span className="text-orange-300">{e.source}</span>
              <span className="text-gray-500">{fmt(e.age_minutes, 1)}m old</span>
              {e.currencies?.slice(0, 3).map((c: string) => (
                <span key={c} className="bg-gray-800 text-amber-300 px-1 rounded">{c}</span>
              ))}
              <span className="text-cyan-300">score {fmt(e.sentiment, 2)}</span>
            </div>
          </a>
        );

      case "basis_carry":
        return (
          <div key={i} className="bg-cyan-950/30 border border-cyan-800/40 rounded p-2">
            <div className="flex justify-between items-center">
              <span className="font-mono font-bold text-white text-sm">{e.symbol}</span>
              <span className="text-[10px] bg-cyan-700 text-white px-1.5 rounded font-bold">
                {fmt(e.net_apr_after_costs, 1)}% net APR
              </span>
            </div>
            <div className="text-[10px] text-cyan-200 mt-0.5 line-clamp-1">{e.description}</div>
            <div className="flex items-center gap-2 mt-1 text-[9px]">
              <span className={`px-1 rounded ${e.strategy?.startsWith("SHORT") ? "bg-red-900 text-red-200" : "bg-green-900 text-green-200"}`}>
                {e.strategy ?? "—"}
              </span>
              <span className="text-gray-400">funding {fmt(e.funding_rate_pct, 4)}%</span>
              <span className="text-gray-500">basis {fmt(e.basis_bps, 1)} bps</span>
            </div>
          </div>
        );

      default:
        return null;
    }
  };

  // Aggregate for "all" tab — sorted by recency
  const allEdges: { kind: string; data: any; ts: number }[] = [];
  if (tab === "all") {
    for (const k of Object.keys(data) as (keyof AllEdges)[]) {
      if (k === "counts" as any) continue;
      const arr = (data as any)[k];
      if (Array.isArray(arr)) {
        arr.forEach((d: any) => allEdges.push({ kind: k, data: d, ts: d.ts || 0 }));
      }
    }
    allEdges.sort((a, b) => b.ts - a.ts);
  }

  const totalCount = Object.values(data.counts || {}).reduce((s, n) => s + n, 0);

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 h-full flex flex-col">
      <div className="border-b border-gray-800 px-3 py-2">
        <div className="flex justify-between items-start mb-2">
          <div>
            <h2 className="text-white font-bold text-sm flex items-center gap-2">
              <span className="text-purple-400">🎯</span> Edge Radar
              <span className="text-[9px] bg-purple-700 text-white px-1.5 py-0.5 rounded uppercase">
                {totalCount} edges live
              </span>
            </h2>
            <p className="text-[10px] text-gray-500">
              6 detectors · math arb · smart money · time decay · related · news · carry
            </p>
          </div>
        </div>
        <div className="flex gap-1 flex-wrap">
          {TABS.map(t => (
            <button key={t.key} onClick={() => setTab(t.key)}
              className={`px-2 py-0.5 text-[10px] rounded uppercase font-bold transition ${
                tab === t.key
                  ? `bg-${t.color}-700 text-white`
                  : "bg-gray-800 text-gray-400 hover:text-white"
              }`}>
              {t.emoji} {t.label}
              {t.key !== "all" && (
                <span className="ml-1 opacity-70">{data.counts?.[t.key] || 0}</span>
              )}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-1.5 max-h-[480px]">
        {tab === "all" && allEdges.length === 0 && (
          <div className="text-gray-600 text-xs p-6 text-center">
            Scanners running… edges appear as they're detected (~30-120s per scanner)
          </div>
        )}
        {tab === "all" && allEdges.slice(0, 20).map((e, i) => renderEdge(e.data, e.kind, i))}

        {tab !== "all" && (data as any)[tab]?.length === 0 && (
          <div className="text-gray-600 text-xs p-6 text-center">No {tab.replace("_", " ")} edges yet</div>
        )}
        {tab !== "all" && (data as any)[tab]?.map((e: any, i: number) => renderEdge(e, tab, i))}
      </div>
    </div>
  );
}
