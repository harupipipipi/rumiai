import { useEffect, useMemo, useState, type ReactNode } from 'react';
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
  ApiStartupCatalog,
  ApiStartupNodePort,
  ApiStartupProfile,
  ApiStartupSlotCandidate,
  ApiStartupSlotSpec,
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
  Clock3,
  Copy,
  ExternalLink,
  FolderKanban,
  Layers3,
  LayoutGrid,
  Loader2,
  Play,
  Plus,
  RefreshCw,
  Rocket,
  Save,
  Search,
  Sparkles,
  Star,
  Trash2,
} from 'lucide-react';

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

function summarizeProvide(value: string): string {
  return value.replace(/^defaults\./, '');
}

function renderContracts(contracts: string[]) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {contracts.map((contract) => (
        <span
          key={contract}
          className="rounded-full border border-stone-800 bg-stone-950 px-2 py-0.5 text-[10px] font-medium text-stone-400"
        >
          {contract}
        </span>
      ))}
    </div>
  );
}

function NodePorts({ ports, direction }: { ports: ApiStartupNodePort[]; direction: 'input' | 'output' }) {
  const directionalPorts = ports.filter((port) => port.direction === direction);
  if (directionalPorts.length === 0) {
    return <div className="min-h-8" />;
  }

  return (
    <div className="flex flex-col gap-2">
      {directionalPorts.map((port) => (
        <div
          key={`${direction}-${port.port_id}`}
          className={`flex items-center gap-2 ${direction === 'output' ? 'justify-end text-right' : ''}`}
        >
          {direction === 'input' ? <span className="h-2.5 w-2.5 shrink-0 rounded-full border border-stone-600 bg-stone-300" /> : null}
          <div className="max-w-[8rem]">
            <div className="text-[10px] font-semibold text-stone-200">{port.label}</div>
            <div className="text-[9px] text-stone-500">{port.multi ? 'multi' : 'single'}</div>
          </div>
          {direction === 'output' ? <span className="h-2.5 w-2.5 shrink-0 rounded-full border border-stone-600 bg-stone-300" /> : null}
        </div>
      ))}
    </div>
  );
}

function ContractNode({
  title,
  subtitle,
  character,
  ports,
  tone = 'amber',
  footer,
}: {
  title: string;
  subtitle: string;
  character: string;
  ports: ApiStartupNodePort[];
  tone?: 'amber' | 'emerald' | 'rose' | 'sky';
  footer?: ReactNode;
}) {
  const toneClasses = {
    amber: 'from-amber-950/60 to-stone-950 border-amber-900/40 text-amber-50',
    emerald: 'from-emerald-950/60 to-stone-950 border-emerald-900/40 text-emerald-50',
    rose: 'from-rose-950/60 to-stone-950 border-rose-900/40 text-rose-50',
    sky: 'from-sky-950/60 to-stone-950 border-sky-900/40 text-sky-50',
  }[tone];

  return (
    <div className="rounded-[24px] border border-stone-900 bg-stone-950/80 p-2 shadow-xl shadow-black/20">
      <div className={`rounded-[18px] border bg-gradient-to-br p-4 ${toneClasses}`}>
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <div className="text-base font-semibold tracking-tight text-white">{title}</div>
            <div className="mt-1 text-xs leading-5 text-stone-400">{subtitle}</div>
          </div>
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/5 text-lg font-black text-stone-200">
            {character}
          </div>
        </div>

        <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-start gap-4">
          <NodePorts ports={ports} direction="input" />
          <div className="mt-2 h-full w-px bg-stone-800" />
          <NodePorts ports={ports} direction="output" />
        </div>

        {footer ? <div className="mt-4 border-t border-stone-800 pt-3">{footer}</div> : null}
      </div>
    </div>
  );
}

function buildStandardPackPorts(catalog: ApiStartupCatalog): ApiStartupNodePort[] {
  return [
    {
      port_id: 'start',
      label: 'start',
      direction: 'input',
      contracts: catalog.start_node.ports[0]?.contracts ?? [],
      multi: false,
    },
    ...catalog.slot_specs.map((slot) => ({
      port_id: slot.slot_id,
      label: slot.label,
      direction: 'output' as const,
      contracts: [slot.contract],
      multi: slot.multi,
    })),
  ];
}

