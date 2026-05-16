"use client";
import { API_URL, api, ws } from "../lib/api";
import { useEffect, useRef, useState } from "react";

interface StreamStat {
  stream: string; kind: string; total: number;
  rate_1s: number; rate_60s: number; rate_5m: number; last_ts: number;
}
interface ActivityData {
  ts: number; total_messages: number;
  total_rate_per_sec: number; total_rate_per_min: number; total_rate_per_hour: number;
  stream_count: number;
  streams: StreamStat[];
  by_kind: Array<{ kind: string; streams: number; total: number; rate: number }>;
}

const KIND_COLOR: Record<string, string> = {
  tick: "bg-blue-500",
  signal: "bg-purple-500",
  order: "bg-yellow-500",
  funding: "bg-cyan-500",
  risk: "bg-red-500",
  model: "bg-pink-500",
  position: "bg-green-500",
  other: "bg-gray-500",
};

const KIND_LABEL: Record<string, string> = {
  tick: "TICKS",
  signal: "SIGNALS",
  order: "ORDERS",
  funding: "FUNDING",
  risk: "RISK",
  model: "MODELS",
  position: "POSITIONS",
  other: "OTHER",
};

function Pulse({ active }: { active: boolean }) {
  return (
    <span className="relative inline-flex h-2 w-2 ml-1">
      {active && (
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
      )}
      <span className={`relative inline-flex rounded-full h-2 w-2 ${active ? "bg-green-500" : "bg-gray-700"}`}></span>
    </span>
  );
}

export default function ActivityMonitor() {
  const [data, setData] = useState<ActivityData | null>(null);
  const [pulses, setPulses] = useState<Record<string, number>>({});
  const lastTotal = useRef(0);
  const sparkRef = useRef<number[]>(Array(30).fill(0));

  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(api("/api/activity"));
        if (r.ok) {
          const j: ActivityData = await r.json();
          setData(j);
          // detect activity per stream (pulse)
          const newPulses: Record<string, number> = {};
          j.streams.forEach(s => {
            if (s.rate_60s > 0) newPulses[s.stream] = Date.now();
          });
          setPulses(prev => ({ ...prev, ...newPulses }));
          // update sparkline (rate per sec)
          sparkRef.current = [...sparkRef.current.slice(1), j.total_rate_per_sec];
          lastTotal.current = j.total_messages;
        }
      } catch {}
    };
    load();
    const id = setInterval(load, 1000);
    return () => clearInterval(id);
  }, []);

  if (!data) return <div className="bg-gray-900 p-3 rounded-lg border border-gray-800 text-gray-500 text-xs">Loading activity...</div>;

  const max = Math.max(1, ...sparkRef.current);

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-3">
      <div className="flex justify-between items-start mb-2">
        <div>
          <h2 className="text-white font-bold text-base flex items-center">
            Live Activity <Pulse active={data.total_rate_per_sec > 0} />
          </h2>
          <p className="text-[10px] text-gray-500">real-time system pulse across {data.stream_count} Redis streams</p>
        </div>
        <div className="text-right">
          <div className="font-mono text-2xl text-green-400">{data.total_rate_per_sec.toFixed(1)}</div>
          <div className="text-[10px] text-gray-500 uppercase">msgs/sec</div>
        </div>
      </div>

      {/* Sparkline */}
      <div className="flex items-end gap-px h-8 mb-3 bg-black/30 rounded p-1">
        {sparkRef.current.map((v, i) => (
          <div key={i} className="flex-1 bg-gradient-to-t from-green-700 to-green-400 rounded-sm transition-all"
            style={{ height: `${Math.max(2, (v / max) * 100)}%`, opacity: 0.4 + (i / sparkRef.current.length) * 0.6 }} />
        ))}
      </div>

      {/* Aggregate rates */}
      <div className="grid grid-cols-3 gap-2 mb-3 text-center">
        <div className="bg-gray-800 rounded p-1.5">
          <div className="text-[9px] text-gray-500 uppercase">per min</div>
          <div className="font-mono text-base text-cyan-400">{data.total_rate_per_min.toFixed(0)}</div>
        </div>
        <div className="bg-gray-800 rounded p-1.5">
          <div className="text-[9px] text-gray-500 uppercase">per hour</div>
          <div className="font-mono text-base text-cyan-400">{data.total_rate_per_hour.toLocaleString()}</div>
        </div>
        <div className="bg-gray-800 rounded p-1.5">
          <div className="text-[9px] text-gray-500 uppercase">total today</div>
          <div className="font-mono text-base text-white">{data.total_messages.toLocaleString()}</div>
        </div>
      </div>

      {/* By kind */}
      <div className="space-y-1">
        {data.by_kind.sort((a, b) => b.rate - a.rate).map(k => (
          <div key={k.kind} className="flex items-center gap-2 text-xs">
            <div className={`w-2 h-2 rounded-full ${KIND_COLOR[k.kind] || "bg-gray-500"}`} />
            <span className="text-gray-300 w-20">{KIND_LABEL[k.kind] || k.kind}</span>
            <div className="flex-1 h-1 bg-gray-800 rounded overflow-hidden">
              <div className={`h-full ${KIND_COLOR[k.kind] || "bg-gray-500"}`}
                style={{ width: `${Math.min(100, k.rate * 5)}%` }} />
            </div>
            <span className="font-mono text-white w-12 text-right">{k.rate.toFixed(1)}/s</span>
            <span className="font-mono text-gray-500 w-12 text-right">{k.total.toLocaleString()}</span>
          </div>
        ))}
      </div>

      {/* Per-stream */}
      <details className="mt-3">
        <summary className="text-[10px] uppercase text-gray-500 cursor-pointer hover:text-gray-300">
          ▾ Per-stream breakdown ({data.streams.length})
        </summary>
        <div className="max-h-40 overflow-y-auto mt-2 space-y-0.5">
          {data.streams.sort((a, b) => b.rate_60s - a.rate_60s).map(s => {
            const active = (Date.now() - s.last_ts) < 5000;
            return (
              <div key={s.stream} className="flex items-center gap-2 text-[10px] py-0.5 px-1 hover:bg-gray-800/50 rounded">
                <Pulse active={active} />
                <span className="font-mono text-gray-300 flex-1 truncate">{s.stream.replace("arb:", "")}</span>
                <span className="font-mono text-cyan-400 w-12 text-right">{s.rate_60s.toFixed(1)}/s</span>
                <span className="font-mono text-gray-600 w-12 text-right">{s.total}</span>
              </div>
            );
          })}
        </div>
      </details>
    </div>
  );
}
