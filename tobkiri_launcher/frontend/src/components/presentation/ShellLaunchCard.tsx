import {useCallback, useEffect, useRef, useState} from 'react';
import {MessageCircle, Monitor, Route} from 'lucide-react';

import {Badge} from '@/src/components/ui/Badge';
import {Button} from '@/src/components/ui/Button';
import {Card, CardContent, CardHeader, CardTitle} from '@/src/components/ui/Card';
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
    : 'Tobkiri could not verify the selected Profile launch surface.';
}

export function ShellLaunchCard({
  runtimeReady,
  profileId,
  profileDisplayName,
}: {
  runtimeReady: boolean;
  profileId: string;
  profileDisplayName: string;
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

  const selectedShell = presentation?.selection
    ? presentation.catalog.shell_providers.find(
      (provider) => provider.provider_id === presentation.selection?.shell_provider_id,
    )
    : null;
  const materialization = presentation?.materialization ?? null;
  const blockedReason = !desktopShell
    ? 'Profile launch is available in Tobkiri Launcher.'
    : !runtimeReady
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
      addToast(result.message || `${profileDisplayName} opened in the selected Shell.`, 'success');
    } catch (launchError) {
      setError(formatError(launchError));
    } finally {
      launchingRef.current = false;
      setLaunching(false);
    }
  };

  return (
    <Card aria-labelledby={`shell-launch-title-${profileId}`}>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            <MessageCircle className="h-4 w-4 text-accent" />
            <CardTitle id={`shell-launch-title-${profileId}`}>{profileDisplayName} launch</CardTitle>
          </div>
          <Badge variant={blockedReason ? 'warning' : 'success'}>
            {blockedReason ? 'Unavailable' : 'Ready'}
          </Badge>
        </div>
        <p className="text-sm leading-relaxed text-text-muted">
          Launch this active execution Profile through its verified Tobkiri Shell binding.
          The handoff remains bound to the Profile revision, activation, and Plan identity.
        </p>
      </CardHeader>
      <CardContent>
        {loading ? (
          <p className="text-sm text-text-muted" role="status">Loading the selected Shell…</p>
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
                <span>{blockedReason ?? 'Verified Profile handoff is ready.'}</span>
              </p>
            </div>
            <Button
              className="min-h-11 shrink-0"
              disabled={Boolean(blockedReason) || launching}
              loading={launching}
              onClick={() => void launch()}
              aria-busy={launching}
            >
              {launching ? 'Opening…' : `Launch ${profileDisplayName}`}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
