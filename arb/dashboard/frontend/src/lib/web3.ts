/**
 * Multi-wallet Web3 helpers — EIP-6963 discovery + legacy fallback.
 *
 * Supports any EVM-compatible wallet: MetaMask, Phantom (EVM mode), Coinbase Wallet,
 * Trust Wallet, OKX, Rabby, Brave, Frame, Tally, Zerion, Rainbow extension, etc.
 *
 * Strategy:
 *   1. Listen for EIP-6963 announceProvider events (modern wallets)
 *   2. Probe common window.* injections (legacy + Phantom EVM)
 *   3. Show picker UI; user chooses which wallet to use
 *   4. Each provider implements EIP-1193 (.request(method, params)) — so the rest of the code is identical
 */

// Polygon mainnet config
export const POLYGON_CHAIN = {
  chainId: "0x89", // 137
  chainName: "Polygon Mainnet",
  nativeCurrency: { name: "MATIC", symbol: "MATIC", decimals: 18 },
  rpcUrls: ["https://polygon-rpc.com", "https://rpc.ankr.com/polygon"],
  blockExplorerUrls: ["https://polygonscan.com"],
};

export const USDC_E_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"; // bridged USDC.e
export const USDC_NATIVE_ADDRESS = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"; // native USDC

const ERC20_BALANCE_OF = "0x70a08231"; // balanceOf(address) selector

// ───────── Provider types ─────────
export interface EIP1193Provider {
  request: (args: { method: string; params?: any[] }) => Promise<any>;
  on?: (event: string, handler: (...args: any[]) => void) => void;
  removeListener?: (event: string, handler: (...args: any[]) => void) => void;
}

export interface EIP6963ProviderInfo {
  uuid: string;
  name: string;
  icon: string;       // base64 or http URL
  rdns: string;       // reverse-DNS identifier (e.g. io.metamask)
}

export interface DetectedWallet {
  info: EIP6963ProviderInfo;
  provider: EIP1193Provider;
}

declare global {
  interface Window {
    ethereum?: any;
    phantom?: any;
    okxwallet?: any;
    trustwallet?: any;
    coinbaseWalletExtension?: any;
    BinanceChain?: any;
  }
}

// ───────── EIP-6963 discovery ─────────
const _discovered = new Map<string, DetectedWallet>();
const _listeners = new Set<(wallets: DetectedWallet[]) => void>();

function _mergeProviders() {
  // Also merge legacy providers into _discovered so everything is in one place
  const legacy = probeLegacyProviders();
  for (const w of legacy) {
    if (!_discovered.has(w.info.uuid)) {
      // Check no duplicate rdns
      const existing = Array.from(_discovered.values());
      if (!existing.some(e => e.info.rdns === w.info.rdns)) {
        _discovered.set(w.info.uuid, w);
      }
    }
  }
}

function notifyListeners() {
  _mergeProviders();
  const list = Array.from(_discovered.values());
  _listeners.forEach((cb) => cb(list));
}

if (typeof window !== "undefined") {
  window.addEventListener("eip6963:announceProvider" as any, (event: any) => {
    const detail = event.detail;
    if (!detail || !detail.info || !detail.provider) return;
    _discovered.set(detail.info.uuid, { info: detail.info, provider: detail.provider });
    notifyListeners();
  });

  // Kick off discovery immediately
  window.dispatchEvent(new Event("eip6963:requestProvider"));

  // Also probe after DOM and window load (extensions inject at different times)
  const _tryDetect = () => {
    _mergeProviders();
    if (_discovered.size > 0) notifyListeners();
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _tryDetect);
  }
  window.addEventListener("load", _tryDetect);

  // Aggressive polling: check every 500ms for 15 seconds (covers slow HTTP injection)
  let _pollCount = 0;
  const _pollTimer = setInterval(() => {
    _pollCount++;
    window.dispatchEvent(new Event("eip6963:requestProvider"));
    _mergeProviders();
    if (_discovered.size > 0) notifyListeners();
    if (_pollCount >= 30) clearInterval(_pollTimer); // stop after 15s
  }, 500);
}

