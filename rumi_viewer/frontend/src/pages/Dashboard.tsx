import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  activateStartupProfile,
  addPackToStartupProfile,
  clearStartupProfileNodeOverride,
  compileStartupProfilePreview,
  createStartupProfile,
  deleteStartupProfile,
  duplicateStartupProfile,
  fetchDashboard,
  fetchStartupProfiles,
  launchStartupProfile,
  removePackFromStartupProfile,
  restartKernel,
  setStartupProfileNodeOverride,
  updateStartupProfile,
} from '@/src/lib/api';
import type {
  ApiStartupProfile,
  StartupProfileCompilePreviewResponseData,
  StartupProfilesResponseData,
} from '@/src/lib/apiTypes';
import {
  buildStartupProfileView,
  compatibleNodesForPort,
  defaultBasePack,
  describeStartupActionError,
  describeStartupIssue,
  filterAndSortStartupProfiles,
  packLabel,
  titleCasePortKey,
  type StartupSortMode,
} from '@/src/lib/startupProfiles';
import { transformDashboard } from '@/src/lib/transforms';
import { useAppStore, type DashboardData } from '@/src/store';
import {
  AlertCircle,
  ArrowLeft,
  Box,
  CheckCircle2,
  Copy,
  Loader2,
  MoreHorizontal,
  Plus,
  RefreshCw,
  Rocket,
  Save,
  Search,
  Star,
  Trash2,
} from 'lucide-react';
import { Popover, PopoverTrigger, PopoverContent } from '@/src/components/ui/Popover';
import { Button } from '@/src/components/ui/Button';
import { Badge } from '@/src/components/ui/Badge';
import { ConstellationMap, type ConstellationNode, type ConstellationEdge } from '@/src/cosmos/ConstellationMap';
import { CosmosLogo } from '@/src/cosmos/CosmosLogo';
import { COSMOS_DECOR, hideOnError } from '@/src/cosmos/assets';
import { cn } from '@/src/lib/utils';
import type { StartupProfileView } from '@/src/lib/startupProfiles';

type ActionState = 'activate' | 'create' | 'delete' | 'duplicate' | 'launch' | 'restart' | 'save';

const defaultDashboard: DashboardData = {
  kernelStatus: 'stopped',
  uptime: '--',
  activePacks: 0,
  registeredFlows: 0,
  activities: [],
};
const INITIAL_PROFILE_LOAD_MAX_ATTEMPTS = 3;
const INITIAL_PROFILE_LOAD_RETRY_DELAY_MS = 900;

function formatTimestamp(timestamp: number): string {
  if (!timestamp) return '--';
  return new Date(timestamp * 1000).toLocaleString();
}

function shouldRetryInitialProfileLoad(errorMessage: string): boolean {
  return /Unauthorized|Invalid or expired code|Too many requests|429|Failed to fetch|NetworkError/i.test(errorMessage);
}

