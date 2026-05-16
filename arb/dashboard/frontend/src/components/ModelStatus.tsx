"use client";
import { API_URL, api, ws } from "../lib/api";
import { useEffect, useState } from "react";

interface ModelData {
  regime: { state: number; label: string; confidence: number; transition_matrix: number[][]; ts: number };
  kalman: Array<{ symbol: string; state: number; covariance: number; ts: number }>;
  cointegration: Array<{ pair: string; hedge_ratio: number; zscore: number; pvalue: number; signal: string; ts: number }>;
  bayesian: Array<{ strategy: string; alpha: number; beta: number; win_prob: number; ts: number }>;
}

const REGIME_COLOR: Record<number, string> = {
  0: "text-green-400 bg-green-950 border-green-800",
  1: "text-yellow-400 bg-yellow-950 border-yellow-800",
  2: "text-red-400 bg-red-950 border-red-800",
};

export default function ModelStatus() {
  const [data, setData] = useState<ModelData | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(api("/api/models"));
        if (r.ok) setData(await r.json());
      } catch {}
    };
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  if (!data) return <div className="bg-gray-900 p-4 rounded-lg border border-gray-800 text-gray-500 text-xs">Loading models...</div>;

  return (
    <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
      <h2 className="text-white font-bold text-base mb-3">ML / Quant Model State</h2>

      {/* HMM Regime */}
      <div className={`p-2.5 rounded border mb-3 ${REGIME_COLOR[data.regime.state] || REGIME_COLOR[0]}`}>
        <div className="flex justify-between items-center">
          <div>
            <div className="text-[10px] uppercase opacity-70">HMM Regime</div>
            <div className="text-lg font-bold">{data.regime.label}</div>
          </div>
          <div className="text-right">
            <div className="text-[10px] uppercase opacity-70">Confidence</div>
            <div className="text-lg font-mono">{(data.regime.confidence * 100).toFixed(0)}%</div>
          </div>
        </div>
        {data.regime.transition_matrix?.length > 0 && (
          <div className="mt-2 grid grid-cols-3 gap-0.5 text-[9px] font-mono">
            {data.regime.transition_matrix.flat().map((v, i) => (
              <div key={i} className="text-center bg-black/30 py-0.5 rounded">
                {(v * 100).toFixed(0)}%
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Cointegration pairs */}
      <div className="mb-3">
        <div className="text-[10px] uppercase text-gray-500 mb-1">Cointegration Pairs</div>
        <div className="space-y-1">
          {data.cointegration.length === 0 && <p className="text-gray-600 text-xs">No active pairs</p>}
          {data.cointegration.map((c, i) => {
            const sigColor =
              c.signal === "long" ? "text-green-400" :
              c.signal === "short" ? "text-red-400" : "text-gray-400";
            return (
              <div key={i} className="bg-gray-800 p-1.5 rounded text-xs flex justify-between items-center">
                <span className="font-mono text-white">{c.pair}</span>
                <div className="flex gap-3 text-[10px]">
                  <span className="text-gray-400">β <span className="text-cyan-300">{c.hedge_ratio.toFixed(2)}</span></span>
                  <span className="text-gray-400">z <span className={Math.abs(c.zscore) > 2 ? "text-yellow-400" : "text-gray-300"}>{c.zscore.toFixed(2)}</span></span>
                  <span className="text-gray-400">p <span className={c.pvalue < 0.05 ? "text-green-400" : "text-gray-400"}>{c.pvalue.toFixed(3)}</span></span>
                  <span className={`font-bold ${sigColor}`}>{c.signal.toUpperCase()}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Bayesian Win Probability */}
      <div className="mb-3">
        <div className="text-[10px] uppercase text-gray-500 mb-1">Bayesian Win Probability</div>
        <div className="space-y-1">
          {data.bayesian.map((b, i) => (
            <div key={i} className="bg-gray-800 p-1.5 rounded text-xs">
              <div className="flex justify-between items-center mb-0.5">
                <span className="text-blue-300 font-bold">{b.strategy}</span>
                <span className={`font-mono ${b.win_prob >= 0.6 ? "text-green-400" : "text-yellow-400"}`}>
                  {(b.win_prob * 100).toFixed(1)}%
                </span>
              </div>
              <div className="h-1 bg-gray-900 rounded overflow-hidden">
                <div className={b.win_prob >= 0.6 ? "bg-green-500 h-full" : "bg-yellow-500 h-full"}
                  style={{ width: `${b.win_prob * 100}%` }} />
              </div>
              <div className="text-[9px] text-gray-500 mt-0.5">α={b.alpha.toFixed(1)} β={b.beta.toFixed(1)} (Beta posterior)</div>
            </div>
          ))}
        </div>
      </div>

      {/* Kalman Filter States */}
      <div>
        <div className="text-[10px] uppercase text-gray-500 mb-1">Kalman Filter States</div>
        <div className="space-y-0.5">
          {data.kalman.map((k, i) => (
            <div key={i} className="flex justify-between text-[11px] bg-gray-800 px-1.5 py-1 rounded">
              <span className="text-white font-mono">{k.symbol}</span>
              <span className="text-cyan-300 font-mono">x={k.state.toFixed(2)}</span>
              <span className="text-gray-400 font-mono">σ²={k.covariance.toFixed(5)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
