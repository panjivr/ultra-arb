"use client";
import { API_URL, api, ws } from "../lib/api";
import { useEffect, useState } from "react";

interface Event { stream: string; ts: number; data: any; }

const STREAM_COLOR: Record<string, string> = {
  signals: "text-purple-400",
  orders: "text-yellow-400",
  "risk:alerts": "text-red-400",
};

function streamColor(stream: string): string {
  if (stream.startsWith("ticks:")) return "text-blue-400";
  if (stream.startsWith("funding:")) return "text-cyan-400";
  if (stream.startsWith("models:")) return "text-pink-400";
  if (stream.startsWith("positions:")) return "text-green-400";
  return STREAM_COLOR[stream] || "text-gray-300";
}

function describe(e: Event): string {
  const d = e.data;
  if (e.stream.startsWith("ticks:")) return `tick ${d.symbol} @${d.exchange} bid ${d.bid} ask ${d.ask}`;
  if (e.stream === "signals") return `${d.strategy} ${d.symbol} P=${((d.probability_score||0)*100).toFixed(0)}% EV=${(d.expected_value||0).toFixed(3)}`;
  if (e.stream === "orders") return `${d.event} ${d.strategy} ${d.symbol} ${d.direction} $${d.size_usd}${d.pnl !== undefined ? ` PnL ${d.pnl >= 0 ? '+' : ''}${d.pnl}` : ''}`;
  if (e.stream.startsWith("funding:")) return `${d.symbol} @${d.exchange} rate ${(d.rate*100).toFixed(4)}%`;
  if (e.stream.startsWith("models:")) return JSON.stringify(d).slice(0, 80);
  if (e.stream.startsWith("positions:")) return `OPEN ${d.symbol} ${d.direction} $${d.size_usd}`;
  if (e.stream === "risk:alerts") return `${d.event} — ${d.reason}`;
  return JSON.stringify(d).slice(0, 80);
}

export default function EventLog() {
  const [events, setEvents] = useState<Event[]>([]);
  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(api("/api/activity/recent?limit=40"));
        if (r.ok) {
          const j = await r.json();
          setEvents(j.events || []);
        }
      } catch {}
    };
    load();
    const id = setInterval(load, 1500);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="bg-gray-900 rounded-lg p-3 border border-gray-800">
      <div className="flex justify-between items-center mb-2">
        <h2 className="text-white font-bold text-base">Event Log</h2>
        <span className="text-[10px] text-gray-500">live · last {events.length} events</span>
      </div>
      <div className="font-mono text-[10px] space-y-0.5 max-h-72 overflow-y-auto bg-black/40 rounded p-2">
        {events.length === 0 && <p className="text-gray-600 text-center py-4">No events</p>}
        {events.map((e, i) => (
          <div key={i} className="flex gap-2 leading-tight hover:bg-white/5 px-1 rounded">
            <span className="text-gray-500 shrink-0">{new Date(e.ts).toLocaleTimeString()}</span>
            <span className={`shrink-0 ${streamColor(e.stream)} w-32 truncate`}>{e.stream}</span>
            <span className="text-gray-300 truncate">{describe(e)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
