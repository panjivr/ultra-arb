"use client";
import { useEffect, useRef, useState } from "react";
import { api, ws } from "../lib/api";

/**
 * Live "system flow" — visualises the running backend as a flowing pipeline:
 *   Ticks → Sinyal → Edge → Gerbang → Order → Resolve
 * Events stream in from the /ws/firehose WebSocket (ticks/signals/orders) and
 * 2s polls (/api/live, /api/edges/all, /api/polymarket/bets). Each stage counts
 * live and pulses as activity passes; a feed narrates what the bot just did.
 * Read-only — it never places or changes anything.
 */

type Tone = "tick" | "signal" | "edge" | "gate" | "order" | "resolve-win" | "resolve-loss";
interface FeedItem { id: string; text: string; tone: Tone; ts: number }
interface LiveState {
  mode: string; armed: boolean; halted: boolean; halt_reason?: string | null;
  total_spend: number; daily_spend: number; open_count: number;
  caps: { bet: number; daily: number; total: number; min_edge_bps: number; max_open: number };
  gates: { mode_real: boolean; armed: boolean; not_halted: boolean };
}

const STAGES = [
  { key: "ticks",   label: "Ticks",   sub: "harga live",   color: "#49c5d6" },
  { key: "signals", label: "Sinyal",  sub: "engine",       color: "#5b8def" },
  { key: "edges",   label: "Edge",    sub: "6 detektor",   color: "#e8b04b" },
  { key: "gates",   label: "Gerbang", sub: "5 cek",        color: "#b57bff" },
  { key: "order",   label: "Order",   sub: "Polymarket",   color: "#37c46a" },
  { key: "resolve", label: "Resolve", sub: "menang/kalah", color: "#9aa7b8" },
] as const;

const CSS = `
@keyframes sf-flow { to { background-position: 26px 0; } }
@keyframes sf-pulse { 0%{transform:scale(1);} 40%{transform:scale(1.13);} 100%{transform:scale(1);} }
@keyframes sf-ring { 0%{box-shadow:0 0 0 0 var(--rc);} 100%{box-shadow:0 0 0 12px transparent;} }
@keyframes sf-in { from{opacity:0; transform:translateY(-6px);} to{opacity:1; transform:none;} }
.sf-conn{background-image:repeating-linear-gradient(90deg,currentColor 0 8px,transparent 8px 26px);
  background-size:26px 2px; background-repeat:repeat-x; background-position:0 0; animation:sf-flow 1s linear infinite;}
.sf-pulse{animation:sf-pulse .5s ease-out, sf-ring .6s ease-out;}
.sf-feed-item{animation:sf-in .3s ease-out;}
@media (prefers-reduced-motion:reduce){.sf-conn,.sf-pulse{animation:none!important;}}
`;

const TONE_COLOR: Record<Tone, string> = {
  tick: "#49c5d6", signal: "#5b8def", edge: "#e8b04b", gate: "#b57bff",
  order: "#37c46a", "resolve-win": "#37c46a", "resolve-loss": "#f0524f",
};

