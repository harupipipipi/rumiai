import { Component, type ErrorInfo, type ReactNode } from "react";

import { reportClientDiagnostic } from "../lib/clientDiagnostics";

type Props = {
  children: ReactNode;
};

type State = {
  failed: boolean;
  message: string;
  diagnosticStatus: "idle" | "sending" | "recorded" | "not_recorded";
};

export class AppErrorBoundary extends Component<Props, State> {
  state: State = {
    failed: false,
    message: "",
    diagnosticStatus: "idle",
  };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return {
      failed: true,
      message: error.message || "Unexpected application failure",
    };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    this.setState({ diagnosticStatus: "sending" });
    void reportClientDiagnostic({
      source: "react.error_boundary",
      category: "render_crash",
      level: "error",
      message: error.message || "React renderer crashed",
      detail: {
        name: error.name,
        stack: error.stack,
        componentStack: info.componentStack,
      },
    }).then((recorded) => {
      this.setState({ diagnosticStatus: recorded ? "recorded" : "not_recorded" });
    });
  }

  diagnosticStatusCopy(): string {
    if (this.state.diagnosticStatus === "sending") {
      return "個人情報を除いた診断情報を整理し、backendへの記録を確認しています。";
    }
    if (this.state.diagnosticStatus === "recorded") {
      return "個人情報を除いた診断情報をbackendに記録しました。";
    }
    if (this.state.diagnosticStatus === "not_recorded") {
      return "診断情報はbackendに記録されていません。画面の再読み込みはそのまま実行できます。";
    }
    return "安全な復帰画面を表示しています。診断情報の記録結果を確認します。";
  }

  render() {
    if (!this.state.failed) return this.props.children;

    return (
      <div className="flex min-h-screen items-center justify-center bg-[#09090b] px-6 text-zinc-100">
        <div className="w-full max-w-xl rounded-3xl border border-red-500/20 bg-zinc-950/90 p-8 shadow-2xl">
          <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-red-300">Safe fallback</p>
          <h1 className="mt-3 text-2xl font-semibold tracking-tight">画面は止めずに、着地できる場所へ戻します。</h1>
          <p className="mt-3 text-sm leading-6 text-zinc-300">{this.diagnosticStatusCopy()}</p>
          <div className="mt-4 rounded-2xl border border-zinc-800 bg-black/20 px-4 py-3 text-sm text-zinc-400">
            {this.state.message || "Unexpected application failure"}
          </div>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="mt-6 inline-flex h-11 items-center justify-center rounded-2xl bg-zinc-100 px-5 text-sm font-semibold text-zinc-950 transition hover:bg-white"
          >
            画面を立て直す
          </button>
        </div>
      </div>
    );
  }
}
