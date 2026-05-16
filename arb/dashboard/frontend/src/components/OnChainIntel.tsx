"use client";
import { api } from "../lib/api";
import { useEffect, useState } from "react";

interface WhaleEntry {
  source: string;
  type: string;
  address?: string;
  coin?: string;
  direction?: string;
  notional?: number;
  size?: number;
  entry_price?: number;
  leverage?: number;
  pnl?: number;
  wallets?: string[];
  count?: number;
  ts?: number;
  [key: string]: any;
}

interface MemeEntry {
  source: string;
  symbol?: string;
  name?: string;
  chain?: string;
  price?: number;
  price_change_1h?: number;
  price_change_24h?: number;
  volume_24h?: number;
  liquidity?: number;
  signal_type?: string;
  score?: number;
  url?: string;
  ts?: number;
  [key: string]: any;
}

interface Summary {
  whales: WhaleEntry[];
  trending: MemeEntry[];
  whale_count: number;
  trending_count: number;
  total_signals: number;
  ts: number;
}

const TABS = [
  { key: "whales", label: "Whale Tracker", emoji: "🐋", color: "blue" },
  { key: "meme", label: "Meme Scanner", emoji: "🔥", color: "orange" },
] as const;

function timeAgo(ts?: number): string {
  if (!ts) return "";
  const sec = Math.floor((Date.now() - ts) / 1000);
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  return `${Math.floor(sec / 3600)}h ago`;
}

function shortAddr(addr?: string): string {
  if (!addr) return "???";
  return addr.slice(0, 6) + "…" + addr.slice(-4);
}

function fmt(n: number | undefined, d = 2): string {
  if (n === undefined || n === null) return "—";
  return Number(n).toFixed(d);
}

function fmtUsd(n: number | undefined): string {
  if (n === undefined || n === null) return "—";
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `$${(n / 1_000).toFixed(1)}K`;
  return `$${n.toFixed(0)}`;
}

