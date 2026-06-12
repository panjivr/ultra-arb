"use client";
import { API_URL, api, ws } from "../lib/api";
import { useEffect, useState } from "react";

interface Market {
  id: string; question: string; slug: string;
  end_date: string; image?: string;
  outcomes: string[];
  yes_price: number; no_price: number;
  implied_prob_yes: number; implied_prob_no: number;
  liquidity: number; volume: number;
  condition_id: string; url: string;
}
interface Bet {
  id: string; ts: number;
  question: string; side: string;
  stake_usd: number; entry_price: number;
  implied_prob: number; our_prob: number;
  edge_bps: number; expected_value_usd: number;
  hours_to_resolve: number; status: string;
  payout_usd?: number;
  btc_at_resolve?: number; in_range?: boolean;
  end_date: string;
}
interface PnL {
  total_bets: number; open: number; resolved: number;
  wins: number; losses: number; win_rate: number;
  total_staked_usd: number; net_pnl_usd: number; roi_pct: number;
}

export default function PolymarketPanel() {
  const [markets, setMarkets] = useState<Market[]>([]);
  const [bets, setBets] = useState<Bet[]>([]);
  const [pnl, setPnl] = useState<PnL | null>(null);
  const [tab, setTab] = useState<"markets" | "bets">("bets");

  useEffect(() => {
    const load = async () => {
      try {
        const [r1, r2, r3] = await Promise.all([
          fetch(api("/api/polymarket/markets")),
          fetch(api("/api/polymarket/bets?limit=50")),
          fetch(api("/api/polymarket/pnl")),
        ]);
        if (r1.ok) setMarkets((await r1.json()).markets || []);
        if (r2.ok) setBets((await r2.json()).bets || []);
        if (r3.ok) setPnl(await r3.json());
      } catch {}
    };
    load();
    const id = setInterval(load, 15_000);
    return () => clearInterval(id);
  }, []);

  const statusColor = (s: string) =>
    s === "won" ? "bg-green-700 text-white" :
    s === "lost" ? "bg-red-700 text-white" :
    "bg-amber-700 text-white";

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 h-full flex flex-col">
      <div className="border-b border-gray-800 px-3 py-2 flex justify-between items-center">
        <div>
          <h2 className="text-white font-bold text-sm flex items-center gap-2">
            <span className="text-purple-400">🎯</span> Polymarket Bets
            <span className="text-[9px] bg-purple-700 text-white px-1.5 py-0.5 rounded uppercase">PAPER</span>
          </h2>
          <p className="text-[10px] text-gray-500">prediction market arbitrage · auto-bet on edge ≥ 5%</p>
        </div>
        <div className="flex gap-1">
          <button onClick={() => setTab("bets")}
            className={`px-2 py-0.5 text-[10px] rounded uppercase ${
              tab === "bets" ? "bg-purple-700 text-white" : "bg-gray-800 text-gray-400"
            }`}>Bets</button>
          <button onClick={() => setTab("markets")}
            className={`px-2 py-0.5 text-[10px] rounded uppercase ${
              tab === "markets" ? "bg-purple-700 text-white" : "bg-gray-800 text-gray-400"
            }`}>Markets</button>
        </div>
      </div>

      {pnl && (
        <div className="grid grid-cols-4 gap-1.5 px-3 py-2 border-b border-gray-800 bg-gray-950/60 text-[10px]">
          <div>
            <div className="text-gray-500 uppercase">Total Bets</div>
            <div className="font-mono text-sm font-bold text-white">{pnl.total_bets}</div>
          </div>
          <div>
            <div className="text-gray-500 uppercase">Open</div>
            <div className="font-mono text-sm font-bold text-amber-400">{pnl.open}</div>
          </div>
          <div>
            <div className="text-gray-500 uppercase">Net PnL</div>
            <div className={`font-mono text-sm font-bold ${pnl.net_pnl_usd >= 0 ? "text-green-400" : "text-red-400"}`}>
              ${pnl.net_pnl_usd.toFixed(2)}
            </div>
          </div>
          <div>
            <div className="text-gray-500 uppercase">ROI</div>
            <div className={`font-mono text-sm font-bold ${pnl.roi_pct >= 0 ? "text-green-400" : "text-red-400"}`}>
              {pnl.roi_pct >= 0 ? "+" : ""}{pnl.roi_pct.toFixed(1)}%
            </div>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto max-h-[420px] divide-y divide-gray-800">
        {tab === "bets" && (
          <>
            {bets.length === 0 && (
              <div className="text-gray-600 text-xs p-4 text-center">No bets yet — engine scans every 60s</div>
            )}
            {bets.slice(0, 25).map((b) => (
              <div key={b.id} className="p-2 hover:bg-gray-800/40">
                <div className="flex justify-between items-start gap-2">
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-white line-clamp-2 leading-snug">{b.question}</p>
                    <div className="flex flex-wrap items-center gap-1.5 mt-1 text-[10px]">
                      <span className={`px-1.5 py-0.5 rounded font-bold uppercase ${statusColor(b.status)}`}>
                        {b.status}
                      </span>
                      <span className={`px-1.5 py-0.5 rounded font-bold ${
                        b.side === "Yes" ? "bg-green-900/60 text-green-300" : "bg-red-900/60 text-red-300"
                      }`}>{b.side}</span>
                      <span className="text-purple-300 font-mono">${b.stake_usd.toFixed(2)}</span>
                      <span className="text-gray-500">@</span>
                      <span className="text-blue-300 font-mono">{(b.entry_price * 100).toFixed(1)}¢</span>
                      <span className="text-gray-600">·</span>
                      <span className={`font-mono ${b.edge_bps >= 0 ? "text-green-400" : "text-red-400"}`}>
                        edge {b.edge_bps >= 0 ? "+" : ""}{(b.edge_bps / 100).toFixed(1)}%
                      </span>
                      <span className="text-gray-600">·</span>
                      <span className="text-emerald-400 font-mono">EV ${b.expected_value_usd.toFixed(2)}</span>
                    </div>
                    {b.status === "open" && (
                      <div className="text-[9px] text-gray-500 mt-1">
                        resolves {b.hours_to_resolve != null ? `in ${b.hours_to_resolve.toFixed(1)}h` : "soon"} · our prob {((b.our_prob ?? 0) * 100).toFixed(1)}% vs market {((b.implied_prob ?? 0) * 100).toFixed(1)}%
                      </div>
                    )}
                    {b.status === "won" && b.payout_usd && (
                      <div className="text-[10px] text-green-400 mt-1">
                        +${(b.payout_usd - b.stake_usd).toFixed(2)} profit{b.btc_at_resolve != null ? ` · BTC closed $${b.btc_at_resolve.toFixed(0)}` : ""}
                      </div>
                    )}
                    {b.status === "lost" && (
                      <div className="text-[10px] text-red-400 mt-1">
                        -${b.stake_usd.toFixed(2)}{b.btc_at_resolve != null ? ` · BTC closed $${b.btc_at_resolve.toFixed(0)}` : ""}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </>
        )}

        {tab === "markets" && (
          <>
            {markets.length === 0 && (
              <div className="text-gray-600 text-xs p-4 text-center">Loading markets…</div>
            )}
            {markets.slice(0, 20).map((m) => (
              <a key={m.id} href={m.url} target="_blank" rel="noopener noreferrer"
                className="block p-2 hover:bg-gray-800/40">
                <p className="text-xs text-white line-clamp-2 leading-snug">{m.question}</p>
                <div className="flex items-center gap-2 mt-1 text-[10px]">
                  <span className="bg-green-900/60 text-green-300 px-1.5 rounded font-mono">
                    Yes {(m.yes_price * 100).toFixed(1)}¢
                  </span>
                  <span className="bg-red-900/60 text-red-300 px-1.5 rounded font-mono">
                    No {(m.no_price * 100).toFixed(1)}¢
                  </span>
                  <span className="text-gray-500">·</span>
                  <span className="text-amber-300">vol ${(m.volume / 1000).toFixed(1)}k</span>
                  <span className="text-gray-500">liq ${(m.liquidity / 1000).toFixed(1)}k</s