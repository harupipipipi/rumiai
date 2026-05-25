export type DesktopPermissionStatus = {
  id: string;
  label: string;
  status: "granted" | "missing" | "not_checked" | "unsupported" | string;
  granted: boolean | null;
  detail: string;
  settings_hint: string;
};

export type DesktopSystemInfo = {
  app_name: string;
  display_version: string;
  viewer_version: string;
  build_channel: string;
  platform: string;
  platform_release: string;
  permissions: DesktopPermissionStatus[];
};

type TauriInvoke = <T>(command: string, args?: Record<string, unknown>) => Promise<T>;

function getTauriInvoke(): TauriInvoke | null {
  const maybeWindow = window as Window & {
    __TAURI__?: {
      core?: {
        invoke?: TauriInvoke;
      };
    };
  };
  const invoke = maybeWindow.__TAURI__?.core?.invoke;
  return typeof invoke === "function" ? invoke : null;
}

export function isDesktopSystemInfoAvailable(): boolean {
  return getTauriInvoke() !== null;
}

export async function fetchDesktopSystemInfo(): Promise<DesktopSystemInfo | null> {
  const invoke = getTauriInvoke();
  if (!invoke) return null;
  return invoke<DesktopSystemInfo>("get_desktop_system_info");
}