// Probe legacy / non-EIP-6963 wallets that inject under specific window keys
function probeLegacyProviders(): DetectedWallet[] {
  if (typeof window === "undefined") return [];
  const out: DetectedWallet[] = [];

  // Phantom (EVM mode) — distinct from window.ethereum
  if (window.phantom?.ethereum) {
    out.push({
      info: { uuid: "legacy-phantom", name: "Phantom", rdns: "app.phantom", icon: PHANTOM_ICON },
      provider: window.phantom.ethereum,
    });
  }
  // OKX Wallet
  if (window.okxwallet) {
    out.push({
      info: { uuid: "legacy-okx", name: "OKX Wallet", rdns: "com.okex.wallet", icon: OKX_ICON },
      provider: window.okxwallet,
    });
  }
  // Trust Wallet (extension) — check multiple injection points
  if (window.trustwallet) {
    out.push({
      info: { uuid: "legacy-trust", name: "Trust Wallet", rdns: "com.trustwallet.app", icon: TRUST_ICON },
      provider: window.trustwallet,
    });
  } else if ((window.ethereum as any)?.isTrust || (window.ethereum as any)?.isTrustWallet) {
    out.push({
      info: { uuid: "legacy-trust", name: "Trust Wallet", rdns: "com.trustwallet.app", icon: TRUST_ICON },
      provider: window.ethereum!,
    });
  }
  // Coinbase Wallet extension
  if (window.coinbaseWalletExtension) {
    out.push({
      info: { uuid: "legacy-coinbase", name: "Coinbase Wallet", rdns: "com.coinbase.wallet", icon: COINBASE_ICON },
      provider: window.coinbaseWalletExtension,
    });
  } else if ((window.ethereum as any)?.isCoinbaseWallet) {
    out.push({
      info: { uuid: "legacy-coinbase", name: "Coinbase Wallet", rdns: "com.coinbase.wallet", icon: COINBASE_ICON },
      provider: window.ethereum!,
    });
  }
  // Binance Chain Wallet
  if (window.BinanceChain) {
    out.push({
      info: { uuid: "legacy-binance", name: "Binance Wallet", rdns: "com.binance.wallet", icon: BINANCE_ICON },
      provider: window.BinanceChain,
    });
  }

  // window.ethereum.providers array — MetaMask + others co-existing
  if (window.ethereum?.providers && Array.isArray(window.ethereum.providers)) {
    for (const p of window.ethereum.providers) {
      if (p.isMetaMask && !out.some(w => w.info.rdns === "io.metamask")) {
        out.push({ info: { uuid: "legacy-metamask-arr", name: "MetaMask", rdns: "io.metamask", icon: METAMASK_ICON }, provider: p });
      }
      if (p.isPhantom && !out.some(w => w.info.rdns === "app.phantom")) {
        out.push({ info: { uuid: "legacy-phantom-arr", name: "Phantom", rdns: "app.phantom", icon: PHANTOM_ICON }, provider: p });
      }
      if (p.isCoinbaseWallet && !out.some(w => w.info.rdns === "com.coinbase.wallet")) {
        out.push({ info: { uuid: "legacy-coinbase-arr", name: "Coinbase Wallet", rdns: "com.coinbase.wallet", icon: COINBASE_ICON }, provider: p });
      }
    }
  }

  // Generic window.ethereum — always check as fallback
  if (window.ethereum && !out.some(w => w.provider === window.ethereum)) {
    let name = "Browser Wallet";
    let rdns = "generic.ethereum";
    let icon = GENERIC_ICON;
    if (window.ethereum.isMetaMask) { name = "MetaMask"; rdns = "io.metamask"; icon = METAMASK_ICON; }
    else if (window.ethereum.isRabby) { name = "Rabby"; rdns = "io.rabby"; icon = RABBY_ICON; }
    else if (window.ethereum.isBraveWallet) { name = "Brave Wallet"; rdns = "com.brave.wallet"; icon = BRAVE_ICON; }
    else if (window.ethereum.isFrame) { name = "Frame"; rdns = "sh.frame"; icon = GENERIC_ICON; }
    // Don't add if we already have this rdns
    if (!out.some(w => w.info.rdns === rdns)) {
      out.push({
        info: { uuid: "legacy-ethereum", name, rdns, icon },
        provider: window.ethereum,
      });
    }
  }
  return out;
}

