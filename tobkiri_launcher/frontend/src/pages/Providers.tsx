import {useEffect, useMemo, useState} from 'react';
import {AlertTriangle, KeyRound, PlugZap, RefreshCw, ShieldCheck} from 'lucide-react';

import {OperationInputForm} from '@/src/components/advanced/OperationInputForm';
import {Badge} from '@/src/components/ui/Badge';
import {Button} from '@/src/components/ui/Button';
import {Card, CardContent, CardDescription, CardHeader, CardTitle} from '@/src/components/ui/Card';
import {InlineLoadError} from '@/src/components/ui/InlineLoadError';
import {useRuntimeOperationInvocation} from '@/src/hooks/useRuntimeOperationInvocation';
import {useRuntimeSurface} from '@/src/hooks/useRuntimeSurface';
import {
  authoritativeOperationKey,
  LAUNCHER_ADVANCED_VIEWS,
  selectAdvancedContractInvokableOperations,
} from '@/src/lib/advancedSurfaces';
import {
  projectProviderConnections,
  providerOperationSchema,
  type ProviderConnectionAction,
} from '@/src/lib/providerConnections';
import type {RuntimeProfileCatalogProjection} from '@/src/lib/runtimeSurface';

const ACTION_LABELS: Record<ProviderConnectionAction, string> = {
  configure: 'Configure',
  set_credential: 'Set credential',
  connect_oauth: 'Connect OAuth',
  test: 'Test connection',
  health: 'Refresh health',
  refresh_models: 'Refresh models',
  delete_credential: 'Disconnect credential',
  delete_instance: 'Delete instance',
  create_instance: 'Add instance',
  select_profile: 'Select for Profile',
};

function statusVariant(status: string): 'success' | 'warning' | 'destructive' | 'outline' {
  if (status === 'healthy' || status === 'connected') return 'success';
  if (status === 'degraded' || status === 'not_configured') return 'warning';
  if (status === 'error') return 'destructive';
  return 'outline';
}

