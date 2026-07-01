import { Component, Suspense, lazy, type ComponentType, type ReactNode } from "react";

import type { ShellRenderer } from "../lib/api";

const TRUSTED_RENDERER_PATH = /^\/static\/packs\/([A-Za-z0-9_.-]+)\/(?:renderers|assets\/renderers)\/[^?#]+\.js$/;

function trustedLocalRendererPackId(modulePath: string | undefined): string | null {
  if (!modulePath) return null;
  if (typeof window === "undefined") return null;
  try {
    const url = new URL(modulePath, window.location.origin);
    if (url.origin !== window.location.origin) return null;
    return TRUSTED_RENDERER_PATH.exec(url.pathname)?.[1] ?? null;
  } catch {
    return null;
  }
}

export function isTrustedLocalRendererModule(modulePath: string | undefined): modulePath is string {
  return trustedLocalRendererPackId(modulePath) !== null;
}

function rendererMatchesCatalogBinding(renderer: ShellRenderer): boolean {
  const modulePackId = trustedLocalRendererPackId(renderer.module);
  const sourcePackId = typeof renderer.source_pack_id === "string" ? renderer.source_pack_id : "";
  const declaredModulePackId = typeof renderer.module_pack_id === "string" ? renderer.module_pack_id : "";
  const integrity = typeof renderer.integrity === "string" ? renderer.integrity : "";
  return Boolean(modulePackId)
    && modulePackId === sourcePackId
    && (!declaredModulePackId || declaredModulePackId === modulePackId)
    && integrity.startsWith("sha256-");
}

export function loadTrustedRenderer<T extends object>(
  renderer: ShellRenderer | null | undefined,
  fallback: ComponentType<T>,
): ComponentType<T> {
  if (renderer?.trust !== "local" || !isTrustedLocalRendererModule(renderer.module) || !rendererMatchesCatalogBinding(renderer)) {
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
