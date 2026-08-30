"use client";
import { useEffect, useState } from "react";
import { api } from "./api";

export interface LiveReal {
  mode: string;
  armed: boolean;
  halted: boolean;
  total_spend: number;
  daily_spend: number;
  open_count: number;
  wallet_balance: number | null;
  realized_pnl: number;
  orders_count: number;
  recent_orders: Array<Record<string, unknown>>;
  caps: { bet: number; daily: number; total: number; max_open: number; min_edge_bps: number };
}

/**
 * Live state of the autonomous executor + REAL Polymarket account figures.
 * `realMode` is true when the operator has switched to REAL — the signal for
 * panels to show the real account (wallet_balance / realized_pnl / real orders)
 * instead of the paper/demo simulation.
 */
export function useLiveReal(intervalMs = 3000) {
  const [live, setLive] = useState<LiveReal | null>(null);
  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const j = await fetch(api("/api/live")).then((r) => r.json());
        if (alive && j && typeof j.mode === "string") setLive(j as LiveReal);
      } catch { /* ignore */ }
    };
    load();
    const id = setInterval(load, intervalMs);
    return () => { alive = false; clearInterval(id); };
  }, [intervalMs]);
  return { live, realMode: live?.mode === "real" };
}