export function listWallets(): DetectedWallet[] {
  const eip6963 = Array.from(_discovered.values());
  const legacy = probeLegacyProviders();
  // De-dup by rdns
  const seen = new Set(eip6963.map(w => w.info.rdns));
  return [...eip6963, ...legacy.filter(w => !seen.has(w.info.rdns))];
}

export function subscribeWallets(cb: (wallets: DetectedWallet[]) => void): () => void {
  _listeners.add(cb);
  // Re-trigger discovery
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event("eip6963:requestProvider"));
    _mergeProviders();
  }
  // Immediate callback with current state
  cb(Array.from(_discovered.values()));
  return () => _listeners.delete(cb);
}

// ───────── Operations (provider-agnostic) ─────────
export async function connect(provider: EIP1193Provider): Promise<string> {
  const accounts: string[] = await provider.request({ method: "eth_requestAccounts" });
  if (!accounts?.length) throw new Error("No account selected");
  return accounts[0];
}

export async function currentChainId(provider: EIP1193Provider): Promise<string> {
  return provider.request({ method: "eth_chainId" });
}

export async function switchToPolygon(provider: EIP1193Provider): Promise<void> {
  try {
    await provider.request({
      method: "wallet_switchEthereumChain",
      params: [{ chainId: POLYGON_CHAIN.chainId }],
    });
  } catch (err: any) {
    if (err.code === 4902 || /unrecognized chain/i.test(err.message || "")) {
      await provider.request({
        method: "wallet_addEthereumChain",
        params: [POLYGON_CHAIN],
      });
    } else {
      throw err;
    }
  }
}

function toHex(addr: string): string {
  return addr.toLowerCase().replace(/^0x/, "").padStart(64, "0");
}

export async function getMaticBalance(provider: EIP1193Provider, address: string): Promise<number> {
  const wei: string = await provider.request({
    method: "eth_getBalance",
    params: [address, "latest"],
  });
  return parseInt(wei, 16) / 1e18;
}

export async function getUsdcBalance(
  provider: EIP1193Provider,
  address: string,
  contract = USDC_E_ADDRESS
): Promise<number> {
  const data = ERC20_BALANCE_OF + toHex(address);
  try {
    const raw: string = await provider.request({
      method: "eth_call",
      params: [{ to: contract, data }, "latest"],
    });
    return parseInt(raw, 16) / 1e6; // USDC = 6 decimals
  } catch {
    return 0;
  }
}

export async function signMessage(
  provider: EIP1193Provider,
  address: string,
  message: string
): Promise<string> {
  return provider.request({
    method: "personal_sign",
    params: [message, address],
  });
}

export function shortAddress(addr: string): string {
  if (!addr) return "";
  return `${addr.slice(0, 6)}…${addr.slice(-4)}`;
}

// ───────── Inline SVG icons (data URI) for known wallets ─────────
const METAMASK_ICON =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 40 40'><path fill='#E2761B' d='M36.5 3.5L22 14.2l2.7-6.3z'/><path fill='#E4761B' d='M3.5 3.5l14.4 10.8L15.3 7.9zM31 27.5l-3.9 5.9 8.3 2.3 2.4-8.1zM2.2 27.6l2.4 8.1 8.3-2.3-3.9-5.9z'/><path fill='#E4761B' d='M12.4 17.9l-2.3 3.5 8.2.4-.3-8.8zM27.6 17.9l-5.7-5 -.2 8.9 8.2-.4zM12.9 33.4l5-2.4-4.3-3.4zM22 31l5.1 2.4-.8-5.8z'/><path fill='#D7C1B3' d='M27.1 33.4l-5.1-2.4.4 3.4-.1 1.4zM12.9 33.4l4.9 2.4-.1-1.4.4-3.4z'/><path fill='#233447' d='M17.9 25.6l-4.1-1.2 2.9-1.3zM22 25.6l1.2-2.5 3 1.3z'/><path fill='#CD6116' d='M12.9 33.4l.9-5.9-4.7.1zM26.2 27.5l.9 5.9 3.8-5.8zM30 21.4l-8.2.4.8 4.2 1.2-2.5 3 1.3zM13.8 24.8l3-1.3 1.2 2.5.8-4.2-8.2-.4z'/><path fill='#E4751F' d='M10 21.4l3.5 6.8-.1-3.4zM26.6 24.8l-.1 3.4 3.5-6.8zM18.2 21.8l-.8 4.2 1 5 .2-6.5zM21.8 21.8l-.4 2.7.2 6.5 1-5z'/><path fill='#F6851B' d='M22.8 26l-1-5-.4 2.7v6.5l-3.4-.7-2-1.4 1.1-1 -.8-4.2-.4-.3 5.4.8 -.5 1.5z'/><path fill='#C0AD9E' d='M22.8 26l-3.4-.7-2-1.4 -.8 1.5 5.4.8z'/><path fill='#161616' d='M13 35.8l5.4-1.6 -.1-1.4 -.7-.6h-3.7l-1 5z'/><path fill='#763D16' d='M27 35.8l-1-3.5h-3.7l-.7.6-.1 1.4z'/></svg>`
  );

