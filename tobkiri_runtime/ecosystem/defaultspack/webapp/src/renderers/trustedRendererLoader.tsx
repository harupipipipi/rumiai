import { Component, Suspense, lazy, type ComponentType, type ReactNode } from "react";

import type { ShellRenderer } from "../lib/api";

const TRUSTED_RENDERER_PREFIXES = [
  "/static/renderers/",
  "/static/assets/renderers/",
] as const;

const quarantinedRendererModules = new Set<string>();

type VerifiedRendererMetadata = {
  verified?: unknown;
  provenance?: {
    source?: unknown;
    content_hash?: unknown;
    build_id?: unknown;
  };
};

export function isTrustedLocalRendererModule(modulePath: string | undefined): modulePath is string {
  if (!modulePath || typeof window === "undefined") return false;
  try {
    const url = new URL(modulePath, window.location.origin);
    if (url.origin !== window.location.origin) return false;
    if (url.username || url.password || url.search || url.hash) return false;
    if (!url.pathname.endsWith(".js") || url.pathname.includes("%")) return false;
    return TRUSTED_RENDERER_PREFIXES.some((prefix) => url.pathname.startsWith(prefix));
  } catch {
    return false;
  }
}

export function hasVerifiedBuiltinRendererProvenance(
  renderer: ShellRenderer | null | undefined,
): boolean {
  if (!renderer) return false;
  const metadata = renderer as ShellRenderer & VerifiedRendererMetadata;
  const provenance = metadata.provenance;
  return metadata.verified === true
    && provenance?.source === "builtin"
    && /^[a-f0-9]{64}$/i.test(String(provenance.content_hash ?? ""))
    && String(provenance.build_id ?? "").trim().length > 0;
}

export function isRendererModuleQuarantined(modulePath: string): boolean {
  return quarantinedRendererModules.has(modulePath);
}

export function resetRendererQuarantineForTests(): void {
  quarantinedRendererModules.clear();
}

export function loadTrustedRenderer<T extends object>(
  renderer: ShellRenderer | null | undefined,
  fallback: ComponentType<T>,
): ComponentType<T> {
  if (
    renderer?.trust !== "local"
    || !hasVerifiedBuiltinRendererProvenance(renderer)
    || !isTrustedLocalRendererModule(renderer.module)
  ) {
    return fallback;
  }

  const modulePath = renderer.module;
  if (quarantinedRendererModules.has(modulePath)) return fallback;
  const exportName = renderer.export || "default";
  const LoadedRenderer = lazy(async () => {
    try {
      const module = await import(/* @vite-ignore */ modulePath) as Record<string, unknown>;
      const loaded = module[exportName];
      if (typeof loaded !== "function") {
        quarantinedRendererModules.add(modulePath);
        return { default: fallback };
      }
      return { default: loaded as ComponentType<T> };
    } catch {
      quarantinedRendererModules.add(modulePath);
      return { default: fallback };
    }
  });

  function VerifiedRendererRegion(props: T) {
    if (quarantinedRendererModules.has(modulePath)) {
      const Fallback = fallback;
      return <Fallback {...props} />;
    }
    const Fallback = fallback;
    const fallbackNode = <Fallback {...props} />;
    return (
      <RendererBoundary
        fallback={fallbackNode}
        onError={() => quarantinedRendererModules.add(modulePath)}
      >
        <LoadedRenderer {...props} />
      </RendererBoundary>
    );
  }

  VerifiedRendererRegion.displayName = `VerifiedRendererRegion(${renderer.id || exportName})`;
  return VerifiedRendererRegion;
}

type RendererErrorBoundaryProps = {
  fallback?: ReactNode;
  onError?: () => void;
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

  componentDidCatch(): void {
    this.props.onError?.();
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
  onError,
}: {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: () => void;
}) {
  return (
    <RendererErrorBoundary fallback={fallback} onError={onError}>
      <Suspense fallback={fallback}>{children}</Suspense>
    </RendererErrorBoundary>
  );
}