export function Dashboard() {
  const addToast = useAppStore((state) => state.addToast);
  const showDialog = useAppStore((state) => state.showDialog);
  const closeDialog = useAppStore((state) => state.closeDialog);
  const runtimeReady = useAppStore((state) => state.runtimeReady);
  const runtimeStatus = useAppStore((state) => state.runtimeStatus);
  const runtimeError = useAppStore((state) => state.runtimeError);
  const [searchParams, setSearchParams] = useSearchParams();

  const [dashboard, setDashboard] = useState<DashboardData>(defaultDashboard);
  const [dashboardLoading, setDashboardLoading] = useState(true);
  const [dashboardError, setDashboardError] = useState<string | null>(null);

  const [payload, setPayload] = useState<StartupProfilesResponseData | null>(null);
  const [profilesLoading, setProfilesLoading] = useState(true);
  const [profilesError, setProfilesError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ message: string; tone: 'error' | 'success' } | null>(null);
  const [actionState, setActionState] = useState<{ profileId?: string; type: ActionState } | null>(null);
  const [draft, setDraft] = useState<ApiStartupProfile | null>(null);

  const editProfileId = searchParams.get('edit');
  const searchQuery = searchParams.get('q') ?? '';
  const sortMode = ((): StartupSortMode => {
    const value = searchParams.get('sort');
    return value === 'name' || value === 'recent' || value === 'recommended' ? value : 'recommended';
  })();

  const patchSearchParams = (updates: Record<string, string | null>) => {
    const next = new URLSearchParams(searchParams);
    Object.entries(updates).forEach(([key, value]) => {
      if (value) {
        next.set(key, value);
      } else {
        next.delete(key);
      }
    });
    setSearchParams(next, { replace: true });
  };

  const translateActionError = (error: unknown, fallbackAction: string) => {
    const rawMessage = error instanceof Error ? error.message : '';
    return describeStartupActionError(rawMessage, fallbackAction);
  };

  const refreshDashboard = async () => {
    setDashboardLoading(true);
    try {
      const response = await fetchDashboard();
      setDashboard(transformDashboard(response));
      setDashboardError(null);
    } catch (error) {
      setDashboardError(translateActionError(error, 'load your workspace summary'));
    } finally {
      setDashboardLoading(false);
    }
  };

  const refreshProfiles = async (preferredProfileId?: string | null) => {
    setProfilesLoading(true);
    const maxAttempts = payload ? 1 : INITIAL_PROFILE_LOAD_MAX_ATTEMPTS;
    let lastErrorMessage = '';

    try {
      for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
        try {
          const response = await fetchStartupProfiles();
          setPayload(response);
          setProfilesError(null);

          if (preferredProfileId) {
            patchSearchParams({ edit: preferredProfileId });
          } else if (editProfileId && !response.profiles.some((profile) => profile.profile_id === editProfileId)) {
            patchSearchParams({ edit: null });
          }
          return;
        } catch (error) {
          lastErrorMessage = translateActionError(error, 'load startup profiles');
          const shouldRetry = attempt < maxAttempts && shouldRetryInitialProfileLoad(lastErrorMessage);
          if (!shouldRetry) break;
          await new Promise<void>((resolve) => {
            window.setTimeout(resolve, INITIAL_PROFILE_LOAD_RETRY_DELAY_MS * attempt);
          });
        }
      }
      setProfilesError(lastErrorMessage || 'The launcher could not load your profiles yet.');
    } finally {
      setProfilesLoading(false);
    }
  };

  useEffect(() => {
    if (!runtimeReady) return;
    void refreshDashboard();
    void refreshProfiles();
  }, [runtimeReady]);

  const selectedProfile = useMemo(
    () => payload?.profiles.find((profile) => profile.profile_id === editProfileId) ?? null,
    [editProfileId, payload],
  );

  useEffect(() => {
    if (!selectedProfile) { setDraft(null); return; }
    setDraft(JSON.parse(JSON.stringify(selectedProfile)));
  }, [selectedProfile]);

  const profileViews = useMemo(() => {
    if (!payload) return [];
    return payload.profiles.map((profile) =>
      buildStartupProfileView(profile, payload.catalog, payload.active_profile_id, payload.last_launched_profile_id),
    );
  }, [payload]);

  const visibleProfiles = useMemo(
    () => filterAndSortStartupProfiles(profileViews, searchQuery, sortMode),
    [profileViews, searchQuery, sortMode],
  );

  const catalog = payload?.catalog ?? null;
  const profileCount = payload?.profiles.length ?? 0;
  const catalogPacks = catalog?.packs ?? [];
  const selectedBasePack = catalogPacks.find((pack) => pack.pack_id === draft?.base_pack) ?? null;
  const defaultCreatePack = defaultBasePack(catalog);
  const availablePacksToAdd = useMemo(
    () => catalogPacks.filter((pack) => pack.available && draft && !draft.packs.includes(pack.pack_id)),
    [catalogPacks, draft],
  );

  const isDirty = useMemo(() => {
    if (!selectedProfile || !draft) return false;
    return JSON.stringify({
      name: selectedProfile.name, base_pack: selectedProfile.base_pack,
      graph_id: selectedProfile.graph_id, packs: selectedProfile.packs,
      node_overrides: selectedProfile.node_overrides,
    }) !== JSON.stringify({
      name: draft.name, base_pack: draft.base_pack,
      graph_id: draft.graph_id, packs: draft.packs,
      node_overrides: draft.node_overrides,
    });
  }, [draft, selectedProfile]);

  const setSuccessFeedback = (message: string) => {
    setFeedback({ message, tone: 'success' });
    addToast(message, 'success');
  };

  const setErrorFeedback = (message: string) => {
    setFeedback({ message, tone: 'error' });
    addToast(message, 'error');
  };

  const handleCreate = async () => {
    setActionState({ type: 'create' });
    setFeedback(null);
    try {
      if (!defaultCreatePack) throw new Error('No available base pack with a startup graph was found.');
      const response = await createStartupProfile({ name: 'New custom profile', base_pack: defaultCreatePack.pack_id });
      await refreshProfiles(response.profile.profile_id);
      setSuccessFeedback('Custom profile created.');
    } catch (error) {
      setErrorFeedback(translateActionError(error, 'create a custom profile'));
    } finally { setActionState(null); }
  };

  const handleSave = async () => {
    if (!draft) return;
    setActionState({ type: 'save', profileId: draft.profile_id });
    setFeedback(null);
    try {
      await updateStartupProfile(draft.profile_id, {
        name: draft.name, base_pack: draft.base_pack, graph_id: draft.graph_id,
        packs: draft.packs, node_overrides: draft.node_overrides,
      });
      await refreshProfiles(draft.profile_id);
      setSuccessFeedback('Profile changes saved.');
    } catch (error) {
      setErrorFeedback(translateActionError(error, 'save this profile'));
    } finally { setActionState(null); }
  };

  const handleAddPack = async (packId: string) => {
    if (!draft || !packId) return;
    setActionState({ type: 'save', profileId: draft.profile_id });
    setFeedback(null);
    try {
      const response = await addPackToStartupProfile(draft.profile_id, packId);
      setDraft(response.profile);
      await refreshProfiles(draft.profile_id);
      setSuccessFeedback('Pack added to profile.');
    } catch (error) {
      setErrorFeedback(translateActionError(error, 'add this pack'));
    } finally { setActionState(null); }
  };

  const handleRemovePack = async (packId: string) => {
    if (!draft || packId === draft.base_pack) return;
    setActionState({ type: 'save', profileId: draft.profile_id });
    setFeedback(null);
    try {
      const response = await removePackFromStartupProfile(draft.profile_id, packId);
      setDraft(response.profile);
      await refreshProfiles(draft.profile_id);
      setSuccessFeedback('Pack removed from profile.');
    } catch (error) {
      setErrorFeedback(translateActionError(error, 'remove this pack'));
    } finally { setActionState(null); }
  };

  const handleOverrideChange = async (portKey: string, nodeId: string) => {
    if (!draft) return;
    setActionState({ type: 'save', profileId: draft.profile_id });
    setFeedback(null);
    try {
      const response = nodeId
        ? await setStartupProfileNodeOverride(draft.profile_id, portKey, nodeId)
        : await clearStartupProfileNodeOverride(draft.profile_id, portKey);
      setDraft(response.profile);
      await refreshProfiles(draft.profile_id);
      setSuccessFeedback(nodeId ? 'Node override saved.' : 'Node override cleared.');
    } catch (error) {
      setErrorFeedback(translateActionError(error, 'update this override'));
    } finally { setActionState(null); }
  };

  const handleDuplicate = async (profileId: string) => {
    setActionState({ type: 'duplicate', profileId });
    setFeedback(null);
    try {
      const response = await duplicateStartupProfile(profileId);
      await refreshProfiles(response.profile.profile_id);
      setSuccessFeedback('Profile duplicated.');
    } catch (error) {
      setErrorFeedback(translateActionError(error, 'duplicate this profile'));
    } finally { setActionState(null); }
  };

  const handleActivate = async (profileId: string) => {
    setActionState({ type: 'activate', profileId });
    setFeedback(null);
    try {
      await activateStartupProfile(profileId);
      await refreshProfiles(profileId);
      setSuccessFeedback('Active profile updated for the next launch.');
    } catch (error) {
      setErrorFeedback(translateActionError(error, 'set this profile as active'));
    } finally { setActionState(null); }
  };

  const handleLaunch = async (profileId: string) => {
    setActionState({ type: 'launch', profileId });
    setFeedback(null);
    try {
      const response = await launchStartupProfile(profileId);
      if (!response.restart_requested) {
        await refreshProfiles(editProfileId);
        await refreshDashboard();
      }
      setSuccessFeedback(response.restart_requested ? 'Profile launched. Kernel restart handoff was requested.' : 'Profile launched.');
    } catch (error) {
      setErrorFeedback(translateActionError(error, 'launch this profile'));
    } finally { setActionState(null); }
  };

  const handleDelete = (profileId: string, name: string) => {
    showDialog({
      title: 'Delete this profile?',
      message: profileCount <= 1
        ? 'At least one startup profile must remain.'
        : `Delete '${name}' and switch back to another saved profile?`,
      confirmText: 'Delete',
      onConfirm: async () => {
        if (profileCount <= 1) return;
        setActionState({ type: 'delete', profileId });
        setFeedback(null);
        try {
          const response = await deleteStartupProfile(profileId);
          if (editProfileId === profileId) patchSearchParams({ edit: null });
          await refreshProfiles(response.active_profile_id);
          setSuccessFeedback('Profile deleted.');
        } catch (error) {
          setErrorFeedback(translateActionError(error, 'delete this profile'));
        } finally { setActionState(null); closeDialog(); }
      },
    });
  };

  const handleRestartKernel = () => {
    showDialog({
      title: 'Restart kernel?',
      message: 'This refreshes the runtime and may interrupt in-flight work.',
      confirmText: 'Restart',
      onConfirm: async () => {
        setActionState({ type: 'restart' });
        setFeedback(null);
        try {
          await restartKernel();
          setDashboard((current) => ({ ...current, kernelStatus: 'stopped' }));
          setSuccessFeedback('Kernel restart requested.');
          closeDialog();
          window.setTimeout(() => { void refreshDashboard(); }, 3000);
        } catch (error) {
          setErrorFeedback(translateActionError(error, 'restart the kernel'));
          closeDialog();
        } finally { setActionState(null); }
      },
    });
  };

  // --- Loading / Error states ---

  if (!runtimeReady && runtimeStatus !== 'error') {
    return <DashboardSkeleton />;
  }

  if (runtimeStatus === 'error' && !payload) {
    return (
      <div className="flex flex-1 items-center justify-center px-6">
        <div className="flex max-w-md flex-col gap-4 rounded-xl border border-red-200 bg-red-50 p-6 dark:border-red-900/40 dark:bg-red-950/20">
          <div className="flex items-start gap-3">
            <AlertCircle className="mt-0.5 h-5 w-5 text-red-500 shrink-0" />
            <div className="space-y-1">
              <h2 className="text-base font-semibold text-text-main">Runtime could not finish starting</h2>
              <p className="text-sm text-text-muted">{runtimeError || 'The control panel opened, but the background runtime startup failed.'}</p>
            </div>
          </div>
          <div className="flex justify-end">
            <Button onClick={() => window.location.reload()} size="sm"><RefreshCw className="h-3.5 w-3.5" /> Reload</Button>
          </div>
        </div>
      </div>
    );
  }

  if (profilesLoading && !payload) return <DashboardSkeleton />;

  if (!payload) {
    return (
      <div className="flex flex-1 items-center justify-center px-6">
        <div className="flex max-w-md flex-col gap-4 rounded-xl border border-border bg-bg-card p-6">
          <div className="flex items-start gap-3">
            <AlertCircle className="mt-0.5 h-5 w-5 text-red-500 shrink-0" />
            <div className="space-y-1">
              <h2 className="text-base font-semibold text-text-main">Home could not load</h2>
              <p className="text-sm text-text-muted">{profilesError || 'The launcher could not load your profiles yet.'}</p>
            </div>
          </div>
          <div className="flex justify-end">
            <Button onClick={() => void refreshProfiles()} size="sm"><RefreshCw className="h-3.5 w-3.5" /> Retry</Button>
          </div>
        </div>
      </div>
    );
  }

  // --- Main render ---

  return (
    <div className="flex flex-1 overflow-hidden">
      <div className="mx-auto flex w-full max-w-[1100px] flex-col gap-6 px-6 py-8 lg:px-10 scrollbar-hidden overflow-y-auto page-enter">
        <CosmosHero
          dashboard={dashboard}
          profileViews={profileViews}
          payload={payload}
        />
        {/* Header section */}
        <section className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-text-main">My Profiles</h1>
            <p className="mt-1 text-sm text-text-muted">Launch and manage your startup profiles.</p>
          </div>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 rounded-lg border border-border bg-bg-card px-3 py-2 text-sm">
              <Search className="h-4 w-4 text-text-muted" />
              <input
                value={searchQuery}
                onChange={(e) => patchSearchParams({ q: e.target.value || null })}
                placeholder="Search profiles..."
                className="w-36 bg-transparent text-sm text-text-main outline-none placeholder:text-text-muted sm:w-48"
                aria-label="Search profiles"
              />
            </label>
            <Button onClick={handleCreate} disabled={actionState?.type === 'create'} loading={actionState?.type === 'create'}>
              <Plus className="h-4 w-4" /> Create
            </Button>
          </div>
        </section>

        {/* Feedback banner */}
        {feedback && (
          <div className={`flex items-center gap-3 rounded-lg border px-4 py-3 text-sm ${
            feedback.tone === 'error'
              ? 'border-red-200 bg-red-50 text-red-700 dark:border-red-900/40 dark:bg-red-950/30 dark:text-red-300'
              : 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/40 dark:bg-emerald-950/20 dark:text-emerald-300'
          }`}>
            {feedback.tone === 'error' ? <AlertCircle className="h-4 w-4 shrink-0" /> : <CheckCircle2 className="h-4 w-4 shrink-0" />}
            <span className="flex-1">{feedback.message}</span>
            {feedback.tone === 'error' && (
              <Button variant="ghost" size="sm" onClick={() => void refreshProfiles(editProfileId)}>
                <RefreshCw className="h-3.5 w-3.5" /> Retry
              </Button>
            )}
          </div>
        )}

        {/* Profile Grid */}
        {visibleProfiles.length === 0 ? (
          <section className="rounded-xl border border-dashed border-border bg-bg-card/50 px-8 py-16 text-center">
            <div className="mx-auto flex max-w-sm flex-col items-center gap-4">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-bg-hover">
                {searchQuery ? <Search className="h-5 w-5 text-text-muted" /> : <Plus className="h-5 w-5 text-text-muted" />}
              </div>
              <div className="space-y-1">
                <h2 className="text-base font-semibold text-text-main">
                  {searchQuery ? 'No profiles match that search' : 'Create your first profile'}
                </h2>
                <p className="text-sm text-text-muted">
                  {searchQuery ? 'Try a different search term.' : 'Profiles keep your preferred settings ready for launch.'}
                </p>
              </div>
              {searchQuery ? (
                <Button variant="outline" size="sm" onClick={() => patchSearchParams({ q: null })}>Clear search</Button>
              ) : (
                <Button size="sm" onClick={handleCreate} disabled={actionState?.type === 'create'}>Create Profile</Button>
              )}
            </div>
          </section>
        ) : (
          <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {visibleProfiles.map((profileView) => {
              const { issues, profile, runtimeReady: profileReady, basePack, lastLaunched } = profileView;
              const hasDanger = issues.some((i) => i.severity === 'danger');
              const isActive = payload.active_profile_id === profile.profile_id;
              const busy = actionState?.profileId === profile.profile_id;

              return (
                <article
                  key={profile.profile_id}
                  className={`group relative flex flex-col rounded-xl border bg-bg-card p-5 transition-all hover:shadow-[var(--shadow-md)] ${
                    isActive ? 'border-accent/25' : 'border-border'
                  }`}
                >
                  {/* Top: status + menu */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      {isActive && (
                        <>
                          <span className="h-2 w-2 rounded-full bg-accent" />
                          <span className="text-[11px] font-medium text-accent">Active</span>
                        </>
                      )}
                      {!isActive && lastLaunched && <span className="text-[11px] text-text-muted">Last used</span>}
                    </div>
                    <Popover>
                      <PopoverTrigger className="rounded-md p-1.5 text-text-muted opacity-0 transition hover:bg-bg-hover group-hover:opacity-100 focus-visible:opacity-100">
                        <MoreHorizontal className="h-4 w-4" />
                        <span className="sr-only">Actions</span>
                      </PopoverTrigger>
                      <PopoverContent className="w-40">
                        <div className="flex flex-col py-1">
                          <button onClick={() => patchSearchParams({ edit: profile.profile_id })} className="flex items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-text-main transition hover:bg-bg-hover">
                            <Save className="h-3.5 w-3.5" /> Edit
                          </button>
                          <button onClick={() => void handleActivate(profile.profile_id)} disabled={isActive || busy} className="flex items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-text-main transition hover:bg-bg-hover disabled:opacity-50">
                            <Star className={`h-3.5 w-3.5 ${isActive ? 'fill-accent text-accent' : ''}`} /> {isActive ? 'Active' : 'Set Active'}
                          </button>
                          <button onClick={() => void handleDuplicate(profile.profile_id)} disabled={busy} className="flex items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-text-main transition hover:bg-bg-hover disabled:opacity-50">
                            <Copy className="h-3.5 w-3.5" /> Duplicate
                          </button>
                          <div className="my-1 border-t border-border" />
                          <button onClick={() => handleDelete(profile.profile_id, profile.name)} disabled={profileCount <= 1 || busy} className="flex items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-red-500 transition hover:bg-red-50 dark:hover:bg-red-950/20 disabled:opacity-50">
                            <Trash2 className="h-3.5 w-3.5" /> Delete
                          </button>
                        </div>
                      </PopoverContent>
                    </Popover>
                  </div>

                  {/* Icon */}
                  <div className="mt-4 flex justify-center">
                    <div className={`flex h-14 w-14 items-center justify-center rounded-xl ${isActive ? 'bg-accent/8 text-accent' : 'bg-bg-hover text-text-muted'}`}>
                      <Box className="h-6 w-6" strokeWidth={1.5} />
                    </div>
                  </div>

                  {/* Name & Pack */}
                  <div className="mt-3 text-center">
                    <h3 className="text-sm font-semibold text-text-main">{profile.name}</h3>
                    <p className="mt-0.5 text-xs text-text-muted">{packLabel(basePack, profile.base_pack)}</p>
                  </div>

                  {/* Status */}
                  <div className="mt-2 min-h-[16px] text-center">
                    {issues.length > 0 ? (
                      <span className={`text-[11px] ${hasDanger ? 'text-red-500' : 'text-amber-500'}`}>{issues[0].description}</span>
                    ) : profileReady ? (
                      <Badge variant="success" className="text-[10px]">Ready</Badge>
                    ) : null}
                  </div>

                  {/* Actions - primary right */}
                  <div className="mt-auto pt-4 flex gap-2 justify-end">
                    <Button variant="outline" size="sm" onClick={() => patchSearchParams({ edit: profile.profile_id })}>Edit</Button>
                    <Button size="sm" onClick={() => void handleLaunch(profile.profile_id)} disabled={!profileReady || busy} loading={actionState?.type === 'launch' && busy}>
                      <Rocket className="h-3.5 w-3.5" /> Launch
                    </Button>
                  </div>
                </article>
              );
            })}

            {/* Create card */}
            <button
              onClick={handleCreate}
              disabled={actionState?.type === 'create'}
              className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border bg-bg-card/50 p-5 text-center transition hover:border-accent/40 hover:bg-bg-card min-h-[240px]"
            >
              <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-border bg-bg-hover text-text-muted">
                {actionState?.type === 'create' ? <Loader2 className="h-5 w-5 animate-spin text-accent" /> : <Plus className="h-5 w-5" />}
              </div>
              <h3 className="mt-3 text-sm font-semibold text-text-main">Create Profile</h3>
              <p className="mt-1 text-xs text-text-muted">Build a new startup profile</p>
            </button>
          </section>
        )}

        {/* Edit Panel */}
        {draft && catalog && <EditPanel
          draft={draft}
          setDraft={setDraft}
          catalog={catalog}
          catalogPacks={catalogPacks}
          selectedBasePack={selectedBasePack}
          availablePacksToAdd={availablePacksToAdd}
          isDirty={isDirty}
          actionState={actionState}
          profileCount={profileCount}
          editProfileId={editProfileId}
          patchSearchParams={patchSearchParams}
          handleSave={handleSave}
          handleActivate={handleActivate}
          handleDuplicate={handleDuplicate}
          handleDelete={handleDelete}
          handleLaunch={handleLaunch}
          handleAddPack={handleAddPack}
          handleRemovePack={handleRemovePack}
          handleOverrideChange={handleOverrideChange}
        />}
      </div>
    </div>
  );
}