export default function SystemFlow() {
  const [counts, setCounts] = useState<Record<string, number>>({
    ticks: 0, signals: 0, edges: 0, order: 0, resolve: 0,
  });
  const [live, setLive] = useState<LiveState | null>(null);
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [pulse, setPulse] = useState<Record<string, number>>({});
  const [connected, setConnected] = useState(false);

  // refs for cross-poll "what's new" detection (don't trigger re-render)
  const seenBets = useRef<Set<string>>(new Set());
  const seenResolved = useRef<Set<string>>(new Set());
  const edgeMaxTs = useRef<number>(0);
  const feedSeq = useRef<number>(0);

  const firePulse = (stage: string) => setPulse((p) => ({ ...p, [stage]: Date.now() }));

  const pushFeed = (text: string, tone: Tone) => {
    const id = `f${feedSeq.current++}`;
    setFeed((f) => [{ id, text, tone, ts: Date.now() }, ...f].slice(0, 9));
  };

  const bump = (stage: keyof typeof counts, by = 1) =>
    setCounts((c) => ({ ...c, [stage]: (c[stage] || 0) + by }));

  // ── WebSocket firehose: ticks / signals / orders ──
  useEffect(() => {
    let alive = true;
    let sock: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;
    const connect = () => {
      if (!alive) return;
      try { sock = new WebSocket(ws("/ws/firehose")); } catch { return; }
      sock.onopen = () => alive && setConnected(true);
      sock.onclose = () => { if (!alive) return; setConnected(false); retry = setTimeout(connect, 2500); };
      sock.onerror = () => { try { sock?.close(); } catch { /* noop */ } };
      sock.onmessage = (ev) => {
        let msg: { messages?: Array<Record<string, unknown>> };
        try { msg = JSON.parse(ev.data); } catch { return; }
        const list = Array.isArray(msg.messages) ? msg.messages : [];
        let nTick = 0, nSig = 0, nOrd = 0;
        for (const m of list) {
          const stream = String((m as { _stream?: string })._stream || "");
          if (stream.startsWith("arb:ticks:")) { nTick++; }
          else if (stream === "arb:signals") {
            nSig++;
            const sym = (m as { symbol?: string }).symbol || "";
            if (nSig <= 1) pushFeed(`sinyal ${sym} terdeteksi`, "signal");
          } else if (stream === "arb:orders") {
            const evt = (m as { event?: string }).event;
            const pnl = Number((m as { pnl?: number }).pnl ?? NaN);
            if (evt === "CLOSE" && !Number.isNaN(pnl)) {
              nOrd++;
              pushFeed(`trade close ${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}`, pnl >= 0 ? "resolve-win" : "resolve-loss");
            }
          }
        }
        if (nTick) { bump("ticks", nTick); firePulse("ticks"); }
        if (nSig) { bump("signals", nSig); firePulse("signals"); }
        if (nOrd) { firePulse("resolve"); }
      };
    };
    connect();
    return () => { alive = false; if (retry) clearTimeout(retry); try { sock?.close(); } catch { /* noop */ } };
  }, []);

  // ── Polls: live state, edges, polymarket bets ──
  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const l = await fetch(api("/api/live")).then((r) => r.json());
        if (alive && l && typeof l.mode === "string") setLive(l as LiveState);
      } catch { /* ignore */ }
      try {
        const e = await fetch(api("/api/edges/all")).then((r) => r.json());
        let total = 0, freshTs = edgeMaxTs.current, sawNew = false;
        for (const k of Object.keys(e || {})) {
          const arr = Array.isArray(e[k]) ? e[k] : [];
          total += arr.length;
          for (const it of arr) {
            const ts = Number(it?.ts || 0);
            if (ts > edgeMaxTs.current) { sawNew = true; if (ts > freshTs) freshTs = ts; }
          }
        }
        if (alive) {
          setCounts((c) => ({ ...c, edges: total }));
          if (sawNew && edgeMaxTs.current > 0) { firePulse("edges"); pushFeed("edge baru menyala", "edge"); }
          edgeMaxTs.current = freshTs;
        }
      } catch { /* ignore */ }
      try {
        const b = await fetch(api("/api/polymarket/bets?limit=60")).then((r) => r.json());
        const bets = Array.isArray(b?.bets) ? b.bets : [];
        let placed = 0, won = 0, lost = 0;
        for (const bet of bets) {
          const id = String(bet?.id || "");
          if (!id) continue;
          const status = bet?.status;
          if (status === "open" && !seenBets.current.has(id)) {
            seenBets.current.add(id);
            if (seenBets.current.size > 1) { placed++; }
          }
          if ((status === "won" || status === "lost") && !seenResolved.current.has(id)) {
            seenResolved.current.add(id);
            if (seenResolved.current.size > 1) { status === "won" ? won++ : lost++; }
          }
        }
        if (alive) {
          if (placed) { bump("order", placed); firePulse("order"); pushFeed(`order ditaruh (${placed})`, "order"); }
          if (won) { bump("resolve", won); firePulse("resolve"); pushFeed(`menang ×${won}`, "resolve-win"); }
          if (lost) { bump("resolve", lost); firePulse("resolve"); pushFeed(`kalah ×${lost}`, "resolve-loss"); }
        }
      } catch { /* ignore */ }
    };
    poll();
    const id = setInterval(poll, 2000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const isLive = live?.mode === "real";
  const gatesOpen = live ? Object.values(live.gates).filter(Boolean).length : 0;
  const halted = live?.halted;

  const stageValue = (key: string): string => {
    if (key === "gates") return halted ? "BLOKIR" : `${gatesOpen}/3`;
    if (key === "edges") return String(counts.edges ?? 0);
    return String(counts[key] ?? 0);
  };
  const recentlyPulsed = (key: string) => pulse[key] && Date.now() - pulse[key] < 650;

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
      <style dangerouslySetInnerHTML={{ __html: CSS }} />

      {/* header + live status strip */}
      <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-b border-gray-800 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-purple-300">◈</span>
          <h2 className="text-white font-bold text-sm">System Flow</h2>
          <span className="text-[10px] text-gray-500 hidden sm:inline">— mesin berpikir, live</span>
        </div>
        <div className="flex items-center gap-2 text-[10px] font-mono flex-wrap">
          <span className={`px-2 py-0.5 rounded font-bold ${isLive
            ? "bg-green-900/50 text-green-300 border border-green-700/50"
            : "bg-gray-800 text-gray-400 border border-gray-700"}`}>
            {isLive ? "● LIVE" : "PAPER"}
          </span>
          {isLive && (
            <span className={`px-2 py-0.5 rounded ${live?.armed
              ? "bg-amber-900/40 text-amber-300" : "bg-gray-800 text-gray-500"}`}>
              {live?.armed ? "ARMED" : "STANDBY"}
            </span>
          )}
          {live && (
            <>
              <span className="text-gray-500">spent <b className="text-gray-300">${live.total_spend.toFixed(2)}</b>/${live.caps.total}</span>
              <span className="text-gray-500">open <b className="text-gray-300">{live.open_count}</b>/{live.caps.max_open}</span>
            </>
          )}
          {halted && <span className="px-2 py-0.5 rounded bg-red-900/50 text-red-300 border border-red-700/50">HALTED</span>}
          <span className={`w-1.5 h-1.5 rounded-full ${connected ? "bg-green-400" : "bg-gray-600"}`} title={connected ? "firehose connected" : "reconnecting"} />
        </div>
      </div>

      {/* the pipeline */}
      <div className="px-4 py-5 overflow-x-auto">
        <div className="flex items-stretch gap-0 min-w-[640px]">
          {STAGES.map((st, i) => (
            <div key={st.key} className="flex items-stretch flex-1">
              <div className="flex flex-col items-center justify-center gap-1.5 flex-1 min-w-[96px]">
                <div
                  className={`relative w-full rounded-lg border bg-gray-950/70 px-2 py-3 text-center ${recentlyPulsed(st.key) ? "sf-pulse" : ""}`}
                  style={{
                    borderColor: recentlyPulsed(st.key) ? st.color : "rgba(255,255,255,.08)",
                    ["--rc" as string]: st.color,
                  }}
                >
                  <div className="text-[9px] uppercase tracking-wider" style={{ color: st.color }}>{st.label}</div>
                  <div className="font-mono font-bold text-lg leading-tight mt-1"
                    style={{ color: st.key === "gates" && halted ? "#f0524f" : "#e8eef4" }}>
                    {stageValue(st.key)}
                  </div>
                  <div className="text-[8.5px] text-gray-500 mt-0.5">{st.sub}</div>
                </div>
              </div>
              {i < STAGES.length - 1 && (
                <div className="flex items-center px-1" style={{ color: st.color, opacity: 0.6 }}>
                  <div className="sf-conn w-6 sm:w-8 h-0.5" />
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* live event feed — "what the bot just did" */}
      <div className="border-t border-gray-800 px-4 py-2 bg-gray-950/40 min-h-[40px]">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[9px] uppercase tracking-widest text-gray-600 font-mono">feed</span>
          {feed.length === 0 && <span className="text-[11px] text-gray-600 font-mono">menunggu aktivitas…</span>}
          {feed.map((f) => (
            <span key={f.id} className="sf-feed-item text-[11px] font-mono px-1.5 py-0.5 rounded"
              style={{ color: TONE_COLOR[f.tone], background: "rgba(255,255,255,.03)" }}>
              {f.text}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
