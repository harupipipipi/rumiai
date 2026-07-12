import { useEffect, useLayoutEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useAppStore } from '@/src/store';
import { Layout } from '@/src/components/layout/Layout';
import { Setup } from '@/src/pages/Setup';
import { Dashboard } from '@/src/pages/Dashboard';
import { Packs } from '@/src/pages/Packs';
import { PackDetail } from '@/src/pages/PackDetail';
import { NodeManager } from '@/src/pages/NodeManager';
import { GraphEditor } from '@/src/pages/GraphEditor';
import { ProfileGraphEditor } from '@/src/pages/ProfileGraphEditor';
import { AiInputInspector } from '@/src/pages/AiInputInspector';
import { ApiMap } from '@/src/pages/ApiMap';
import { ProfileWorkspace } from '@/src/pages/ProfileWorkspace';
import { StartupProfiles } from '@/src/pages/StartupProfiles';
import { Flows } from '@/src/pages/Flows';
import { Settings } from '@/src/pages/Settings';
import { ToastContainer } from '@/src/components/ui/ToastContainer';
import { DialogContainer } from '@/src/components/ui/DialogContainer';
import { bootstrapPanelSession, hasPendingPanelBootstrapCode } from '@/src/lib/api';
import { applyAppearanceToRoot } from '@/src/lib/appearance';
import { runtimeMonitorDelay } from '@/src/lib/runtimeHealth';
import { panelRoutes } from '@/src/lib/routes';
import { hasSelectedSetupPack } from '@/src/lib/setupPacks';

function SetupVerificationGate() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-bg-main p-6 text-sm text-text-muted">
      Verifying setup...
    </div>
  );
}

export default function App() {
  const theme = useAppStore(state => state.theme);
  const colorMode = useAppStore(state => state.colorMode);
  const isSetupDone = useAppStore(state => state.isSetupDone);
  const setSetupDone = useAppStore(state => state.setSetupDone);
  const addToast = useAppStore(state => state.addToast);
  const refreshRuntimeHealth = useAppStore(state => state.refreshRuntimeHealth);
  const [setupPackVerified, setSetupPackVerified] = useState(!isSetupDone);

  useLayoutEffect(() => {
    applyAppearanceToRoot(document.documentElement, { theme, colorMode });
  }, [theme, colorMode]);

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
    if (!isSetupDone) {
      setSetupPackVerified(false);
      return;
    }

    let cancelled = false;
    setSetupPackVerified(false);
    void hasSelectedSetupPack()
      .then((verified) => {
        if (cancelled) return;
        setSetupPackVerified(verified);
        if (!verified) {
          setSetupDone(false);
        }
      })
      .catch((error) => {
        if (cancelled) return;
        setSetupPackVerified(false);
        setSetupDone(false);
        addToast(error instanceof Error ? error.message : 'Setup pack verification failed', 'error');
      });

    return () => {
      cancelled = true;
    };
  }, [isSetupDone, setSetupDone, addToast]);

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
      <Routes>
        <Route path={panelRoutes.setup} element={<Setup />} />

        <Route
          path={panelRoutes.home}
          element={isSetupDone
            ? (setupPackVerified ? <Layout /> : <SetupVerificationGate />)
            : <Navigate to={panelRoutes.setup} replace />}
        >
          <Route index element={<Dashboard />} />
          <Route path={panelRoutes.packs.slice(1)} element={<Packs />} />
          <Route path={`${panelRoutes.packs.slice(1)}/:id`} element={<PackDetail />} />
          <Route path={panelRoutes.nodes.slice(1)} element={<NodeManager />} />
          <Route path={panelRoutes.graphEditor.slice(1)} element={<GraphEditor />} />
          <Route path={panelRoutes.profileGraph.slice(1)} element={<ProfileGraphEditor />} />
          <Route path={panelRoutes.aiInput.slice(1)} element={<AiInputInspector />} />
          <Route path={panelRoutes.apiMap.slice(1)} element={<ApiMap />} />
          <Route path={panelRoutes.profileWorkspace.slice(1)} element={<ProfileWorkspace />} />
          <Route path={panelRoutes.startup.slice(1)} element={<StartupProfiles />} />
          <Route path={panelRoutes.flows.slice(1)} element={<Flows />} />
          <Route path={panelRoutes.settings.slice(1)} element={<Settings />} />
        </Route>
      </Routes>
      <ToastContainer />
      <DialogContainer />
    </BrowserRouter>
  );
}
