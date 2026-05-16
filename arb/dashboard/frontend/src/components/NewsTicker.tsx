"use client";
import { API_URL, api, ws } from "../lib/api";
import { useEffect, useState } from "react";

interface NewsItem {
  title: string;
  source: string;
  url: string;
  published_at: string;
  currencies: string[];
  kind: string;
  votes: { positive: number; negative: number; important: number };
}

export default function NewsTicker() {
  const [items, setItems] = useState<NewsItem[]>([]);
  const [filter, setFilter] = useState<"all" | "important">("all");

  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(api("/api/bloomberg/news"));
        if (r.ok) {
          const j = await r.json();
          setItems(j.items || []);
        }
      } catch {}
    };
    load();
    const id = setInterval(load, 60_000); // 1 min
    return () => clearInterval(id);
  }, []);

  const filtered = filter === "important"
    ? items.filter(i => i.votes.important > 0 || /fed|fomc|cpi|inflat|rate|sec|etf/i.test(i.title))
    : items;

  const fmtAgo = (iso: string) => {
    if (!iso) return "";
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    const mins = Math.floor((Date.now() - d.getTime()) / 60_000);
    if (mins < 1) return "now";
    if (mins < 60) return `${mins}m`;
    if (mins < 1440) return `${Math.floor(mins/60)}h`;
    return `${Math.floor(mins/1440)}d`;
  };

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 h-full flex flex-col">
      <div className="border-b border-gray-800 px-3 py-2 flex justify-between items-center">
        <div>
          <h2 className="text-white font-bold text-sm flex items-center gap-2">
            <span className="text-orange-400">⚡</span> Market News
          </h2>
          <p className="text-[10px] text-gray-500">crypto + macro headlines</p>
        </div>
        <div className="flex gap-1">
          {(["all", "important"] as const).map(f => (
            <button key={f} onClick={() => setFilter(f)}
              className={`px-2 py-0.5 text-[10px] rounded uppercase ${
                filter === f ? "bg-orange-700 text-white" : "bg-gray-800 text-gray-400 hover:text-white"
              }`}>
              {f}
            </button>
          ))}
        </div>
      </div>
      <div className="overflow-y-auto flex-1 divide-y divide-gray-800 max-h-[420px]">
        {filtered.length === 0 && (
          <div className="text-gray-600 text-xs p-4 text-center">Loading news…</div>
        )}
        {filtered.slice(0, 20).map((n, i) => {
          const isImportant = n.votes.important > 0 || /fed|fomc|cpi|inflat|rate|sec|etf/i.test(n.title);
          return (
            <a key={i} href={n.url} target="_blank" rel="noopener noreferrer"
              className="block p-2 hover:bg-gray-800/50 transition-colors">
              <div className="flex items-start gap-2">
                {isImportant && (
                  <span className="text-[9px] bg-red-900/60 text-red-300 px-1 py-0.5 rounded font-bold whitespace-nowrap mt-0.5">
                    HIGH
                  </span>
                )}
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-white line-clamp-2 leading-snug">{n.title}</p>
                  <div className="flex items-center gap-2 mt-1 text-[9px] text-gray-500">
                    <span className="text-blue-400">{n.source}</span>
                    <span>·</span>
                    <span>{fmtAgo(n.published_at)} ago</span>
                    {n.currencies.slice(0, 3).map(c => (
                      <span key={c} className="bg-gray-800 text-orange-300 px-1 rounded">{c}</span>
                    ))}
                    {n.votes.positive > 0 && (
                      <span className="text-green-500">▲{n.votes.positive}</span>
                    )}
                    {n.votes.negative > 0 && (
                      <span className="text-red-500">▼{n.votes.negative}</span>
                    )}
                  </div>
                </div>
              </div>
            </a>
          );
        })}
      </div>
    </div>
  );
}
