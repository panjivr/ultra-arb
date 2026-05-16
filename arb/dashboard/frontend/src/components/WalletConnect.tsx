"use client";
import { api } from "../lib/api";
import { useEffect, useRef, useState, useCallback } from "react";
import {
  EIP1193Provider,
  DetectedWallet,
  subscribeWallets,
  connect,
  currentChainId,
  switchToPolygon,
  getUsdcBalance,
  getMaticBalance,
  signMessage,
  shortAddress,
  POLYGON_CHAIN,
  USDC_E_ADDRESS,
  USDC_NATIVE_ADDRESS,
} from "../lib/web3";

// ─── Types ────────────────────────────────────────────────────────────────────

interface LinkedWallet {
  address: string;
  wallet_name: string | null;
  wallet_icon: string | null;
  usdc_balance: number;
  matic_balance: number;
  linked_at: number;
  last_chain_sync: number;
  is_active: boolean;
  // live provider (only present in the browser session that connected it)
  provider?: EIP1193Provider;
  chainId?: string;
}

interface State {
  available: DetectedWallet[];
  linked: LinkedWallet[];          // all wallets known to backend
  activeAddr: string | null;       // which one is "active trading wallet"
  showPicker: boolean;
  showPanel: boolean;
  loading: boolean;
  error: string | null;
  connectingAddr: string | null;   // address currently being connected
}

const STORAGE_KEY = "reyog_wallets_last";  // comma-separated rdns list

// ─── Component ────────────────────────────────────────────────────────────────

