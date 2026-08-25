"use client";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import ErrorBoundary from "../src/components/ErrorBoundary";

// Wrap every panel in its own error boundary so a single crashing panel
// (e.g. a missing field from a degraded upstream API) never blanks the whole
// dashboard. Client-only (ssr:false) to match the original dynamic imports.
function safeDynamic(loader: () => Promise<{ default: React.ComponentType<Record<string, unknown>> }>) {
  const C = dynamic(loader, { ssr: false });
  const Wrapped = (props: Record<string, unknown>) => (
    <ErrorBoundary>
      <C {...props} />
    </ErrorBoundary>
  );
  return Wrapped;
}

const StatsBar = safeDynamic(() => import("../src/components/StatsBar"));
const WalletConnect = safeDynamic(() => import("../src/components/WalletConnect"));
const EquityChart = safeDynamic(() => import("../src/components/EquityChart"));
const StrategyPerformance = safeDynamic(() => import("../src/components/StrategyPerformance"));
const PositionsTable = safeDynamic(() => import("../src/components/PositionsTable"));
const DetailedSignals = safeDynamic(() => import("../src/components/DetailedSignals"));
const ModelStatus = safeDynamic(() => import("../src/components/ModelStatus"));
const RiskPanel = safeDynamic(() => import("../src/components/RiskPanel"));
const SpreadsMonitor = safeDynamic(() => import("../src/components/SpreadsMonitor"));
const FundingRates = safeDynamic(() => import("../src/components/FundingRates"));
const ActivityMonitor = safeDynamic(() => import("../src/components/ActivityMonitor"));
const ExtendedStats = safeDynamic(() => import("../src/components/ExtendedStats"));
const HourlyHeatmap = safeDynamic(() => import("../src/components/HourlyHeatmap"));
const CorrelationMatrix = safeDynamic(() => import("../src/components/CorrelationMatrix"));
const EventLog = safeDynamic(() => import("../src/components/EventLog"));
const TickerStream = safeDynamic(() => import("../src/components/TickerStream"));
// REYOG CAPITAL — Bloomberg-style market intelligence
const NewsTicker = safeDynamic(() => import("../src/components/NewsTicker"));
const MacroBar = safeDynamic(() => import("../src/components/MacroBar"));
const EconomicCalendar = safeDynamic(() => import("../src/components/EconomicCalendar"));
const LatencyMonitor = safeDynamic(() => import("../src/components/LatencyMonitor"));
const DerivativesPanel = safeDynamic(() => import("../src/components/DerivativesPanel"));
const TrendingCoins = safeDynamic(() => import("../src/components/TrendingCoins"));
const EquityWatchlist = safeDynamic(() => import("../src/components/EquityWatchlist"));
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
            <p className="text-[10px] text-amber-500/80 uppercase tracking-widest">Advanced AI Market Intelligence</p>
          </div>
          <div className="flex gap-1.5 text-[10px]">
            <span className="bg-yellow-900/50 text-yellow-400 px-2 py-1 rounded font-bold">PAPER</span>
            <span className="bg-green-900/40 text-green-300 px-2 py-1 rounded font-bold">REAL DATA</span>
            <span className="bg-cyan-900/40 text-cyan-300 px-2 py-1 rounded font-bold">0ms WS</span>
            <span className="bg-gray-800 text-green-400 px-2 py-1 rounded font-mono">● GATEIO</span>
            <span className="bg-gray-800 text-green-400 px-2 py-1 rounded font-mono">● HTX</span>
          </div>
        </div>
        <div className="flex items-center gap-3 text-xs">
          <WalletConnect />
          <Clock />
        </div>
      </div>

      {/* Macro intelligence bar */}
      <div className="px-4 pt-3">
        <MacroBar />
      </div>

      {/* Live ticker bar */}
      <div className="px-4 pt-3">
        <TickerStream />
      </div>

      {/* KPI Strip */}
      <div className="px-4 py-3 border-b border-gray-900">
        <StatsBar />
      </div>

      <div className="p-4 space-y-3">
        {/* Row 1: Equity chart + Activity Monitor + Latency */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
          <div className="lg:col-span-7">
            <EquityChart />
          </div>
          <div className="lg:col-span-5 space-y-3">
            <ActivityMonitor />
            <LatencyMonitor />
          </div>
        </div>

        {/* Row 2: News + Calendar + Equities Watchlist — Bloomberg intel */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
          <div className="lg:col-span-5">
            <NewsTicker />
          </div>
          <div className="lg:col-span-4">
            <EconomicCalendar />
          </div>
          <div className="lg:col-span-3">
            <EquityWatchlist />
          </div>
        </div>

        {/* Row 2b: On-Chain Intelligence — whale tracker + meme scanner */}
        <OnChainIntel />

        {/* Row 2c: Edge Radar — the alpha-finder */}
        <EdgeRadar />

        {/* Row 2c: Polymarket + Compounding — the money-printing duo */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          <PolymarketPanel />
          <CompoundingTracker />
        </div>

        {/* Row 2c: Derivatives + Trending */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          <DerivativesPanel />
          <TrendingCoins />
        </div>

        {/* Row 3: Strategy perf + Risk + Extended stats */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <StrategyPerformance />
          <RiskPanel />
          <ExtendedStats />
        </div>

        {/* Row 4: Positions */}
        <PositionsTable />

        {/* Row 5: Signals wide + Models */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <div className="lg:col-span-2">
            <DetailedSignals />
          </div>
          <ModelStatus />
        </div>

        {/* Row 6: Spreads + Funding + Hourly Heatmap */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <SpreadsMonitor />
          <FundingRates />
          <HourlyHeatmap />
        </div>

        {/* Row 7: Correlation + Event log */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <CorrelationMatrix />
          <div className="lg:col-span-2">
            <EventLog />
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="border-t border-amber-900/40 bg-gray-950 px-4 py-2 text-[10px] text-gray-600 flex justify-between">
        <span>REYOG CAPITAL · v0.3 · Python 3.12 · Rust PyO3 hot-paths · NautilusTrader · Redis · PostgreSQL 17</span>
        <span>WebSocket firehose · sub-ms decision latency · <Clock /></span>
      </div>
    </div>
  );
}
