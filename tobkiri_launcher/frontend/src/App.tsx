import { useDeferredValue, useEffect, useLayoutEffect, useState, type ReactNode } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Link, useLocation } from 'react-router';
import {
  cancelPackMutationReconciliation,
  useAppStore,
} from '@/src/store';
import type {RuntimeStatus} from '@/src/lib/apiTypes';
import { Layout } from '@/src/components/layout/Layout';
import { Setup } from '@/src/pages/Setup';
import { Dashboard } from '@/src/pages/Dashboard';
import { ToastContainer } from '@/src/components/ui/ToastContainer';
import { DialogContainer } from '@/src/components/ui/DialogContainer';
import { bootstrapPanelSession, hasPendingPanelBootstrapCode } from '@/src/lib/api';
import { applyAppearanceToRoot } from '@/src/lib/appearance';
import { runtimeMonitorDelay } from '@/src/lib/runtimeHealth';
import { panelRoutes } from '@/src/lib/routes';
import {
  resolveSetupVerificationState,
  type SetupVerificationState,
} from '@/src/lib/setupVerification';
import { RouteAnnouncer } from '@/src/components/layout/RouteAnnouncer';
import {
  LazyAiInput,
  LazyApiMap,
  LazyFlow,
  LazyGraph,
  LazyPackDetail,
  LazyPacks,
  LazyNodeManager,
  LazyProfile,
  LazyProfileFiles,
  LazyProfileWiring,
  LazySettings,
} from '@/src/lib/routeModules';

export default function App() {
  const theme = useAppStore(state => state.theme);
  const colorMode = useAppStore(state => state.colorMode);
  const isSetupDone = useAppStore(state => state.isSetupDone);
  const runtimeReady = useAppStore(state => state.runtimeReady);
  const runtimeStatus = useAppStore(state => state.runtimeStatus);
  const runtimeDisconnected = useAppStore(state => state.runtimeDisconnected);
  const addToast = useAppStore(state => state.addToast);
  const refreshRuntimeHealth = useAppStore(state => state.refreshRuntimeHealth);

  useLayoutEffect(() => {
    applyAppearanceToRoot(document.documentElement, { theme, colorMode });
  }, [theme, colorMode]);

  useEffect(() => () => {
    cancelPackMutationReconciliation();
  }, []);

  useEffect(() => {
    if (!hasPendingPanelBootstrapCode()) {
      return;
    }

    void bootstrapPanelSession().catch((error) => {
      const message = error instanceof Error ? error.message : 'Panel bootstrap failed';
      addToast(message, 'error');
    });
  }, [addToast]);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    const pollRuntimeHealth = async () => {
      while (!cancelled) {
        await refreshRuntimeHealth();
        if (cancelled) {
          return;
        }
        const currentState = useAppStore.getState();
        await new Promise<void>((resolve) => {
          timer = window.setTimeout(resolve, runtimeMonitorDelay({
            runtimeReady: currentState.runtimeReady,
            runtimeStatus: currentState.runtimeStatus,
            runtimeError: currentState.runtimeError,
            runtimeDisconnected: currentState.runtimeDisconnected,
            lastRuntimeHealthyAt: currentState.lastRuntimeHealthyAt,
          }));
        });
      }
    };

    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible') {
        void refreshRuntimeHealth();
      }
    };

    window.addEventListener('focus', refreshWhenVisible);
    window.addEventListener('online', refreshWhenVisible);
    document.addEventListener('visibilitychange', refreshWhenVisible);
    void pollRuntimeHealth();

    return () => {
      cancelled = true;
      if (timer !== undefined) {
        window.clearTimeout(timer);
      }
      window.removeEventListener('focus', refreshWhenVisible);
      window.removeEventListener('online', refreshWhenVisible);
      document.removeEventListener('visibilitychange', refreshWhenVisible);
    };
  }, [refreshRuntimeHealth]);

  return (
    <BrowserRouter basename="/panel">
      <DeferredRouteTree
        isSetupDone={isSetupDone}
        runtimeReady={runtimeReady}
        runtimeStatus={runtimeStatus}
        runtimeDisconnected={runtimeDisconnected}
        onRetryRuntimeHealth={refreshRuntimeHealth}
      />
      <ToastContainer />
      <DialogContainer />
    </BrowserRouter>
  );
}

export interface SetupVerificationGateProps {
  children: ReactNode;
  isSetupDone: boolean;
  runtimeReady: boolean;
  runtimeStatus: RuntimeStatus;
  runtimeDisconnected: boolean;
  onRetry?: () => void | Promise<void>;
}

type SetupVerificationCopy = {
  role: 'status' | 'alert';
  title: string;
  detail: string;
};

const setupVerificationCopy: Record<SetupVerificationState, SetupVerificationCopy> = {
  checking: {
    role: 'status',
    title: 'Verifying Tobkiri setup',
    detail: 'The local runtime is still being verified. Pages and runtime actions will appear after the current Profile and authority state are confirmed.',
  },
  verified: {
    role: 'status',
    title: 'Tobkiri setup verified',
    detail: 'The local runtime is ready.',
  },
  needs_setup: {
    role: 'alert',
    title: 'Complete setup to continue',
    detail: 'Open Setup to review the Host-owned activation state before using runtime pages.',
  },
  needs_reconfirm: {
    role: 'alert',
    title: 'Review setup before continuing',
    detail: 'The active Profile needs a fresh Host verification before runtime pages and actions can resume.',
  },
  denied: {
    role: 'alert',
    title: 'Setup verification is unavailable',
    detail: 'Tobkiri could not confirm the local runtime. Retry verification or open Setup to recover safely.',
  },
};

