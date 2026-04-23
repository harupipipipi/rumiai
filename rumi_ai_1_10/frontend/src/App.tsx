import { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useAppStore } from '@/src/store';
import { Layout } from '@/src/components/layout/Layout';
import { Setup } from '@/src/pages/Setup';
import { Dashboard } from '@/src/pages/Dashboard';
import { Packs } from '@/src/pages/Packs';
import { PackDetail } from '@/src/pages/PackDetail';
import { StartupProfiles } from '@/src/pages/StartupProfiles';
import { Flows } from '@/src/pages/Flows';
import { Settings } from '@/src/pages/Settings';
import { ToastContainer } from '@/src/components/ui/ToastContainer';
import { DialogContainer } from '@/src/components/ui/DialogContainer';
import { bootstrapPanelSession, hasPendingPanelBootstrapCode } from '@/src/lib/api';
import { panelRoutes } from '@/src/lib/routes';
import { Button } from '@/src/components/ui/Button';
import { Loader2 } from 'lucide-react';

export default function App() {
  const theme = useAppStore(state => state.theme);
  const colorMode = useAppStore(state => state.colorMode);
  const isSetupDone = useAppStore(state => state.isSetupDone);
  const addToast = useAppStore(state => state.addToast);
  const [panelReady, setPanelReady] = useState(() => !hasPendingPanelBootstrapCode());
  const [panelBootstrapError, setPanelBootstrapError] = useState<string | null>(null);

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
    let alive = true;
    if (!hasPendingPanelBootstrapCode()) {
      setPanelReady(true);
      setPanelBootstrapError(null);
      return () => {
        alive = false;
      };
    }

    setPanelReady(false);
    setPanelBootstrapError(null);
    bootstrapPanelSession().catch((error) => {
      const message = error instanceof Error ? error.message : 'Panel bootstrap failed';
      if (alive) {
        setPanelBootstrapError(message);
      }
      addToast(message, 'error');
    }).finally(() => {
      if (alive) {
        setPanelReady(true);
      }
    });

    return () => {
      alive = false;
    };
  }, [addToast]);

  if (!panelReady) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg-main px-4 text-text-main">
        <div className="flex max-w-md flex-col items-center gap-4 text-center">
          <Loader2 className="h-8 w-8 animate-spin text-accent" />
          <div className="space-y-2">
            <h1 className="text-2xl font-semibold">Opening your launcher session</h1>
            <p className="text-sm text-text-muted">We&apos;re securing the panel before loading your profiles.</p>
          </div>
        </div>
      </div>
    );
  }

  if (panelBootstrapError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg-main px-4 text-text-main">
        <div className="flex max-w-lg flex-col gap-4 rounded-2xl border border-border bg-bg-card p-8 shadow-sm">
          <div className="space-y-2">
            <h1 className="text-2xl font-semibold">Panel session could not start</h1>
            <p className="text-sm text-text-muted">
              {panelBootstrapError}
            </p>
          </div>
          <Button onClick={() => window.location.reload()} className="w-full sm:w-fit">
            Reload panel
          </Button>
        </div>
      </div>
    );
  }

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
