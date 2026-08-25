"use client";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import ErrorBoundary from "../src/components/ErrorBoundary";

// LEAN Polymarket-focused dashboard.
// Only fast, Redis/DB-backed panels relevant to Polymarket copy-trading are
// loaded. The heavy Bloomberg/crypto panels that each polled a slow external
// API (macro, news, calendar, derivatives, trending, correlation, equities,
// spreads, funding, heatmap, positions, models, event log, latency) were
// removed: ~28 simultaneous polls on page load saturated a small VPS and the
// browser's per-host connection limit, which is what caused the intermittent
// "This page couldn't load / must reload". Fewer panels = the page stays
// responsive and reloads reliably. See docs/11-lean-polymarket.md.
//
// safeDynamic additionally wraps each panel in its own error boundary so a
// single crashing panel (e.g. a missing field from a degraded upstream) can
// never blank the whole dashboard.
function safeDynamic(loader: () => Promise<{ default: React.ComponentType<Record<string, unknown>> }>) {
  const C = dynamic(loader, { ssr: false });
  const Wrapped = (props: Record<string, unknown>) => (
    <ErrorBoundary>
      <C {...props} />
    </ErrorBoundary>
  );
  return Wrapped;
}

const WalletConnect = safeDynamic(() => import("../src/components/WalletConnect"));
const ModeToggle = safeDynamic(() => import("../src/components/ModeToggle"));
const LeaderCopyPanel = safeDynamic(() => import("../src/components/LeaderCopyPanel"));
const RobustnessMatrix = safeDynamic(() => import("../src/components/RobustnessMatrix"));
const LiveEquity = safeDynamic(() => import("../src/components/LiveEquity"));
const AlertTicker = safeDynamic(() => import("../src/components/AlertTicker"));
const TickerStream = safeDynamic(() => import("../src/components/TickerStream"));
const StatsBar = safeDynamic(() => import("../src/components/StatsBar"));
const EquityChart = safeDynamic(() => import("../src/components/EquityChart"));
const ActivityMonitor = safeDynamic(() => import("../src/components/ActivityMonitor"));
const PolymarketPanel = safeDynamic(() => import("../src/components/PolymarketPanel"));
const CompoundingTracker = safeDynamic(() => import("../src/components/CompoundingTracker"));
const EdgeRadar = safeDynamic(() => import("../src/components/EdgeRadar"));
const OnChainIntel = safeDynamic(() => import("../src/components/OnChainIntel"));

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

      {/* Scrolling alert ticker — real copy-trade events */}
      <AlertTicker />

      {/* Live equity — realized + unrealized mark-to-market, moves every ~1.5s */}
      <LiveEquity />

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

        {/* Real multi-timeframe returns heatmap (Robustness Matrix) */}
        <RobustnessMatrix />

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