const PHANTOM_ICON =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 128 128'><circle cx='64' cy='64' r='64' fill='#AB9FF2'/><path fill='#fff' d='M110 64.8c0 25.4-22.8 45.7-46.1 45.7-19.3 0-31.3-13-37-29.8-2.5-7.3 4.5-12.3 9.8-7.6 5.7 5 13 8.1 17.1 8.1 5.3 0 6.4-4 8.4-9.4 2.5-6.5 6.6-15 16-15 9.5 0 13.6 8.5 16 15 2 5.4 3.2 9.4 8.4 9.4 4.2 0 11.5-3.1 17.2-8.1 5.3-4.7 12.3.3 9.8 7.6 -5.7 16.8-17.7 29.8-37 29.8 -23.3 0-46.1-20.3-46.1-45.7C46.5 38 70 17 95.6 17S110 38.7 110 64.8'/><circle cx='53' cy='53' r='4' fill='#000'/><circle cx='80' cy='53' r='4' fill='#000'/></svg>`
  );

const COINBASE_ICON =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><circle cx='16' cy='16' r='16' fill='#0052FF'/><path fill='#fff' d='M16 22a6 6 0 110-12 6 6 0 010 12zm-3-7v2h6v-2h-6z'/></svg>`
  );

const TRUST_ICON =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='6' fill='#3375BB'/><path fill='#fff' d='M16 5l8 3v8c0 5-4 9-8 11-4-2-8-6-8-11V8z'/></svg>`
  );

const OKX_ICON =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='6' fill='#000'/><path fill='#fff' d='M6 6h7v7H6zm13 0h7v7h-7zM6 19h7v7H6zm13 0h7v7h-7zM13 13h6v6h-6z'/></svg>`
  );

const BINANCE_ICON =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><circle cx='16' cy='16' r='16' fill='#F3BA2F'/><path fill='#fff' d='M9 16l3-3 4 4 4-4 3 3-7 7zm0 0l7-7 7 7-3 3-4-4-4 4z'/></svg>`
  );

const RABBY_ICON =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><circle cx='16' cy='16' r='16' fill='#7084FF'/><path fill='#fff' d='M10 18c0-3 3-6 6-6s6 3 6 6c-1 2-3 4-6 4s-5-2-6-4z'/><circle cx='13' cy='17' r='1.5' fill='#7084FF'/><circle cx='19' cy='17' r='1.5' fill='#7084FF'/></svg>`
  );

const BRAVE_ICON =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='6' fill='#FB542B'/><path fill='#fff' d='M16 4l4 4-4 2-4-2zm-8 8l4 16 4-4 4 4 4-16-4-2-4 2z'/></svg>`
  );

const GENERIC_ICON =
  "data:image/svg+xml;utf8," +
  encodeURIComponent(
    `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='6' fill='#6366F1'/><path fill='#fff' d='M22 11h-12c-1 0-2 1-2 2v10c0 1 1 2 2 2h12c1 0 2-1 2-2v-3h-7c-1 0-2-1-2-2v-2c0-1 1-2 2-2h7v-1c0-1-1-2-2-2zm-5 7h6v2h-6z'/></svg>`
  );