function buildSlotNodePorts(slot: ApiStartupSlotSpec, candidate: ApiStartupSlotCandidate | null): ApiStartupNodePort[] {
  const ports: ApiStartupNodePort[] = [
    {
      port_id: `${slot.slot_id}-in`,
      label: slot.label,
      direction: 'input',
      contracts: [slot.contract],
      multi: slot.multi,
    },
  ];

  if (!candidate) {
    return ports;
  }

  candidate.provides.slice(0, 3).forEach((provide, index) => {
    ports.push({
      port_id: `${slot.slot_id}-out-${index}`,
      label: summarizeProvide(provide),
      direction: 'output',
      contracts: [provide],
      multi: true,
    });
  });

  return ports;
}

function toneClassesForIssue(hasDanger: boolean, hasWarning: boolean): string {
  if (hasDanger) return 'from-rose-950/70 to-stone-950 border-rose-900/40';
  if (hasWarning) return 'from-amber-950/70 to-stone-950 border-amber-900/40';
  return 'from-stone-900 to-stone-950 border-stone-800';
}

function accentClassesForIssue(hasDanger: boolean, hasWarning: boolean): string {
  if (hasDanger) return 'bg-rose-950/60 text-rose-200 ring-1 ring-inset ring-rose-900/60';
  if (hasWarning) return 'bg-amber-950/60 text-amber-200 ring-1 ring-inset ring-amber-900/60';
  return 'bg-violet-600/15 text-violet-200 ring-1 ring-inset ring-violet-500/30';
}

