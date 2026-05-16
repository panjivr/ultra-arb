"use client";
import { API_URL, api, ws } from "../lib/api";
import { useEffect, useRef, useState } from "react";

interface Tick {
  symbol: string; exchange: string;
  bid: number; ask: number; mid: number; ts: number;
  source?: string;
}

interface PriceRow {
  symbol: string;
  exchanges: Record<string, { mid: number; prev: number; ts: number; direction: 'up' | 'down' | 'flat'; source?: string }>;
}

export default function TickerStream() {
  const [rows, setRows] = useState<Record<string, PriceRow>>({});
  const prevRef = useRef<Record<string, Record<string, number>>>({});

  const [isReal, setIsReal] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const r2 = await fetch(api("/api/activity/recent?limit=60"));
        if (r2.ok) {
          const j = await r2.json();
          const next = { ...rows };
          let sawReal = false;
          (j.events || []).forEach((e: any) => {
            if (!e.stream.startsWith("ticks:")) return;
            const d = e.data;
            const sym = d.symbol; const ex = d.exchange;
            if (!sym || !ex) return;
            if (d.source === "REAL") sawReal = true;
            if (!next[sym]) next[sym] = { symbol: sym, exchanges: {} };
            const prev = prevRef.current[sym]?.[ex] ?? d.mid;
            const dir: 'up' | 'down' | 'flat' = d.mid > prev ? 'up' : d.mid < prev ? 'down' : 'flat';
            next[sym].exchanges[ex] = { mid: d.mid, prev, ts: d.ts, direction: dir, source: d.source };
            if (!prevRef.current[sym]) prevRef.current[sym] = {};
            prevRef.current[sym][ex] = d.mid;
          });
          setRows(next);
          setIsReal(sawReal);
        }
      } catch {}
    };
    load();
    const id = setInterval(load, 1000);
    return () => clearInterval(id);
  }, []);

  const symbols = Object.values(rows);
  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
      <div className="bg-black/60 px-3 py-1.5 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-gray-500 uppercase tracking-widest">LIVE TICKER</span>
          {isReal && (
            <span className="text-[9px] bg-green-900/60 text-green-300 px-1.5 py-0.5 rounded font-bold uppercase tracking-wide">
              ● REAL MARKET DATA
            </span>
          )}
          {!isReal && symbols.length > 0 && (
            <span className="text-[9px] bg-yellow-900/60 text-yellow-300 px-1.5 py-0.5 rounded font-bold uppercase">
              SIM
            </span>
          )}
        </div>
        <span className="text-[10px] text-green-400 animate-pulse">● streaming</span>
      </div>
      <div className="overflow-x-auto whitespace-nowrap py-2 px-2 flex gap-3">
        {symbols.length === 0 && <span className="text-gray-600 text-xs">No ticks yet — start feeds</span>}
        {symbols.map(row =>
          Object.entries(row.exchanges).map(([ex, e]) => {
            const decimals = e.mid >= 1000 ? 2 : e.mid >= 10 ? 3 : 4;
            return (
              <div key={`${row.symbol}-${ex}`} className="flex items-center gap-2 bg-gray-800 rounded px-2 py-1 text-xs flex-shrink-0">
                <span className="font-bold text-white font-mono">{row.symbol}</span>
                <span className="text-[9px] text-gray-500 uppercase">{ex}</span>
                <span className={`font-mono font-bold ${e.direction === 'up' ? 'text-green-400' : e.direction === 'down' ? 'text-red-400' : 'text-white'}`}>
                  {e.mid.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}
                </span>
                <span className={`text-xs ${e.direction === 'up' ? 'text-green-400' : e.direction === 'down' ? 'text-red-400' : 'text-gray-600'}`}>
                  {e.direction === 'up' ? '▲' : e.direction === 'down' ? '▼' : '—'}
                </span>
                {e.source === "REAL" && <span className="text-[8px] text-green-500 font-bold">●</span>}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
