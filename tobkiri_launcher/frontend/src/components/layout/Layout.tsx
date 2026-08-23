import { useEffect, useState } from 'react';
import { Copy, RefreshCw, Settings } from 'lucide-react';
import { Link, Outlet, Navigate, useLocation } from 'react-router';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { ViewerVersionLabel } from './ViewerVersionLabel';
import { useAppStore } from '@/src/store';
import { describeRuntimeStatus } from '@/src/lib/runtimeHealth';
import { useT } from '@/src/lib/i18n';
import { panelRoutes } from '@/src/lib/routes';
import { RouteBoundary } from './RouteBoundary';
import { Button } from '@/src/components/ui/Button';

export function Layout() {
  const t = useT();
  const location = useLocation();
  const [errorCopied, setErrorCopied] = useState(false);
  const isSetupDone = useAppStore(state => state.isSetupDone);
  const runtimeReady = useAppStore(state => state.runtimeReady);
  const runtimeStatus = useAppStore(state => state.runtimeStatus);
  const runtimeError = useAppStore(state => state.runtimeError);
  const runtimeDisconnected = useAppStore(state => state.runtimeDisconnected);
  const lastRuntimeHealthyAt = useAppStore(state => state.lastRuntimeHealthyAt);

  const runtimeStatusDescription = describeRuntimeStatus({
    runtimeReady,
    runtimeStatus,
    runtimeError,
    runtimeDisconnected,
    lastRuntimeHealthyAt,
  });

  useEffect(() => {
    setErrorCopied(false);
  }, [runtimeStatusDescription.kind, runtimeStatusDescription.errorDetail]);

  if (!isSetupDone) {
    return <Navigate to={panelRoutes.setup} replace />;
  }
  if (runtimeStatus === 'profile_reconfirmation_required') {
    return <Navigate to={panelRoutes.setup} replace />;
  }

  return (
    <div className="flex h-screen overflow-hidden bg-bg-main text-text-main">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header />
        <main id="panel-main" tabIndex={-1} className="flex-1 flex flex-col relative overflow-hidden">
          {runtimeStatusDescription.kind !== 'healthy' && (
            <div
              role="status"
              aria-live="polite"
              aria-atomic="true"
              data-runtime-status={runtimeStatusDescription.kind}
              className={`flex flex-wrap items-center gap-3 border-b px-4 py-3 text-sm sm:px-6 ${
                runtimeStatusDescription.tone === 'danger'
                  ? 'border-red-200 bg-red-50 text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-300'
                  : 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/30 dark:bg-amber-950/20 dark:text-amber-300'
              }`}
            >
              <div className={`h-2 w-2 shrink-0 rounded-full ${runtimeStatusDescription.tone === 'danger' ? 'bg-red-500' : 'bg-amber-500 animate-pulse'}`} />
              <div className="min-w-[12rem] flex-1">
                <p className="font-medium">{t(runtimeStatusDescription.titleKey)}</p>
                <p className="text-xs opacity-80">
                  {runtimeStatusDescription.errorDetail || t(runtimeStatusDescription.detailKey)}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button type="button" variant="outline" size="sm" onClick={() => window.location.reload()}>
                  <RefreshCw className="h-4 w-4" aria-hidden="true" />
                  {t('runtime.retry')}
                </Button>
                {runtimeStatusDescription.tone === 'danger' && (
                  <Link
                    to={panelRoutes.settings}
                    className="inline-flex h-8 items-center justify-center gap-2 rounded-md border border-border bg-bg-main px-3 text-xs font-medium transition hover:bg-bg-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring-color)]"
                  >
                    <Settings className="h-4 w-4" aria-hidden="true" />
                    {t('runtime.open_settings')}
                  </Link>
                )}
                {runtimeStatusDescription.errorDetail && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      const errorDetail = runtimeStatusDescription.errorDetail;
                      if (!errorDetail) return;
                      void copyRuntimeDetails(errorDetail)
                        .then(setErrorCopied)
                        .catch(() => setErrorCopied(false));
                    }}
                  >
                    <Copy className="h-4 w-4" aria-hidden="true" />
                    {t(errorCopied ? 'runtime.copied' : 'runtime.copy_details')}
                  </Button>
                )}
              </div>
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

/** Copy a runtime diagnostic without retaining it in application state or storage. */
export async function copyRuntimeDetails(
  text: string,
  clipboard: Pick<Clipboard, 'writeText'> | undefined = navigator.clipboard,
  documentRef: Document = document,
): Promise<boolean> {
  let shouldUseFallback = !clipboard?.writeText;
  try {
    if (clipboard?.writeText) {
      await clipboard.writeText(text);
      return true;
    }
  } catch {
    shouldUseFallback = true;
  }

  if (!shouldUseFallback) return false;
  const textarea = documentRef.createElement('textarea');
  textarea.value = text;
  textarea.setAttribute('readonly', '');
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  documentRef.body.appendChild(textarea);
  textarea.select();
  try {
    return documentRef.execCommand?.('copy') ?? false;
  } catch {
    return false;
  } finally {
    textarea.remove();
  }
}