export default function WalletConnect() {
  const [s, setS] = useState<State>({
    available: [],
    linked: [],
    activeAddr: null,
    showPicker: false,
    showPanel: false,
    loading: false,
    error: null,
    connectingAddr: null,
  });

  // Map address → live provider (from browser session)
  const providersRef = useRef<Map<string, EIP1193Provider>>(new Map());
  const listenersRef = useRef<Map<string, boolean>>(new Map());

  // ── 1. Discover wallets ──
  useEffect(() => {
    const unsub = subscribeWallets((wallets) => {
      setS(prev => ({ ...prev, available: wallets }));
      tryAutoReconnect(wallets);
    });
    return unsub;
  }, []);

  // ── 2. Load wallets from backend on mount + poll ──
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const r = await fetch(api("/api/wallet/list"));
        if (!r.ok || cancelled) return;
        const data = await r.json();
        if (!cancelled) {
          setS(prev => ({
            ...prev,
            linked: mergeProviders(data.wallets || [], providersRef.current),
            activeAddr: (data.wallets || []).find((w: LinkedWallet) => w.is_active)?.address || null,
          }));
        }
      } catch {}
    };
    load();
    const id = setInterval(load, 15_000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  // ── 3. Refresh balances for connected providers ──
  useEffect(() => {
    if (providersRef.current.size === 0) return;
    const refresh = () => {
      providersRef.current.forEach((provider, addr) => {
        refreshBalance(provider, addr);
      });
    };
    const id = setInterval(refresh, 20_000);
    return () => clearInterval(id);
  }, [s.linked.length]);

  function mergeProviders(backendWallets: LinkedWallet[], providers: Map<string, EIP1193Provider>): LinkedWallet[] {
    return backendWallets.map(w => ({
      ...w,
      provider: providers.get(w.address) || undefined,
    }));
  }

  // ── Auto-reconnect wallets that were previously connected ──
  async function tryAutoReconnect(wallets: DetectedWallet[]) {
    const lastRdns = localStorage.getItem(STORAGE_KEY)?.split(",") || [];
    for (const rdns of lastRdns) {
      const match = wallets.find(w => w.info.rdns === rdns);
      if (!match) continue;
      try {
        const accounts: string[] = await match.provider.request({ method: "eth_accounts" });
        if (!accounts || accounts.length === 0) continue;
        const addr = accounts[0].toLowerCase();
        if (!addr.startsWith("0x") || addr.length !== 42) continue;
        if (providersRef.current.has(addr)) continue; // already connected
        const chain = await match.provider.request({ method: "eth_chainId" });
        providersRef.current.set(addr, match.provider);
        attachListeners(match.provider, addr);
        setS(prev => ({
          ...prev,
          linked: prev.linked.map(w => w.address === addr ? { ...w, provider: match.provider, chainId: chain } : w),
        }));
      } catch {}
    }
  }

  function attachListeners(provider: EIP1193Provider, addr: string) {
    if (listenersRef.current.get(addr)) return;
    if (!provider.on) return;
    provider.on("accountsChanged", (accounts: string[]) => {
      if (!accounts || accounts.length === 0) {
        // Wallet disconnected in browser — keep backend record but remove provider
        providersRef.current.delete(addr);
        listenersRef.current.delete(addr);
        setS(prev => ({
          ...prev,
          linked: prev.linked.map(w => w.address === addr ? { ...w, provider: undefined } : w),
        }));
      }
    });
    provider.on("chainChanged", (chainId: string) => {
      setS(prev => ({
        ...prev,
        linked: prev.linked.map(w => w.address === addr ? { ...w, chainId } : w),
      }));
      refreshBalance(provider, addr);
    });
    listenersRef.current.set(addr, true);
  }

  async function refreshBalance(provider: EIP1193Provider, addr: string) {
    try {
      const [usdc1, usdc2, matic, chain] = await Promise.all([
        getUsdcBalance(provider, addr, USDC_E_ADDRESS),
        getUsdcBalance(provider, addr, USDC_NATIVE_ADDRESS),
        getMaticBalance(provider, addr),
        currentChainId(provider),
      ]);
      const usdc = usdc1 + usdc2;
      setS(prev => ({
        ...prev,
        linked: prev.linked.map(w => w.address === addr
          ? { ...w, usdc_balance: usdc, matic_balance: matic, chainId: chain }
          : w),
      }));
      await fetch(api("/api/wallet/sync"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ address: addr, usdc_balance: usdc, matic_balance: matic }),
      }).catch(() => {});
    } catch {}
  }

  async function selectAndConnect(wallet: DetectedWallet) {
    setS(prev => ({ ...prev, loading: true, error: null, showPicker: false }));
    try {
      const provider = wallet.provider;
      const addr = (await connect(provider)).toLowerCase();

      if (!addr || !addr.startsWith("0x") || addr.length !== 42) {
        throw new Error(
          `${wallet.info.name} returned a non-EVM account. ` +
          (wallet.info.name === "Phantom"
            ? "Open Phantom and select an Ethereum/Polygon account."
            : "Switch to an EVM account in your wallet.")
        );
      }

      // Already connected? Just switch active
      const already = s.linked.find(w => w.address === addr);
      if (already) {
        providersRef.current.set(addr, provider);
        attachListeners(provider, addr);
        setS(prev => ({
          ...prev,
          loading: false,
          linked: prev.linked.map(w => w.address === addr ? { ...w, provider } : w),
        }));
        saveLastRdns(addr, wallet.info.rdns);
        return;
      }

      // Force Polygon
      let chain = await currentChainId(provider);
      for (let i = 0; i < 3 && chain !== POLYGON_CHAIN.chainId; i++) {
        try {
          await switchToPolygon(provider);
          await new Promise(r => setTimeout(r, 600));
          chain = await currentChainId(provider);
        } catch (e: any) {
          if (e.code === 4001 || /user rejected/i.test(e.message || "")) {
            throw new Error(`Polygon network required. Please approve the network switch.`);
          }
        }
      }

      const nonce = Math.random().toString(36).slice(2, 10);
      const msg = `REYOG CAPITAL — Sign in\nWallet: ${wallet.info.name}\nAddress: ${addr}\nNonce: ${nonce}\nTime: ${new Date().toISOString()}`;
      let sig: string | null = null;
      try { sig = await signMessage(provider, addr, msg); } catch {}

      const [usdc1, usdc2, matic] = await Promise.all([
        getUsdcBalance(provider, addr, USDC_E_ADDRESS),
        getUsdcBalance(provider, addr, USDC_NATIVE_ADDRESS),
        getMaticBalance(provider, addr),
      ]);
      const usdc = usdc1 + usdc2;

      const res = await fetch(api("/api/wallet/link"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          address: addr,
          chain_id: parseInt(POLYGON_CHAIN.chainId, 16),
          signature: sig, nonce,
          usdc_balance: usdc, matic_balance: matic,
          wallet_name: wallet.info.name,
          wallet_icon: wallet.info.icon,
        }),
      });
      const data = await res.json();

      providersRef.current.set(addr, provider);
      attachListeners(provider, addr);
      saveLastRdns(addr, wallet.info.rdns);

      const allWallets: LinkedWallet[] = (data.all_wallets || [data.wallet]).map((w: LinkedWallet) => ({
        ...w,
        provider: providersRef.current.get(w.address),
        chainId: w.address === addr ? chain : undefined,
      }));

      setS(prev => ({
        ...prev,
        linked: allWallets,
        activeAddr: allWallets.find(w => w.is_active)?.address || addr,
        loading: false,
        showPanel: true,
      }));
    } catch (e: any) {
      setS(prev => ({ ...prev, loading: false, error: e?.message || "Connection failed" }));
    }
  }

  function saveLastRdns(addr: string, rdns: string) {
    const existing = localStorage.getItem(STORAGE_KEY)?.split(",").filter(Boolean) || [];
    if (!existing.includes(rdns)) existing.push(rdns);
    localStorage.setItem(STORAGE_KEY, existing.join(","));
  }

  async function handleSetActive(addr: string) {
    await fetch(api("/api/wallet/set-active"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ address: addr }),
    });
    setS(prev => ({
      ...prev,
      activeAddr: addr,
      linked: prev.linked.map(w => ({ ...w, is_active: w.address === addr })),
    }));
  }

  async function handleUnlink(addr: string) {
    const res = await fetch(api("/api/wallet/unlink"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ address: addr }),
    });
    const data = await res.json();
    providersRef.current.delete(addr);
    listenersRef.current.delete(addr);
    // Update saved rdns
    const wallet = s.linked.find(w => w.address === addr);
    if (wallet) {
      const saved = localStorage.getItem(STORAGE_KEY)?.split(",").filter(Boolean) || [];
      // We don't have rdns here easily, just clear all for this addr — safe fallback
      localStorage.setItem(STORAGE_KEY, saved.join(","));
    }
    const remaining: LinkedWallet[] = (data.all_wallets || []).map((w: LinkedWallet) => ({
      ...w,
      provider: providersRef.current.get(w.address),
    }));
    setS(prev => ({
      ...prev,
      linked: remaining,
      activeAddr: remaining.find(w => w.is_active)?.address || null,
      showPanel: remaining.length > 0,
    }));
  }

  async function handleForceRefresh(addr: string) {
    const res = await fetch(api("/api/wallet/refresh"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ address: addr }),
    });
    const data = await res.json();
    if (data.ok) {
      setS(prev => ({
        ...prev,
        linked: prev.linked.map(w => w.address === addr
          ? { ...w, usdc_balance: data.usdc_balance || 0, matic_balance: data.matic_balance || 0, last_chain_sync: data.last_chain_sync || Date.now() }
          : w),
      }));
    }
  }

  const totalUsdc = s.linked.reduce((sum, w) => sum + (w.usdc_balance || 0), 0);
  const activeWallet = s.linked.find(w => w.address === s.activeAddr) || s.linked[0] || null;

  // ─── Manual address link (for HTTP sites where extensions don't inject) ───
  const [showManual, setShowManual] = useState(false);
  const [manualAddr, setManualAddr] = useState("");
  const [manualName, setManualName] = useState("Trust Wallet");
  const [previewBalance, setPreviewBalance] = useState<{ usdc: number; matic: number } | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [manualExpanded, setManualExpanded] = useState(false);
  const [detectStartedAt, setDetectStartedAt] = useState(0);
  const [, forceTick] = useState(0);

  const WALLET_PRESETS = [
    { name: "Trust Wallet", icon: "🛡️" },
    { name: "MetaMask", icon: "🦊" },
    { name: "Phantom", icon: "👻" },
    { name: "OKX Wallet", icon: "⬛" },
    { name: "Coinbase Wallet", icon: "🔵" },
    { name: "Rabby", icon: "🐰" },
  ];

  const previewAddr = async (addr: string) => {
    if (!addr.startsWith("0x") || addr.length !== 42) {
      setPreviewBalance(null);
      return;
    }
    setPreviewLoading(true);
    try {
      const r = await fetch(api("/api/wallet/preview-balance"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ address: addr }),
      });
      if (r.ok) {
        const data = await r.json();
        setPreviewBalance({ usdc: data.usdc_balance || 0, matic: data.matic_balance || 0 });
      }
    } catch {} finally { setPreviewLoading(false); }
  };

  const linkManualAddress = async () => {
    const addr = manualAddr.trim();
    if (!addr.startsWith("0x") || addr.length !== 42) {
      setS(prev => ({ ...prev, error: "Invalid address. Must be 0x... (42 chars)" }));
      return;
    }
    setS(prev => ({ ...prev, loading: true, error: null }));
    try {
      const resp = await fetch(api("/api/wallet/link"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          address: addr,
          chain_id: 137,
          wallet_name: manualName || "Wallet",
          usdc_balance: previewBalance?.usdc || 0,
          matic_balance: previewBalance?.matic || 0,
        }),
      });
      const res = await resp.json();
      if (res.ok) {
        const wallets = (res.all_wallets || [res.wallet]).map((w: any) => ({ ...w, provider: undefined }));
        const active = wallets.find((w: any) => w.is_active)?.address || addr.toLowerCase();
        setS(prev => ({ ...prev, linked: wallets, activeAddr: active, loading: false }));
        setShowManual(false);
        setManualAddr("");
        setPreviewBalance(null);
      } else {
        setS(prev => ({ ...prev, error: res.error || "Link failed", loading: false }));
      }
    } catch (e: any) {
      setS(prev => ({ ...prev, error: e.message, loading: false }));
    }
  };

  const openConnectModal = () => {
    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event("eip6963:requestProvider"));
    }
    import("../lib/web3").then(({ listWallets }) => {
      const fresh = listWallets();
      setS(prev => ({ ...prev, available: fresh }));
    });
    setShowManual(true);
    setManualExpanded(false);
    setDetectStartedAt(Date.now());
    setS(prev => ({ ...prev, error: null }));
    setPreviewBalance(null);
    setManualAddr("");
    // Re-probe a few times while modal is open (extensions inject async)
    let n = 0;
    const t = setInterval(() => {
      n++;
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event("eip6963:requestProvider"));
      }
      import("../lib/web3").then(({ listWallets }) => {
        const fresh = listWallets();
        setS(prev => (fresh.length !== prev.available.length ? { ...prev, available: fresh } : prev));
      });
      forceTick(x => x + 1);
      if (n >= 8) clearInterval(t);
    }, 700);
  };

  const detectElapsed = detectStartedAt ? Date.now() - detectStartedAt : 0;

  // ─── Render: no wallets connected ───
  if (s.linked.length === 0) {
    return (
      <>
        <div className="flex items-center gap-1">
          <button
            onClick={openConnectModal}
            disabled={s.loading}
            className="flex items-center gap-1.5 bg-gradient-to-r from-purple-700 to-purple-600 hover:from-purple-600 hover:to-purple-500 disabled:opacity-50 text-white text-xs font-bold px-3 py-1.5 rounded transition-colors"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <path d="M21 18v1c0 1.1-.9 2-2 2H5c-1.11 0-2-.9-2-2V5c0-1.1.89-2 2-2h14c1.1 0 2 .9 2 2v1h-9c-1.11 0-2 .9-2 2v8c0 1.1.89 2 2 2h9zm-9-2h10V8H12v8zm4-2.5c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5z" />
            </svg>
            {s.loading ? "Connecting..." : "Connect Wallet"}
          </button>
        </div>

        {/* Unified connect modal — extensions + manual address */}
        {showManual && (
          <div className="fixed inset-0 bg-black/70 z-[60] flex items-center justify-center" onClick={() => setShowManual(false)}>
            <div className="bg-gray-900 border border-gray-700 rounded-lg shadow-2xl w-[440px] max-h-[85vh] overflow-hidden" onClick={e => e.stopPropagation()}>
              {/* Header */}
              <div className="bg-gradient-to-r from-purple-900 to-indigo-900 px-5 py-4 border-b border-gray-700 flex justify-between items-center">
                <div>
                  <h3 className="text-white font-bold text-base">Connect Wallet</h3>
                  <p className="text-[11px] text-purple-300 mt-0.5">Polygon network · Balance fetched from chain</p>
                </div>
                <button onClick={() => setShowManual(false)} className="text-gray-400 hover:text-white text-xl px-1">×</button>
              </div>

              {/* Detected wallet extensions — primary connect path */}
              <div className="px-4 pt-4 pb-2">
                {s.available.length > 0 ? (
                  <>
                    <div className="text-[10px] text-gray-500 uppercase font-bold mb-2">
                      Choose a wallet · click to sign &amp; connect
                    </div>
                    <div className="space-y-1.5">
                      {s.available.map(w => (
                        <button key={w.info.uuid} onClick={() => { setShowManual(false); selectAndConnect(w); }}
                          disabled={s.loading}
                          className="w-full flex items-center gap-3 bg-gray-800 hover:bg-gray-700 border border-gray-700 hover:border-purple-500 rounded-lg p-3 text-left transition-all disabled:opacity-50">
                          <img src={w.info.icon} alt="" className="w-9 h-9 rounded" onError={e => (e.target as HTMLImageElement).style.display = "none"} />
                          <div className="flex-1">
                            <div className="text-white font-bold text-sm">{w.info.name}</div>
                            <div className="text-[10px] text-gray-500">Opens wallet for confirmation</div>
                          </div>
                          <span className="text-purple-400 text-xs font-bold">Connect →</span>
                        </button>
                      ))}
                    </div>
                  </>
                ) : (
                  <div className="flex flex-col items-center text-center py-6">
                    <div className="w-7 h-7 border-2 border-purple-500 border-t-transparent rounded-full animate-spin mb-3" />
                    <div className="text-white text-sm font-bold mb-1">Detecting wallet extensions…</div>
                    <p className="text-gray-500 text-[11px] max-w-[300px]">
                      Make sure your wallet extension (Trust Wallet, MetaMask, etc.) is
                      installed, <b>unlocked</b>, and this site is allowed. It may take a few seconds.
                    </p>
                    {detectElapsed > 6000 && (
                      <p className="text-amber-400/80 text-[10px] mt-2 max-w-[300px]">
                        Still nothing? Open your wallet, unlock it, then click "Connect Wallet" again.
                      </p>
                    )}
                  </div>
                )}

                {/* Manual fallback toggle */}
                <button
                  onClick={() => setManualExpanded(v => !v)}
                  className="w-full mt-3 text-center text-[11px] text-gray-500 hover:text-gray-300 transition-colors"
                >
                  {manualExpanded ? "▲ Hide manual entry" : "Can't connect? Enter address manually ▼"}
                </button>
              </div>

              {/* Manual address input — secondary fallback */}
              {manualExpanded && (
              <div className="px-4 pb-2 pt-1 border-t border-gray-800">
                <p className="text-gray-400 text-[11px] mt-3 mb-3">
                  Read-only: paste your Polygon address to track balance (cannot sign trades).
                </p>
                <input
                  type="text"
                  placeholder="0x... (Polygon wallet address)"
                  value={manualAddr}
                  onChange={e => {
                    setManualAddr(e.target.value);
                    const v = e.target.value.trim();
                    if (v.startsWith("0x") && v.length === 42) previewAddr(v);
                    else setPreviewBalance(null);
                  }}
                  className="w-full bg-gray-800 border border-gray-700 text-white text-sm font-mono px-3 py-2.5 rounded-lg mb-3 focus:outline-none focus:border-purple-500 placeholder:text-gray-600"
                  autoFocus
                />

                {/* Balance preview */}
                {previewLoading && (
                  <div className="bg-gray-800/50 rounded-lg p-3 mb-3 flex items-center gap-2">
                    <div className="w-4 h-4 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
                    <span className="text-gray-400 text-xs">Fetching balance from Polygon…</span>
                  </div>
                )}
                {previewBalance && !previewLoading && (
                  <div className="bg-gray-800 border border-gray-700 rounded-lg p-3 mb-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div className="w-6 h-6 bg-blue-600 rounded-full flex items-center justify-center text-[10px] font-bold text-white">$</div>
                        <div>
                          <div className="text-white text-sm font-bold">USDC</div>
                          <div className="text-[10px] text-gray-500">Polygon</div>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-white text-sm font-bold font-mono">${previewBalance.usdc.toFixed(2)}</div>
                      </div>
                    </div>
                    <div className="flex items-center justify-between mt-2 pt-2 border-t border-gray-700/50">
                      <div className="flex items-center gap-2">
                        <div className="w-6 h-6 bg-purple-600 rounded-full flex items-center justify-center text-[10px] font-bold text-white">M</div>
                        <div>
                          <div className="text-white text-sm font-bold">POL</div>
                          <div className="text-[10px] text-gray-500">Gas token</div>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-white text-sm font-mono">{previewBalance.matic.toFixed(4)}</div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Wallet name selector */}
                <div className="text-[10px] text-gray-500 uppercase font-bold mb-1.5">Wallet type</div>
                <div className="flex flex-wrap gap-1.5 mb-4">
                  {WALLET_PRESETS.map(w => (
                    <button key={w.name} onClick={() => setManualName(w.name)}
                      className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium transition-all ${
                        manualName === w.name
                          ? "bg-purple-700 text-white border border-purple-500"
                          : "bg-gray-800 text-gray-400 border border-gray-700 hover:text-white hover:border-gray-600"
                      }`}>
                      <span>{w.icon}</span> {w.name}
                    </button>
                  ))}
                </div>

                {/* Link button */}
                <button
                  onClick={linkManualAddress}
                  disabled={s.loading || !manualAddr.trim() || manualAddr.trim().length !== 42}
                  className="w-full bg-gradient-to-r from-purple-700 to-purple-600 hover:from-purple-600 hover:to-purple-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-bold py-3 rounded-lg transition-colors mb-3"
                >
                  {s.loading ? "Linking…" : "Link Read-only Address"}
                </button>
              </div>
              )}

              {/* Always-visible footer */}
              <div className="px-4 pb-4 pt-1">
                <button
                  onClick={() => setShowManual(false)}
                  className="w-full bg-gray-800 hover:bg-gray-700 text-gray-400 text-sm py-2 rounded-lg transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}

        {s.error && (
          <div className="absolute top-12 right-4 bg-red-950 border border-red-700 text-red-200 text-xs px-3 py-2 rounded shadow-lg max-w-sm z-50">
            <button onClick={() => setS(prev => ({ ...prev, error: null }))} className="float-right ml-2 text-red-400 hover:text-red-200">x</button>
            {s.error}
          </div>
        )}
      </>
    );
  }

  // ─── Render: wallets connected ───
  return (
    <div className="relative">
      {/* Top bar button */}
      <button
        onClick={() => setS(prev => ({ ...prev, showPanel: !prev.showPanel }))}
        className="flex items-center gap-2 bg-gray-800 hover:bg-gray-700 border border-purple-700/50 text-white text-xs px-2 py-1 rounded transition-colors"
      >
        {activeWallet?.wallet_icon && <img src={activeWallet.wallet_icon} className="w-4 h-4 rounded" alt="" />}
        <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
        {s.linked.length > 1 ? (
          <>
            <span className="font-mono text-purple-300">{s.linked.length} wallets</span>
            <span className="text-green-400 font-bold font-mono">${totalUsdc.toFixed(2)}</span>
          </>
        ) : (
          <>
            <span className="font-mono text-purple-300">{shortAddress(activeWallet?.address || "")}</span>
            <span className="text-green-400 font-bold font-mono">${(activeWallet?.usdc_balance || 0).toFixed(2)}</span>
          </>
        )}
        <span className="text-gray-500">USDC</span>
        {s.linked.length > 1 && (
          <span className="text-[9px] bg-purple-900/70 px-1 rounded">{s.linked.length}</span>
        )}
      </button>

      {/* Panel */}
      {s.showPanel && (
        <div className="absolute top-full right-0 mt-2 bg-gray-900 border border-gray-700 rounded-lg shadow-2xl w-96 z-50 overflow-hidden">
          {/* Header */}
          <div className="bg-gradient-to-r from-purple-900 to-indigo-900 px-4 py-3 border-b border-gray-700 flex items-center justify-between">
            <div>
              <div className="text-white font-bold text-sm">Connected Wallets</div>
              <div className="text-[11px] text-purple-300">
                {s.linked.length} wallet{s.linked.length > 1 ? "s" : ""} · ${totalUsdc.toFixed(2)} USDC total
              </div>
            </div>
            <button
              onClick={() => {
                if (typeof window !== "undefined") {
                  window.dispatchEvent(new Event("eip6963:requestProvider"));
                }
                import("../lib/web3").then(({ listWallets }) => {
                  const fresh = listWallets();
                  setS(prev => ({ ...prev, available: fresh, showPicker: true }));
                });
                setS(prev => ({ ...prev, showPicker: true }));
              }}
              className="text-[11px] bg-purple-700 hover:bg-purple-600 text-white px-2 py-1 rounded font-bold"
            >
              + Add Wallet
            </button>
          </div>

          {/* Wallet list */}
          <div className="max-h-[60vh] overflow-y-auto divide-y divide-gray-800">
            {s.linked.map(w => (
              <WalletRow
                key={w.address}
                wallet={w}
                isActive={w.is_active}
                onSetActive={() => handleSetActive(w.address)}
                onUnlink={() => handleUnlink(w.address)}
                onRefresh={() => handleForceRefresh(w.address)}
              />
            ))}
          </div>

          {/* Footer */}
          <div className="bg-gray-950 border-t border-gray-700 px-4 py-2 text-[10px] text-gray-500">
            Active wallet funds betting · All wallets shown on Polygonscan · Polygon Mainnet
          </div>
        </div>
      )}

      <WalletPicker
        show={s.showPicker}
        available={s.available}
        onSelect={selectAndConnect}
        onClose={() => setS(prev => ({ ...prev, showPicker: false }))}
      />

      {s.error && (
        <div className="absolute top-12 right-4 bg-red-950 border border-red-700 text-red-200 text-xs px-3 py-2 rounded shadow-lg max-w-sm z-50">
          <button onClick={() => setS(prev => ({ ...prev, error: null }))} className="float-right ml-2">×</button>
          {s.error}
        </div>
      )}
    </div>
  );
}

// ─── WalletRow ─────────────────────────────────────────────────────────────────

function WalletRow({
  wallet, isActive, onSetActive, onUnlink, onRefresh,
}: {
  wallet: LinkedWallet;
  isActive: boolean;
  onSetActive: () => void;
  onUnlink: () => void;
  onRefresh: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const isPolygon = !wallet.chainId || wallet.chainId === POLYGON_CHAIN.chainId;
  const syncAge = wallet.last_chain_sync
    ? Math.floor((Date.now() - wallet.last_chain_sync) / 1000)
    : null;

  return (
    <div className={`px-4 py-3 ${isActive ? "bg-purple-950/30" : "hover:bg-gray-800/50"} transition-colors`}>
      <div className="flex items-center gap-3">
        {/* Wallet icon */}
        <div className="relative">
          {wallet.wallet_icon
            ? <img src={wallet.wallet_icon} className="w-8 h-8 rounded" alt="" />
            : <div className="w-8 h-8 rounded bg-gray-700 flex items-center justify-center text-gray-400 text-sm">W</div>
          }
          {isActive && (
            <span className="absolute -top-1 -right-1 w-3 h-3 bg-green-500 rounded-full border border-gray-900" title="Active trading wallet" />
          )}
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-white text-xs font-bold truncate">{wallet.wallet_name || "Wallet"}</span>
            {isActive && <span className="text-[9px] bg-green-800 text-green-300 px-1 rounded">ACTIVE</span>}
            {!isPolygon && <span className="text-[9px] bg-yellow-800 text-yellow-300 px-1 rounded">WRONG CHAIN</span>}
            {wallet.provider && <span className="text-[9px] bg-blue-900 text-blue-300 px-1 rounded">LIVE</span>}
          </div>
          <div className="font-mono text-[11px] text-gray-400">{shortAddress(wallet.address)}</div>
        </div>

        {/* Balance */}
        <div className="text-right shrink-0">
          <div className="font-mono text-sm font-bold text-green-400">${(wallet.usdc_balance || 0).toFixed(2)}</div>
          <div className="text-[9px] text-gray-500">USDC</div>
        </div>

        {/* Expand */}
        <button onClick={() => setExpanded(!expanded)} className="text-gray-500 hover:text-gray-300 ml-1">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
            <path d={expanded ? "M7 14l5-5 5 5z" : "M7 10l5 5 5-5z"} />
          </svg>
        </button>
      </div>

      {expanded && (
        <div className="mt-3 space-y-2">
          {/* Balance detail */}
          <div className="bg-gray-950 rounded p-2.5 text-[11px] border border-gray-800">
            <div className="flex justify-between items-center">
              <div>
                <div className="text-gray-500 mb-0.5">Trading capital</div>
                <div className="font-mono text-lg font-bold text-green-400">${(wallet.usdc_balance || 0).toFixed(2)} USDC</div>
                {syncAge !== null && (
                  <div className="text-[9px] text-gray-600 mt-0.5">
                    RPC sync: {syncAge < 60 ? `${syncAge}s` : `${Math.floor(syncAge / 60)}m`} ago
                    <button onClick={onRefresh} className="ml-1 text-purple-400 hover:text-purple-200">↻</button>
                  </div>
                )}
              </div>
              <div className="text-right">
                <div className="text-gray-500 text-[10px]">Gas (MATIC)</div>
                <div className="font-mono text-blue-400">{(wallet.matic_balance || 0).toFixed(3)}</div>
              </div>
            </div>
            {(wallet.usdc_balance || 0) === 0 && (
              <div className="mt-2 text-amber-300 text-[10px]">
                No USDC detected. Bridge via{" "}
                <a href="https://wallet.polygon.technology/bridge" target="_blank" rel="noopener" className="underline">Polygon bridge</a>
                {" "}or send USDC.e from CEX via Polygon network.
              </div>
            )}
          </div>

          {/* Address */}
          <div className="bg-gray-950 rounded p-2 border border-gray-800 flex items-center gap-2">
            <code className="font-mono text-[10px] text-gray-300 flex-1 break-all">{wallet.address}</code>
            <button
              onClick={() => navigator.clipboard.writeText(wallet.address)}
              className="text-[10px] bg-gray-800 hover:bg-gray-700 text-white px-2 py-1 rounded shrink-0"
            >Copy</button>
          </div>

          {/* Actions */}
          <div className="flex gap-1.5">
            {!isActive && (
              <button
                onClick={onSetActive}
                className="flex-1 text-[11px] bg-purple-700 hover:bg-purple-600 text-white px-2 py-1.5 rounded font-bold"
              >Set Active</button>
            )}
            <a
              href={`https://polygonscan.com/address/${wallet.address}`}
              target="_blank" rel="noopener"
              className="flex-1 text-center text-[11px] bg-gray-800 hover:bg-gray-700 text-white px-2 py-1.5 rounded"
            >Polygonscan ↗</a>
            <button
              onClick={onUnlink}
              className="text-[11px] bg-red-900/40 hover:bg-red-900/60 border border-red-700/50 text-red-300 px-2 py-1.5 rounded"
            >Disconnect</button>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── WalletPicker ──────────────────────────────────────────────────────────────

function WalletPicker({
  show, available, onSelect, onClose,
}: {
  show: boolean;
  available: DetectedWallet[];
  onSelect: (w: DetectedWallet) => void;
  onClose: () => void;
}) {
  if (!show) return null;
  return (
    <div className="fixed inset-0 bg-black/70 z-[60] flex items-center justify-center" onClick={onClose}>
      <div className="bg-gray-900 border border-gray-700 rounded-lg shadow-2xl w-[420px] max-h-[80vh] overflow-hidden" onClick={e => e.stopPropagation()}>
        <div className="bg-gradient-to-r from-purple-900 to-indigo-900 px-4 py-3 border-b border-gray-700 flex justify-between items-center">
          <div>
            <h3 className="text-white font-bold">Connect a wallet</h3>
            <p className="text-[11px] text-purple-300 mt-0.5">
              {available.length} wallet{available.length !== 1 ? "s" : ""} detected · Multiple wallets supported
            </p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-xl px-1">×</button>
        </div>

        <div className="overflow-y-auto max-h-[55vh] p-2 space-y-1">
          {available.length === 0 ? (
            <div className="text-center text-gray-500 text-sm py-8">No wallet extensions detected</div>
          ) : (
            available.map(w => (
              <button
                key={w.info.uuid}
                onClick={() => onSelect(w)}
                className="w-full flex items-center gap-3 bg-gray-800 hover:bg-gray-700 border border-gray-700 hover:border-purple-600 transition-all rounded p-3 text-left"
              >
                <img src={w.info.icon} alt={w.info.name} className="w-9 h-9 rounded" onError={e => (e.target as HTMLImageElement).style.display = "none"} />
                <div className="flex-1">
                  <div className="text-white font-bold text-sm">{w.info.name}</div>
                  <div className="text-[10px] text-gray-500 font-mono">{w.info.rdns}</div>
                </div>
                <span className="text-purple-400 text-xs">Connect →</span>
              </button>
            ))
          )}
        </div>

        <div className="bg-gray-950 border-t border-gray-700 px-4 py-3 text-[11px] text-gray-400">
          <div className="font-semibold text-gray-300 mb-1">Don't see your wallet?</div>
          <div className="flex flex-wrap gap-2 mt-1">
            {[
              ["MetaMask", "https://metamask.io/download"],
              ["Phantom", "https://phantom.app/download"],
              ["Coinbase", "https://www.coinbase.com/wallet"],
              ["Trust", "https://trustwallet.com/download"],
              ["OKX", "https://www.okx.com/web3"],
              ["Rabby", "https://rabby.io"],
            ].map(([name, url]) => (
              <a key={name} href={url} target="_blank" rel="noopener" className="bg-gray-800 hover:bg-gray-700 px-2 py-0.5 rounded text-blue-300">{name}</a>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
