import { FormEvent, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router';
import {
  fetchDashboard,
  createNamedProfile,
  deleteNamedProfile,
  duplicateNamedProfile,
  fetchNamedProfiles,
  updateNamedProfile,
  type NamedProfileRecord,
  type NamedProfileRegistry,
} from '@/src/lib/api';
import { useAppStore } from '@/src/store';
import { TobkiriLoader, TobkiriLoadingMark } from '@/src/components/ui/TobkiriLoader';
import {
  AlertCircle,
  Copy,
  Monitor,
  Route,
  ShieldCheck,
  Terminal,
  Cloud,
  Package,
  Workflow,
  Pencil,
  Plus,
  Search,
  Trash2,
} from 'lucide-react';
import { Button } from '@/src/components/ui/Button';
import { Badge } from '@/src/components/ui/Badge';
import { transformDashboard } from '@/src/lib/transforms';
import type { DashboardData } from '@/src/store';
import { panelRoutes } from '@/src/lib/routes';
import { ShellLaunchCard } from '@/src/components/presentation/ShellLaunchCard';

const defaultDashboard: DashboardData = {
  kernelStatus: 'stopped',
  uptime: '--',
  activePacks: 0,
  registeredFlows: 0,
  activities: [],
  supervisor: null,
};

export async function copyTextToClipboard(
  text: string,
  clipboard: Pick<Clipboard, 'writeText'> | undefined = typeof navigator === 'undefined'
    ? undefined
    : navigator.clipboard,
): Promise<boolean> {
  if (!clipboard) return false;

  try {
    await clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

export function nextDuplicateProfileId(
  profileId: string,
  existingProfileIds: Iterable<string>,
): string {
  const baseId = `${profileId}-copy`;
  const usedIds = new Set(existingProfileIds);
  let candidate = baseId;
  let suffix = 2;
  while (usedIds.has(candidate)) {
    candidate = `${baseId}-${suffix}`;
    suffix += 1;
  }
  return candidate;
}

export function Dashboard() {
  const addToast = useAppStore((state) => state.addToast);
  const runtimeReady = useAppStore((state) => state.runtimeReady);
  const runtimeStatus = useAppStore((state) => state.runtimeStatus);
  const runtimeError = useAppStore((state) => state.runtimeError);

  const [dashboard, setDashboard] = useState<DashboardData>(defaultDashboard);
  const [dashboardLoading, setDashboardLoading] = useState(true);
  const [dashboardError, setDashboardError] = useState<string | null>(null);
  const [registry, setRegistry] = useState<NamedProfileRegistry | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [profileBusy, setProfileBusy] = useState<string | null>(null);
  const [profileQuery, setProfileQuery] = useState('');
  const [newProfileId, setNewProfileId] = useState('');
  const [newProfileName, setNewProfileName] = useState('');
  const [showAddProfile, setShowAddProfile] = useState(false);
  const [editingProfileId, setEditingProfileId] = useState<string | null>(null);
  const [editingProfileName, setEditingProfileName] = useState('');

  const refreshDashboard = async () => {
    setDashboardLoading(true);
    try {
      const response = await fetchDashboard();
      setDashboard(transformDashboard(response));
      setDashboardError(null);
    } catch (error) {
      const rawMessage = error instanceof Error ? error.message : '';
      setDashboardError(rawMessage || 'Failed to load your workspace summary.');
    } finally {
      setDashboardLoading(false);
    }
  };

  const refreshProfiles = async () => {
    try {
      setRegistry(await fetchNamedProfiles());
      setProfileError(null);
    } catch (error) {
      setProfileError(error instanceof Error ? error.message : 'Named Profiles could not be loaded.');
    }
  };

  useEffect(() => {
    if (runtimeReady) {
      void refreshDashboard();
    } else {
      setDashboardLoading(false);
    }
  }, [runtimeReady]);

  useEffect(() => {
    void refreshProfiles();
  }, []);

  const visibleProfiles = useMemo(() => {
    const query = profileQuery.trim().toLocaleLowerCase();
    return (registry?.profiles ?? []).filter((entry) => {
      const name = String(entry.profile.display_name ?? entry.profile_id);
      return !query
        || entry.profile_id.toLocaleLowerCase().includes(query)
        || name.toLocaleLowerCase().includes(query);
    });
  }, [profileQuery, registry]);

  const commitProfileMutation = async (
    key: string,
    operation: () => Promise<NamedProfileRegistry>,
    successMessage: string,
  ) => {
    setProfileBusy(key);
    try {
      setRegistry(await operation());
      setProfileError(null);
      addToast(successMessage, 'success');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Profile mutation was rejected.';
      setProfileError(message);
      addToast(message, 'error');
    } finally {
      setProfileBusy(null);
    }
  };

  const submitNewProfile = async (event: FormEvent) => {
    event.preventDefault();
    const profileId = newProfileId.trim();
    const displayName = newProfileName.trim();
    if (!profileId || !displayName || !registry) return;
    const sourceProfileId = registry.active_profile_id ?? registry.profiles[0]?.profile_id;
    if (!sourceProfileId) return;
    await commitProfileMutation(
      'create',
      () => createNamedProfile({
        profile_id: profileId,
        display_name: displayName,
        source_profile_id: sourceProfileId,
        expected_store_generation: registry.generation,
      }),
      `Profile ${displayName} created.`,
    );
    setNewProfileId('');
    setNewProfileName('');
    setShowAddProfile(false);
  };

  const submitProfileName = async (event: FormEvent, entry: NamedProfileRecord) => {
    event.preventDefault();
    if (!registry) return;
    const displayName = editingProfileName.trim();
    if (!displayName) return;
    await commitProfileMutation(
      `edit:${entry.profile_id}`,
      () => updateNamedProfile({
        profile_id: entry.profile_id,
        display_name: displayName,
        expected_profile_revision: entry.profile_revision,
        expected_store_generation: registry.generation,
      }),
      `Profile ${displayName} updated.`,
    );
    setEditingProfileId(null);
    setEditingProfileName('');
  };

  const duplicateProfile = async (entry: NamedProfileRecord) => {
    if (!registry) return;
    const candidate = nextDuplicateProfileId(
      entry.profile_id,
      registry.profiles.map((profile) => profile.profile_id),
    );
    const displayName = `${String(entry.profile.display_name ?? entry.profile_id)} Copy`;
    await commitProfileMutation(
      `duplicate:${entry.profile_id}`,
      () => duplicateNamedProfile({
        profile_id: entry.profile_id,
        new_profile_id: candidate,
        display_name: displayName,
        expected_profile_revision: entry.profile_revision,
        expected_store_generation: registry.generation,
      }),
      `Profile ${displayName} created.`,
    );
  };

  const removeProfile = async (entry: NamedProfileRecord) => {
    if (!registry || registry.active_profile_id === entry.profile_id) return;
    await commitProfileMutation(
      `delete:${entry.profile_id}`,
      () => deleteNamedProfile({
        profile_id: entry.profile_id,
        expected_profile_revision: entry.profile_revision,
        expected_store_generation: registry.generation,
      }),
      `Profile ${String(entry.profile.display_name ?? entry.profile_id)} deleted.`,
    );
  };

  const copyRuntimeError = async () => {
    const message = runtimeError || 'The control panel opened, but the background runtime startup failed.';
    const copied = await copyTextToClipboard(message);
    addToast(
      copied ? 'Error copied to clipboard.' : 'Could not copy the error. Please select and copy it manually.',
      copied ? 'success' : 'error',
    );
  };

  if (runtimeStatus === 'error' && !dashboardLoading && !dashboard.activePacks && !dashboard.supervisor) {
    return (
      <div className="flex flex-1 items-center justify-center px-6">
        <div className="flex max-w-md flex-col gap-4 rounded-xl border border-red-200 bg-red-50 p-6 dark:border-red-900/40 dark:bg-red-950/20">
          <div className="flex items-start gap-3">
            <AlertCircle className="mt-0.5 h-5 w-5 text-red-500 shrink-0" />
            <div className="space-y-1">
              <h2 className="text-base font-semibold text-text-main">Runtime could not finish starting</h2>
              <div className="flex items-start gap-1">
                <p className="text-sm text-text-muted">{runtimeError || 'The control panel opened, but the background runtime startup failed.'}</p>
                <Button
                  aria-label="Copy error message"
                  className="h-7 w-7 shrink-0 p-0"
                  onClick={() => void copyRuntimeError()}
                  size="icon"
                  title="Copy error message"
                  variant="ghost"
                >
                  <Copy className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          </div>
          <div className="flex justify-end">
            <Button onClick={() => window.location.reload()} size="sm"><AlertCircle className="h-3.5 w-3.5" /> Reload</Button>
          </div>
        </div>
      </div>
    );
  }

  if (dashboardLoading && !dashboard.activePacks && !dashboard.supervisor) {
    return <DashboardSkeleton />;
  }

  if (dashboardError && !dashboard.activePacks && !dashboard.supervisor) {
    return (
      <div className="flex flex-1 items-center justify-center px-6">
        <div className="flex max-w-md flex-col gap-4 rounded-xl border border-border bg-bg-card p-6">
          <div className="flex items-start gap-3">
            <AlertCircle className="mt-0.5 h-5 w-5 text-red-500 shrink-0" />
            <div className="space-y-1">
              <h2 className="text-base font-semibold text-text-main">Home could not load</h2>
              <p className="text-sm text-text-muted">{dashboardError}</p>
            </div>
          </div>
          <div className="flex justify-end">
            <Button onClick={() => void refreshDashboard()} size="sm"><Route className="h-3.5 w-3.5" /> Retry</Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 overflow-hidden">
      <div className="mx-auto flex w-full max-w-[1100px] flex-col gap-6 px-6 py-8 lg:px-10 scrollbar-hidden overflow-y-auto page-enter">
        {/* Header section */}
        <section className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-text-main">Home</h1>
            <p className="mt-1 text-sm text-text-muted">Browse every Profile without changing the active execution Profile.</p>
          </div>
          <div className="flex items-center gap-3">
            <Button onClick={() => setShowAddProfile((shown) => !shown)}>
              <Plus className="h-4 w-4" /> Add Profile
            </Button>
            <Button variant="outline" size="icon" title="Refresh" onClick={() => {
              void refreshDashboard();
              void refreshProfiles();
            }}>
              <Route className="h-4 w-4" />
            </Button>
          </div>
        </section>

        {dashboardError && (
          <div className="flex items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-200">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span className="flex-1">{dashboardError}</span>
            <Button variant="ghost" size="sm" onClick={() => void refreshDashboard()}>
              <Route className="h-3.5 w-3.5" /> Retry
            </Button>
          </div>
        )}

        {!runtimeReady && runtimeStatus === 'panel_ready' && (
          <div className="flex items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-200">
            <TobkiriLoadingMark />
            <span className="flex-1">Runtime is still preparing. Packs are available now, and launch surfaces will open after readiness.</span>
          </div>
        )}

        <section className="rounded-xl border border-border bg-bg-card p-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-base font-semibold text-text-main">Profiles</h2>
              <p className="mt-1 text-xs text-text-muted">
                Selection only changes what you inspect. Activation always uses the v4 review and approval ceremony.
              </p>
            </div>
            <label className="relative block sm:w-72">
              <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-text-muted" />
              <input
                aria-label="Search Profiles"
                className="h-9 w-full rounded-lg border border-border bg-bg-main pl-9 pr-3 text-sm text-text-main outline-none focus:border-accent"
                onChange={(event) => setProfileQuery(event.target.value)}
                placeholder="Search Profiles"
                value={profileQuery}
              />
            </label>
          </div>

          {showAddProfile && (
            <form className="mt-4 grid gap-3 rounded-lg border border-border bg-bg-main p-4 sm:grid-cols-[1fr_1fr_auto]" onSubmit={submitNewProfile}>
              <input
                aria-label="New Profile ID"
                className="h-9 rounded-lg border border-border bg-bg-card px-3 text-sm text-text-main"
                onChange={(event) => setNewProfileId(event.target.value)}
                placeholder="profile-id"
                value={newProfileId}
              />
              <input
                aria-label="New Profile name"
                className="h-9 rounded-lg border border-border bg-bg-card px-3 text-sm text-text-main"
                onChange={(event) => setNewProfileName(event.target.value)}
                placeholder="Display name"
                value={newProfileName}
              />
              <Button disabled={!registry || profileBusy === 'create'} size="sm" type="submit">
                <Plus className="h-3.5 w-3.5" /> Create
              </Button>
            </form>
          )}

          {profileError && (
            <div className="mt-4 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-950/20 dark:text-red-200">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span className="flex-1">{profileError}</span>
              <Button onClick={() => void refreshProfiles()} size="sm" variant="ghost">Retry</Button>
            </div>
          )}

          <div className="mt-4 space-y-3">
            {!registry && !profileError && (
              <div className="flex items-center justify-center py-8"><TobkiriLoadingMark /></div>
            )}
            {registry && visibleProfiles.length === 0 && (
              <p className="py-8 text-center text-sm text-text-muted">No Profiles match this search.</p>
            )}
            {visibleProfiles.map((entry) => {
              const active = registry?.active_profile_id === entry.profile_id;
              const displayName = String(entry.profile.display_name ?? entry.profile_id);
              const busy = profileBusy?.endsWith(entry.profile_id) ?? false;
              return (
                <article className="rounded-lg border border-border bg-bg-main p-4" key={entry.profile_id}>
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="truncate font-medium text-text-main">{displayName}</h3>
                        {active && <Badge variant="success">Active execution</Badge>}
                        <Badge variant="outline">{entry.profile_id}</Badge>
                      </div>
                      <p className="mt-1 truncate font-mono text-[11px] text-text-muted" title={entry.profile_revision}>
                        revision {entry.profile_revision}
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Link
                        className="inline-flex h-8 items-center justify-center rounded-md border border-border bg-bg-main px-3 text-xs font-medium hover:bg-bg-hover"
                        to={`${panelRoutes.profile}?profile_id=${encodeURIComponent(entry.profile_id)}`}
                      >
                        Browse &amp; review
                      </Link>
                      <Link
                        className="inline-flex h-8 items-center justify-center gap-2 rounded-md border border-border bg-bg-main px-3 text-xs font-medium hover:bg-bg-hover"
                        to={`${panelRoutes.profile}?profile_id=${encodeURIComponent(entry.profile_id)}#profile-closure`}
                      >
                        <Package className="h-3.5 w-3.5" /> Pack closure
                      </Link>
                      <Button
                        aria-label={`Edit ${displayName}`}
                        disabled={busy}
                        onClick={() => {
                          setEditingProfileId(entry.profile_id);
                          setEditingProfileName(displayName);
                        }}
                        size="icon"
                        variant="ghost"
                      ><Pencil className="h-3.5 w-3.5" /></Button>
                      <Button
                        aria-label={`Duplicate ${displayName}`}
                        disabled={busy}
                        onClick={() => void duplicateProfile(entry)}
                        size="icon"
                        variant="ghost"
                      ><Copy className="h-3.5 w-3.5" /></Button>
                      <Button
                        aria-label={`Delete ${displayName}`}
                        disabled={active || busy}
                        onClick={() => void removeProfile(entry)}
                        size="icon"
                        title={active ? 'Switch away before deleting this Profile' : 'Delete Profile'}
                        variant="ghost"
                      ><Trash2 className="h-3.5 w-3.5" /></Button>
                    </div>
                  </div>
                  {editingProfileId === entry.profile_id && (
                    <form className="mt-3 flex gap-2 border-t border-border pt-3" onSubmit={(event) => void submitProfileName(event, entry)}>
                      <input
                        aria-label={`Display name for ${entry.profile_id}`}
                        className="h-9 min-w-0 flex-1 rounded-lg border border-border bg-bg-card px-3 text-sm text-text-main"
                        onChange={(event) => setEditingProfileName(event.target.value)}
                        value={editingProfileName}
                      />
                      <Button disabled={busy} size="sm" type="submit">Save</Button>
                      <Button onClick={() => setEditingProfileId(null)} size="sm" type="button" variant="ghost">Cancel</Button>
                    </form>
                  )}
                  {active && (
                    <div className="mt-4 border-t border-border pt-4">
                      <ShellLaunchCard
                        profileDisplayName={displayName}
                        profileId={entry.profile_id}
                        runtimeReady={runtimeReady}
                      />
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        </section>

        {/* Summary tiles */}
        <section className="grid gap-4 sm:grid-cols-3">
          <Link
            to={panelRoutes.packs}
            className="rounded-xl border border-border bg-bg-card p-5 transition hover:border-accent/25 hover:bg-bg-hover/40"
          >
            <div className="flex items-center gap-2">
              <Package className="h-4 w-4 text-accent" />
              <h2 className="text-sm font-semibold text-text-main">Active Packs</h2>
            </div>
            <div className="mt-3 text-3xl font-semibold tracking-tight text-text-main">{dashboard.activePacks}</div>
            <p className="mt-1 text-xs text-text-muted">Enabled in the current v4 Profile</p>
          </Link>
          <div className="rounded-xl border border-border bg-bg-card p-5">
            <div className="flex items-center gap-2">
              <Workflow className="h-4 w-4 text-accent" />
              <h2 className="text-sm font-semibold text-text-main">Flows</h2>
            </div>
            <div className="mt-3 text-3xl font-semibold tracking-tight text-text-main">{dashboard.registeredFlows}</div>
            <p className="mt-1 text-xs text-text-muted">Registered flow definitions</p>
          </div>
          <div className="rounded-xl border border-border bg-bg-card p-5">
            <div className="flex items-center gap-2">
              <Monitor className="h-4 w-4 text-accent" />
              <h2 className="text-sm font-semibold text-text-main">Kernel</h2>
            </div>
            <div className="mt-3 flex items-center gap-2">
              <span className={`h-2.5 w-2.5 rounded-full ${
                dashboard.kernelStatus === 'running' ? 'bg-emerald-500' : 'bg-amber-500'
              }`} />
              <span className="text-xl font-semibold tracking-tight text-text-main">
                {dashboard.kernelStatus === 'running' ? 'Running' : 'Stopped'}
              </span>
            </div>
            <p className="mt-1 text-xs text-text-muted">Uptime: {dashboard.uptime}</p>
          </div>
        </section>

        {/* Supervisor Snapshot */}
        <SupervisorSnapshot
          data={dashboard.supervisor}
          loading={dashboardLoading && !dashboard.supervisor}
          error={dashboardError}
        />
      </div>
    </div>
  );
}

function SupervisorSnapshot({
  data,
  loading,
  error,
}: {
  data: DashboardData['supervisor'];
  loading: boolean;
  error: string | null;
}) {
  const router = data?.router ?? null;
  const metrics = data?.metrics ?? null;
  const defaultSandbox = data?.sandbox_providers.find((provider) => provider.default) ?? null;
  const localSandbox = data?.sandbox_providers.find((provider) => provider.id === 'local_packaged') ?? null;
  const selectedSession = data?.selected_session ?? null;
  const computerLayer = router?.fallback_layers.find((layer) => layer.id === 'computer_use') ?? null;
  const recentEvent = data?.recent_events[0] ?? null;
  const macDriverOrder = router?.computer_driver_order.darwin ?? [];
  const routeCount = (router?.operation_layers.length ?? 0) + (router?.fallback_layers.length ?? 0);
  const capabilities = data?.capabilities ?? null;

  if (!data) {
    return (
      <section className="rounded-xl border border-border bg-bg-card p-5">
        <div className="flex items-center gap-3">
          <Monitor className="h-4 w-4 text-text-muted" />
          <div className="min-w-0 flex-1">
            <h2 className="text-sm font-semibold text-text-main">Supervisor Snapshot</h2>
            <p className="text-xs text-text-muted">
              {loading ? 'Loading runtime snapshot...' : error || 'Runtime snapshot unavailable.'}
            </p>
          </div>
          {loading && <TobkiriLoadingMark />}
        </div>
      </section>
    );
  }

  return (
    <section className="grid gap-4 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)_minmax(0,1fr)]">
      <article className="min-w-0 rounded-xl border border-border bg-bg-card p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            <Route className="h-4 w-4 text-accent" />
            <h2 className="text-sm font-semibold text-text-main">Runtime Router</h2>
          </div>
          <Badge variant="secondary" className="text-[10px]">{formatRuntimeLabel(router?.policy)}</Badge>
        </div>
        <div className="mt-4 grid grid-cols-3 gap-2 text-center">
          <MetricTile label="Routes" value={String(routeCount || '--')} />
          <MetricTile label="Structured" value={String(router?.operation_layers.length ?? '--')} />
          <MetricTile label="Fallback" value={String(router?.fallback_layers.length ?? '--')} />
        </div>
        <div className="mt-4 space-y-2">
          <div className="flex items-center justify-between gap-3 text-xs">
            <span className="text-text-muted">First layer</span>
            <span className="truncate text-text-main">{router?.operation_layers[0]?.label ?? '--'}</span>
          </div>
          <div className="flex items-center justify-between gap-3 text-xs">
            <span className="text-text-muted">Last layer</span>
            <span className="truncate text-text-main">{computerLayer?.label ?? 'Computer use'}</span>
          </div>
          <div className="flex items-center gap-2 text-xs text-text-muted">
            <Terminal className="h-3.5 w-3.5" />
            <span className="truncate">{formatCompactList(macDriverOrder.slice(0, 4))}</span>
          </div>
        </div>
      </article>

      <article className="min-w-0 rounded-xl border border-border bg-bg-card p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            <Cloud className="h-4 w-4 text-accent" />
            <h2 className="text-sm font-semibold text-text-main">Sandbox Providers</h2>
          </div>
          <Badge variant="success" className="text-[10px]">{defaultSandbox?.tier ?? 'default'}</Badge>
        </div>
        <div className="mt-4 space-y-3">
          <ProviderRow provider={defaultSandbox} />
          <ProviderRow provider={localSandbox} />
        </div>
        <div className="mt-4 flex items-center gap-2 text-xs text-text-muted">
          <ShieldCheck className="h-3.5 w-3.5" />
          <span className="truncate">{formatCompactList(data.security_guardrails.slice(0, 3))}</span>
        </div>
      </article>

      <article className="min-w-0 rounded-xl border border-border bg-bg-card p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            <Monitor className="h-4 w-4 text-accent" />
            <h2 className="text-sm font-semibold text-text-main">Run Snapshot</h2>
          </div>
          <Badge variant={capabilities?.snapshot ? 'success' : 'secondary'} className="text-[10px]">
            {capabilities?.snapshot ? 'Snapshot' : 'Unavailable'}
          </Badge>
        </div>
        <div className="mt-4 grid grid-cols-4 gap-2 text-center">
          <MetricTile label="Active" value={String(metrics?.active_runs ?? 0)} />
          <MetricTile label="Approval" value={String(metrics?.waiting_approvals ?? 0)} />
          <MetricTile label="Stale" value={String(metrics?.stale_runs ?? 0)} />
          <MetricTile label="Failed" value={String(metrics?.failed_runs ?? 0)} />
        </div>
        <div className="mt-4 space-y-2 text-xs">
          <div className="flex items-center justify-between gap-3">
            <span className="text-text-muted">Run</span>
            <span className="truncate text-text-main">{selectedSession?.run_id ?? 'No run snapshot'}</span>
          </div>
          <div className="flex items-center justify-between gap-3">
            <span className="text-text-muted">Last event</span>
            <span className="truncate text-text-main">{recentEvent?.event_type ?? '--'}</span>
          </div>
          <CapabilityRow label="Live screen" enabled={capabilities?.live_screen === true} />
          <CapabilityRow label="Takeover" enabled={capabilities?.takeover === true} />
          <CapabilityRow label="Replay" enabled={capabilities?.replay === true} />
        </div>
      </article>
    </section>
  );
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-bg-hover/40 px-2 py-2">
      <div className="text-[11px] text-text-muted">{label}</div>
      <div className="mt-1 text-sm font-semibold text-text-main">{value}</div>
    </div>
  );
}

function CapabilityRow({ label, enabled }: { label: string; enabled: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-text-muted">{label}</span>
      <span className={enabled ? 'truncate text-text-main' : 'truncate text-text-muted'}>
        {enabled ? 'Available' : 'Not available'}
      </span>
    </div>
  );
}

function ProviderRow({ provider }: { provider: NonNullable<DashboardData['supervisor']>['sandbox_providers'][number] | null }) {
  if (!provider) {
    return null;
  }
  return (
    <div className="flex items-start justify-between gap-3 rounded-lg border border-border bg-bg-hover/40 px-3 py-2">
      <div className="min-w-0">
        <div className="truncate text-xs font-medium text-text-main">{provider.label}</div>
        <div className="mt-0.5 truncate text-[11px] text-text-muted">{formatCompactList(provider.providers.slice(0, 4))}</div>
      </div>
      <Badge variant={provider.default ? 'success' : 'secondary'} className="shrink-0 text-[10px]">
        {provider.default ? 'Default' : formatRuntimeLabel(provider.user_burden)}
      </Badge>
    </div>
  );
}

function formatRuntimeLabel(value: string | undefined): string {
  if (!value) return '--';
  return value.replaceAll('_', ' ');
}

function formatCompactList(values: string[]): string {
  if (!values.length) return '--';
  return values.map(formatRuntimeLabel).join(' / ');
}

function DashboardSkeleton() {
  return <TobkiriLoader label="Loading Tobkiri home..." />;
}
