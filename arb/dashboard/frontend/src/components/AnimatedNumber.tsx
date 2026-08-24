"use client";
import { useEffect, useRef, useState } from "react";

/**
 * Smoothly animates a number from its previous value to the new one whenever
 * `value` changes (easeOutCubic, ~700ms). Makes polled stats glide instead of
 * jumping, so the terminal feels live without fabricating any movement — it only
 * ever animates toward the real value.
 */
export default function AnimatedNumber({
  value, format, className = "", duration = 700,
}: {
  value: number;
  format?: (n: number) => string;
  className?: string;
  duration?: number;
}) {
  const [display, setDisplay] = useState(value);
  const fromRef = useRef(value);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const from = fromRef.current;
    const to = Number.isFinite(value) ? value : 0;
    if (from === to) { setDisplay(to); return; }
    const start = performance.now();
    const step = (now: number) => {
      const t = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplay(from + (to - from) * eased);
      if (t < 1) {
        rafRef.current = requestAnimationFrame(step);
      } else {
        fromRef.current = to;
      }
    };
    rafRef.current = requestAnimationFrame(step);
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  }, [value, duration]);

  const fmt = format || ((n: number) => n.toFixed(2));
  return <span className={className}>{fmt(display)}</span>;
}
