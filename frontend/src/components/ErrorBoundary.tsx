import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";

interface State {
  error: Error | null;
}

/** Keeps the shell (sidebar, banner, top bar) alive if one region throws. */
export class ErrorBoundary extends Component<{ children: ReactNode; resetKey?: unknown }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("UI error", error, info.componentStack);
  }

  componentDidUpdate(prev: { resetKey?: unknown }) {
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" className="rounded-card border border-bad/20 bg-bad-50 p-5 text-bad">
        <div className="flex items-center gap-2 font-semibold">
          <AlertTriangle className="h-4 w-4" aria-hidden /> Something went wrong on this page
        </div>
        <p className="mt-1 text-[13px] text-ink/80">{this.state.error.message}</p>
        <button
          className="mt-3 rounded-ctl border border-bad/30 bg-surface px-3 py-1.5 text-[13px] font-medium text-bad hover:bg-bad-50"
          onClick={() => this.setState({ error: null })}
        >
          Try again
        </button>
      </div>
    );
  }
}
