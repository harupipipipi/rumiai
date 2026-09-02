import { Outlet, useLocation } from 'react-router';
import type {ReactNode} from 'react';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { ViewerVersionLabel } from './ViewerVersionLabel';
import { useAppStore } from '@/src/store';
import { describeRuntimeBanner } from '@/src/lib/runtimeHealth';
import { panelRoutes } from '@/src/lib/routes';
import { RouteBoundary } from './RouteBoundary';
import {CopyErrorButton} from '@/src/components/ui/CopyErrorButton';

export function shouldShowRuntimeErrorCopy(
  banner: Pick<ReturnType<typeof describeRuntimeBanner>, 'tone' | 'detail'>,
): boolean {
  return banner.tone === 'danger' && Boolean(banner.detail.trim());
}

export function Layout({verificationBanner}: {verificationBanner?: ReactNode}) {
  const location = useLocation();
  const runtimeReady = useAppStore(state => state.runtimeReady);
  const runtimeStatus = useAppStore(state => state.runtimeStatus);
  const runtimeError = useAppStore(state => state.runtimeError);
  const runtimeDisconnected = useAppStore(state => state.runtimeDisconnected);
  const lastRuntimeHealthyAt = useAppStore(state => state.lastRuntimeHealthyAt);

  const runtimeBanner = describeRuntimeBanner({
    runtimeReady,
    runtimeStatus,
    runtimeError,
    runtimeDisconnected,
    lastRuntimeHealthyAt,
  });
  const canCopyRuntimeError = shouldShowRuntimeErrorCopy(runtimeBanner);

  return (
    <div className="flex h-screen overflow-hidden bg-bg-main text-text-main">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header />
        <main id="panel-main" tabIndex={-1} className="flex-1 flex flex-col relative overflow-hidden">
          {verificationBanner}
          {!runtimeReady && !verificationBanner && (
            <div
              role="alert"
              className={`flex items-center gap-3 border-b px-6 py-3 text-sm ${
                runtimeBanner.tone === 'danger'
                  ? 'border-red-200 bg-red-50 text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-300'
                  : 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/30 dark:bg-amber-950/20 dark:text-amber-300'
              }`}
            >
              <div className={`mt-1 h-2 w-2 shrink-0 rounded-full ${runtimeBanner.tone === 'danger' ? 'bg-red-500' : 'bg-amber-500 animate-pulse'}`} />
              <div className="min-w-0 flex-1">
                <p className="font-medium">{runtimeBanner.title}</p>
                <p className="text-xs opacity-80">{runtimeBanner.detail}</p>
              </div>
              {canCopyRuntimeError ? (
                <CopyErrorButton
                  label="Copy runtime status error"
                  text={`${runtimeBanner.title}\n${runtimeBanner.detail}`}
                />
              ) : null}
            </div>
          )}
          <RouteBoundary>
            <Outlet />
          </RouteBoundary>
          {location.pathname === panelRoutes.home && <ViewerVersionLabel />}
        </main>
      </div>
    </div>
  );
}