export function Providers() {
  const contracts = useRuntimeSurface<unknown>('contracts');
  const operations = useRuntimeSurface<unknown>('operations');
  const profiles = useRuntimeSurface<RuntimeProfileCatalogProjection>('profiles');
  const providers = useMemo(() => projectProviderConnections({
    contractsData: contracts.data?.data,
    operationsData: operations.data?.data,
    activeProfileId: contracts.data?.profile_id ?? null,
  }), [contracts.data, operations.data]);
  const [selectedInstanceId, setSelectedInstanceId] = useState<string | null>(null);
  const [selectedAction, setSelectedAction] = useState<ProviderConnectionAction | null>(null);
  const selectedProvider = providers.find((provider) => provider.instanceId === selectedInstanceId)
    ?? providers[0]
    ?? null;
  const activeProfileDiagnostics = profiles.data?.data.profiles.find((entry) => entry.active)?.diagnostics ?? [];

  const declaredOperationIds = new Set(
    Object.values(selectedProvider?.operationIds ?? {}).filter((value): value is string => Boolean(value)),
  );
  const invokable = selectAdvancedContractInvokableOperations(
    LAUNCHER_ADVANCED_VIEWS.providerConnections,
    {status: operations.status, stale: operations.stale, error: operations.error},
    operations.data,
    Object.values(selectedProvider?.operations ?? {}),
    declaredOperationIds,
  );
  const selectedOperation = selectedAction && selectedProvider?.operations[selectedAction]
    ? invokable.find((operation) => (
      authoritativeOperationKey(operation.contract_id, operation.operation_id)
      === authoritativeOperationKey(
        selectedProvider.operations[selectedAction]!.contract_id,
        selectedProvider.operations[selectedAction]!.operation_id,
      )
    )) ?? null
    : null;
  const invocation = useRuntimeOperationInvocation(
    operations.data,
    selectedOperation ? providerOperationSchema(selectedProvider!, selectedOperation) : null,
  );

  useEffect(() => {
    if (!selectedProvider) {
      setSelectedInstanceId(null);
      setSelectedAction(null);
      return;
    }
    if (selectedInstanceId !== selectedProvider.instanceId) {
      setSelectedInstanceId(selectedProvider.instanceId);
      setSelectedAction(null);
    }
  }, [selectedInstanceId, selectedProvider?.instanceId]);

  const refresh = async () => {
    await Promise.all([contracts.refresh(true), operations.refresh(true), profiles.refresh(true)]);
    await invocation.reconcileUnknown();
  };

  const loading = contracts.status === 'loading' || operations.status === 'loading';
  const loadError = contracts.error ?? operations.error;
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 p-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold text-text-main">
            <PlugZap className="size-6 text-accent" aria-hidden="true" />Providers
          </h1>
          <p className="mt-1 max-w-3xl text-sm text-text-muted">
            AI connections discovered from verified Pack Contract metadata. Tobkiri Launcher does not maintain a vendor list.
          </p>
        </div>
        <Button type="button" variant="outline" onClick={() => void refresh()} disabled={loading} aria-label="Refresh provider connections">
          <RefreshCw className="mr-2 size-4" aria-hidden="true" />Refresh
        </Button>
      </header>

      {loadError ? (
        <InlineLoadError title="Provider connections could not be loaded" message={loadError.message} onRetry={() => void refresh()} />
      ) : null}
      {activeProfileDiagnostics.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Active Profile needs attention</CardTitle>
            <CardDescription>A selected provider that is removed, disabled, incompatible, or policy-blocked remains unresolved; Tobkiri does not silently choose a fallback.</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2" aria-label="Active Profile diagnostics">
              {activeProfileDiagnostics.map((diagnostic) => (
                <li key={`${diagnostic.code}:${diagnostic.subject}`} className="rounded-lg border border-amber-300/70 bg-amber-50/70 px-3 py-2 text-sm text-amber-900 dark:border-amber-800/60 dark:bg-amber-950/20 dark:text-amber-100">
                  <span className="font-mono">{diagnostic.code}</span> · {diagnostic.subject}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
      {loading && providers.length === 0 ? <p role="status" className="text-sm text-text-muted">Loading provider connections…</p> : null}
      {!loading && !loadError && providers.length === 0 ? (
        <Card>
          <CardContent className="flex items-start gap-3 py-8">
            <AlertTriangle className="mt-0.5 size-5 text-amber-600" aria-hidden="true" />
            <div>
              <p className="font-medium text-text-main">No conforming AI provider instance is available</p>
              <p className="mt-1 text-sm text-text-muted">Install or select a Pack that declares an AI provider connection contract in the active Profile.</p>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {providers.length > 0 ? (
        <div className="grid gap-5 lg:grid-cols-[minmax(17rem,0.8fr)_minmax(0,1.35fr)]">
          <section aria-label="Provider instances" className="flex flex-col gap-3">
            {providers.map((provider) => (
              <button
                key={provider.instanceId}
                type="button"
                className="min-h-11 rounded-xl border border-border bg-bg-main p-4 text-left transition-colors hover:bg-bg-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring-color)]"
                aria-pressed={provider.instanceId === selectedProvider?.instanceId}
                onClick={() => {
                  setSelectedInstanceId(provider.instanceId);
                  setSelectedAction(null);
                }}
              >
                <span className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold text-text-main">{provider.displayName}</span>
                  <Badge variant={statusVariant(provider.status)}>{provider.status.replaceAll('_', ' ')}</Badge>
                </span>
                <span className="mt-2 block text-xs text-text-muted">{provider.pack.display_name} · {provider.pack.version}</span>
                <span className="mt-1 block break-all font-mono text-[11px] text-text-muted">{provider.instanceId}</span>
              </button>
            ))}
          </section>

          {selectedProvider ? (
            <Card>
              <CardHeader>
                <div className="flex flex-wrap items-center gap-2">
                  <CardTitle>{selectedProvider.displayName}</CardTitle>
                  {selectedProvider.pack.approved ? <Badge variant="success"><ShieldCheck className="mr-1 size-3" aria-hidden="true" />Approved</Badge> : <Badge variant="destructive">Not approved</Badge>}
                  {selectedProvider.credentialPresent ? <Badge variant="outline"><KeyRound className="mr-1 size-3" aria-hidden="true" />Credential stored</Badge> : null}
                </div>
                <CardDescription>{selectedProvider.description ?? 'This Pack did not declare a connection description.'}</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-5">
                <dl className="grid gap-3 text-sm sm:grid-cols-2">
                  <div><dt className="text-text-muted">Authentication</dt><dd className="mt-1 text-text-main">{selectedProvider.authModes.join(', ')}</dd></div>
                  <div><dt className="text-text-muted">Connection</dt><dd className="mt-1 text-text-main">{selectedProvider.configured ? 'Configured' : 'Not configured'}</dd></div>
                  <div><dt className="text-text-muted">Models</dt><dd className="mt-1 text-text-main">{selectedProvider.modelCount ?? 'Unknown'}</dd></div>
                  <div><dt className="text-text-muted">Model catalog refreshed</dt><dd className="mt-1 text-text-main">{selectedProvider.lastRefreshAt ? <time dateTime={selectedProvider.lastRefreshAt}>{new Date(selectedProvider.lastRefreshAt).toLocaleString()}</time> : 'Unknown'}</dd></div>
                  <div><dt className="text-text-muted">Pack state</dt><dd className="mt-1 text-text-main">{selectedProvider.pack.enabled ? 'Enabled' : 'Disabled'} · {selectedProvider.pack.approved ? 'Approved' : 'Unapproved'}</dd></div>
                  <div><dt className="text-text-muted">Multiple instances</dt><dd className="mt-1 text-text-main">{selectedProvider.multiInstance ? 'Supported' : 'Not supported'}</dd></div>
                  <div><dt className="text-text-muted">Network</dt><dd className="mt-1 text-text-main">{selectedProvider.endpointRequirements.networkRequired === true ? 'Required' : selectedProvider.endpointRequirements.localAllowed === true ? 'Local endpoint allowed' : 'Pack-declared'}</dd></div>
                  <div className="sm:col-span-2"><dt className="text-text-muted">Selected by Profile</dt><dd className="mt-1 text-text-main">{selectedProvider.selectedBy.join(', ') || 'Not selected'}</dd></div>
                </dl>
                {selectedProvider.diagnosticCode ? <p role="alert" className="rounded-lg border border-amber-300/70 bg-amber-50/70 px-3 py-2 text-sm text-amber-900 dark:border-amber-800/60 dark:bg-amber-950/20 dark:text-amber-100">{selectedProvider.diagnosticCode}</p> : null}
                <div className="flex flex-wrap gap-2" role="toolbar" aria-label={`${selectedProvider.displayName} connection actions`}>
                  {(Object.keys(selectedProvider.operationIds) as ProviderConnectionAction[]).map((action) => {
                    const operation = selectedProvider.operations[action];
                    const enabled = operation && invokable.some((candidate) => candidate.operation_id === operation.operation_id);
                    return (
                      <Button
                        key={action}
                        type="button"
                        variant={selectedAction === action ? 'default' : 'outline'}
                        disabled={!enabled || invocation.busy}
                        aria-pressed={selectedAction === action}
                        onClick={() => setSelectedAction(action)}
                      >
                        {ACTION_LABELS[action]}
                      </Button>
                    );
                  })}
                </div>
                {selectedOperation ? (
                  <OperationInputForm
                    operation={providerOperationSchema(selectedProvider, selectedOperation)}
                    descriptor={LAUNCHER_ADVANCED_VIEWS.providerConnections}
                    busy={invocation.busy}
                    canInvoke={!invocation.error}
                    onInvoke={invocation.invoke}
                    fixedValues={selectedProvider.instanceField && selectedAction !== 'create_instance'
                      ? {[selectedProvider.instanceField]: selectedProvider.instanceId}
                      : {}}
                    submitLabel={ACTION_LABELS[selectedAction!]}
                    submitAriaLabel={`${ACTION_LABELS[selectedAction!]} for ${selectedProvider.displayName}`}
                  />
                ) : <p className="text-sm text-text-muted">Choose an available declared action. Disabled actions are not authorized by the captured Profile and ResolvedPlan.</p>}
                {invocation.error ? <p role="alert" className="text-sm text-destructive">{invocation.error.message}</p> : null}
                {invocation.state === 'succeeded' ? <p role="status" className="text-sm text-emerald-700 dark:text-emerald-300">The generic provider operation completed.</p> : null}
              </CardContent>
            </Card>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
