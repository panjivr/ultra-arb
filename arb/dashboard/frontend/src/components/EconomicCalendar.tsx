"use client";
import { API_URL, api, ws } from "../lib/api";
import { useEffect, useState } from "react";

interface Event {
  date: string;
  title: string;
  importance: "high" | "medium" | "low";
  description: string;
  days_until: number;
  in_past: boolean;
}

export default function EconomicCalendar() {
  const [events, setEvents] = useState<Event[]>([]);

  useEffect(() => {
    const load = async () => {
      try {
        const r = await fetch(api("/api/bloomberg/calendar?days=120"));
        if (r.ok) setEvents((await r.json()).events || []);
      } catch {}
    };
    load();
    const id = setInterval(load, 3_600_000); // 1h
    return () => clearInterval(id);
  }, []);

  const importanceStyle = (imp: string) => {
    if (imp === "high") return "bg-red-900/40 border-red-700/60 text-red-200";
    if (imp === "medium") return "bg-amber-900/40 border-amber-700/60 text-amber-200";
    return "bg-gray-800/60 border-gray-600/40 text-gray-300";
  };
  const importanceTag = (imp: string) => {
    if (imp === "high") return "bg-red-700 text-white";
    if (imp === "medium") return "bg-amber-700 text-white";
    return "bg-gray-700 text-gray-200";
  };

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 h-full">
      <div className="border-b border-gray-800 px-3 py-2">
        <h2 className="text-white font-bold text-sm flex items-center gap-2">
          <span className="text-amber-400">📅</span> Economic Calendar
        </h2>
        <p className="text-[10px] text-gray-500">FOMC · CPI · NFP · crypto upgrades</p>
      </div>
      <div className="overflow-y-auto max-h-[420px] divide-y divide-gray-800">
        {events.length === 0 && (
          <div className="text-gray-600 text-xs p-4 text-center">Loading calendar…</div>
        )}
        {events.map((e, i) => (
          <div key={i}
            className={`p-2.5 border-l-2 ${importanceStyle(e.importance)}`}>
            <div className="flex justify-between items-start gap-2">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded ${importanceTag(e.importance)}`}>
                    {e.importance}
                  </span>
                  <span className="font-mono text-[10px] text-gray-400">{e.date}</span>
                  {!e.in_past && (
                    <span className="text-[10px] font-bold text-blue-300">
                      {e.days_until === 0 ? "TODAY" : `in ${e.days_until}d`}
                    </span>
                  )}
                  {e.in_past && (
                    <span className="text-[10px] text-gray-500">passed</span>
                  )}
                </div>
                <div className="text-xs font-bold text-white mt-0.5">{e.title}</div>
                <div className="text-[10px] text-gray-400 mt-0.5">{e.description}</div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
