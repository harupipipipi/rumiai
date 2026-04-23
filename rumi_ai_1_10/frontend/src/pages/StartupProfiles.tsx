import { useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  activateStartupProfile,
  createStartupProfile,
  deleteStartupProfile,
  duplicateStartupProfile,
  fetchStartupProfiles,
  launchStartupProfile,
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
import { useAppStore } from '@/src/store';
import { Loader2, Rocket, Save, Plus, AlertCircle, Copy, CheckCircle2, Trash2, ArrowLeft, Package, ChevronRight } from 'lucide-react';

type ActionState = 'create' | 'save' | 'duplicate' | 'activate' | 'launch' | 'delete' | null;

function formatTimestamp(timestamp: number): string {
  if (!timestamp) return '--';
  return new Date(timestamp * 1000).toLocaleString();
}

function summarizeProvide(value: string): string {
  return value.replace(/^defaults\./, '');
}

function renderContracts(contracts: string[]) {
  return (
    <div className="flex flex-wrap gap-1">
      {contracts.map((contract) => (
        <span
          key={contract}
          className="rounded border border-stone-700 bg-stone-800 px-1.5 py-0.5 text-[9px] font-semibold text-stone-300"
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
          {direction === 'input' ? <span className="h-2.5 w-2.5 shrink-0 rounded-full border border-stone-600 bg-stone-400" /> : null}
          <div className="max-w-[8rem]">
            <div className="text-[10px] font-semibold text-stone-300">{port.label}</div>
            <div className="text-[9px] text-stone-500">{port.multi ? 'multi' : 'single'}</div>
          </div>
          {direction === 'output' ? <span className="h-2.5 w-2.5 shrink-0 rounded-full border border-stone-600 bg-stone-400" /> : null}
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
  tone?: 'amber' | 'rose' | 'sky' | 'emerald';
  footer?: ReactNode;
}) {
  const toneClasses = {
    amber: 'from-amber-900/30 to-stone-900/50 border-amber-700/30 text-amber-100',
    rose: 'from-rose-900/30 to-stone-900/50 border-rose-700/30 text-rose-100',
    sky: 'from-sky-900/30 to-stone-900/50 border-sky-700/30 text-sky-100',
    emerald: 'from-emerald-900/30 to-stone-900/50 border-emerald-700/30 text-emerald-100',
  }[tone];

  return (
    <div className="rounded-[24px] border border-stone-800 bg-stone-900 p-2.5 shadow-lg">
      <div className={`rounded-[18px] border bg-gradient-to-br p-4 ${toneClasses}`}>
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <div className="text-base font-bold tracking-tight text-stone-100">{title}</div>
            <div className="mt-1 text-xs leading-5 text-stone-400">{subtitle}</div>
          </div>
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/5 text-lg font-black text-stone-200 shadow-sm">
            {character}
          </div>
        </div>

        <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-start gap-4">
          <NodePorts ports={ports} direction="input" />
          <div className="mt-2 h-full w-px bg-stone-500/20" />
          <NodePorts ports={ports} direction="output" />
        </div>

        {footer ? <div className="mt-4 border-t border-stone-700/30 pt-3">{footer}</div> : null}
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

export function StartupProfiles() {
  const addToast = useAppStore((state) => state.addToast);
  const showDialog = useAppStore((state) => state.showDialog);
  
  const [payload, setPayload] = useState<StartupProfilesResponseData | null>(null);
  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(null);
  const [draft, setDraft] = useState<ApiStartupProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionState, setActionState] = useState<ActionState>(null);
  const [viewMode, setViewMode] = useState<'launcher' | 'editor'>('launcher');
  const [showAdvanced, setShowAdvanced] = useState(false);

  const load = async (preferredProfileId?: string) => {
    setLoading(true);
    try {
      const response = await fetchStartupProfiles();
      setPayload(response);
      const nextProfileId =
        preferredProfileId ??
        selectedProfileId ??
        response.active_profile_id ??
        response.profiles[0]?.profile_id ??
        null;
      setSelectedProfileId(nextProfileId);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to load startup profiles';
      addToast(message, 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const selectedProfile = useMemo(
    () => payload?.profiles.find((profile) => profile.profile_id === selectedProfileId) ?? null,
    [payload, selectedProfileId],
  );

  useEffect(() => {
    if (!selectedProfile) {
      setDraft(null);
      return;
    }
    setDraft(JSON.parse(JSON.stringify(selectedProfile)));
  }, [selectedProfile?.profile_id, payload?.profiles]);

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
  }, [selectedProfile, draft]);

  const selectedCandidatesBySlot = useMemo(() => {
    if (!catalog || !draft) return {};
    return Object.fromEntries(
      slotSpecs.map((slot) => [
        slot.slot_id,
        (catalog.slot_candidates[slot.slot_id] ?? []).find((candidate) => candidate.pack_id === draft.slots[slot.slot_id]) ?? null,
      ]),
    ) as Record<string, ApiStartupSlotCandidate | null>;
  }, [catalog, draft, slotSpecs]);

  const handleCreate = async () => {
    setActionState('create');
    try {
      const response = await createStartupProfile({ name: 'New startup profile' });
      addToast('Startup profile created', 'success');
      await load(response.profile.profile_id);
      setViewMode('editor');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to create startup profile';
      addToast(message, 'error');
    } finally {
      setActionState(null);
    }
  };

  const handleSave = async () => {
    if (!draft) return;
    setActionState('save');
    try {
      await updateStartupProfile(draft.profile_id, {
        name: draft.name,
        standard_pack_id: draft.standard_pack_id,
        slots: draft.slots,
      });
      addToast('Startup profile saved', 'success');
      await load(draft.profile_id);
      setViewMode('launcher');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to save startup profile';
      addToast(message, 'error');
    } finally {
      setActionState(null);
    }
  };

  const handleDuplicate = async (profileId: string) => {
    setActionState('duplicate');
    try {
      const response = await duplicateStartupProfile(profileId);
      addToast('Startup profile duplicated', 'success');
      await load(response.profile.profile_id);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to duplicate startup profile';
      addToast(message, 'error');
    } finally {
      setActionState(null);
    }
  };

  const handleActivate = async (profileId: string) => {
    setActionState('activate');
    try {
      await activateStartupProfile(profileId);
      addToast('Active startup profile updated for the next launch', 'success');
      await load(profileId);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to switch startup profile';
      addToast(message, 'error');
    } finally {
      setActionState(null);
    }
  };

  const handleLaunch = async (profileId: string) => {
    setActionState('launch');
    setSelectedProfileId(profileId);
    try {
      const response = await launchStartupProfile(profileId);
      setPayload((current) => {
        if (!current) return current;
        return {
          ...current,
          active_profile_id: response.active_profile_id ?? current.active_profile_id,
          last_launched_profile_id: response.profile.profile_id,
          profiles: current.profiles.map((profile) =>
            profile.profile_id === response.profile.profile_id ? response.profile : profile,
          ),
        };
      });
      addToast(
        response.restart_requested
          ? 'Startup profile launched. Kernel restart scheduled.'
          : 'Startup profile launched',
        'success',
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to launch startup profile';
      addToast(message, 'error');
    } finally {
      setActionState(null);
    }
  };

  const handleDelete = (profileId: string, name: string) => {
    showDialog({
      title: 'Delete startup profile?',
      message:
        profileCount <= 1
          ? 'At least one startup profile must remain.'
          : `Delete '${name}' and switch to another saved profile?`,
      confirmText: 'Delete',
      onConfirm: async () => {
        if (profileCount <= 1) return;
        setActionState('delete');
        try {
          const response = await deleteStartupProfile(profileId);
          addToast('Startup profile deleted', 'success');
          await load(response.active_profile_id ?? undefined);
          if (selectedProfileId === profileId) {
            setViewMode('launcher');
          }
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Failed to delete startup profile';
          addToast(message, 'error');
        } finally {
          setActionState(null);
        }
      },
    });
  };

  if (loading && !payload) {
    return (
      <div className="flex flex-1 items-center justify-center bg-stone-950">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-stone-400" />
          <span className="text-sm text-stone-500">Loading startup profiles...</span>
        </div>
      </div>
    );
  }

  const renderLauncher = () => (
    <>
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 mb-4">
        <div>
          <h1 className="text-3xl font-black tracking-tight text-white">Startup Profiles</h1>
          <p className="mt-2 text-sm text-stone-400">Select a profile to launch or configure your ecosystem.</p>
        </div>
        <button
          onClick={handleCreate}
          disabled={actionState === 'create'}
          className="flex items-center gap-2 rounded-xl bg-stone-100 px-4 py-2.5 text-sm font-bold text-stone-900 transition hover:bg-white disabled:opacity-50"
        >
          {actionState === 'create' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
          Create Custom Profile
        </button>
      </div>

      <div className="grid gap-6 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
        {payload?.profiles.map((profile) => {
          const isActive = payload?.active_profile_id === profile.profile_id;
          const isLastLaunched = payload?.last_launched_profile_id === profile.profile_id;
          
          const standardPack = standardPacks.find(p => p.pack_id === profile.standard_pack_id);
          const hasIssue = !standardPack?.runtime_ready; // Simplified issue check

          return (
            <div key={profile.profile_id} className="group relative flex flex-col justify-between rounded-2xl border border-stone-800 bg-stone-900/40 p-6 transition-all hover:bg-stone-900 hover:border-stone-700 hover:shadow-xl hover:shadow-black/20">
              <div>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-xl font-bold text-stone-100">{profile.name}</h3>
                    <div className="mt-1 flex items-center gap-2 text-xs font-mono text-stone-500">
                      <Package className="h-3 w-3" />
                      {profile.standard_pack_id}
                    </div>
                  </div>
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                  {isActive && (
                    <span className="flex items-center gap-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-400">
                      <CheckCircle2 className="h-3 w-3" /> Active
                    </span>
                  )}
                  {isLastLaunched && (
                    <span className="flex items-center gap-1 rounded-full bg-stone-800 border border-stone-700 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-stone-400">
                      Last Launched
                    </span>
                  )}
                  {hasIssue && (
                    <span className="flex items-center gap-1 rounded-full bg-amber-500/10 border border-amber-500/20 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-400">
                      <AlertCircle className="h-3 w-3" /> Issue
                    </span>
                  )}
                </div>

                <div className="mt-6 space-y-2">
                  {Object.entries(profile.slots).slice(0, 3).map(([slotId, packId]) => (
                    <div key={slotId} className="flex items-center justify-between text-xs">
                      <span className="text-stone-500">{slotId}</span>
                      <span className="text-stone-300 font-medium truncate ml-2">{packId}</span>
                    </div>
                  ))}
                  {Object.keys(profile.slots).length > 3 && (
                    <div className="text-xs text-stone-600 italic pt-1">
                      + {Object.keys(profile.slots).length - 3} more slots
                    </div>
                  )}
                </div>
              </div>

              <div className="mt-6 border-t border-stone-800 pt-5">
                <div className="flex flex-col gap-3">
                  <button
                    onClick={() => handleLaunch(profile.profile_id)}
                    disabled={actionState === 'launch'}
                    className="flex w-full items-center justify-center gap-2 rounded-xl bg-stone-100 py-3 text-sm font-bold text-stone-900 transition hover:bg-white disabled:opacity-50"
                  >
                    {actionState === 'launch' && selectedProfileId === profile.profile_id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Rocket className="h-4 w-4" />}
                    Launch Profile
                  </button>
                  
                  <div className="flex items-center justify-between gap-2">
                    <button
                      onClick={() => {
                        setSelectedProfileId(profile.profile_id);
                        setViewMode('editor');
                      }}
                      className="flex-1 rounded-lg border border-stone-800 bg-transparent py-2 text-xs font-semibold text-stone-300 transition hover:bg-stone-800"
                    >
                      Edit
                    </button>
                    {!isActive && (
                      <button
                        onClick={() => handleActivate(profile.profile_id)}
                        disabled={actionState === 'activate'}
                        className="flex-1 rounded-lg border border-stone-800 bg-transparent py-2 text-xs font-semibold text-stone-300 transition hover:bg-stone-800 disabled:opacity-50"
                      >
                        Set Active
                      </button>
                    )}
                    <button
                      onClick={() => handleDuplicate(profile.profile_id)}
                      disabled={actionState === 'duplicate'}
                      className="flex h-8 w-8 items-center justify-center rounded-lg border border-stone-800 text-stone-400 transition hover:bg-stone-800 hover:text-stone-300"
                      title="Duplicate"
                    >
                      <Copy className="h-3.5 w-3.5" />
                    </button>
                    <button
                      onClick={() => handleDelete(profile.profile_id, profile.name)}
                      disabled={actionState === 'delete' || profileCount <= 1}
                      className="flex h-8 w-8 items-center justify-center rounded-lg border border-stone-800 text-stone-400 transition hover:bg-red-950/30 hover:text-red-400 disabled:opacity-30"
                      title="Delete"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );

  const renderEditor = () => {
    if (!draft || !catalog) return null;
    return (
      <div className="flex flex-col gap-8 pb-10">
        <div className="flex flex-col md:flex-row md:items-center justify-between border-b border-stone-800 pb-5 gap-4">
          <div className="flex items-center gap-4">
            <button
              onClick={() => setViewMode('launcher')}
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-stone-900 text-stone-400 transition hover:bg-stone-800 hover:text-stone-100"
            >
              <ArrowLeft className="h-5 w-5" />
            </button>
            <div>
              <h2 className="text-2xl font-black tracking-tight text-white">Edit Profile</h2>
              <p className="text-sm text-stone-500">Configure packs and slots for {draft.name}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={handleSave}
              disabled={!isDirty || actionState === 'save'}
              className="flex items-center gap-2 rounded-xl bg-stone-100 px-5 py-2.5 text-sm font-bold text-stone-900 transition hover:bg-white disabled:opacity-50"
            >
              {actionState === 'save' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              Save Changes
            </button>
          </div>
        </div>

        <div className="grid gap-8 lg:grid-cols-[1fr_320px]">
          <div className="flex flex-col gap-8">
            <div className="rounded-2xl border border-stone-800 bg-stone-900/30 p-6">
               <h3 className="text-lg font-bold text-stone-100 mb-5">General Settings</h3>
               <div className="grid gap-5 md:grid-cols-2">
                 <div className="space-y-2">
                   <label className="text-xs font-bold uppercase tracking-wider text-stone-500">Profile Name</label>
                   <input
                     value={draft.name}
                     onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                     className="w-full rounded-xl border border-stone-700 bg-stone-900 px-4 py-2.5 text-sm text-stone-100 outline-none transition focus:border-stone-500 focus:ring-1 focus:ring-stone-500"
                   />
                 </div>
                 <div className="space-y-2">
                   <label className="text-xs font-bold uppercase tracking-wider text-stone-500">Standard Pack</label>
                   <select
                     value={draft.standard_pack_id}
                     onChange={(e) => setDraft({ ...draft, standard_pack_id: e.target.value })}
                     className="w-full rounded-xl border border-stone-700 bg-stone-900 px-4 py-2.5 text-sm text-stone-100 outline-none transition focus:border-stone-500 focus:ring-1 focus:ring-stone-500"
                   >
                     {standardPacks.map((pack) => (
                       <option key={pack.pack_id} value={pack.pack_id} disabled={!pack.available}>
                         {pack.display_name} {pack.available ? '' : pack.enabled ? '(issue)' : '(disabled)'}
                       </option>
                     ))}
                   </select>
                 </div>
               </div>
               {selectedStandardPack && !selectedStandardPack.runtime_ready && (
                 <div className="mt-5 rounded-xl border border-amber-900/50 bg-amber-950/30 p-4 text-amber-200/80">
                   <div className="flex items-center gap-2 font-bold text-amber-400">
                     <AlertCircle className="h-4 w-4" /> Standard pack issue
                   </div>
                   <ul className="mt-2 ml-6 list-disc text-sm space-y-1">
                     {selectedStandardPack.runtime_issues.map((i, idx) => <li key={idx}>{i}</li>)}
                   </ul>
                 </div>
               )}
            </div>

            <div className="rounded-2xl border border-stone-800 bg-stone-900/30 p-6">
               <h3 className="text-lg font-bold text-stone-100 mb-5">Slot Configuration</h3>
               <div className="grid gap-4">
                 {slotSpecs.map((slot) => {
                   const candidates = catalog.slot_candidates[slot.slot_id] ?? [];
                   const selectedCandidate = selectedCandidatesBySlot[slot.slot_id];
                   return (
                     <div key={slot.slot_id} className="rounded-xl border border-stone-800 bg-stone-900 p-5">
                       <div className="flex items-center justify-between mb-4">
                         <div>
                           <div className="font-bold text-stone-200">{slot.label}</div>
                           <div className="text-xs text-stone-500 mt-0.5">{slot.description}</div>
                         </div>
                       </div>
                       <select
                         value={draft.slots[slot.slot_id] ?? ''}
                         onChange={(e) => setDraft({ ...draft, slots: { ...draft.slots, [slot.slot_id]: e.target.value } })}
                         className="w-full rounded-lg border border-stone-700 bg-stone-950 px-3 py-2 text-sm text-stone-200 outline-none transition focus:border-stone-500 focus:ring-1 focus:ring-stone-500"
                       >
                         {candidates.map((c) => (
                           <option key={c.pack_id} value={c.pack_id} disabled={!c.runtime_ready}>
                             {c.display_name} {c.runtime_ready ? '' : '(issue)'}
                           </option>
                         ))}
                       </select>
                       {selectedCandidate && !selectedCandidate.runtime_ready && (
                         <div className="mt-3 flex items-start gap-2 text-xs text-amber-400">
                           <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                           <div>
                             {selectedCandidate.runtime_issues.map((i, idx) => <div key={idx}>{i}</div>)}
                           </div>
                         </div>
                       )}
                     </div>
                   );
                 })}
               </div>
            </div>

            <div>
              <button
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="flex items-center gap-2 text-sm font-bold text-stone-500 hover:text-stone-300"
              >
                <ChevronRight className={`h-4 w-4 transition-transform ${showAdvanced ? 'rotate-90' : ''}`} />
                Advanced / Contract Graph
              </button>
              
              {showAdvanced && (
                <div className="mt-4 rounded-2xl border border-stone-800 bg-stone-900/30 p-6">
                   <div className="mb-6">
                     <h3 className="text-lg font-bold text-stone-100">Contract Graph</h3>
                     <p className="text-sm text-stone-500 mt-1">Graph visualization for debugging contract connections.</p>
                   </div>
                   
                   <div className="space-y-5">
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
                             <div className="text-xs font-bold uppercase tracking-wider text-stone-500">Pack Identity</div>
                             <div className="text-sm text-stone-400">{selectedStandardPack?.pack_identity || 'Unavailable'}</div>
                           </div>
                         }
                       />
                     </div>

                     <div className="grid gap-4 md:grid-cols-2">
                       {slotSpecs.map((slot) => {
                         const candidate = selectedCandidatesBySlot[slot.slot_id];
                         return (
                           <ContractNode
                             key={`node-${slot.slot_id}`}
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
                </div>
              )}
            </div>
          </div>

          <div className="flex flex-col gap-4">
             <div className="rounded-2xl border border-stone-800 bg-stone-900/30 p-5">
               <h4 className="text-sm font-bold uppercase tracking-wider text-stone-500 mb-4">Profile Metadata</h4>
               <div className="space-y-4 text-sm">
                 <div>
                   <div className="text-stone-600 text-xs mb-1">Profile ID</div>
                   <div className="font-mono text-stone-400 break-all bg-stone-900 p-2 rounded-lg text-xs">{draft.profile_id}</div>
                 </div>
                 <div>
                   <div className="text-stone-600 text-xs mb-1">Created</div>
                   <div className="text-stone-300">{formatTimestamp(draft.created_at)}</div>
                 </div>
                 <div>
                   <div className="text-stone-600 text-xs mb-1">Last Updated</div>
                   <div className="text-stone-300">{formatTimestamp(draft.updated_at)}</div>
                 </div>
                 <div className="pt-2 border-t border-stone-800">
                   <div className="text-stone-600 text-xs mb-1">Status</div>
                   <div className="text-stone-300">{isDirty ? 'Unsaved changes' : 'Saved'}</div>
                 </div>
               </div>
             </div>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="flex flex-1 overflow-y-auto bg-stone-950 text-stone-300 p-6 lg:p-10 font-sans">
      <div className="mx-auto w-full max-w-[1200px] flex flex-col gap-8">
        {viewMode === 'launcher' ? renderLauncher() : renderEditor()}
      </div>
    </div>
  );
}
