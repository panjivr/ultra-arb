"use client";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";

const StatsBar = dynamic(() => import("../src/components/StatsBar"), { ssr: false });
const WalletConnect = dynamic(() => import("../src/components/WalletConnect"), { ssr: false });
const EquityChart = dynamic(() => import("../src/components/EquityChart"), { ssr: false });
const StrategyPerformance = dynamic(() => import("../src/components/StrategyPerformance"), { ssr: false });
const PositionsTable = dynamic(() => import("../src/components/PositionsTable"), { ssr: false });
const DetailedSignals = dynamic(() => import("../src/components/DetailedSignals"), { ssr: false });
const ModelStatus = dynamic(() => import("../src/components/ModelStatus"), { ssr: false });
const RiskPanel = dynamic(() => import("../src/components/RiskPanel"), { ssr: false });
const SpreadsMonitor = dynamic(() => import("../src/components/SpreadsMonitor"), { ssr: false });
const FundingRates = dynamic(() => import("../src/components/FundingRates"), { ssr: false });
const ActivityMonitor = dynamic(() => import("../src/components/ActivityMonitor"), { ssr: false });
const ExtendedStats = dynamic(() => import("../src/components/ExtendedStats"), { ssr: false });
const HourlyHeatmap = dynamic(() => import("../src/components/HourlyHeatmap"), { ssr: false });
const CorrelationMatrix = dynamic(() => import("../src/components/CorrelationMatrix"), { ssr: false });
const EventLog = dynamic(() => import("../src/components/EventLog"), { ssr: false });
const TickerStream = dynamic(() => import("../src/components/TickerStream"), { ssr: false });
// REYOG CAPITAL — Bloomberg-style market intelligence
const NewsTicker = dynamic(() => import("../src/components/NewsTicker"), { ssr: false });
const MacroBar = dynamic(() => import("../src/components/MacroBar"), { ssr: false });
const EconomicCalendar = dynamic(() => import("../src/components/EconomicCalendar"), { ssr: false });
const LatencyMonitor = dynamic(() => import("../src/components/LatencyMonitor"), { ssr: false });
const DerivativesPanel = dynamic(() => import("../src/components/DerivativesPanel"), { ssr: false });
const TrendingCoins = dynamic(() => import("../src/components/TrendingCoins"), { ssr: false });
const EquityWatchlist = dynamic(() => import("../src/components/EquityWatchlist"), { ssr: false });
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
