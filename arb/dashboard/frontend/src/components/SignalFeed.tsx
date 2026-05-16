"use client";
import { API_URL, api, ws } from "../lib/api";
import { useEffect, useRef, useState } from "react";

interface Signal {
  ts: number; strategy: string; symbol: string;
  probability_score?: number; expected_value?: number;
  direction?: string; tradeable?: boolean; regime?: number;
  _stream?: string; heartbeat?: boolean;
}

const REGIME_LABEL: Record<number, string> = { 0: "LOW VOL", 1: "MED VOL", 2: "HIGH VOL" };
const REGIME_COLOR: Record<number, string> = { 0: "text-green-400", 1: "text-yellow-400", 2: "text-red-400" };

export default function SignalFeed() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const connect = () => {
      const sock = new WebSocket(ws("/ws/live"));
      wsRef.current = sock;
      sock.onopen = () => setConnected(true);
      sock.onclose = () => { setConnected(false); setTimeout(connect, 2000); };
      sock.onmessage = (e) => {
        const data = JSON.parse(e.data);
        if (data.heartbeat) return;
        const msgs = (data.messages || []).filter((m: Signal) => m.strategy && !m.heartbeat);
        if (msgs.length) {
          setSignals(prev => [...msgs, ...prev].slice(0, 100));
        }
      };
    };
    connect();
    return () => wsRef.current?.close();
  }, []);

  return (
    <div className="bg-gray-900 rounded-xl p-4 border border-gray-700">
      <div className="flex justify-between items-center mb-3">
        <h2 className="text-white font-bold text-lg">Live Signal Feed</h2>
        <div className={`text-xs px-2 py-1 rounded ${connected ? "bg-green-900 text-green-400" : "bg-red-900 text-red-400"}`}>
          {connected ? "● LIVE" : "○ CONNECTING"}
        </div>
      </div>
      <div className="overflow-y-auto max-h-64 space-y-1">
        {signals.length === 0 && (
          <p className="text-gray-500 text-sm text-center py-8">Waiting for signals...</p>
        )}
        {signals.map((s, i) => (
          <div key={i} className={`text-xs p-2 rounded ${s.tradeable ? "bg-blue-950 border border-blue-800" : "bg-gray-800"}`}>
            <div className="flex items-center justify-between gap-2">
              <span className="text-blue-300 font-bold truncate max-w-[120px]">{s.strategy}</span>
              <span className="text-white font-mono">{s.symbol?.slice(0, 10)}</span>
              {s.tradeable && <span className="text-green-400 shrink-0">⚡ TRADE</span>}
              <span className="text-gray-500 font-mono shrink-0">{new Date(s.ts).toLocaleTimeString()}</span>
            </div>
            <div className="flex items-center gap-3 mt-1">
              {s.probability_score !== undefined && (
                <span className={(s.probability_score||0) > 0.7 ? "text-green-400" : "text-yellow-400"}>
                  P={((s.probability_score||0)*100).toFixed(0)}%
                </span>
              )}
              {s.expected_value !== undefined && (
                <span className="text-cyan-400">EV={s.expected_value.toFixed(3)}</span>
              )}
              {s.regime !== undefined && (
                <span className={REGIME_COLOR[s.regime]}>{REGIME_LABEL[s.regime]}</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
