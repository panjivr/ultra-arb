"use client";
import { useEffect, useState } from "react";
import { api } from "../lib/api";

interface ModeState {
  mode: string; effective: string; server_live_ready: boolean;
  wallet?: string | null; note?: string | null;
}

export default function ModeToggle() {
  const [st, setSt] = useState<ModeState | null>(null);
  const [wallet, setWallet] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    try {
      const [m, w] = await Promise.all([
        fetch(api("/api/mode")).then(r => r.json()),
        fetch(api("/api/wallet/list")).then(r => r.json()).catch(() => ({})),
      ]);
      setSt(m);
      const active = (w.wallets || []).find((x: { is_active?: boolean }) => x.is_active);
      setWallet(active?.address || null);
    } catch { /* ignore */ }
  };

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 6000);
    return () => clearInterval(id);
  }, []);

  const setMode = async (mode: "demo" | "real") => {
    if (mode === "real" && !wallet) return;
    if (mode === "real" && !confirm(
      "Switch to REAL MONEY mode?\n\nBets will use your connected wallet's real USDC once the server has a live key. Only do this if you accept the risk of real losses."
    )) return;
    setBusy(true);
    try {
      await fetch(api("/api/mode"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode, wallet: wallet || "" }),
      });
      await refresh();
    } finally { setBusy(false); }
  };

  const isReal = st?.mode === "real";
  const effReal = st?.effective === "real";

  return (
    <div className="flex items-center gap-2">
      {/* Current mode badge */}
      <span
        className={`text-[10px] px-2 py-1 rounded font-bold ${
          effReal ? "bg-red-900/60 text-red-300" : "bg-yellow-900/50 text-yellow-400"
        }`}
        title={st?.note || ""}
      >
        {effReal ? "● REAL MONEY" : isReal ? "REAL (armed, paper)" : "DEMO"}
      </span>

      {/* Toggle button */}
      {!isReal ? (
        <button
          onClick={() => setMode("real")}
          disabled={!wallet || busy}
          title={wallet ? "Enable real-money mode" : "Connect a wallet first"}
          className={`text-[10px] px-2 py-1 rounded font-bold border ${
            wallet
              ? "border-red-700 text-red-300 hover:bg-red-950"
              : "border-gray-700 text-gray-600 cursor-not-allowed"
          }`}
        >
          {wallet ? "Enable REAL" : "Connect wallet → REAL"}
        </button>
      ) : (
        <button
          onClick={() => setMode("demo")}
          disabled={busy}
          className="text-[10px] px-2 py-1 rounded font-bold border border-gray-600 text-gray-300 hover:bg-gray-800"
        >
          Back to DEMO
        </button>
      )}
    </div>
  );
}
