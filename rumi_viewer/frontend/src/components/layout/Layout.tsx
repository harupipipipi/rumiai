import { Outlet, Navigate } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { useAppStore } from '@/src/store';
import { panelRoutes } from '@/src/lib/routes';
import { cn } from '@/src/lib/utils';

export function Layout() {
  const isSetupDone = useAppStore(state => state.isSetupDone);
  const runtimeReady = useAppStore(state => state.runtimeReady);
  const runtimeStatus = useAppStore(state => state.runtimeStatus);
  const runtimeError = useAppStore(state => state.runtimeError);
  const theme = useAppStore(state => state.theme);
  const isCosmos = theme === 'Cosmos';

  if (!isSetupDone) {
    return <Navigate to={panelRoutes.setup} replace />;
  }

  return (
    <div className={cn('relative flex h-screen overflow-hidden text-text-main', isCosmos ? 'bg-transparent' : 'bg-bg-main')}>
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header />
        <main className="relative flex flex-1 flex-col overflow-hidden">
          {!runtimeReady && (
            <div
              role="alert"
              className={cn(
                'flex items-center gap-3 border-b px-6 py-3 text-sm',
                isCosmos
                  ? runtimeStatus === 'error'
                    ? 'cosmos-glass border-[color:color-mix(in_srgb,var(--destructive)_30%,transparent)] text-[color:var(--destructive)]'
                    : 'cosmos-glass border-[color:color-mix(in_srgb,var(--cosmos-gold)_28%,transparent)] text-[color:var(--cosmos-gold)]'
                  : runtimeStatus === 'error'
                    ? 'border-red-200 bg-red-50 text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-300'
                    : 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/30 dark:bg-amber-950/20 dark:text-amber-300',
              )}
            >
              <div
                className={cn(
                  'h-2 w-2 rounded-full',
                  runtimeStatus === 'error'
                    ? isCosmos ? 'bg-[color:var(--destructive)]' : 'bg-red-500'
                    : isCosmos
                      ? 'bg-[color:var(--cosmos-gold)] cosmos-anim-pulse'
                      : 'bg-amber-500 animate-pulse',
                )}
              />
              <span>
                {runtimeStatus === 'error'
                  ? runtimeError || 'Runtime startup failed. Open Settings or restart the kernel to recover.'
                  : isCosmos
                    ? 'Calibrating Rumi’s constellations…'
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
