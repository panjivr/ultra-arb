"use client";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";

// LEAN Polymarket-focused dashboard.
// Only fast, Redis/DB-backed panels relevant to Polymarket copy-trading are
// loaded. The heavy Bloomberg/crypto panels that each polled a slow external
// API (macro, news, calendar, derivatives, trending, correlation, equities,
// spreads, funding, heatmap, positions, models, event log, latency) were
// removed: ~28 simultaneous polls on page load saturated a small VPS and the
// browser's per-host connection limit, which is what caused the intermittent
// "This page couldn't load / must reload". Fewer panels = the page stays
// responsive and reloads reliably. See docs/11-lean-polymarket.md.
const WalletConnect = dynamic(() => import("../src/components/WalletConnect"), { ssr: false });
const ModeToggle = dynamic(() => import("../src/components/ModeToggle"), { ssr: false });
const LeaderCopyPanel = dynamic(() => import("../src/components/LeaderCopyPanel"), { ssr: false });
const TickerStream = dynamic(() => import("../src/components/TickerStream"), { ssr: false });
const StatsBar = dynamic(() => import("../src/components/StatsBar"), { ssr: false });
const EquityChart = dynamic(() => import("../src/components/EquityChart"), { ssr: false });
const ActivityMonitor = dynamic(() => import("../src/components/ActivityMonitor"), { ssr: false });
const PolymarketPanel = dynamic(() => import("../src/components/PolymarketPanel"), { ssr: false });
const CompoundingTracker = dynamic(() => import("../src/components/CompoundingTracker"), { ssr: false });
const EdgeRadar = dynamic(() => import("../src/components/EdgeRadar"), { ssr: false });
const OnChainIntel = dynamic(() => import("../src/components/OnChainIntel"), { ssr: false });

function Clock() {
  const [t, setT] = useState<string>("");
  useEffect(() => {
    const tick = () => setT(new Date().toLocaleTimeString());
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);
  return <span className="font-mono text-gray-400">{t}</span>;
}

export default function Dashboard() {
  return (
    <div className="min-h-screen bg-black text-white">
      {/* Top bar */}
      <div className="border-b border-amber-900/40 bg-gray-950 px-4 py-2 flex items-center justify-between sticky top-0 z-10">
        <div className="flex items-center gap-4">
          <div>
            <h1 className="text-base font-bold text-white tracking-wider">REYOG CAPITAL</h1>
            <p className="text-[10px] text-amber-500/80 uppercase tracking-widest">Polymarket Copy-Trade Terminal</p>
          </div>
          <div className="flex gap-1.5 text-[10px] items-center">
            <ModeToggle />
            <span className="bg-green-900/40 text-green-300 px-2 py-1 rounded font-bold">REAL DATA</span>
            <span className="bg-fuchsia-900/40 text-fuchsia-300 px-2 py-1 rounded font-bold">POLYMARKET</span>
          </div>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <WalletConnect />
          <Clock />
        </div>
      </div>

      {/* Live crypto ticker — context for 5m/15m/30m Polymarket bets */}
      <div className="px-4 pt-3">
        <TickerStream />
      </div>

      {/* KPI strip — live PnL / win-rate */}
      <div className="px-4 py-3 border-b border-gray-900">
        <StatsBar />
      </div>

      <div className="p-4 space-y-3">
        {/* Equity curve + live activity */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
          <div className="lg:col-span-7">
            <EquityChart />
          </div>
          <div className="lg:col-span-5">
            <ActivityMonitor />
          </div>
        </div>

        {/* THE CORE: copy the top 1-10 Polymarket champions */}
        <LeaderCopyPanel />

        {/* Polymarket bets + compounding projection */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          <PolymarketPanel />
          <CompoundingTracker />
        </div>

        {/* Whale / smart-money intel — the wallets we copy */}
        <OnChainIntel />

        {/* Edge radar — copy-trade & arbitrage opportunities */}
        <EdgeRadar />
      </div>

      {/* Footer */}
      <div className="border-t border-amber-900/40 bg-gray-950 px-4 py-2 text-[10px] text-gray-600 flex justify-between">
        <span>REYOG CAPITAL · Polymarket-only · lean build</span>
        <span><Clock /></span>
      </div>
    </div>
  );
}
