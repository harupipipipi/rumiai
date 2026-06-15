import type { AuthorityUiOperator } from "./api";

type TauriInvoke = <T = unknown>(command: string, args?: Record<string, unknown>) => Promise<T>;

type TauriWindow = Window & {
  __TAURI_INTERNALS__?: unknown;
  __TAURI__?: {
    core?: {
      invoke?: TauriInvoke;
    };
  };
};

export type AuthorityApprovalContext = {
  request_id: string;
  ui_operator: AuthorityUiOperator;
};

function tauriInvoke(): TauriInvoke | null {
  const invoke = (window as TauriWindow).__TAURI__?.core?.invoke;
  return typeof invoke === "function" ? invoke : null;
}

function isLikelyTauri(): boolean {
  const maybeWindow = window as TauriWindow;
  return Boolean(maybeWindow.__TAURI__ || maybeWindow.__TAURI_INTERNALS__);
}

async function loadTauriInvoke(): Promise<TauriInvoke | null> {
  const globalInvoke = tauriInvoke();
  if (globalInvoke) return globalInvoke;
  if (!isLikelyTauri()) return null;
  try {
    const mod = await import("@tauri-apps/api/core");
    return mod.invoke as TauriInvoke;
  } catch {
    return null;
  }
}

export async function openAuthorityApprovalWindow(requestId: string): Promise<boolean> {
  const invoke = await loadTauriInvoke();
  if (!invoke) return false;
  await invoke("open_authority_approval_window", { requestId });
  return true;
}

export async function openAmbientTriggerWindow(): Promise<boolean> {
  const invoke = await loadTauriInvoke();
  if (!invoke) return false;
  await invoke("open_ambient_trigger_window");
  return true;
}

export async function getAuthorityApprovalContext(requestId: string): Promise<AuthorityApprovalContext> {
  const invoke = await loadTauriInvoke();
  if (!invoke) {
    throw new Error("承認コンテキストは Rumi Viewer の専用ウィンドウでのみ利用できます。");
  }
  return invoke<AuthorityApprovalContext>("authority_approval_context", { requestId });
}
