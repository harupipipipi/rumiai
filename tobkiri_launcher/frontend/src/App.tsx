import { useDeferredValue, useEffect, useLayoutEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router';
import {
  cancelPackMutationReconciliation,
  useAppStore,
} from '@/src/store';
import { Layout } from '@/src/components/layout/Layout';
import { Setup } from '@/src/pages/Setup';
import { Dashboard } from '@/src/pages/Dashboard';
import { ToastContainer } from '@/src/components/ui/ToastContainer';
import { DialogContainer } from '@/src/components/ui/DialogContainer';
import { bootstrapPanelSession, hasPendingPanelBootstrapCode } from '@/src/lib/api';
import { applyAppearanceToRoot } from '@/src/lib/appearance';
import { runtimeMonitorDelay } from '@/src/lib/runtimeHealth';
import { panelRoutes } from '@/src/lib/routes';
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
      <DeferredRouteTree isSetupDone={isSetupDone} />
      <ToastContainer />
      <DialogContainer />
    </BrowserRouter>
  );
}

function DeferredRouteTree({
  isSetupDone,
}: {
  isSetupDone: boolean;
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
            ? <Layout />
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
