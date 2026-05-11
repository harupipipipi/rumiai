import { Outlet, Navigate } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { useAppStore } from '@/src/store';
import { panelRoutes } from '@/src/lib/routes';

export function Layout() {
  const isSetupDone = useAppStore(state => state.isSetupDone);
  const runtimeReady = useAppStore(state => state.runtimeReady);
  const runtimeStatus = useAppStore(state => state.runtimeStatus);
  const runtimeError = useAppStore(state => state.runtimeError);

  if (!isSetupDone) {
    return <Navigate to={panelRoutes.setup} replace />;
  }

  return (
    <div className="flex h-screen overflow-hidden bg-bg-main text-text-main">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header />
        <main className="flex-1 flex flex-col relative overflow-hidden">
          {!runtimeReady && (
            <div
              role="alert"
              className={`flex items-center gap-3 border-b px-6 py-3 text-sm ${
                runtimeStatus === 'error'
                  ? 'border-red-200 bg-red-50 text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-300'
                  : 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/30 dark:bg-amber-950/20 dark:text-amber-300'
              }`}
            >
              <div className={`h-2 w-2 rounded-full ${runtimeStatus === 'error' ? 'bg-red-500' : 'bg-amber-500 animate-pulse'}`} />
              <span>
                {runtimeStatus === 'error'
                  ? runtimeError || 'Runtime startup failed. Open Settings or restart the kernel to recover.'
                  : 'Runtime is warming up in the background…'}
              </span>
            </div>
          )}
          <Outlet />
        </main>
      </div>
    </div>
  );
}
