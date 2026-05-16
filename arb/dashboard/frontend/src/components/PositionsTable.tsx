"use client";
import { API_URL, api, ws } from "../lib/api";
import { useEffect, useState } from "react";

interface Position {
  symbol: string; strategy: string; exchange: string;
  direction: string; qty: number;
  entry_price: number; mark_price: number; size_usd: number;
  unrealized_pnl_usd: number; unrealized_pnl_pct: number;
  opened_at: number;
}

const ago = (ts: number) => {
  const s = Math.floor((Date.now() - ts) / 1000);
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s/60)}m`;
  return `${Math.floor(s/3600)}h`;
};

export default function PositionsTable() {
  const [positions, setPositions] = useState<Position[]>([]);

  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(api("/api/positions/open"));
        if (r.ok) {
          const j = await r.json();
          setPositions(j.positions || []);
        }
      } catch {}
    };
    load();
    const id = setInterval(load, 2000);
    return () => clearInterval(id);
  }, []);

  const totalUnrealized = positions.reduce((s, p) => s + p.unrealized_pnl_usd, 0);
  const totalExposure = positions.reduce((s, p) => s + p.size_usd, 0);

  return (
    <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
      <div className="flex justify-between items-center mb-3">
        <div>
          <h2 className="text-white font-bold text-base">Open Positions</h2>
          <p className="text-xs text-gray-500">{positions.length}/5 slots used · ${totalExposure.toFixed(0)} exposure</p>
        </div>
        <div className={`font-mono text-lg ${totalUnrealized >= 0 ? "text-green-400" : "text-red-400"}`}>
          {totalUnrealized >= 0 ? "+" : ""}{totalUnrealized.toFixed(2)} <span className="text-xs text-gray-500">USD unrealized</span>
        </div>
      </div>
      {positions.length === 0 ? (
        <p className="text-gray-500 text-xs text-center py-6">No open positions</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-gray-500 text-[10px] uppercase border-b border-gray-800">
              <tr>
                <th className="text-left py-2">Symbol</th>
                <th className="text-left">Strat</th>
                <th className="text-left">Side</th>
                <th className="text-right">Qty</th>
                <th className="text-right">Entry</th>
                <th className="text-right">Mark</th>
                <th className="text-right">Size</th>
                <th className="text-right">uPnL</th>
                <th className="text-right">%</th>
                <th className="text-right">Age</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p, i) => {
                const positive = p.unrealized_pnl_usd >= 0;
                return (
                  <tr key={i} className="border-b border-gray-800/50 hover:bg-gray-800/50">
                    <td className="py-1.5 font-mono text-white">{p.symbol}</td>
                    <td className="text-blue-300">{p.strategy}</td>
                    <td className={p.direction === "long" ? "text-green-400" : "text-red-400"}>
                      {p.direction.toUpperCase()}
                    </td>
                    <td className="text-right font-mono text-gray-300">{p.qty}</td>
                    <td className="text-right font-mono text-gray-400">{p.entry_price}</td>
                    <td className="text-right font-mono text-white">{p.mark_price}</td>
                    <td className="text-right font-mono text-gray-400">${p.size_usd.toFixed(0)}</td>
                    <td className={`text-right font-mono ${positive ? "text-green-400" : "text-red-400"}`}>
                      {positive ? "+" : ""}{p.unrealized_pnl_usd.toFixed(2)}
                    </td>
                    <td className={`text-right font-mono ${positive ? "text-green-400" : "text-red-400"}`}>
                      {positive ? "+" : ""}{p.unrealized_pnl_pct.toFixed(2)}%
                    </td>
                    <td className="text-right text-gray-500">{ago(p.opened_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
