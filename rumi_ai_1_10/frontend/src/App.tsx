/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useAppStore } from '@/src/store';
import { Layout } from '@/src/components/layout/Layout';
import { Setup } from '@/src/pages/Setup';
import { Dashboard } from '@/src/pages/Dashboard';
import { Packs } from '@/src/pages/Packs';
import { PackDetail } from '@/src/pages/PackDetail';
import { Flows } from '@/src/pages/Flows';
import { Settings } from '@/src/pages/Settings';
import { ToastContainer } from '@/src/components/ui/ToastContainer';
import { DialogContainer } from '@/src/components/ui/DialogContainer';

export default function App() {
  const theme = useAppStore(state => state.theme);
  const colorMode = useAppStore(state => state.colorMode);
  const isSetupDone = useAppStore(state => state.isSetupDone);

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

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to={isSetupDone ? "/panel" : "/setup"} replace />} />
        <Route path="/setup" element={<Setup />} />
        
        <Route path="/panel" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="packs" element={<Packs />} />
          <Route path="packs/:id" element={<PackDetail />} />
          <Route path="flows" element={<Flows />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
      <ToastContainer />
      <DialogContainer />
    </BrowserRouter>
  );
}
