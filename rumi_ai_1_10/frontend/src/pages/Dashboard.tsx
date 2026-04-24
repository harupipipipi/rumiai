import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  activateStartupProfile,
  createStartupProfile,
  deleteStartupProfile,
  duplicateStartupProfile,
  fetchDashboard,
  fetchStartupProfiles,
  launchStartupProfile,
  restartKernel,
  updateStartupProfile,
} from '@/src/lib/api';
import type {
  ApiStartupProfile,
  StartupProfilesResponseData,
} from '@/src/lib/apiTypes';
import {
  buildStartupProfileView,
  describeStartupActionError,
  describeStartupIssue,
  filterAndSortStartupProfiles,
  type StartupSortMode,
} from '@/src/lib/startupProfiles';
import { transformDashboard } from '@/src/lib/transforms';
import { useAppStore, type DashboardData } from '@/src/store';
import {
  AlertCircle,
  ArrowLeft,
  Box,
  CheckCircle2,
  ChevronRight,
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

type ActionState = 'activate' | 'create' | 'delete' | 'duplicate' | 'launch' | 'restart' | 'save';

const defaultDashboard: DashboardData = {
  kernelStatus: 'stopped',
  uptime: '--',
  activePacks: 0,
  registeredFlows: 0,
  activities: [],
};

function formatTimestamp(timestamp: number): string {
  if (!timestamp) return '--';
  return new Date(timestamp * 1000).toLocaleString();
}

function cardBorderClass(hasDanger: boolean, hasWarning: boolean, isActive: boolean): string {
  if (hasDanger) return 'border-rose-900/40';
  if (hasWarning) return 'border-amber-900/40';
  if (isActive) return 'border-accent/25';
  return 'border-border';
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
    try {
      const response = await fetchStartupProfiles();
      setPayload(response);
      setProfilesError(null);

      if (preferredProfileId) {
        patchSearchParams({ edit: preferredProfileId });
      } else if (editProfileId && !response.profiles.some((profile) => profile.profile_id === editProfileId)) {
        patchSearchParams({ edit: null });
      }
    } catch (error) {
      setProfilesError(translateActionError(error, 'load startup profiles'));
    } finally {
      setProfilesLoading(false);
    }
  };

  useEffect(() => {
    if (!runtimeReady) {
      return;
    }
    void refreshDashboard();
    void refreshProfiles();
  }, [runtimeReady]);

  const selectedProfile = useMemo(
    () => payload?.profiles.find((profile) => profile.profile_id === editProfileId) ?? null,
    [editProfileId, payload],
  );

  useEffect(() => {
    if (!selectedProfile) {
      setDraft(null);
      return;
    }
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
  const slotSpecs = catalog?.slot_specs ?? [];
  const standardPacks = catalog?.standard_packs ?? [];
  const selectedStandardPack = standardPacks.find((pack) => pack.pack_id === draft?.standard_pack_id) ?? null;

  const isDirty = useMemo(() => {
    if (!selectedProfile || !draft) return false;
    return JSON.stringify({
      name: selectedProfile.name,
      standard_pack_id: selectedProfile.standard_pack_id,
      slots: selectedProfile.slots,
    }) !== JSON.stringify({
      name: draft.name,
      standard_pack_id: draft.standard_pack_id,
      slots: draft.slots,
    });
  }, [draft, selectedProfile]);

  const selectedCandidatesBySlot = useMemo(() => {
    if (!catalog || !draft) return {} as Record<string, any>;
    return Object.fromEntries(
      slotSpecs.map((slot) => [
        slot.slot_id,
        (catalog.slot_candidates[slot.slot_id] ?? []).find((candidate) => candidate.pack_id === draft.slots[slot.slot_id]) ?? null,
      ]),
    ) as Record<string, any>;
  }, [catalog, draft, slotSpecs]);

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
      const response = await createStartupProfile({ name: 'New custom profile' });
      await refreshProfiles(response.profile.profile_id);
      setSuccessFeedback('Custom profile created. Finish the details and save when ready.');
    } catch (error) {
      setErrorFeedback(translateActionError(error, 'create a custom profile'));
    } finally {
      setActionState(null);
    }
  };

  const handleSave = async () => {
    if (!draft) return;
    setActionState({ type: 'save', profileId: draft.profile_id });
    setFeedback(null);
    try {
      await updateStartupProfile(draft.profile_id, {
        name: draft.name,
        standard_pack_id: draft.standard_pack_id,
        slots: draft.slots,
      });
      await refreshProfiles(draft.profile_id);
      setSuccessFeedback('Profile changes saved.');
    } catch (error) {
      setErrorFeedback(translateActionError(error, 'save this profile'));
    } finally {
      setActionState(null);
    }
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
    } finally {
      setActionState(null);
    }
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
    } finally {
      setActionState(null);
    }
  };

  const handleLaunch = async (profileId: string) => {
    setActionState({ type: 'launch', profileId });
    setFeedback(null);
    try {
      const response = await launchStartupProfile(profileId);
      await refreshProfiles(profileId);
      await refreshDashboard();
      setSuccessFeedback(
        response.restart_requested
          ? 'Profile launched. Kernel restart handoff was requested.'
          : 'Profile launched.',
      );
    } catch (error) {
      setErrorFeedback(translateActionError(error, 'launch this profile'));
    } finally {
      setActionState(null);
    }
  };

  const handleDelete = (profileId: string, name: string) => {
    showDialog({
      title: 'Delete this profile?',
      message:
        profileCount <= 1
          ? 'At least one startup profile must remain.'
          : `Delete '${name}' and switch back to another saved profile?`,
      confirmText: 'Delete',
      onConfirm: async () => {
        if (profileCount <= 1) return;
        setActionState({ type: 'delete', profileId });
        setFeedback(null);
        try {
          const response = await deleteStartupProfile(profileId);
          if (editProfileId === profileId) {
            patchSearchParams({ edit: null });
          }
          await refreshProfiles(response.active_profile_id);
          setSuccessFeedback('Profile deleted.');
        } catch (error) {
          setErrorFeedback(translateActionError(error, 'delete this profile'));
        } finally {
          setActionState(null);
          closeDialog();
        }
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
          window.setTimeout(() => {
            void refreshDashboard();
          }, 3000);
        } catch (error) {
          setErrorFeedback(translateActionError(error, 'restart the kernel'));
          closeDialog();
        } finally {
          setActionState(null);
        }
      },
    });
  };

  if (!runtimeReady && runtimeStatus !== 'error') {
    return <DashboardSkeleton />;
  }

  if (runtimeStatus === 'error' && !payload) {
    return (
      <div className="flex flex-1 items-center justify-center bg-bg-main px-4 text-text-main">
        <div className="flex max-w-lg flex-col gap-4 rounded-2xl border border-rose-900/40 bg-rose-950/20 p-8">
          <div className="flex items-start gap-3">
            <AlertCircle className="mt-0.5 h-5 w-5 text-rose-400" />
            <div className="space-y-2">
              <h1 className="text-2xl font-semibold text-text-main">Runtime could not finish starting</h1>
              <p className="text-sm text-text-muted">
                {runtimeError || 'The control panel opened, but the background runtime startup failed.'}
              </p>
            </div>
          </div>
          <button
            onClick={() => window.location.reload()}
            className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-accent px-4 py-3 text-sm font-semibold text-accent-fg transition hover:opacity-90 sm:w-fit"
          >
            <RefreshCw className="h-4 w-4" />
            Reload
          </button>
        </div>
      </div>
    );
  }

  if (profilesLoading && !payload) {
    return <DashboardSkeleton />;
  }

  if (!payload) {
    return (
      <div className="flex flex-1 items-center justify-center bg-bg-main px-4 text-text-main">
        <div className="flex max-w-lg flex-col gap-4 rounded-2xl border border-border bg-bg-card p-8">
          <div className="flex items-start gap-3">
            <AlertCircle className="mt-0.5 h-5 w-5 text-rose-400" />
            <div className="space-y-2">
              <h1 className="text-2xl font-semibold text-text-main">Home could not load</h1>
              <p className="text-sm text-text-muted">{profilesError || 'The launcher could not load your profiles yet.'}</p>
            </div>
          </div>
          <button
            onClick={() => void refreshProfiles()}
            className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-accent px-4 py-3 text-sm font-semibold text-accent-fg transition hover:opacity-90 sm:w-fit"
          >
            <RefreshCw className="h-4 w-4" />
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 overflow-hidden bg-bg-main text-text-main">
      <div className="mx-auto flex w-full max-w-[1200px] flex-col gap-6 px-6 py-8 lg:px-10 scrollbar-hidden overflow-y-auto">
        {/* Header */}
        <section className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-text-main">My Profiles</h1>
            <p className="mt-1 text-sm text-text-muted">Launch and manage your startup profiles.</p>
          </div>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 rounded-xl border border-border bg-bg-card px-3 py-2 text-sm">
              <Search className="h-4 w-4 text-text-muted" />
              <input
                value={searchQuery}
                onChange={(e) => patchSearchParams({ q: e.target.value || null })}
                placeholder="Search profiles..."
                className="w-40 bg-transparent text-sm text-text-main outline-none placeholder:text-text-muted sm:w-52"
              />
            </label>
            <button
              onClick={handleCreate}
              disabled={actionState?.type === 'create'}
              className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-accent-fg transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {actionState?.type === 'create' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              Create Profile
            </button>
          </div>
        </section>

        {/* Feedback */}
        {feedback ? (
          <div
            className={`flex flex-col gap-3 rounded-2xl border px-5 py-4 sm:flex-row sm:items-center sm:justify-between ${
              feedback.tone === 'error'
                ? 'border-rose-900/60 bg-rose-950/30 text-rose-100'
                : 'border-emerald-900/60 bg-emerald-950/20 text-emerald-100'
            }`}
          >
            <div className="flex items-start gap-3">
              {feedback.tone === 'error' ? (
                <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />
              ) : (
                <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0" />
              )}
              <p className="text-sm">{feedback.message}</p>
            </div>
            {feedback.tone === 'error' ? (
              <button
                onClick={() => void refreshProfiles(editProfileId)}
                className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-black/20 px-4 py-2 text-sm font-medium transition hover:bg-black/35"
              >
                <RefreshCw className="h-4 w-4" />
                Retry load
              </button>
            ) : null}
          </div>
        ) : null}

        {/* Partial Error */}
        {profilesError ? (
          <div className="flex flex-col gap-3 rounded-2xl border border-amber-900/40 bg-amber-950/20 px-5 py-4 text-amber-100 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-3">
              <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />
              <div className="space-y-1">
                <p className="text-sm font-medium">Some profile data could not refresh.</p>
                <p className="text-sm text-amber-200/80">{profilesError}</p>
              </div>
            </div>
            <button
              onClick={() => void refreshProfiles(editProfileId)}
              className="inline-flex items-center gap-2 rounded-xl border border-amber-800/80 bg-black/20 px-4 py-2 text-sm font-medium transition hover:bg-black/35"
            >
              <RefreshCw className="h-4 w-4" />
              Retry
            </button>
          </div>
        ) : null}

        {/* Profile Grid */}
        {visibleProfiles.length === 0 ? (
          <section className="rounded-2xl border border-dashed border-border bg-bg-card/50 px-8 py-14 text-center">
            <div className="mx-auto flex max-w-xl flex-col items-center gap-4">
              <div className="flex h-16 w-16 items-center justify-center rounded-full border border-border bg-bg-hover text-text-muted">
                {searchQuery ? <Search className="h-7 w-7" /> : <Plus className="h-7 w-7" />}
              </div>
              <div className="space-y-2">
                <h2 className="text-xl font-semibold text-text-main">
                  {searchQuery ? 'No profiles match that search' : 'Create your first profile'}
                </h2>
                <p className="text-sm leading-6 text-text-muted">
                  {searchQuery
                    ? 'Try a different profile name, pack name, or slot search.'
                    : 'Profiles keep your preferred standard pack and slot setup ready for launch.'}
                </p>
              </div>
              <div className="flex flex-col gap-3 sm:flex-row">
                {searchQuery ? (
                  <button
                    onClick={() => patchSearchParams({ q: null })}
                    className="rounded-xl border border-border bg-bg-hover px-4 py-2.5 text-sm font-medium text-text-main transition hover:bg-bg-hover/80"
                  >
                    Clear search
                  </button>
                ) : null}
                <button
                  onClick={handleCreate}
                  disabled={actionState?.type === 'create'}
                  className="rounded-xl bg-accent px-4 py-2.5 text-sm font-semibold text-accent-fg transition hover:opacity-90 disabled:opacity-60"
                >
                  Create Profile
                </button>
              </div>
            </div>
          </section>
        ) : (
          <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {visibleProfiles.map((profileView) => {
              const { issues, profile, runtimeReady, standardPack, lastLaunched } = profileView;
              const hasDanger = issues.some((i) => i.severity === 'danger');
              const hasWarning = issues.some((i) => i.severity === 'warning');
              const isActive = payload.active_profile_id === profile.profile_id;
              const busy = actionState?.profileId === profile.profile_id;
              const borderClass = cardBorderClass(hasDanger, hasWarning, isActive);

              return (
                <article
                  key={profile.profile_id}
                  className={`group relative flex flex-col rounded-2xl border bg-bg-card p-5 transition hover:border-text-muted/30 ${borderClass}`}
                >
                  {/* Top row */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      {isActive ? (
                        <>
                          <span className="h-2 w-2 rounded-full bg-accent shadow-[0_0_6px_rgba(99,102,241,0.5)]" />
                          <span className="text-[11px] font-medium text-accent">Active</span>
                        </>
                      ) : lastLaunched ? (
                        <span className="text-[11px] text-text-muted">Last used</span>
                      ) : (
                        <span className="text-[11px] text-transparent">.</span>
                      )}
                    </div>

                    <Popover>
                      <PopoverTrigger className="rounded-lg p-1.5 text-text-muted opacity-0 transition hover:bg-bg-hover group-hover:opacity-100">
                        <MoreHorizontal className="h-4 w-4" />
                      </PopoverTrigger>
                      <PopoverContent className="w-40">
                        <div className="flex flex-col">
                          <button
                            onClick={() => patchSearchParams({ edit: profile.profile_id })}
                            className="flex items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-text-main transition hover:bg-bg-hover"
                          >
                            <Save className="h-3.5 w-3.5" /> Edit
                          </button>
                          <button
                            onClick={() => void handleActivate(profile.profile_id)}
                            disabled={isActive || busy}
                            className={`flex items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition hover:bg-bg-hover ${isActive ? 'cursor-not-allowed opacity-50' : 'text-text-main'}`}
                          >
                            <Star className={`h-3.5 w-3.5 ${isActive ? 'fill-accent text-accent' : ''}`} />
                            {isActive ? 'Active' : 'Set Active'}
                          </button>
                          <button
                            onClick={() => void handleDuplicate(profile.profile_id)}
                            disabled={busy}
                            className="flex items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-text-main transition hover:bg-bg-hover disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {actionState?.type === 'duplicate' && busy ? (
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            ) : (
                              <Copy className="h-3.5 w-3.5" />
                            )}
                            Duplicate
                          </button>
                          <div className="my-1 border-t border-border" />
                          <button
                            onClick={() => handleDelete(profile.profile_id, profile.name)}
                            disabled={profileCount <= 1 || busy}
                            className="flex items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-rose-400 transition hover:bg-rose-500/10 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {actionState?.type === 'delete' && busy ? (
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            ) : (
                              <Trash2 className="h-3.5 w-3.5" />
                            )}
                            Delete
                          </button>
                        </div>
                      </PopoverContent>
                    </Popover>
                  </div>

                  {/* Icon */}
                  <div className="mt-4 flex justify-center">
                    <div className={`flex h-16 w-16 items-center justify-center rounded-2xl ${isActive ? 'bg-accent/10 text-accent' : 'bg-bg-hover text-text-muted'}`}>
                      <Box className="h-7 w-7" strokeWidth={1.5} />
                    </div>
                  </div>

                  {/* Name & Pack */}
                  <div className="mt-4 text-center">
                    <h3 className="font-semibold text-text-main">{profile.name}</h3>
                    <p className="mt-0.5 text-xs text-text-muted">
                      {standardPack?.display_name || profile.standard_pack_id}
                    </p>
                  </div>

                  {/* Status */}
                  <div className="mt-2 min-h-[18px] text-center">
                    {issues.length > 0 ? (
                      <span className={`text-[11px] ${hasDanger ? 'text-rose-400' : 'text-amber-400'}`}>
                        {issues[0].description}
                      </span>
                    ) : runtimeReady ? (
                      <span className="text-[11px] text-emerald-400/90">Ready</span>
                    ) : null}
                  </div>

                  {/* Actions */}
                  <div className="mt-auto pt-4 flex gap-2">
                    <button
                      onClick={() => void handleLaunch(profile.profile_id)}
                      disabled={!runtimeReady || busy}
                      className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-xl bg-accent px-3 py-2.5 text-sm font-semibold text-accent-fg transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      {actionState?.type === 'launch' && busy ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Rocket className="h-3.5 w-3.5" />
                      )}
                      Launch
                    </button>
                    <button
                      onClick={() => patchSearchParams({ edit: profile.profile_id })}
                      className="inline-flex items-center justify-center rounded-xl border border-border bg-bg-hover px-3 py-2.5 text-sm font-medium text-text-main transition hover:bg-bg-hover/80"
                    >
                      Edit
                    </button>
                  </div>
                </article>
              );
            })}

            {/* Create new card */}
            <button
              onClick={handleCreate}
              disabled={actionState?.type === 'create'}
              className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border bg-bg-card/50 p-5 text-center transition hover:border-accent/50 hover:bg-bg-card min-h-[260px]"
            >
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl border border-border bg-bg-hover text-text-muted">
                {actionState?.type === 'create' ? <Loader2 className="h-7 w-7 animate-spin text-accent" /> : <Plus className="h-7 w-7" />}
              </div>
              <h3 className="mt-4 font-semibold text-text-main">Create Profile</h3>
              <p className="mt-1 text-xs text-text-muted">Build a new startup profile</p>
            </button>
          </section>
        )}

        {/* Edit Panel */}
        {draft && catalog ? (
          <section className="rounded-2xl border border-border bg-bg-card p-6 lg:p-8">
            <div className="flex flex-col gap-6 border-b border-border pb-6 lg:flex-row lg:items-end lg:justify-between">
              <div className="space-y-2">
                <button
                  onClick={() => patchSearchParams({ edit: null })}
                  className="inline-flex items-center gap-2 text-sm font-medium text-text-muted transition hover:text-text-main"
                >
                  <ArrowLeft className="h-4 w-4" />
                  Back to profiles
                </button>
                <div>
                  <h2 className="text-2xl font-semibold tracking-tight text-text-main">{draft.name}</h2>
                  <p className="mt-1 text-sm text-text-muted">Edit profile settings and slot assignments.</p>
                </div>
              </div>

              <div className="flex flex-col gap-3 sm:flex-row">
                <button
                  onClick={() => void handleActivate(draft.profile_id)}
                  disabled={actionState?.profileId === draft.profile_id}
                  className="rounded-xl border border-border bg-bg-hover px-4 py-2.5 text-sm font-medium text-text-main transition hover:bg-bg-hover/80 disabled:opacity-60"
                >
                  Set Active
                </button>
                <button
                  onClick={() => void handleDuplicate(draft.profile_id)}
                  disabled={actionState?.profileId === draft.profile_id}
                  className="inline-flex items-center justify-center gap-2 rounded-xl border border-border bg-bg-hover px-4 py-2.5 text-sm font-medium text-text-main transition hover:bg-bg-hover/80 disabled:opacity-60"
                >
                  <Copy className="h-4 w-4" />
                  Duplicate
                </button>
                <button
                  onClick={() => handleDelete(draft.profile_id, draft.name)}
                  disabled={profileCount <= 1 || actionState?.profileId === draft.profile_id}
                  className="inline-flex items-center justify-center gap-2 rounded-xl border border-rose-950 bg-rose-950/20 px-4 py-2.5 text-sm font-medium text-rose-300 transition hover:bg-rose-950/40 disabled:opacity-60"
                >
                  <Trash2 className="h-4 w-4" />
                  Delete
                </button>
                <button
                  onClick={handleSave}
                  disabled={!isDirty || actionState?.type === 'save'}
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-accent px-5 py-2.5 text-sm font-semibold text-accent-fg transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {actionState?.type === 'save' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                  Save Changes
                </button>
              </div>
            </div>

            <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
              <div className="space-y-6">
                <section className="rounded-2xl border border-border bg-bg-main p-5">
                  <h3 className="text-base font-semibold text-text-main">General settings</h3>
                  <p className="mt-1 text-sm text-text-muted">Edit the profile name and choose which standard pack anchors the setup.</p>

                  <div className="mt-5 grid gap-5 md:grid-cols-2">
                    <label className="space-y-2">
                      <span className="text-xs font-semibold uppercase tracking-wider text-text-muted">Profile name</span>
                      <input
                        value={draft.name}
                        onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                        className="w-full rounded-xl border border-border bg-bg-hover px-4 py-3 text-sm text-text-main outline-none transition focus:border-accent"
                      />
                    </label>

                    <label className="space-y-2">
                      <span className="text-xs font-semibold uppercase tracking-wider text-text-muted">Standard pack</span>
                      <select
                        value={draft.standard_pack_id}
                        onChange={(event) => setDraft({ ...draft, standard_pack_id: event.target.value })}
                        className="w-full rounded-xl border border-border bg-bg-hover px-4 py-3 text-sm text-text-main outline-none transition focus:border-accent"
                      >
                        {standardPacks.map((pack) => (
                          <option key={pack.pack_id} value={pack.pack_id} disabled={!pack.available}>
                            {pack.display_name} {pack.available ? '' : '(unavailable)'}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>

                  {selectedStandardPack && !selectedStandardPack.runtime_ready ? (
                    <div className="mt-5 rounded-2xl border border-amber-900/40 bg-amber-950/20 p-4">
                      <div className="flex items-center gap-2 font-medium text-amber-100">
                        <AlertCircle className="h-4 w-4" />
                        Standard pack needs attention
                      </div>
                      <ul className="mt-3 space-y-2 text-sm text-amber-200/90">
                        {selectedStandardPack.runtime_issues.map((issue) => (
                          <li key={issue}>{describeStartupIssue(issue, selectedStandardPack.display_name).description}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </section>

                <section className="rounded-2xl border border-border bg-bg-main p-5">
                  <h3 className="text-base font-semibold text-text-main">Slot configuration</h3>
                  <p className="mt-1 text-sm text-text-muted">Choose the pack used for each slot.</p>

                  <div className="mt-5 grid gap-4">
                    {slotSpecs.map((slot) => {
                      const candidates = catalog.slot_candidates[slot.slot_id] ?? [];
                      const selectedCandidate = selectedCandidatesBySlot[slot.slot_id];

                      return (
                        <div key={slot.slot_id} className="rounded-xl border border-border bg-bg-hover/50 p-4">
                          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                            <div>
                              <div className="text-sm font-semibold text-text-main">{slot.label}</div>
                              <div className="mt-0.5 text-xs text-text-muted">{slot.description}</div>
                            </div>
                            <span className="rounded-full border border-border bg-bg-hover px-2.5 py-0.5 text-[11px] font-medium text-text-muted">
                              {slot.contract}
                            </span>
                          </div>

                          <select
                            value={draft.slots[slot.slot_id] ?? ''}
                            onChange={(event) =>
                              setDraft({
                                ...draft,
                                slots: { ...draft.slots, [slot.slot_id]: event.target.value },
                              })
                            }
                            className="mt-3 w-full rounded-xl border border-border bg-bg-hover px-4 py-2.5 text-sm text-text-main outline-none transition focus:border-accent"
                          >
                            {candidates.length === 0 ? <option value="">No compatible packs available</option> : null}
                            {candidates.map((candidate) => (
                              <option key={candidate.pack_id} value={candidate.pack_id} disabled={!candidate.runtime_ready}>
                                {candidate.display_name} {candidate.runtime_ready ? '' : '(needs attention)'}
                              </option>
                            ))}
                          </select>

                          {selectedCandidate && !selectedCandidate.runtime_ready ? (
                            <div className="mt-3 space-y-2 rounded-xl border border-amber-900/30 bg-amber-950/15 p-3 text-sm text-amber-100">
                              {selectedCandidate.runtime_issues.map((issue: string) => (
                                <div key={issue} className="flex items-start gap-2">
                                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                                  <span>{describeStartupIssue(issue, slot.label).description}</span>
                                </div>
                              ))}
                            </div>
                          ) : null}
                        </div>
                      );
                    })}
                  </div>
                </section>
              </div>

              <aside className="space-y-4">
                <section className="rounded-2xl border border-border bg-bg-main p-5">
                  <div className="text-xs font-semibold uppercase tracking-wider text-text-muted">Quick launch</div>
                  <div className="mt-4 space-y-3">
                    <button
                      onClick={() => void handleLaunch(draft.profile_id)}
                      disabled={actionState?.profileId === draft.profile_id}
                      className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-accent px-4 py-3 text-sm font-semibold text-accent-fg transition hover:opacity-90 disabled:opacity-50"
                    >
                      {actionState?.type === 'launch' && actionState?.profileId === draft.profile_id ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Rocket className="h-4 w-4" />
                      )}
                      Launch Profile
                    </button>
                    <p className="text-sm leading-6 text-text-muted">
                      Launch always uses the latest saved server state.
                    </p>
                  </div>
                </section>

                <section className="rounded-2xl border border-border bg-bg-main p-5">
                  <div className="text-xs font-semibold uppercase tracking-wider text-text-muted">Profile metadata</div>
                  <div className="mt-4 space-y-4 text-sm">
                    <div>
                      <div className="text-text-muted">Profile ID</div>
                      <div className="mt-1 break-all rounded-xl border border-border bg-bg-hover px-3 py-2 font-mono text-xs text-text-main">
                        {draft.profile_id}
                      </div>
                    </div>
                    <div>
                      <div className="text-text-muted">Created</div>
                      <div className="mt-1 text-text-main">{formatTimestamp(draft.created_at)}</div>
                    </div>
                    <div>
                      <div className="text-text-muted">Last updated</div>
                      <div className="mt-1 text-text-main">{formatTimestamp(draft.updated_at)}</div>
                    </div>
                    <div>
                      <div className="text-text-muted">Save status</div>
                      <div className="mt-1 text-text-main">{isDirty ? 'Unsaved changes' : 'Saved'}</div>
                    </div>
                  </div>
                </section>
              </aside>
            </div>
          </section>
        ) : null}
      </div>
    </div>
  );
}

function SkeletonPulse({ className }: { className: string }) {
  return (
    <div
      className={`animate-pulse rounded-xl bg-bg-hover ${className}`}
    />
  );
}

function DashboardSkeleton() {
  return (
    <div className="flex flex-1 overflow-hidden bg-bg-main text-text-main">
      <div className="mx-auto flex w-full max-w-[1200px] flex-col gap-6 px-6 py-8 lg:px-10 scrollbar-hidden overflow-y-auto">
        {/* Header skeleton */}
        <section className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-2">
            <SkeletonPulse className="h-8 w-48" />
            <SkeletonPulse className="h-4 w-64" />
          </div>
          <div className="flex items-center gap-3">
            <SkeletonPulse className="h-10 w-40" />
            <SkeletonPulse className="h-10 w-32" />
          </div>
        </section>

        {/* Profile cards skeleton */}
        <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <article
              key={i}
              className="flex flex-col rounded-2xl border border-border bg-bg-card p-5"
            >
              <div className="flex items-center justify-between">
                <SkeletonPulse className="h-3 w-12" />
                <SkeletonPulse className="h-6 w-6 rounded-lg" />
              </div>
              <div className="mt-4 flex justify-center">
                <SkeletonPulse className="h-16 w-16 rounded-2xl" />
              </div>
              <div className="mt-4 flex flex-col items-center gap-2">
                <SkeletonPulse className="h-5 w-32" />
                <SkeletonPulse className="h-3 w-24" />
              </div>
              <div className="mt-2 flex justify-center">
                <SkeletonPulse className="h-3 w-20" />
              </div>
              <div className="mt-auto pt-4 flex gap-2">
                <SkeletonPulse className="h-10 flex-1" />
                <SkeletonPulse className="h-10 w-16" />
              </div>
            </article>
          ))}
          {/* Create card skeleton */}
          <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border bg-bg-card/50 p-5 min-h-[260px]">
            <SkeletonPulse className="h-16 w-16 rounded-2xl" />
            <SkeletonPulse className="mt-4 h-5 w-28" />
            <SkeletonPulse className="mt-1 h-3 w-36" />
          </div>
        </section>
      </div>
    </div>
  );
}
