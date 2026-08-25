"use client";
import { Component, ReactNode } from "react";

interface Props { children: ReactNode; }
interface State { hasError: boolean; msg: string; }

/**
 * Per-panel error boundary. A single panel that throws during render (e.g. a
 * missing field from a degraded upstream API) is contained to its own tile —
 * the rest of the dashboard keeps working instead of the whole page going
 * blank. Auto-recovers when the failing panel's data next loads cleanly.
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, msg: "" };

  static getDerivedStateFromError(err: unknown): State {
    return { hasError: true, msg: err instanceof Error ? err.message : String(err) };
  }

  componentDidUpdate(prevProps: Props) {
    // Reset when children identity changes so a recovered panel can re-render.
    if (this.state.hasError && prevProps.children !== this.props.children) {
      this.setState({ hasError: false, msg: "" });
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="bg-gray-900 rounded-lg border border-red-900/40 p-3 text-[11px] text-gray-500 h-full flex flex-col items-center justify-center gap-1 min-h-[80px]">
          <span className="text-red-400/80">⚠ panel unavailable</span>
          <span className="text-gray-600 text-[9px] font-mono text-center truncate max-w-full">{this.state.msg}</span>
        </div>
      );
    }
    return this.props.children;
  }
}
