import { Component, Suspense, lazy, type ComponentType, type ReactNode } from "react";

import type { ShellRenderer } from "../lib/api";

const TRUSTED_RENDERER_PREFIXES = [
  "/static/renderers/",
  "/static/assets/renderers/",
  "/static/user_renderers/",
] as const;

export function isTrustedLocalRendererModule(modulePath: string | undefined): modulePath is string {
  if (!modulePath) return false;
  try {
    const url = new URL(modulePath, window.location.origin);
    return url.origin === window.location.origin
      && TRUSTED_RENDERER_PREFIXES.some((prefix) => url.pathname.startsWith(prefix));
  } catch {
    return false;
  }
}

export function loadTrustedRenderer<T extends object>(
  renderer: ShellRenderer | null | undefined,
  fallback: ComponentType<T>,
): ComponentType<T> {
  if (renderer?.trust !== "local" || !isTrustedLocalRendererModule(renderer.module)) {
    return fallback;
  }

  const exportName = renderer.export || "default";
  return lazy(async () => {
    const module = await import(/* @vite-ignore */ renderer.module as string) as Record<string, unknown>;
    const loaded = module[exportName];
    return { default: typeof loaded === "function" ? loaded as ComponentType<T> : fallback };
  });
}

type RendererErrorBoundaryProps = {
  fallback?: ReactNode;
  children: ReactNode;
};

type RendererErrorBoundaryState = {
  failed: boolean;
};

export class RendererErrorBoundary extends Component<RendererErrorBoundaryProps, RendererErrorBoundaryState> {
  state: RendererErrorBoundaryState = { failed: false };

  static getDerivedStateFromError(): RendererErrorBoundaryState {
    return { failed: true };
  }

  render() {
    if (this.state.failed) {
      return this.props.fallback ?? null;
    }
    return this.props.children;
  }
}

export function RendererBoundary({
  children,
  fallback = null,
}: {
  children: ReactNode;
  fallback?: ReactNode;
}) {
  return (
    <RendererErrorBoundary fallback={fallback}>
      <Suspense fallback={fallback}>{children}</Suspense>
    </RendererErrorBoundary>
  );
}