/**
 * Keep every runtime route behind the same health and authority decision.
 * Setup remains reachable because it is the recovery surface for unresolved
 * or stale runtime state.
 */
export function SetupVerificationGate({
  children,
  isSetupDone,
  runtimeReady,
  runtimeStatus,
  runtimeDisconnected,
  onRetry,
}: SetupVerificationGateProps) {
  const state = resolveSetupVerificationState({
    isSetupDone,
    runtimeReady,
    runtimeStatus,
    runtimeDisconnected,
  });
  const [retrying, setRetrying] = useState(false);

  if (state === 'verified') return <>{children}</>;

  const copy = setupVerificationCopy[state];
  const retry = () => {
    if (!onRetry || retrying) return;
    setRetrying(true);
    void Promise.resolve()
      .then(onRetry)
      .finally(() => setRetrying(false));
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-bg-main px-6 py-10 text-text-main">
      <section
        aria-busy={state === 'checking'}
        aria-labelledby="setup-verification-title"
        aria-live={copy.role === 'status' ? 'polite' : 'assertive'}
        className="w-full max-w-xl rounded-2xl border border-border bg-bg-card p-7 shadow-lg"
        data-testid="setup-verification-gate"
        role={copy.role}
      >
        <p className="text-xs font-medium uppercase tracking-[.12em] text-text-muted">
          Runtime access
        </p>
        <h1 id="setup-verification-title" className="mt-3 text-2xl font-semibold tracking-tight">
          {copy.title}
        </h1>
        <p className="mt-3 text-sm leading-6 text-text-muted">{copy.detail}</p>
        <div className="mt-6 flex flex-wrap items-center gap-3">
          {onRetry ? (
            <button
              type="button"
              className="inline-flex min-h-11 items-center justify-center rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-fg transition-colors hover:bg-accent/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring-color)] focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50"
              disabled={retrying}
              aria-busy={retrying}
              onClick={retry}
            >
              {retrying ? 'Checking…' : 'Retry verification'}
            </button>
          ) : null}
          <Link
            className="inline-flex min-h-11 items-center justify-center rounded-lg border border-border bg-bg-main px-4 py-2 text-sm font-medium transition-colors hover:bg-bg-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring-color)] focus-visible:ring-offset-2"
            to={panelRoutes.setup}
          >
            Open Setup
          </Link>
        </div>
      </section>
    </main>
  );
}

function DeferredRouteTree({
  isSetupDone,
  runtimeReady,
  runtimeStatus,
  runtimeDisconnected,
  onRetryRuntimeHealth,
}: {
  isSetupDone: boolean;
  runtimeReady: boolean;
  runtimeStatus: RuntimeStatus;
  runtimeDisconnected: boolean;
  onRetryRuntimeHealth: () => Promise<void>;
}) {
  const location = useLocation();
  const deferredLocation = useDeferredValue(location);
  const routePending =
    deferredLocation.pathname !== location.pathname ||
    deferredLocation.search !== location.search ||
    deferredLocation.hash !== location.hash;

  return (
    <>
      <RouteAnnouncer pathname={deferredLocation.pathname} />
      <Routes location={deferredLocation}>
        <Route path={panelRoutes.setup} element={<Setup />} />

        <Route
          path={panelRoutes.home}
          element={isSetupDone
            ? (
              <SetupVerificationGate
                isSetupDone={isSetupDone}
                runtimeReady={runtimeReady}
                runtimeStatus={runtimeStatus}
                runtimeDisconnected={runtimeDisconnected}
                onRetry={onRetryRuntimeHealth}
              >
                <Layout />
              </SetupVerificationGate>
            )
            : <Navigate to={panelRoutes.setup} replace />}
        >
          <Route index element={<Dashboard />} />
          <Route path={panelRoutes.packs.slice(1)} element={<LazyPacks />} />
          <Route path={`${panelRoutes.packs.slice(1)}/:id`} element={<LazyPackDetail />} />
          <Route path={panelRoutes.profile.slice(1)} element={<LazyProfile />} />
          <Route path={panelRoutes.settings.slice(1)} element={<LazySettings />} />
          <Route path={panelRoutes.profileWiring.slice(1)} element={<LazyProfileWiring />} />
          <Route path={panelRoutes.profileFiles.slice(1)} element={<LazyProfileFiles />} />
          <Route path={panelRoutes.flow.slice(1)} element={<LazyFlow />} />
          <Route path={panelRoutes.graph.slice(1)} element={<LazyGraph />} />
          <Route path={panelRoutes.aiInput.slice(1)} element={<LazyAiInput />} />
          <Route path={panelRoutes.apiMap.slice(1)} element={<LazyApiMap />} />
          <Route path={panelRoutes.nodeManager.slice(1)} element={<LazyNodeManager />} />
        </Route>
      </Routes>
      {routePending && (
        <div
          role="status"
          aria-label="Opening page"
          className="pointer-events-none fixed inset-x-0 top-0 z-[100] h-0.5 overflow-hidden bg-accent/15"
        >
          <div className="h-full w-1/3 animate-pulse bg-accent" />
        </div>
      )}
    </>
  );
}