export function Dashboard() {
  const addToast = useAppStore((state) => state.addToast);
  const showDialog = useAppStore((state) => state.showDialog);
  const closeDialog = useAppStore((state) => state.closeDialog);
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
  const [showAdvanced, setShowAdvanced] = useState(false);

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
    void refreshDashboard();
    void refreshProfiles();
  }, []);

  const selectedProfile = useMemo(
    () => payload?.profiles.find((profile) => profile.profile_id === editProfileId) ?? null,
    [editProfileId, payload],
  );

  useEffect(() => {
    if (!selectedProfile) {
      setDraft(null);
      setShowAdvanced(false);
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
    if (!catalog || !draft) return {} as Record<string, ApiStartupSlotCandidate | null>;
    return Object.fromEntries(
      slotSpecs.map((slot) => [
        slot.slot_id,
        (catalog.slot_candidates[slot.slot_id] ?? []).find((candidate) => candidate.pack_id === draft.slots[slot.slot_id]) ?? null,
      ]),
    ) as Record<string, ApiStartupSlotCandidate | null>;
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

  if (profilesLoading && !payload) {
    return (
      <div className="flex flex-1 items-center justify-center bg-[#0b0b0c] px-4 text-stone-200">
        <div className="flex max-w-md flex-col items-center gap-4 text-center">
          <Loader2 className="h-8 w-8 animate-spin text-violet-400" />
          <div className="space-y-2">
            <h1 className="text-2xl font-semibold text-white">Loading your launcher home</h1>
            <p className="text-sm text-stone-500">Fetching profiles, pack readiness, and workspace status.</p>
          </div>
        </div>
      </div>
    );
  }

  if (!payload) {
    return (
      <div className="flex flex-1 items-center justify-center bg-[#0b0b0c] px-4 text-stone-200">
        <div className="flex max-w-lg flex-col gap-4 rounded-3xl border border-stone-800 bg-stone-950/90 p-8">
          <div className="flex items-start gap-3">
            <AlertCircle className="mt-0.5 h-5 w-5 text-rose-400" />
            <div className="space-y-2">
              <h1 className="text-2xl font-semibold text-white">Home could not load</h1>
              <p className="text-sm text-stone-400">{profilesError || 'The launcher could not load your profiles yet.'}</p>
            </div>
          </div>
          <button
            onClick={() => void refreshProfiles()}
            className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-violet-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-violet-500 sm:w-fit"
          >
            <RefreshCw className="h-4 w-4" />
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 overflow-y-auto bg-[#0b0b0c] text-stone-200">
      <div className="mx-auto flex w-full max-w-[1460px] flex-col gap-8 px-6 py-8 lg:px-10">
        <section className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-2">
            <div className="inline-flex items-center gap-2 rounded-full border border-stone-800 bg-stone-950/70 px-3 py-1 text-xs font-medium text-stone-400">
              <Sparkles className="h-3.5 w-3.5 text-violet-300" />
              Launcher Home
            </div>
            <div>
              <h1 className="text-4xl font-semibold tracking-tight text-white">My Profiles</h1>
              <p className="mt-2 text-base text-stone-500">
                Launch fast, keep custom setups organized, and open advanced editing only when you need it.
              </p>
            </div>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <label className="flex items-center gap-2 rounded-xl border border-stone-800 bg-stone-950 px-3 py-2 text-sm text-stone-400">
              <LayoutGrid className="h-4 w-4" />
              <select
                value={sortMode}
                onChange={(event) => patchSearchParams({ sort: event.target.value })}
                className="bg-transparent text-sm text-stone-200 outline-none"
              >
                <option value="recommended">Recommended</option>
                <option value="recent">Recently updated</option>
                <option value="name">Name</option>
              </select>
            </label>

            <button
              onClick={handleCreate}
              disabled={actionState?.type === 'create'}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-violet-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {actionState?.type === 'create' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              Create Custom Profile
            </button>
          </div>
        </section>

        {feedback ? (
          <div
            className={`flex flex-col gap-3 rounded-2xl border px-5 py-4 sm:flex-row sm:items-center sm:justify-between ${
              feedback.tone === 'error'
                ? 'border-rose-900/60 bg-rose-950/40 text-rose-100'
                : 'border-emerald-900/60 bg-emerald-950/30 text-emerald-100'
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

        {profilesError ? (
          <div className="flex flex-col gap-3 rounded-2xl border border-amber-900/40 bg-amber-950/25 px-5 py-4 text-amber-100 sm:flex-row sm:items-center sm:justify-between">
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

        {visibleProfiles.length === 0 ? (
          <section className="rounded-[28px] border border-dashed border-stone-800 bg-stone-950/60 px-8 py-14 text-center">
            <div className="mx-auto flex max-w-xl flex-col items-center gap-4">
              <div className="flex h-20 w-20 items-center justify-center rounded-full border border-stone-800 bg-stone-900 text-stone-500">
                {searchQuery ? <Search className="h-9 w-9" /> : <Plus className="h-9 w-9" />}
              </div>
              <div className="space-y-2">
                <h2 className="text-2xl font-semibold text-white">
                  {searchQuery ? 'No profiles match that search' : 'Create your first profile'}
                </h2>
                <p className="text-sm leading-6 text-stone-500">
                  {searchQuery
                    ? 'Try a different profile name, pack name, or slot search.'
                    : 'Profiles keep your preferred standard pack and slot setup ready for launch.'}
                </p>
              </div>
              <div className="flex flex-col gap-3 sm:flex-row">
                {searchQuery ? (
                  <button
                    onClick={() => patchSearchParams({ q: null })}
                    className="rounded-xl border border-stone-800 bg-stone-900 px-4 py-3 text-sm font-medium text-stone-200 transition hover:bg-stone-800"
                  >
                    Clear search
                  </button>
                ) : null}
                <button
                  onClick={handleCreate}
                  disabled={actionState?.type === 'create'}
                  className="rounded-xl bg-violet-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-violet-500 disabled:opacity-60"
                >
                  Create Custom Profile
                </button>
              </div>
            </div>
          </section>
        ) : (
          <section className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
            {visibleProfiles.map((profileView) => {
              const { badges, issueCount, issues, profile, runtimeReady, slots, standardPack } = profileView;
              const hasDanger = issues.some((issue) => issue.severity === 'danger');
              const hasWarning = issues.some((issue) => issue.severity === 'warning');
              const busy = actionState?.profileId === profile.profile_id;
              const statusTone = toneClassesForIssue(hasDanger, hasWarning);
              const accentTone = accentClassesForIssue(hasDanger, hasWarning);
              const summaryLine = issueCount > 0
                ? issues[0]?.description || 'Needs attention before launch.'
                : runtimeReady
                  ? 'Ready for quick play.'
                  : 'Needs attention before launch.';

              return (
                <article
                  key={profile.profile_id}
                  className={`group flex min-h-[380px] flex-col rounded-[28px] border bg-gradient-to-br p-6 shadow-[0_24px_80px_-48px_rgba(0,0,0,0.85)] ${statusTone}`}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex flex-wrap gap-2">
                      {badges.map((badge) => (
                        <span
                          key={`${profile.profile_id}-${badge.label}`}
                          className={`rounded-full px-3 py-1 text-[11px] font-medium ${
                            badge.tone === 'accent'
                              ? 'bg-violet-600/20 text-violet-100 ring-1 ring-inset ring-violet-500/30'
                              : badge.tone === 'success'
                                ? 'bg-emerald-600/15 text-emerald-100 ring-1 ring-inset ring-emerald-500/25'
                                : badge.tone === 'danger'
                                  ? 'bg-rose-600/15 text-rose-100 ring-1 ring-inset ring-rose-500/25'
                                  : badge.tone === 'warning'
                                    ? 'bg-amber-600/15 text-amber-100 ring-1 ring-inset ring-amber-500/25'
                                    : 'bg-stone-800 text-stone-300 ring-1 ring-inset ring-stone-700'
                          }`}
                        >
                          {badge.label}
                        </span>
                      ))}
                    </div>

                    <button
                      onClick={() => void handleActivate(profile.profile_id)}
                      disabled={busy || payload.active_profile_id === profile.profile_id}
                      className={`inline-flex h-10 w-10 items-center justify-center rounded-xl transition ${
                        payload.active_profile_id === profile.profile_id
                          ? 'bg-white/10 text-white'
                          : 'bg-black/20 text-stone-400 hover:bg-black/35 hover:text-white'
                      } disabled:cursor-not-allowed disabled:opacity-70`}
                      title={payload.active_profile_id === profile.profile_id ? 'Active profile' : 'Set active'}
                    >
                      {actionState?.type === 'activate' && busy ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Star className="h-4 w-4" fill={payload.active_profile_id === profile.profile_id ? 'currentColor' : 'none'} />
                      )}
                    </button>
                  </div>

                  <div className="mt-8 flex justify-center">
                    <div className={`flex h-24 w-24 items-center justify-center rounded-full ${accentTone}`}>
                      <Box className="h-10 w-10" strokeWidth={1.5} />
                    </div>
                  </div>

                  <div className="mt-8 space-y-3">
                    <div>
                      <h2 className="text-2xl font-semibold tracking-tight text-white">{profile.name}</h2>
                      <p className="mt-2 text-sm text-stone-400">
                        {standardPack?.display_name || profile.standard_pack_id}
                      </p>
                    </div>
                    <p className="text-sm leading-6 text-stone-500">{summaryLine}</p>
                  </div>

                  <div className="mt-auto pt-6">
                    <div className="grid grid-cols-2 gap-3">
                      <button
                        onClick={() => patchSearchParams({ edit: profile.profile_id })}
                        className="rounded-xl border border-stone-800 bg-stone-900 px-4 py-3 text-sm font-medium text-white transition hover:bg-stone-800"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => void handleLaunch(profile.profile_id)}
                        disabled={!runtimeReady || busy}
                        className="inline-flex items-center justify-center gap-2 rounded-xl bg-violet-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {actionState?.type === 'launch' && busy ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Play className="h-4 w-4 fill-current" />
                        )}
                        Play
                      </button>
                    </div>

                    <div className="mt-3 grid grid-cols-3 gap-3">
                      <button
                        onClick={() => void handleActivate(profile.profile_id)}
                        disabled={busy || payload.active_profile_id === profile.profile_id}
                        className="rounded-xl border border-stone-800 bg-black/20 px-3 py-2.5 text-xs font-medium text-stone-300 transition hover:bg-stone-900 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Set Active
                      </button>
                      <button
                        onClick={() => void handleDuplicate(profile.profile_id)}
                        disabled={busy}
                        className="inline-flex items-center justify-center gap-1.5 rounded-xl border border-stone-800 bg-black/20 px-3 py-2.5 text-xs font-medium text-stone-300 transition hover:bg-stone-900 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {actionState?.type === 'duplicate' && busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Copy className="h-3.5 w-3.5" />}
                        Duplicate
                      </button>
                      <button
                        onClick={() => handleDelete(profile.profile_id, profile.name)}
                        disabled={profileCount <= 1 || busy}
                        className="inline-flex items-center justify-center gap-1.5 rounded-xl border border-rose-950 bg-rose-950/20 px-3 py-2.5 text-xs font-medium text-rose-200 transition hover:bg-rose-950/40 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {actionState?.type === 'delete' && busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                        Delete
                      </button>
                    </div>
                  </div>
                </article>
              );
            })}

            <button
              onClick={handleCreate}
              disabled={actionState?.type === 'create'}
              className="flex min-h-[420px] flex-col items-center justify-center rounded-[28px] border border-dashed border-stone-800 bg-stone-950/50 p-6 text-center transition hover:border-violet-700 hover:bg-stone-950"
            >
              <div className="flex h-24 w-24 items-center justify-center rounded-full border border-stone-800 bg-stone-900 text-stone-500">
                {actionState?.type === 'create' ? <Loader2 className="h-9 w-9 animate-spin text-violet-400" /> : <Plus className="h-9 w-9" strokeWidth={1.25} />}
              </div>
              <h2 className="mt-8 text-2xl font-semibold text-white">Create Custom Profile</h2>
              <p className="mt-3 max-w-[240px] text-sm leading-6 text-stone-500">
                Start from scratch, keep a test setup separate, or build a launch profile for a specific workflow.
              </p>
            </button>
          </section>
        )}

        {draft && catalog ? (
          <section className="rounded-[32px] border border-stone-800 bg-stone-950/90 p-6 shadow-[0_32px_120px_-64px_rgba(0,0,0,0.95)] lg:p-8">
            <div className="flex flex-col gap-6 border-b border-stone-800 pb-6 lg:flex-row lg:items-end lg:justify-between">
              <div className="space-y-2">
                <button
                  onClick={() => patchSearchParams({ edit: null })}
                  className="inline-flex items-center gap-2 text-sm font-medium text-stone-500 transition hover:text-stone-300"
                >
                  <ArrowLeft className="h-4 w-4" />
                  Back to library
                </button>
                <div>
                  <h2 className="text-3xl font-semibold tracking-tight text-white">{draft.name}</h2>
                  <p className="mt-2 text-sm text-stone-500">
                    Keep the simple launcher view above, and open advanced pack wiring only when you need to inspect it.
                  </p>
                </div>
              </div>

              <div className="flex flex-col gap-3 sm:flex-row">
                <button
                  onClick={() => void handleActivate(draft.profile_id)}
                  disabled={actionState?.profileId === draft.profile_id}
                  className="rounded-xl border border-stone-800 bg-stone-900 px-4 py-3 text-sm font-medium text-stone-200 transition hover:bg-stone-800 disabled:opacity-60"
                >
                  Set Active
                </button>
                <button
                  onClick={() => void handleDuplicate(draft.profile_id)}
                  disabled={actionState?.profileId === draft.profile_id}
                  className="inline-flex items-center justify-center gap-2 rounded-xl border border-stone-800 bg-stone-900 px-4 py-3 text-sm font-medium text-stone-200 transition hover:bg-stone-800 disabled:opacity-60"
                >
                  <Copy className="h-4 w-4" />
                  Duplicate
                </button>
                <button
                  onClick={() => handleDelete(draft.profile_id, draft.name)}
                  disabled={profileCount <= 1 || actionState?.profileId === draft.profile_id}
                  className="inline-flex items-center justify-center gap-2 rounded-xl border border-rose-950 bg-rose-950/20 px-4 py-3 text-sm font-medium text-rose-200 transition hover:bg-rose-950/40 disabled:opacity-60"
                >
                  <Trash2 className="h-4 w-4" />
                  Delete
                </button>
                <button
                  onClick={handleSave}
                  disabled={!isDirty || actionState?.type === 'save'}
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-violet-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {actionState?.type === 'save' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                  Save Changes
                </button>
              </div>
            </div>

            <div className="mt-8 grid gap-8 xl:grid-cols-[minmax(0,1fr)_320px]">
              <div className="space-y-6">
                <section className="rounded-[24px] border border-stone-800 bg-stone-950/70 p-6">
                  <h3 className="text-lg font-semibold text-white">General settings</h3>
                  <p className="mt-1 text-sm text-stone-500">Edit the profile name and choose which standard pack anchors the setup.</p>

                  <div className="mt-6 grid gap-5 md:grid-cols-2">
                    <label className="space-y-2">
                      <span className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Profile name</span>
                      <input
                        value={draft.name}
                        onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                        className="w-full rounded-xl border border-stone-800 bg-stone-900 px-4 py-3 text-sm text-white outline-none transition focus:border-violet-600"
                      />
                    </label>

                    <label className="space-y-2">
                      <span className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Standard pack</span>
                      <select
                        value={draft.standard_pack_id}
                        onChange={(event) => setDraft({ ...draft, standard_pack_id: event.target.value })}
                        className="w-full rounded-xl border border-stone-800 bg-stone-900 px-4 py-3 text-sm text-white outline-none transition focus:border-violet-600"
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

                <section className="rounded-[24px] border border-stone-800 bg-stone-950/70 p-6">
                  <h3 className="text-lg font-semibold text-white">Slot configuration</h3>
                  <p className="mt-1 text-sm text-stone-500">Choose the pack used for each slot, and keep launch-blocking issues visible before save.</p>

                  <div className="mt-6 grid gap-4">
                    {slotSpecs.map((slot) => {
                      const candidates = catalog.slot_candidates[slot.slot_id] ?? [];
                      const selectedCandidate = selectedCandidatesBySlot[slot.slot_id];

                      return (
                        <div key={slot.slot_id} className="rounded-2xl border border-stone-800 bg-black/20 p-5">
                          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                            <div>
                              <div className="text-base font-semibold text-white">{slot.label}</div>
                              <div className="mt-1 text-sm text-stone-500">{slot.description}</div>
                            </div>
                            <span className="rounded-full border border-stone-800 bg-stone-900 px-2.5 py-1 text-[11px] font-medium text-stone-400">
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
                            className="mt-4 w-full rounded-xl border border-stone-800 bg-stone-900 px-4 py-3 text-sm text-white outline-none transition focus:border-violet-600"
                          >
                            {candidates.length === 0 ? <option value="">No compatible packs available</option> : null}
                            {candidates.map((candidate) => (
                              <option key={candidate.pack_id} value={candidate.pack_id} disabled={!candidate.runtime_ready}>
                                {candidate.display_name} {candidate.runtime_ready ? '' : '(needs attention)'}
                              </option>
                            ))}
                          </select>

                          {selectedCandidate && !selectedCandidate.runtime_ready ? (
                            <div className="mt-3 space-y-2 rounded-2xl border border-amber-900/30 bg-amber-950/15 p-3 text-sm text-amber-100">
                              {selectedCandidate.runtime_issues.map((issue) => (
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

                <section className="rounded-[24px] border border-stone-800 bg-stone-950/70 p-6">
                  <button
                    onClick={() => setShowAdvanced((current) => !current)}
                    className="flex w-full items-center justify-between text-left"
                  >
                    <div>
                      <h3 className="text-lg font-semibold text-white">Advanced inspector</h3>
                      <p className="mt-1 text-sm text-stone-500">Contract graph and pack identity stay available, but out of the main launcher flow.</p>
                    </div>
                    <ChevronRight className={`h-5 w-5 text-stone-500 transition-transform ${showAdvanced ? 'rotate-90' : ''}`} />
                  </button>

                  {showAdvanced ? (
                    <div className="mt-6 space-y-5">
                      <div className="grid gap-4 xl:grid-cols-[240px_1fr]">
                        <ContractNode
                          title={catalog.start_node.title}
                          subtitle={catalog.start_node.subtitle}
                          character={catalog.start_node.character}
                          ports={catalog.start_node.ports}
                          tone="rose"
                          footer={renderContracts(catalog.start_node.ports[0]?.contracts ?? [])}
                        />
                        <ContractNode
                          title={selectedStandardPack?.display_name ?? draft.standard_pack_id}
                          subtitle={selectedStandardPack?.description ?? 'Reference pack.'}
                          character={selectedStandardPack?.character ?? 'D'}
                          ports={buildStandardPackPorts(catalog)}
                          tone="amber"
                          footer={
                            <div className="space-y-2">
                              <div className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Pack identity</div>
                              <div className="text-sm text-stone-300">{selectedStandardPack?.pack_identity || 'Unavailable'}</div>
                            </div>
                          }
                        />
                      </div>

                      <div className="grid gap-4 md:grid-cols-2">
                        {slotSpecs.map((slot) => {
                          const candidate = selectedCandidatesBySlot[slot.slot_id];
                          return (
                            <ContractNode
                              key={slot.slot_id}
                              title={candidate?.display_name ?? slot.label}
                              subtitle={`${slot.label} slot`}
                              character={candidate?.character ?? slot.character}
                              ports={buildSlotNodePorts(slot, candidate)}
                              tone={slot.slot_id === 'frontend' ? 'sky' : slot.slot_id === 'memory' ? 'emerald' : 'amber'}
                              footer={
                                <div className="space-y-2">
                                  {renderContracts([slot.contract])}
                                  <div className="text-xs text-stone-500">
                                    Connected from <span className="font-semibold text-stone-300">{draft.standard_pack_id}.{slot.slot_id}</span>
                                  </div>
                                </div>
                              }
                            />
                          );
                        })}
                      </div>
                    </div>
                  ) : null}
                </section>
              </div>

              <aside className="space-y-4">
                <section className="rounded-[24px] border border-stone-800 bg-stone-950/70 p-5">
                  <div className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Profile metadata</div>
                  <div className="mt-4 space-y-4 text-sm">
                    <div>
                      <div className="text-stone-500">Profile ID</div>
                      <div className="mt-1 break-all rounded-xl border border-stone-800 bg-stone-900 px-3 py-2 font-mono text-xs text-stone-300">
                        {draft.profile_id}
                      </div>
                    </div>
                    <div>
                      <div className="text-stone-500">Created</div>
                      <div className="mt-1 text-stone-200">{formatTimestamp(draft.created_at)}</div>
                    </div>
                    <div>
                      <div className="text-stone-500">Last updated</div>
                      <div className="mt-1 text-stone-200">{formatTimestamp(draft.updated_at)}</div>
                    </div>
                    <div>
                      <div className="text-stone-500">Save status</div>
                      <div className="mt-1 text-stone-200">{isDirty ? 'Unsaved changes' : 'Saved'}</div>
                    </div>
                  </div>
                </section>

                <section className="rounded-[24px] border border-stone-800 bg-stone-950/70 p-5">
                  <div className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500">Quick launch</div>
                  <div className="mt-4 space-y-3">
                    <button
                      onClick={() => void handleLaunch(draft.profile_id)}
                      disabled={actionState?.profileId === draft.profile_id}
                      className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-violet-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-violet-500 disabled:opacity-50"
                    >
                      {actionState?.type === 'launch' && actionState?.profileId === draft.profile_id ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Rocket className="h-4 w-4" />
                      )}
                      Launch Profile
                    </button>
                    <p className="text-sm leading-6 text-stone-500">
                      Launch always uses the latest saved server state, then requests the handoff the runtime actually supports.
                    </p>
                  </div>
                </section>
              </aside>
            </div>
          </section>
        ) : null}

        <section className="grid gap-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,0.7fr)]">
          <div className="rounded-[28px] border border-stone-800 bg-stone-950/70 p-6">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="text-xl font-semibold text-white">System overview</h2>
                <p className="mt-1 text-sm text-stone-500">A quick workspace summary stays on Home so launch actions never feel detached from runtime status.</p>
              </div>
              <button
                onClick={handleRestartKernel}
                disabled={actionState?.type === 'restart'}
                className="inline-flex items-center justify-center gap-2 rounded-xl border border-stone-800 bg-stone-900 px-4 py-3 text-sm font-medium text-stone-200 transition hover:bg-stone-800 disabled:opacity-60"
              >
                {actionState?.type === 'restart' ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                Restart Kernel
              </button>
            </div>

            {dashboardError ? (
              <div className="mt-5 rounded-2xl border border-amber-900/40 bg-amber-950/25 p-4 text-sm text-amber-100">
                <div className="flex items-start gap-2">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>{dashboardError}</span>
                </div>
                <button
                  onClick={() => void refreshDashboard()}
                  className="mt-3 inline-flex items-center gap-2 rounded-xl border border-amber-900/40 bg-black/20 px-3 py-2 text-sm font-medium text-amber-100 transition hover:bg-black/35"
                >
                  <RefreshCw className="h-4 w-4" />
                  Retry summary
                </button>
              </div>
            ) : null}

            <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {[
                {
                  icon: <Rocket className="h-5 w-5 text-violet-300" />,
                  label: 'Kernel',
                  value: dashboardLoading ? 'Loading...' : dashboard.kernelStatus,
                },
                {
                  icon: <Clock3 className="h-5 w-5 text-sky-300" />,
                  label: 'Uptime',
                  value: dashboardLoading ? 'Loading...' : dashboard.uptime,
                },
                {
                  icon: <FolderKanban className="h-5 w-5 text-emerald-300" />,
                  label: 'Active Packs',
                  value: dashboardLoading ? 'Loading...' : String(dashboard.activePacks),
                },
                {
                  icon: <LayoutGrid className="h-5 w-5 text-amber-300" />,
                  label: 'Registered Flows',
                  value: dashboardLoading ? 'Loading...' : String(dashboard.registeredFlows),
                },
              ].map((card) => (
                <div key={card.label} className="rounded-2xl border border-stone-800 bg-black/20 p-4">
                  <div className="flex items-center gap-3 text-sm text-stone-500">
                    {card.icon}
                    <span>{card.label}</span>
                  </div>
                  <div className="mt-3 text-xl font-semibold text-white">{card.value}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-[28px] border border-stone-800 bg-stone-950/70 p-6">
            <div className="flex items-start gap-4">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-stone-800 bg-stone-900 text-stone-300">
                <Layers3 className="h-5 w-5" />
              </div>
              <div>
                <h2 className="text-xl font-semibold text-white">What is a profile?</h2>
                <p className="mt-2 text-sm leading-7 text-stone-500">
                  Profiles save different combinations of standard packs and slot selections. Keep a stable default, build a test profile for experiments,
                  and jump between them without reopening raw editor screens.
                </p>
              </div>
            </div>

            <div className="mt-6 flex flex-col gap-3 text-sm text-stone-400">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-300" />
                Play is always the primary action from Home.
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-300" />
                Advanced contract details stay tucked away until inspection is needed.
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-300" />
                Runtime issues are translated into launcher-friendly guidance.
              </div>
            </div>

            <button className="mt-6 inline-flex items-center gap-2 rounded-xl border border-stone-800 bg-stone-900 px-4 py-3 text-sm font-medium text-stone-200 transition hover:bg-stone-800">
              Learn More
              <ExternalLink className="h-4 w-4" />
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}
