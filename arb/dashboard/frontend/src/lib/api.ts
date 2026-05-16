/**
 * Centralized API endpoint configuration.
 *
 * Reads NEXT_PUBLIC_API_URL at build time (Vercel/Docker) or runtime (browser).
 * Defaults to localhost:8000 for development.
 *
 * Set in .env.local or .env.production:
 *   NEXT_PUBLIC_API_URL=https://api.reyog.capital
 *   NEXT_PUBLIC_WS_URL=wss://api.reyog.capital
 */

const isBrowser = typeof window !== "undefined";

function detectDefaultApi(): string {
  if (!isBrowser) return "http://localhost:8000";
  // Same-origin default — works behind nginx reverse-proxy
  const proto = window.location.protocol;
  const host = window.location.hostname;
  // If running on localhost:3000 dev → backend on :8000
  if (host === "localhost" || host === "127.0.0.1") {
    return "http://localhost:8000";
  }
  // Production: same origin (nginx routes /api to backend)
  return `${proto}//${host}`;
}

function detectDefaultWs(): string {
  if (!isBrowser) return "ws://localhost:8000";
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = window.location.hostname;
  if (host === "localhost" || host === "127.0.0.1") {
    return "ws://localhost:8000";
  }
  return `${proto}//${host}`;
}

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  (isBrowser ? detectDefaultApi() : "http://localhost:8000");

export const WS_URL =
  process.env.NEXT_PUBLIC_WS_URL ||
  (isBrowser ? detectDefaultWs() : "ws://localhost:8000");

export function api(path: string): string {
  return `${API_URL}${path.startsWith("/") ? path : "/" + path}`;
}

export function ws(path: string): string {
  return `${WS_URL}${path.startsWith("/") ? path : "/" + path}`;
}
