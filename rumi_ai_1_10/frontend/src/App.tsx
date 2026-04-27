import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useAppStore } from '@/src/store';
import { Layout } from '@/src/components/layout/Layout';
import { Setup } from '@/src/pages/Setup';
import { Dashboard } from '@/src/pages/Dashboard';
import { Packs } from '@/src/pages/Packs';
import { PackDetail } from '@/src/pages/PackDetail';
import { NodeManager } from '@/src/pages/NodeManager';
import { StartupProfiles } from '@/src/pages/StartupProfiles';
import { Flows } from '@/src/pages/Flows';
import { Settings } from '@/src/pages/Settings';
import { ToastContainer } from '@/src/components/ui/ToastContainer';
import { DialogContainer } from '@/src/components/ui/DialogContainer';
import { bootstrapPanelSession, hasPendingPanelBootstrapCode } from '@/src/lib/api';
import { panelRoutes } from '@/src/lib/routes';

export default function App() {
  const theme = useAppStore(state => state.theme);
  const colorMode = useAppStore(state => state.colorMode);
  const isSetupDone = useAppStore(state => state.isSetupDone);
  const addToast = useAppStore(state => state.addToast);
  const refreshRuntimeHealth = useAppStore(state => state.refreshRuntimeHealth);
  const runtimeReady = useAppStore(state => state.runtimeReady);
  const runtimeStatus = useAppStore(state => state.runtimeStatus);

  useEffect(() => {
    const root = document.documentElement;
    root.classList.remove('theme-rumi', 'theme-minimal', 'theme-standard', 'theme-rounded');
    root.classList.add(`theme-${theme.toLowerCase()}`);
  }, [theme]);

  useEffect(() => {
    const root = document.documentElement;
    if (colorMode === 'dark') {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
  }, [colorMode]);

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

    const pollRuntimeReadiness = async () => {
      while (!cancelled) {
        await refreshRuntimeHealth();
        if (cancelled) {
          return;
        }
        const currentState = useAppStore.getState();
        if (currentState.runtimeReady || currentState.runtimeStatus === 'error') {
          return;
        }
        await new Promise<void>((resolve) => {
          timer = window.setTimeout(resolve, 250);
        });
      }
    };

    void pollRuntimeReadiness();

    return () => {
      cancelled = true;
      if (timer !== undefined) {
        window.clearTimeout(timer);
      }
    };
  }, [refreshRuntimeHealth, runtimeReady, runtimeStatus]);

  return (
    <BrowserRouter basename="/panel">
      <Routes>
        <Route path={panelRoutes.setup} element={<Setup />} />

        <Route
          path={panelRoutes.home}
          element={isSetupDone ? <Layout /> : <Navigate to={panelRoutes.setup} replace />}
        >
          <Route index element={<Dashboard />} />
          <Route path={panelRoutes.packs.slice(1)} element={<Packs />} />
          <Route path={`${panelRoutes.packs.slice(1)}/:id`} element={<PackDetail />} />
          <Route path={panelRoutes.nodes.slice(1)} element={<NodeManager />} />
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
