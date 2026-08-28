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
import { resolveSetupVerificationState } from '@/src/lib/setupVerification';
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

function profileDisplayName(entry: NamedProfileRecord): string {
  return String(entry.profile.display_name ?? entry.profile_id);
}

function isActiveExecutionProfile(
  registry: NamedProfileRegistry,
  entry: NamedProfileRecord,
): boolean {
  // The registry's active revision is the resolved runtime plan revision. It
  // intentionally differs from the immutable definition revision on a live
  // registry record.
  return registry.active_profile_id === entry.profile_id
    && registry.active_profile_revision !== null;
}

function profileHref(profileId: string, hash?: string): string {
  const query = `?profile_id=${encodeURIComponent(profileId)}`;
  return `${panelRoutes.profile}${query}${hash ? `#${hash}` : ''}`;
}

export function Dashboard() {
  const addToast = useAppStore((state) => state.addToast);
  const showDialog = useAppStore((state) => state.showDialog);
  const isSetupDone = useAppStore((state) => state.isSetupDone);
  const runtimeReady = useAppStore((state) => state.runtimeReady);
  const runtimeStatus = useAppStore((state) => state.runtimeStatus);
  const runtimeError = useAppStore((state) => state.runtimeError);
  const runtimeDisconnected = useAppStore((state) => state.runtimeDisconnected);
  const runtimeVerified = resolveSetupVerificationState({
    isSetupDone,
    runtimeReady,
    runtimeStatus,
    runtimeDisconnected,
  }) === 'verified';

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
      const name = profileDisplayName(entry);
      return !query
        || entry.profile_id.toLocaleLowerCase().includes(query)
        || name.toLocaleLowerCase().includes(query);
    });
  }, [profileQuery, registry]);

  const activeProfile = useMemo(() => {
    if (!registry || !registry.active_profile_id || !registry.active_profile_revision) {
      return null;
    }
    return registry.profiles.find((entry) => isActiveExecutionProfile(registry, entry)) ?? null;
  }, [registry]);

  const commitProfileMutation = async (
    key: string,
    operation: () => Promise<NamedProfileRegistry>,
    successMessage: string,
    throwOnError = false,
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
      if (throwOnError) throw error;
      return false;
    } finally {
      setProfileBusy(null);
    }
    return true;
  };

  const submitNewProfile = async (event: FormEvent) => {
    event.preventDefault();
    const profileId = newProfileId.trim();
    const displayName = newProfileName.trim();
    if (!registry) return;
    if (!profileId || !displayName) {
      setProfileError('Enter a Profile ID and display name before creating a Profile.');
      return;
    }
    const sourceProfileId = registry.active_profile_id ?? registry.profiles[0]?.profile_id;
    if (!sourceProfileId) return;
    const created = await commitProfileMutation(
      'create',
      () => createNamedProfile({
        profile_id: profileId,
        display_name: displayName,
        source_profile_id: sourceProfileId,
        expected_store_generation: registry.generation,
      }),
      `Profile ${displayName} created.`,
    );
    if (!created) return;
    setNewProfileId('');
    setNewProfileName('');
    setShowAddProfile(false);
  };

  const submitProfileName = async (event: FormEvent, entry: NamedProfileRecord) => {
    event.preventDefault();
    if (!registry) return;
    const displayName = editingProfileName.trim();
    if (!displayName) return;
    const updated = await commitProfileMutation(
      `edit:${entry.profile_id}`,
      () => updateNamedProfile({
        profile_id: entry.profile_id,
        display_name: displayName,
        expected_profile_revision: entry.profile_revision,
        expected_store_generation: registry.generation,
      }),
      `Profile ${displayName} updated.`,
    );
    if (!updated) return;
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

  const removeProfile = (entry: NamedProfileRecord) => {
    if (!registry || registry.active_profile_id === entry.profile_id) return;
    const displayName = profileDisplayName(entry);
    showDialog({
      title: `Delete ${displayName}?`,
      message: `This removes ${displayName} from the live Profile registry. Its immutable revision history remains retained by the Host, and the active execution Profile is not changed.`,
      confirmText: 'Delete Profile',
      cancelText: 'Keep Profile',
      onConfirm: async () => {
        await commitProfileMutation(
          `delete:${entry.profile_id}`,
          () => deleteNamedProfile({
            profile_id: entry.profile_id,
            expected_profile_revision: entry.profile_revision,
            expected_store_generation: registry.generation,
          }),
          `Profile ${displayName} deleted.`,
          true,
        );
      },
    });
  };

  const copyRuntimeError = async () => {
    const message = runtimeError || 'The control panel opened, but the background runtime startup failed.';
    const copied = await copyTextToClipboard(message);
    addToast(
      copied ? 'Error copied to clipboard.' : 'Could not copy the error. Please select and copy it manually.',
      copied ? 'success' : 'error',
    );
  };

  if (dashboardLoading && !dashboard.activePacks && !dashboard.supervisor && !registry && !profileError) {
    return <DashboardSkeleton />;
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
            <Button
              aria-controls="add-profile-form"
              aria-expanded={showAddProfile}
              onClick={() => setShowAddProfile((shown) => !shown)}
              type="button"
            >
              <Plus className="h-4 w-4" /> Add Profile
            </Button>
            <Button
              aria-label="Refresh Home and Profiles"
              onClick={() => {
                void refreshDashboard();
                void refreshProfiles();
              }}
              size="icon"
              title="Refresh Home and Profiles"
              type="button"
              variant="outline"
            >
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

        {runtimeStatus === 'error' && (
          <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900/40 dark:bg-red-950/20 dark:text-red-200" role="alert">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-1">
              <span className="font-medium">Runtime could not finish starting.</span>
              <span>{runtimeError || 'Profile launch surfaces remain unavailable until runtime readiness returns.'}</span>
            </div>
            <Button
              aria-label="Copy runtime error message"
              className="h-7 w-7 shrink-0 p-0"
              onClick={() => void copyRuntimeError()}
              size="icon"
              title="Copy runtime error message"
              type="button"
              variant="ghost"
            >
              <Copy className="h-3.5 w-3.5" />
            </Button>
          </div>
        )}

        {!runtimeReady && runtimeStatus === 'panel_ready' && (
          <div className="flex items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-200">
            <TobkiriLoadingMark />
            <span className="flex-1">Runtime is still preparing. Packs are available now, and launch surfaces will open after readiness.</span>
          </div>
        )}

        <section className="rounded-xl border border-border bg-bg-card p-5" aria-labelledby="active-execution-title">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h2 id="active-execution-title" className="text-base font-semibold text-text-main">Active execution Profile</h2>
              <p className="mt-1 text-sm text-text-muted">
                This is the Profile used by runtime execution. Browsing another Profile below never changes it.
              </p>
            </div>
            {activeProfile ? <Badge variant="success">Active execution</Badge> : <Badge variant="warning">Not published</Badge>}
          </div>
          {activeProfile ? (
            <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-border bg-bg-main px-4 py-3">
              <span className="font-medium text-text-main">{profileDisplayName(activeProfile)}</span>
              <span className="font-mono text-xs text-text-muted">{activeProfile.profile_id}</span>
              <span className="font-mono text-xs text-text-muted" title={activeProfile.profile_revision}>
                definition revision {activeProfile.profile_revision}
              </span>
              <span className="font-mono text-xs text-text-muted" title={registry.active_profile_revision}>
                execution revision {registry.active_profile_revision}
              </span>
            </div>
          ) : (
            <p className="mt-4 rounded-lg border border-dashed border-border px-4 py-3 text-sm text-text-muted" role="status">
              No active execution Profile is published in the Host registry.
            </p>
          )}
        </section>

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
            <form
              aria-describedby="add-profile-help"
              className="mt-4 grid gap-3 rounded-lg border border-border bg-bg-main p-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end"
              id="add-profile-form"
              onSubmit={submitNewProfile}
            >
              <label className="space-y-1.5 text-sm font-medium text-text-main">
                <span>Profile ID <span className="text-destructive" aria-hidden="true">*</span></span>
                <input
                  aria-label="New Profile ID"
                  className="h-9 w-full rounded-lg border border-border bg-bg-card px-3 text-sm font-normal text-text-main"
                  maxLength={80}
                  onChange={(event) => setNewProfileId(event.target.value)}
                  pattern="[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*"
                  placeholder="profile-id"
                  required
                  value={newProfileId}
                />
              </label>
              <label className="space-y-1.5 text-sm font-medium text-text-main">
                <span>Display name <span className="text-destructive" aria-hidden="true">*</span></span>
                <input
                  aria-label="New Profile name"
                  className="h-9 w-full rounded-lg border border-border bg-bg-card px-3 text-sm font-normal text-text-main"
                  maxLength={120}
                  onChange={(event) => setNewProfileName(event.target.value)}
                  placeholder="Display name"
                  required
                  value={newProfileName}
                />
              </label>
              <div className="flex flex-col gap-2">
                <span className="sr-only" id="add-profile-help">Create a named Profile from the active execution Profile.</span>
                <Button disabled={!registry || profileBusy === 'create'} size="sm" type="submit">
                  <Plus className="h-3.5 w-3.5" /> Create
                </Button>
              </div>
            </form>
          )}

          {profileError && (
            <div aria-live="assertive" className="mt-4 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-950/20 dark:text-red-200" role="alert">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span className="flex-1">{profileError}</span>
              <Button onClick={() => void refreshProfiles()} size="sm" type="button" variant="ghost">Retry</Button>
            </div>
          )}

          <div aria-live="polite" className="mt-4 space-y-3">
            {!registry && !profileError && (
              <div className="flex items-center justify-center py-8"><TobkiriLoadingMark /></div>
            )}
            {registry && visibleProfiles.length === 0 && (
              <p className="py-8 text-center text-sm text-text-muted">No Profiles match this search.</p>
            )}
            {visibleProfiles.map((entry) => {
              const active = registry ? isActiveExecutionProfile(registry, entry) : false;
              const displayName = profileDisplayName(entry);
              const busy = profileBusy?.endsWith(entry.profile_id) ?? false;
              const browseHref = profileHref(entry.profile_id);
              const closureHref = profileHref(entry.profile_id, 'profile-closure');
              const activationHref = profileHref(entry.profile_id, 'profile-ceremony');
              return (
                <article
                  aria-labelledby={`profile-${entry.profile_id}-title`}
                  className="rounded-lg border border-border bg-bg-main p-4"
                  data-profile-id={entry.profile_id}
                  key={entry.profile_id}
                >
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="truncate font-medium text-text-main" id={`profile-${entry.profile_id}-title`}>{displayName}</h3>
                        {active && <Badge variant="success">Active execution</Badge>}
                        {!active && <Badge variant="outline">Browsing only</Badge>}
                        <Badge variant="outline">{entry.profile_id}</Badge>
                      </div>
                      <p className="mt-1 truncate font-mono text-[11px] text-text-muted" title={entry.profile_revision}>
                        revision {entry.profile_revision}
                      </p>
                      <p className="mt-1 text-xs text-text-muted">
                        {active ? 'Runtime execution uses this Profile.' : 'Inspect and prepare this Profile without changing runtime execution.'}
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Link
                        aria-label={`Browse and review ${displayName}`}
                        className="inline-flex min-h-11 items-center justify-center rounded-md border border-border bg-bg-main px-3 text-xs font-medium hover:bg-bg-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring-color)] focus-visible:ring-offset-2"
                        to={browseHref}
                      >
                        <span>Browse &amp; review</span>
                      </Link>
                      <Link
                        aria-label={`View Pack closure for ${displayName}`}
                        className="inline-flex min-h-11 items-center justify-center gap-2 rounded-md border border-border bg-bg-main px-3 text-xs font-medium hover:bg-bg-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring-color)] focus-visible:ring-offset-2"
                        to={closureHref}
                      >
                        <Package className="h-3.5 w-3.5" /> Pack closure
                      </Link>
                      {!active && (
                        <Link
                          aria-label={`Activate ${displayName}`}
                          aria-disabled={!runtimeVerified}
                          className={runtimeVerified
                            ? 'inline-flex min-h-11 items-center justify-center rounded-md bg-accent px-3 text-xs font-medium text-accent-fg hover:bg-accent/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring-color)] focus-visible:ring-offset-2'
                            : 'inline-flex min-h-11 cursor-not-allowed items-center justify-center rounded-md bg-accent/50 px-3 text-xs font-medium text-accent-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring-color)] focus-visible:ring-offset-2'}
                          onClick={(event) => {
                            if (!runtimeVerified) event.preventDefault();
                          }}
                          to={activationHref}
                          tabIndex={runtimeVerified ? undefined : -1}
                          title={runtimeVerified ? undefined : 'Complete Setup verification before activating a Profile'}
                        >
                          {runtimeVerified ? 'Activate' : 'Activate (Setup required)'}
                        </Link>
                      )}
                      <Button
                        aria-label={`Edit ${displayName}`}
                        className="min-h-11 min-w-11"
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
                        className="min-h-11 min-w-11"
                        disabled={busy}
                        onClick={() => void duplicateProfile(entry)}
                        size="icon"
                        variant="ghost"
                      ><Copy className="h-3.5 w-3.5" /></Button>
                      <Button
                        aria-label={`Delete ${displayName}`}
                        className="min-h-11 min-w-11"
                        disabled={active || busy}
                        onClick={() => void removeProfile(entry)}
                        size="icon"
                        title={active ? 'Switch away before deleting this Profile' : 'Delete Profile'}
                        variant="ghost"
                      ><Trash2 className="h-3.5 w-3.5" /></Button>
                    </div>
                  </div>
                  {editingProfileId === entry.profile_id && (
                    <form className="mt-3 flex flex-wrap items-end gap-2 border-t border-border pt-3" onSubmit={(event) => void submitProfileName(event, entry)}>
                      <label className="min-w-0 flex-1 space-y-1.5 text-sm font-medium text-text-main">
                        <span>Display name</span>
                        <input
                          aria-label={`Display name for ${entry.profile_id}`}
                          className="h-9 w-full rounded-lg border border-border bg-bg-card px-3 text-sm font-normal text-text-main"
                          maxLength={120}
                          onChange={(event) => setEditingProfileName(event.target.value)}
                          required
                          value={editingProfileName}
                        />
                      </label>
                      <Button disabled={busy} size="sm" type="submit">Save</Button>
                      <Button onClick={() => setEditingProfileId(null)} size="sm" type="button" variant="ghost">Cancel</Button>
                    </form>
                  )}
                  <div className="mt-4 border-t border-border pt-4">
                    <ShellLaunchCard
                      activationHref={activationHref}
                      active={active}
                      profileDisplayName={displayName}
                      profileId={entry.profile_id}
                      runtimeReady={runtimeVerified}
                    />
                  </div>
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
