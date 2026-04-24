import { Outlet, Navigate } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { useAppStore } from '@/src/store';
import { panelRoutes } from '@/src/lib/routes';
import { PanelLeft } from 'lucide-react';

export function Layout() {
  const isSetupDone = useAppStore(state => state.isSetupDone);
  const isSidebarOpen = useAppStore(state => state.isSidebarOpen);
  const setSidebarOpen = useAppStore(state => state.setSidebarOpen);
  const runtimeReady = useAppStore(state => state.runtimeReady);
  const runtimeStatus = useAppStore(state => state.runtimeStatus);
  const runtimeError = useAppStore(state => state.runtimeError);

  if (!isSetupDone) {
    return <Navigate to={panelRoutes.setup} replace />;
  }

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-bg-main text-text-main transition-colors duration-200 font-sans">
      <Header />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 flex flex-col relative overflow-hidden scrollbar-hidden">
          {!runtimeReady && (
            <div
              className={`border-b px-6 py-3 text-sm ${
                runtimeStatus === 'error'
                  ? 'border-rose-900/50 bg-rose-950/30 text-rose-100'
                  : 'border-amber-900/30 bg-amber-950/20 text-amber-100'
              }`}
            >
              {runtimeStatus === 'error'
                ? runtimeError || 'Runtime startup failed. Open Settings or restart the kernel to recover.'
                : 'Home shell is ready. Runtime data is still warming up in the background.'}
            </div>
          )}
          {!isSidebarOpen && (
            <div className="absolute top-3 left-3 z-50">
              <button
                onClick={() => setSidebarOpen(true)}
                className="p-2 hover:bg-bg-hover rounded-md text-text-muted transition-colors bg-bg-main border border-border shadow-sm"
              >
                <PanelLeft className="w-5 h-5" />
              </button>
            </div>
          )}
          <Outlet />
        </main>
      </div>
    </div>
  );
}
