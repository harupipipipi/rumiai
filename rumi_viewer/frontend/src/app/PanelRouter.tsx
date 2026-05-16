import type { ReactNode } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

import { Layout } from '@/src/components/layout/Layout';
import { DialogContainer } from '@/src/components/ui/DialogContainer';
import { ToastContainer } from '@/src/components/ui/ToastContainer';
import { Dashboard } from '@/src/pages/Dashboard';
import { Flows } from '@/src/pages/Flows';
import { GraphEditor } from '@/src/pages/GraphEditor';
import { NodeManager } from '@/src/pages/NodeManager';
import { PackDetail } from '@/src/pages/PackDetail';
import { Packs } from '@/src/pages/Packs';
import { Settings } from '@/src/pages/Settings';
import { Setup } from '@/src/pages/Setup';
import { StartupProfiles } from '@/src/pages/StartupProfiles';
import {
  PANEL_BASENAME,
  panelChildRoutes,
  panelPackDetailRoute,
  panelRoutes,
  type PanelChildRouteKey,
} from '@/src/lib/routes';

interface PanelRouterProps {
  isSetupDone: boolean;
}

const panelRouteElements: Record<PanelChildRouteKey, ReactNode> = {
  dashboard: <Dashboard />,
  packs: <Packs />,
  nodes: <NodeManager />,
  graphEditor: <GraphEditor />,
  startup: <StartupProfiles />,
  flows: <Flows />,
  settings: <Settings />,
};

export function PanelRouter({ isSetupDone }: PanelRouterProps) {
  return (
    <BrowserRouter basename={PANEL_BASENAME}>
      <Routes>
        <Route path={panelRoutes.setup} element={<Setup />} />

        <Route
          path={panelRoutes.home}
          element={isSetupDone ? <Layout /> : <Navigate to={panelRoutes.setup} replace />}
        >
          {panelChildRoutes.map((route) => (
            route.index ? (
              <Route key={route.key} index element={panelRouteElements[route.key]} />
            ) : (
              <Route key={route.key} path={route.path} element={panelRouteElements[route.key]} />
            )
          ))}
          <Route path={panelPackDetailRoute.path} element={<PackDetail />} />
        </Route>
      </Routes>
      <ToastContainer />
      <DialogContainer />
    </BrowserRouter>
  );
}
