import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface Props {
  children: ReactNode;
  title?: string;
  resetKey?: string;
}

interface State {
  hasError: boolean;
  message: string;
}

export class PageErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: "" };

  static getDerivedStateFromError(error: unknown): State {
    return {
      hasError: true,
      message: error instanceof Error ? error.message : "Bilinmeyen bir hata oluştu.",
    };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    if (import.meta.env.DEV) {
      console.error("[HYDRO] sayfa hatası", error, info.componentStack);
    }
  }

  componentDidUpdate(previous: Props): void {
    if (this.state.hasError && previous.resetKey !== this.props.resetKey) {
      this.setState({ hasError: false, message: "" });
    }
  }

  render(): ReactNode {
    if (!this.state.hasError) return this.props.children;
    return (
      <div className="panel border-[var(--danger-border)] p-5">
        <div className="flex items-start gap-3">
          <AlertTriangle size={18} className="mt-0.5 shrink-0 text-[var(--danger)]" aria-hidden />
          <div>
            <p className="text-[14px] font-semibold text-[var(--danger)]">
              {this.props.title ?? "Bu bölüm yüklenemedi"}
            </p>
            <p className="mt-1 max-w-[60ch] text-[11.5px] leading-relaxed text-[var(--text-muted)]">
              {this.state.message} Form verileri korunuyor. Diğer sekmeler çalışmaya devam eder.
            </p>
            <button
              type="button"
              className="btn btn-sm mt-3"
              onClick={() => this.setState({ hasError: false, message: "" })}
            >
              <RefreshCw size={12} aria-hidden /> Tekrar dene
            </button>
          </div>
        </div>
      </div>
    );
  }
}
