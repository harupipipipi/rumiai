import {useCallback, useEffect, useRef, useState} from 'react';
import {AppWindow, Monitor, Route} from 'lucide-react';

import {Badge} from '@/src/components/ui/Badge';
import {Button} from '@/src/components/ui/Button';
import {Card, CardContent, CardHeader, CardTitle} from '@/src/components/ui/Card';
import {TobkiriLoadingMark} from '@/src/components/ui/TobkiriLoader';
import {
  fetchPresentationState,
  isDesktopShellAvailable,
  launchSelectedPresentation,
} from '@/src/lib/api';
import type {ApiPresentationState} from '@/src/lib/apiTypes';
import {launchDisabledReason} from '@/src/lib/presentation';
import {useAppStore} from '@/src/store';

function formatError(error: unknown): string {
  return error instanceof Error && error.message.trim()
    ? error.message
    : 'Tobkiri could not verify the selected Defaults Profile application.';
}

export function ShellLaunchCard({
  runtimeReady,
  onChooseShell,
}: {
  runtimeReady: boolean;
  onChooseShell?: () => void;
}) {
  const addToast = useAppStore((state) => state.addToast);
  const [presentation, setPresentation] = useState<ApiPresentationState | null>(null);
  const [loading, setLoading] = useState(false);
  const [launching, setLaunching] = useState(false);
  const launchingRef = useRef(false);
  const [error, setError] = useState<string | null>(null);

  const desktopShell = isDesktopShellAvailable();
  const loadSurfaceState = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const nextPresentation = await fetchPresentationState();
      setPresentation(nextPresentation);
    } catch (loadError) {
      setError(formatError(loadError));
      setPresentation(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (desktopShell && runtimeReady) {
      void loadSurfaceState();
    }
  }, [desktopShell, runtimeReady, loadSurfaceState]);

  if (!desktopShell) return null;

  const selectedShell = presentation?.selection
    ? presentation.catalog.shell_providers.find(
      (provider) => provider.provider_id === presentation.selection?.shell_provider_id,
    )
    : null;
  const materialization = presentation?.materialization ?? null;
  const needsSelection = Boolean(presentation && !presentation.selection);
  const blockedReason = !runtimeReady
    ? 'The selected Shell becomes available after Tobkiri runtime readiness.'
    : !presentation?.selection
      ? 'No verified Shell selection is active.'
      : materialization
        ? launchDisabledReason(materialization)
        : 'The selected Shell materialization is unavailable.';

  const launch = async () => {
    if (blockedReason || launching || launchingRef.current) return;
    launchingRef.current = true;
    setLaunching(true);
    setError(null);
    try {
      const result = await launchSelectedPresentation();
      addToast(result.message || 'Defaults Profile opened in the selected Shell.', 'success');
    } catch (launchError) {
      setError(formatError(launchError));
    } finally {
      launchingRef.current = false;
      setLaunching(false);
    }
  };

  return (
    <Card aria-labelledby="shell-launch-title">
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            <AppWindow className="h-4 w-4 text-accent" />
            <CardTitle id="shell-launch-title">Defaults Profile</CardTitle>
          </div>
          <Badge variant={blockedReason ? 'warning' : 'success'}>
            {blockedReason ? 'Unavailable' : 'Ready'}
          </Badge>
        </div>
        <p className="text-sm leading-relaxed text-text-muted">
          Open the active Defaults Profile application through the selected Tobkiri Shell.
          Conversation is one route inside that application, not the application itself.
        </p>
      </CardHeader>
      <CardContent>
        {loading ? (
          <p className="flex items-center gap-2 text-sm text-text-muted" role="status" aria-busy="true">
            <TobkiriLoadingMark />
            Loading the selected Shell…
          </p>
        ) : error ? (
          <div className="flex flex-wrap items-center gap-3" role="alert">
            <p className="flex-1 text-sm text-destructive">{error}</p>
            <Button variant="outline" size="sm" onClick={() => void loadSurfaceState()}>
              Retry
            </Button>
          </div>
        ) : (
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 space-y-1 text-sm">
              <p className="flex items-center gap-2 text-text-main">
                <Monitor className="h-4 w-4 shrink-0 text-text-muted" />
                <span className="truncate">{selectedShell?.display_name ?? 'No Shell selected'}</span>
              </p>
              <p className="flex items-center gap-2 text-xs text-text-muted">
                <Route className="h-3.5 w-3.5 shrink-0" />
                <span>{blockedReason ?? 'Defaults Profile is ready in the selected Shell.'}</span>
              </p>
            </div>
            <Button
              className="min-h-11 shrink-0"
              disabled={(Boolean(blockedReason) && (!needsSelection || !onChooseShell)) || launching}
              loading={launching}
              onClick={() => needsSelection ? onChooseShell?.() : void launch()}
              aria-busy={launching}
            >
              {launching ? 'Opening…' : needsSelection ? 'Choose Shell' : 'Open Defaults Profile'}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