export default function OnChainIntel() {
  const [data, setData] = useState<Summary | null>(null);
  const [tab, setTab] = useState<string>("whales");

  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(api("/api/onchain/summary"));
        if (r.ok) setData(await r.json());
      } catch {}
    };
    load();
    const id = setInterval(load, 10_000);
    return () => clearInterval(id);
  }, []);

  if (!data)
    return (
      <div className="bg-gray-900 rounded-lg border border-gray-800 p-4 h-full flex items-center justify-center">
        <span className="text-gray-500 text-xs">Scanning on-chain…</span>
      </div>
    );

  const renderWhale = (w: WhaleEntry, i: number) => {
    const isCoordinated = w.type === "hl_whale:coordinated";
    const isNew = w.type === "hl_whale:new_position";
    const isIncrease = w.type === "hl_whale:position_increase";

    const label = isCoordinated
      ? "COORDINATED"
      : isNew
      ? "NEW POSITION"
      : isIncrease
      ? "SIZE UP"
      : w.type?.split(":").pop()?.toUpperCase() || "SIGNAL";

    const labelColor = isCoordinated
      ? "bg-red-700"
      : isNew
      ? "bg-green-700"
      : "bg-blue-700";

    return (
      <div
        key={i}
        className={`border rounded p-2 ${
          isCoordinated
            ? "bg-red-950/30 border-red-800/50"
            : "bg-blue-950/20 border-blue-800/40"
        }`}
      >
        <div className="flex justify-between items-start gap-2">
          <div className="flex items-center gap-2">
            <span className="text-sm">{isCoordinated ? "🚨" : "🐋"}</span>
            <span className="text-xs font-bold text-white">
              {w.coin || "—"}
            </span>
            <span
              className={`text-[9px] px-1.5 py-0.5 rounded font-bold text-white ${
                w.direction === "LONG" || w.direction === "long"
                  ? "bg-green-700"
                  : "bg-red-700"
              }`}
            >
              {w.direction?.toUpperCase() || "—"}
            </span>
          </div>
          <span
            className={`text-[9px] px-1.5 py-0.5 rounded font-bold text-white ${labelColor}`}
          >
            {label}
          </span>
        </div>

        <div className="flex items-center gap-3 mt-1 text-[10px]">
          {isCoordinated ? (
            <>
              <span className="text-red-300 font-bold">
                {w.count || 0} whales aligned
              </span>
              {w.wallets?.slice(0, 3).map((a, j) => (
                <span key={j} className="text-gray-500 font-mono">
                  {shortAddr(a)}
                </span>
              ))}
            </>
          ) : (
            <>
              <span className="text-gray-400 font-mono">
                {shortAddr(w.address)}
              </span>
              <span className="text-purple-300 font-bold">
                {fmtUsd(w.notional)}
              </span>
              {w.leverage && (
                <span className="text-amber-300">{w.leverage}x</span>
              )}
              {w.pnl !== undefined && (
                <span
                  className={
                    w.pnl >= 0 ? "text-green-400" : "text-red-400"
                  }
                >
                  PnL {w.pnl >= 0 ? "+" : ""}
                  {fmtUsd(w.pnl)}
                </span>
              )}
            </>
          )}
          <span className="text-gray-600 ml-auto">{timeAgo(w.ts)}</span>
        </div>
      </div>
    );
  };

  const renderMeme = (m: MemeEntry, i: number) => {
    const change1h = m.price_change_1h ?? 0;
    const change24h = m.price_change_24h ?? 0;

    return (
      <div
        key={i}
        className="bg-orange-950/20 border border-orange-800/40 rounded p-2"
      >
        <div className="flex justify-between items-start gap-2">
          <div className="flex items-center gap-2">
            <span className="text-sm">🔥</span>
            <span className="text-xs font-bold text-white">
              {m.symbol || m.name || "—"}
            </span>
            {m.chain && (
              <span className="text-[9px] bg-gray-800 text-gray-400 px-1 rounded">
                {m.chain}
              </span>
            )}
          </div>
          {m.signal_type && (
            <span className="text-[9px] bg-orange-700 text-white px-1.5 py-0.5 rounded font-bold">
              {m.signal_type.replace(/_/g, " ").toUpperCase()}
            </span>
          )}
        </div>

        <div className="flex items-center gap-3 mt-1 text-[10px]">
          {m.price !== undefined && (
            <span className="text-white font-mono">
              ${m.price < 0.01 ? m.price.toExponential(2) : fmt(m.price, 4)}
            </span>
          )}
          <span className={change1h >= 0 ? "text-green-400" : "text-red-400"}>
            1h {change1h >= 0 ? "+" : ""}
            {fmt(change1h, 1)}%
          </span>
          <span
            className={change24h >= 0 ? "text-green-400" : "text-red-400"}
          >
            24h {change24h >= 0 ? "+" : ""}
            {fmt(change24h, 1)}%
          </span>
          {m.volume_24h !== undefined && (
            <span className="text-cyan-300">Vol {fmtUsd(m.volume_24h)}</span>
          )}
          {m.liquidity !== undefined && (
            <span className="text-gray-500">Liq {fmtUsd(m.liquidity)}</span>
          )}
          <span className="text-gray-600 ml-auto">{timeAgo(m.ts)}</span>
        </div>
      </div>
    );
  };

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 h-full flex flex-col">
      <div className="border-b border-gray-800 px-3 py-2">
        <div className="flex justify-between items-start mb-2">
          <div>
            <h2 className="text-white font-bold text-sm flex items-center gap-2">
              <span className="text-blue-400">⛓</span> On-Chain Intelligence
              <span className="text-[9px] bg-blue-700 text-white px-1.5 py-0.5 rounded uppercase">
                {data.total_signals} signals
              </span>
            </h2>
            <p className="text-[10px] text-gray-500">
              Hyperliquid whale tracker · DexScreener meme scanner · 60s refresh
            </p>
          </div>
          <div className="flex items-center gap-2 text-[10px]">
            <span className="text-gray-600">
              🐋 {data.whale_count} · 🔥 {data.trending_count}
            </span>
          </div>
        </div>
        <div className="flex gap-1">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-2 py-0.5 text-[10px] rounded uppercase font-bold transition ${
                tab === t.key
                  ? t.key === "whales"
                    ? "bg-blue-700 text-white"
                    : "bg-orange-700 text-white"
                  : "bg-gray-800 text-gray-400 hover:text-white"
              }`}
            >
              {t.emoji} {t.label}
              <span className="ml-1 opacity-70">
                {t.key === "whales" ? data.whale_count : data.trending_count}
              </span>
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-1.5 max-h-[400px]">
        {tab === "whales" && data.whales.length === 0 && (
          <div className="text-gray-600 text-xs p-6 text-center">
            Scanning Hyperliquid whales… signals appear every ~60s
          </div>
        )}
        {tab === "whales" &&
          data.whales.slice(0, 25).map((w, i) => renderWhale(w, i))}

        {tab === "meme" && data.trending.length === 0 && (
          <div className="text-gray-600 text-xs p-6 text-center">
            Scanning DexScreener… trending tokens appear every ~60s
          </div>
        )}
        {tab === "meme" &&
          data.trending.slice(0, 25).map((m, i) => renderMeme(m, i))}
      </div>
    </div>
  );
}
