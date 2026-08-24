"use client";
import { useEffect, useState } from "react";
import { api } from "../lib/api";

interface Leader {
  rank: number; wallet: string; name?: string;
  profit_usd?: number | null; volume_usd?: number; source?: string;
}
interface CopyTrade {
  ts: number; asset?: string; side?: string; question?: string;
  leader_rank?: number; leader_name?: string; leader_wallet?: string;
  leader_size_usd?: number; stake_usd?: number; entry_price?: number;
  status?: string; mode?: string;
}

function short(w?: string) {
  if (!w) return "—";
  return w.slice(0, 6) + "…" + w.slice(-4);
}

export default function LeaderCopyPanel() {
  const [leaders, setLeaders] = useState<Leader[]>([]);
  const [trades, setTrades] = useState<CopyTrade[]>([]);
  const [src, setSrc] = useState<string>("");

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const [lRes, tRes] = await Promise.all([
          fetch(api("/api/edges/leaders")).then(r => r.json()),
          fetch(api("/api/edges/copy-trades?limit=30")).then(r => r.json()),
        ]);
        if (!alive) return;
        const ls: Leader[] = lRes.leaders || [];
        setLeaders(ls);
        setSrc(ls[0]?.source || "");
        setTrades((tRes.items || []).filter((x: CopyTrade) => x.status === "open"));
      } catch { /* ignore */ }
    };
    load();
    const id = setInterval(load, 8000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  return (
    <div className="bg-gray-900 rounded-xl p-4 border border-fuchsia-900/40">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-white font-bold text-lg">🏆 Copy the Champions</h2>
          <p className="text-[11px] text-gray-500">
            Mirroring the top {leaders.length || 10} Polymarket wallets
            {src ? ` · ${src === "polymarket_leaderboard" ? "profit-ranked" : "by volume"}` : ""}
          </p>
        </div>
        <span className="text-[10px] bg-fuchsia-900/40 text-fuchsia-300 px-2 py-1 rounded font-bold">
          COPY-TRADE
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Leaderboard */}
        <div>
          <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-1">Leaderboard (1–{leaders.length || 10})</div>
          <div className="space-y-1 max-h-64 overflow-y-auto">
            {leaders.length === 0 && <p className="text-gray-600 text-xs py-4">Ranking leaders…</p>}
            {leaders.map((l) => (
              <div key={l.wallet} className="flex items-center justify-between text-xs bg-gray-800/60 rounded px-2 py-1.5">
                <span className="flex items-center gap-2">
                  <span className={`font-bold w-5 ${l.rank <= 3 ? "text-amber-400" : "text-gray-400"}`}>#{l.rank}</span>
                  <span className="text-white font-mono">{l.name || short(l.wallet)}</span>
                </span>
                <span className="font-mono text-green-400">
                  {l.profit_usd != null ? `+$${l.profit_usd.toLocaleString()}` :
                    l.volume_usd != null ? `$${Math.round(l.volume_usd).toLocaleString()} vol` : ""}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Recent copied trades */}
        <div>
          <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-1">Copied trades (live)</div>
          <div className="space-y-1 max-h-64 overflow-y-auto">
            {trades.length === 0 && <p className="text-gray-600 text-xs py-4">Waiting for a champion to move…</p>}
            {trades.map((t, i) => (
              <div key={i} className="text-xs bg-gray-800/60 rounded px-2 py-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-fuchsia-300 font-bold">#{t.leader_rank ?? "?"} {t.leader_name || short(t.leader_wallet)}</span>
                  <span className="text-gray-500 font-mono">{new Date(t.ts).toLocaleTimeString()}</span>
                </div>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-white font-mono">{t.asset}</span>
                  <span className={t.side?.includes("YES") || t.side?.includes("BUY") || t.side?.includes("UP") ? "text-green-400" : "text-red-400"}>{t.side}</span>
                  <span className="text-cyan-400">@{t.entry_price}</span>
                  <span className="text-gray-500">→ ${t.stake_usd}</span>
                  {t.mode === "real" && <span className="text-amber-400 font-bold">REAL</span>}
                </div>
                <div className="text-gray-500 truncate">{t.question}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