// --- Edit Panel (extracted for readability) ---

interface EditPanelProps {
  draft: ApiStartupProfile;
  setDraft: (d: ApiStartupProfile) => void;
  catalog: any;
  catalogPacks: any[];
  selectedBasePack: any;
  availablePacksToAdd: any[];
  isDirty: boolean;
  actionState: { profileId?: string; type: string } | null;
  profileCount: number;
  editProfileId: string | null;
  patchSearchParams: (u: Record<string, string | null>) => void;
  handleSave: () => Promise<void>;
  handleActivate: (id: string) => Promise<void>;
  handleDuplicate: (id: string) => Promise<void>;
  handleDelete: (id: string, name: string) => void;
  handleLaunch: (id: string) => Promise<void>;
  handleAddPack: (packId: string) => Promise<void>;
  handleRemovePack: (packId: string) => Promise<void>;
  handleOverrideChange: (portKey: string, nodeId: string) => Promise<void>;
}

function EditPanel({
  draft, setDraft, catalog, catalogPacks, selectedBasePack, availablePacksToAdd,
  isDirty, actionState, profileCount, editProfileId, patchSearchParams,
  handleSave, handleActivate, handleDuplicate, handleDelete, handleLaunch,
  handleAddPack, handleRemovePack, handleOverrideChange,
}: EditPanelProps) {
  const [compilePreview, setCompilePreview] = useState<StartupProfileCompilePreviewResponseData | null>(null);
  const [compilePreviewError, setCompilePreviewError] = useState<string | null>(null);
  const [compilePreviewLoading, setCompilePreviewLoading] = useState(false);
  const compilePreviewKey = useMemo(
    () => JSON.stringify({
      profile_id: draft.profile_id,
      base_pack: draft.base_pack,
      graph_id: draft.graph_id,
      packs: draft.packs,
      node_overrides: draft.node_overrides,
      launch_capability_graph: draft.launch_capability_graph,
      capability_profile_id: draft.capability_profile_id,
      surfaces: draft.surfaces,
    }),
    [draft],
  );

  useEffect(() => {
    let cancelled = false;
    setCompilePreviewLoading(true);
    setCompilePreviewError(null);
    const timeout = window.setTimeout(() => {
      void compileStartupProfilePreview(draft.profile_id, draft)
        .then((preview) => {
          if (cancelled) return;
          setCompilePreview(preview);
        })
        .catch((error) => {
          if (cancelled) return;
          setCompilePreview(null);
          setCompilePreviewError(error instanceof Error ? error.message : 'Compile preview failed.');
        })
        .finally(() => {
          if (!cancelled) setCompilePreviewLoading(false);
        });
    }, 300);
    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [draft.profile_id, compilePreviewKey]);

  const launchTarget = compilePreview?.surface_launch_target ?? compilePreview?.capability_graph?.surface_launch_target ?? null;
  const previewDiagnostics = compilePreview?.diagnostics ?? compilePreview?.capability_graph?.diagnostics ?? [];
  const firstPreviewError = previewDiagnostics.find((item) => item.level === 'error')?.message ?? null;

  return (
    <section className="rounded-xl border border-border bg-bg-card p-6">
      {/* Edit header */}
      <div className="flex flex-col gap-4 border-b border-border pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-2">
          <button
            onClick={() => patchSearchParams({ edit: null })}
            className="inline-flex items-center gap-1.5 text-sm text-text-muted transition hover:text-text-main"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> Back to profiles
          </button>
          <div>
            <h2 className="text-xl font-semibold tracking-tight text-text-main">{draft.name}</h2>
            <p className="mt-0.5 text-sm text-text-muted">Edit profile settings, packs, and graph port overrides.</p>
          </div>
        </div>

        {/* Actions - destructive separated left, primary right */}
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={() => void handleDuplicate(draft.profile_id)} disabled={actionState?.profileId === draft.profile_id}>
            <Copy className="h-3.5 w-3.5" /> Duplicate
          </Button>
          <Button variant="destructive" size="sm" onClick={() => handleDelete(draft.profile_id, draft.name)} disabled={profileCount <= 1 || actionState?.profileId === draft.profile_id}>
            <Trash2 className="h-3.5 w-3.5" /> Delete
          </Button>
          <div className="flex-1" />
          <Button size="sm" onClick={() => void handleLaunch(draft.profile_id)} disabled={actionState?.profileId === draft.profile_id} loading={actionState?.type === 'launch' && actionState?.profileId === draft.profile_id}>
            <Rocket className="h-3.5 w-3.5" /> Launch
          </Button>
          <Button size="sm" onClick={handleSave} disabled={!isDirty || actionState?.type === 'save'} loading={actionState?.type === 'save'}>
            <Save className="h-3.5 w-3.5" /> Save
          </Button>
        </div>
      </div>

      {/* Edit body */}
      <div className="mt-6 grid gap-6 xl:grid-cols-[1fr_280px]">
        <div className="space-y-6">
          {/* General settings */}
          <div className="rounded-lg border border-border bg-bg-main p-5">
            <h3 className="text-sm font-semibold text-text-main">General settings</h3>
            <p className="mt-0.5 text-xs text-text-muted">Profile name and base pack.</p>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <label className="text-xs font-medium uppercase tracking-wider text-text-muted">Profile name</label>
                <input
                  value={draft.name}
                  onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                  className="w-full rounded-lg border border-border bg-bg-hover px-3 py-2.5 text-sm text-text-main outline-none transition focus:border-accent focus:ring-2 focus:ring-[var(--ring-color)]"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-medium uppercase tracking-wider text-text-muted">Base pack</label>
                <select
                  value={draft.base_pack}
                  onChange={(e) => {
                    const nextBasePack = e.target.value;
                    const nextPack = catalogPacks.find((pack: any) => pack.pack_id === nextBasePack);
                    setDraft({
                      ...draft,
                      base_pack: nextBasePack,
                      graph_id: nextPack?.graphs[0]?.graph_id ?? draft.graph_id,
                      packs: draft.packs.includes(nextBasePack) ? draft.packs : [nextBasePack, ...draft.packs],
                    });
                  }}
                  className="w-full rounded-lg border border-border bg-bg-hover px-3 py-2.5 text-sm text-text-main outline-none transition focus:border-accent focus:ring-2 focus:ring-[var(--ring-color)]"
                >
                  {catalogPacks.map((pack: any) => (
                    <option key={pack.pack_id} value={pack.pack_id} disabled={!pack.available}>
                      {packLabel(pack)} {pack.available ? '' : '(unavailable)'}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {selectedBasePack && !selectedBasePack.available && (
              <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 dark:border-amber-900/30 dark:bg-amber-950/20">
                <div className="flex items-center gap-2 text-sm font-medium text-amber-700 dark:text-amber-300">
                  <AlertCircle className="h-4 w-4" /> Base pack needs attention
                </div>
                <ul className="mt-2 space-y-1 text-xs text-text-muted">
                  {selectedBasePack.approval_issues.map((issue: string) => (
                    <li key={issue}>{describeStartupIssue(issue, packLabel(selectedBasePack)).description}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Profile packs */}
          <div className="rounded-lg border border-border bg-bg-main p-5">
            <h3 className="text-sm font-semibold text-text-main">Profile packs</h3>
            <p className="mt-0.5 text-xs text-text-muted">Add packs before using their nodes as overrides.</p>
            <div className="mt-4 space-y-3">
              {draft.packs.map((packId: string) => {
                const pack = catalogPacks.find((item: any) => item.pack_id === packId) ?? null;
                const canRemove = packId !== draft.base_pack;
                return (
                  <div key={packId} className="flex items-center justify-between gap-3 rounded-lg border border-border bg-bg-hover/50 p-3">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium text-text-main">{packLabel(pack, packId)}</div>
                      <div className="truncate text-xs text-text-muted">{packId}</div>
                    </div>
                    <Button variant="outline" size="sm" onClick={() => void handleRemovePack(packId)} disabled={!canRemove || actionState?.profileId === draft.profile_id}>
                      {packId === draft.base_pack ? 'Base' : 'Remove'}
                    </Button>
                  </div>
                );
              })}
              <div className="space-y-1.5">
                <label className="text-xs font-medium uppercase tracking-wider text-text-muted">Add pack</label>
                <select
                  value=""
                  onChange={(e) => void handleAddPack(e.target.value)}
                  disabled={availablePacksToAdd.length === 0 || actionState?.profileId === draft.profile_id}
                  className="w-full rounded-lg border border-border bg-bg-hover px-3 py-2.5 text-sm text-text-main outline-none transition focus:border-accent disabled:opacity-60"
                >
                  <option value="">Select a pack</option>
                  {availablePacksToAdd.map((pack: any) => (
                    <option key={pack.pack_id} value={pack.pack_id}>{packLabel(pack)}</option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* Graph port overrides */}
          <div className="rounded-lg border border-border bg-bg-main p-5">
            <h3 className="text-sm font-semibold text-text-main">Graph port overrides</h3>
            <p className="mt-0.5 text-xs text-text-muted">Override graph inputs with compatible nodes.</p>
            <div className="mt-4 space-y-3">
              {draft.graph_ports.map((graphPort: any) => {
                const compatibleNodes = compatibleNodesForPort(catalog, draft, graphPort);
                const currentOverride = draft.node_overrides[graphPort.port_key] ?? '';
                const defaultNode = graphPort.source_node_ref || graphPort.source_ref;
                return (
                  <div key={graphPort.port_key} className="rounded-lg border border-border bg-bg-hover/50 p-3">
                    <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <div className="text-sm font-medium text-text-main">{titleCasePortKey(graphPort.port_key)}</div>
                        <div className="text-xs text-text-muted">Default: {defaultNode}</div>
                      </div>
                      <Badge variant="outline" className="text-[10px] w-fit">
                        {(graphPort.target_port?.standards ?? graphPort.target_port?.contracts ?? []).join(', ') || graphPort.port_key}
                      </Badge>
                    </div>
                    <select
                      value={currentOverride}
                      onChange={(e) => void handleOverrideChange(graphPort.port_key, e.target.value)}
                      disabled={actionState?.profileId === draft.profile_id}
                      className="mt-2 w-full rounded-lg border border-border bg-bg-hover px-3 py-2 text-sm text-text-main outline-none transition focus:border-accent"
                    >
                      <option value="">Use graph default ({defaultNode})</option>
                      {compatibleNodes.map((node: any) => (
                        <option key={node.node_id} value={node.node_id}>{node.node_id}</option>
                      ))}
                    </select>
                    {compatibleNodes.length === 0 && (
                      <div className="mt-2 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-2 text-xs text-amber-700 dark:border-amber-900/30 dark:bg-amber-950/20 dark:text-amber-300">
                        <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                        <span>No compatible nodes available from this profile's packs.</span>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Sidebar metadata */}
        <aside className="space-y-4">
          <div className="rounded-lg border border-border bg-bg-main p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="text-xs font-medium uppercase tracking-wider text-text-muted">Launch target</div>
              {compilePreviewLoading ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin text-text-muted" />
              ) : compilePreview?.ok ? (
                <Badge variant="success" className="text-[10px]">Ready</Badge>
              ) : (
                <Badge variant="warning" className="text-[10px]">Check</Badge>
              )}
            </div>
            <div className="mt-3 space-y-2 text-sm">
              {launchTarget ? (
                <>
                  <div>
                    <div className="text-text-muted text-xs">Pack</div>
                    <div className="mt-1 break-all rounded-md border border-border bg-bg-hover px-2.5 py-1.5 font-mono text-xs text-text-main">{launchTarget.pack_id}</div>
                  </div>
                  {launchTarget.node_id && (
                    <div>
                      <div className="text-text-muted text-xs">Node</div>
                      <div className="mt-1 break-all rounded-md border border-border bg-bg-hover px-2.5 py-1.5 font-mono text-xs text-text-main">{launchTarget.node_id}</div>
                    </div>
                  )}
                  {launchTarget.surface && (
                    <div>
                      <div className="text-text-muted text-xs">Surface</div>
                      <div className="mt-0.5 text-text-main text-xs">{launchTarget.surface}</div>
                    </div>
                  )}
                </>
              ) : (
                <div className="rounded-md border border-border bg-bg-hover px-2.5 py-2 text-xs text-text-muted">
                  {compilePreviewError || firstPreviewError || 'No launch target resolved.'}
                </div>
              )}
            </div>
          </div>
          <div className="rounded-lg border border-border bg-bg-main p-4">
            <div className="text-xs font-medium uppercase tracking-wider text-text-muted">Metadata</div>
            <div className="mt-3 space-y-3 text-sm">
              <div>
                <div className="text-text-muted text-xs">Profile ID</div>
                <div className="mt-1 break-all rounded-md border border-border bg-bg-hover px-2.5 py-1.5 font-mono text-xs text-text-main">{draft.profile_id}</div>
              </div>
              <div>
                <div className="text-text-muted text-xs">Created</div>
                <div className="mt-0.5 text-text-main text-xs">{formatTimestamp(draft.created_at)}</div>
              </div>
              <div>
                <div className="text-text-muted text-xs">Last updated</div>
                <div className="mt-0.5 text-text-main text-xs">{formatTimestamp(draft.updated_at)}</div>
              </div>
              <div>
                <div className="text-text-muted text-xs">Status</div>
                <div className="mt-0.5 text-text-main text-xs">{isDirty ? 'Unsaved changes' : 'Saved'}</div>
              </div>
            </div>
          </div>
        </aside>
      </div>
    </section>
  );
}

// --- Skeleton ---

function SkeletonPulse({ className }: { className: string }) {
  return <div className={`animate-pulse rounded-lg bg-bg-hover ${className}`} />;
}

function DashboardSkeleton() {
  return (
    <div className="flex flex-1 overflow-hidden">
      <div className="mx-auto flex w-full max-w-[1100px] flex-col gap-6 px-6 py-8 lg:px-10 scrollbar-hidden overflow-y-auto">
        <section className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-2">
            <SkeletonPulse className="h-7 w-44" />
            <SkeletonPulse className="h-4 w-56" />
          </div>
          <div className="flex items-center gap-3">
            <SkeletonPulse className="h-10 w-40" />
            <SkeletonPulse className="h-10 w-28" />
          </div>
        </section>
        <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <article key={i} className="flex flex-col rounded-xl border border-border bg-bg-card p-5">
              <div className="flex items-center justify-between">
                <SkeletonPulse className="h-3 w-12" />
                <SkeletonPulse className="h-6 w-6 rounded-md" />
              </div>
              <div className="mt-4 flex justify-center">
                <SkeletonPulse className="h-14 w-14 rounded-xl" />
              </div>
              <div className="mt-3 flex flex-col items-center gap-2">
                <SkeletonPulse className="h-4 w-28" />
                <SkeletonPulse className="h-3 w-20" />
              </div>
              <div className="mt-auto pt-4 flex gap-2 justify-end">
                <SkeletonPulse className="h-8 w-14" />
                <SkeletonPulse className="h-8 w-20" />
              </div>
            </article>
          ))}
        </section>
      </div>
    </div>
  );
}


// =====================================================================
// Cosmos Hero — visible at the top of the Home dashboard.
// Displays a glowing greeting, kernel status, and a small Canvas
// constellation that maps the kernel + each saved startup profile +
// their packs as orbiting stars.
// =====================================================================
interface CosmosHeroProps {
  dashboard: DashboardData;
  profileViews: StartupProfileView[];
  payload: StartupProfilesResponseData | null;
}

function CosmosHero({ dashboard, profileViews, payload }: CosmosHeroProps) {
  const theme = useAppStore((state) => state.theme);
  const profile = useAppStore((state) => state.profile);
  const isCosmos = theme === 'Cosmos';

  // Build a compact constellation: kernel core + up to 6 profiles + a comet for flow count.
  const nodes = useMemo<ConstellationNode[]>(() => {
    const result: ConstellationNode[] = [
      {
        id: 'kernel',
        label: 'Kernel',
        kind: 'core',
        angle: 0,
        distance: 0,
        active: dashboard.kernelStatus === 'running',
      },
    ];

    const cap = Math.min(profileViews.length, 6);
    profileViews.slice(0, cap).forEach((view, idx) => {
      const angle = (idx / cap) * Math.PI * 2 - Math.PI / 2;
      const isActive = payload?.active_profile_id === view.profile.profile_id;
      result.push({
        id: view.profile.profile_id,
        label: view.profile.name.slice(0, 14),
        kind: isActive ? 'profile' : 'pack',
        angle,
        distance: 0.62 + (idx % 3) * 0.08,
        active: view.runtimeReady,
      });
    });

    if (dashboard.registeredFlows > 0) {
      result.push({
        id: 'flows',
        label: `${dashboard.registeredFlows} flows`,
        kind: 'flow',
        angle: Math.PI / 4,
        distance: 0.95,
        active: true,
      });
    }
    return result;
  }, [dashboard.kernelStatus, dashboard.registeredFlows, payload?.active_profile_id, profileViews]);

  const edges = useMemo<ConstellationEdge[]>(
    () =>
      nodes
        .filter((n) => n.id !== 'kernel')
        .map((n) => ({ from: 'kernel', to: n.id, active: n.active })),
    [nodes],
  );

  const greetingName = profile.username && profile.username !== 'User' ? profile.username : 'navigator';

  if (!isCosmos) {
    // Lighter hero for non-cosmos themes — keeps the page balanced.
    return (
      <section className="rounded-xl border border-border bg-bg-card p-6 sm:p-8">
        <div className="flex flex-col gap-2">
          <span className="text-xs font-medium uppercase tracking-[0.32em] text-text-muted">Welcome back</span>
          <h2 className="text-2xl font-semibold tracking-tight text-text-main">
            Hello, {greetingName}
          </h2>
          <p className="text-sm text-text-muted">
            {dashboard.kernelStatus === 'running'
              ? `Kernel is running · ${dashboard.activePacks} active pack${dashboard.activePacks === 1 ? '' : 's'} · ${dashboard.registeredFlows} flow${dashboard.registeredFlows === 1 ? '' : 's'}`
              : 'Kernel is offline.'}
          </p>
        </div>
      </section>
    );
  }

  return (
    <section
      className={cn(
        'cosmos-glass-strong relative overflow-hidden rounded-3xl px-6 py-6 sm:px-10 sm:py-8',
      )}
    >
      {/* Decorative orbit ring on the right edge */}
      <img
        src={COSMOS_DECOR.orbitRing}
        onError={hideOnError}
        alt=""
        className="pointer-events-none absolute -right-20 -top-20 hidden h-[340px] w-[340px] opacity-30 cosmos-anim-orbit md:block"
        style={{ animationDuration: '180s' }}
        loading="lazy"
        decoding="async"
      />

      <div className="relative grid items-center gap-6 md:grid-cols-[1.2fr_1fr]">
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-3">
            <CosmosLogo size={42} glow />
            <span className="text-xs uppercase tracking-[0.32em] text-[color:var(--cosmos-gold)]">
              Cosmos · v1
            </span>
          </div>
          <h2 className="cosmos-text-gradient font-display text-3xl font-semibold tracking-wide sm:text-4xl">
            Hello, {greetingName}
          </h2>
          <p className="max-w-prose text-sm leading-relaxed text-text-muted">
            Your Rumi constellation is{' '}
            <strong className="text-text-main">
              {dashboard.kernelStatus === 'running' ? 'aligned' : dashboard.kernelStatus === 'error' ? 'misaligned' : 'awaiting boot'}
            </strong>
            . Tend to your stars below.
          </p>
          <div className="mt-1 flex flex-wrap gap-2">
            <CosmosStat label="Kernel" value={dashboard.kernelStatus === 'running' ? 'Running' : dashboard.kernelStatus === 'error' ? 'Error' : 'Stopped'} tone={dashboard.kernelStatus === 'running' ? 'success' : dashboard.kernelStatus === 'error' ? 'error' : 'muted'} />
            <CosmosStat label="Uptime" value={dashboard.uptime} tone="muted" />
            <CosmosStat label="Packs" value={String(dashboard.activePacks)} tone="info" />
            <CosmosStat label="Flows" value={String(dashboard.registeredFlows)} tone="magenta" />
          </div>
        </div>

        <div className="hidden md:block">
          <ConstellationMap
            nodes={nodes}
            edges={edges}
            height={220}
            caption="Constellation"
          />
        </div>
      </div>
    </section>
  );
}

interface CosmosStatProps {
  label: string;
  value: string;
  tone: 'success' | 'error' | 'info' | 'magenta' | 'muted';
}

function CosmosStat({ label, value, tone }: CosmosStatProps) {
  const ring =
    tone === 'success'
      ? 'cosmos-halo-blue'
      : tone === 'error'
        ? 'cosmos-halo-magenta'
        : tone === 'info'
          ? 'cosmos-halo-blue'
          : tone === 'magenta'
            ? 'cosmos-halo-magenta'
            : '';
  return (
    <div className={cn('flex flex-col rounded-xl border border-[color:color-mix(in_srgb,var(--cosmos-gold)_18%,var(--border))] bg-[color:color-mix(in_srgb,var(--bg-card)_60%,transparent)] px-3 py-2', ring && ring)}>
      <span className="text-[10px] uppercase tracking-[0.28em] text-[color:var(--text-muted)]">{label}</span>
      <span className="font-display text-base text-text-main">{value}</span>
    </div>
  );
}
