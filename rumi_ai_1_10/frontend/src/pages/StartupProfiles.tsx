import { useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  activateStartupProfile,
  createStartupProfile,
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
import { Button } from '@/src/components/ui/Button';
import { Input } from '@/src/components/ui/Input';
import { Badge } from '@/src/components/ui/Badge';
import { Loader2, Copy, Rocket, Save, PackagePlus, PlugZap, CheckCircle2, PlayCircle } from 'lucide-react';

type ActionState = 'create' | 'save' | 'duplicate' | 'activate' | 'launch' | null;

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
          className="rounded-full border border-amber-300/70 bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-900"
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
          {direction === 'input' ? <span className="h-3 w-3 shrink-0 rounded-full border-2 border-amber-700 bg-amber-300" /> : null}
          <div className="max-w-[9rem]">
            <div className="text-[11px] font-semibold text-stone-800">{port.label}</div>
            <div className="text-[10px] text-stone-500">{port.multi ? 'multi' : 'single'}</div>
          </div>
          {direction === 'output' ? <span className="h-3 w-3 shrink-0 rounded-full border-2 border-amber-700 bg-amber-300" /> : null}
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
    amber: 'from-amber-400 via-orange-300 to-yellow-200 border-amber-200',
    rose: 'from-rose-400 via-orange-300 to-amber-200 border-rose-200',
    sky: 'from-sky-400 via-cyan-300 to-blue-200 border-sky-200',
    emerald: 'from-emerald-400 via-lime-300 to-yellow-200 border-emerald-200',
  }[tone];

  return (
    <div className="rounded-[28px] border border-stone-200 bg-white/90 p-3 shadow-[0_18px_50px_rgba(120,53,15,0.15)] backdrop-blur">
      <div className={`rounded-[22px] border bg-gradient-to-br p-4 ${toneClasses}`}>
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <div className="text-lg font-black tracking-tight text-stone-900">{title}</div>
            <div className="mt-1 text-xs leading-5 text-stone-700">{subtitle}</div>
          </div>
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-white/60 bg-white/80 text-lg font-black text-stone-900 shadow-sm">
            {character}
          </div>
        </div>

        <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-start gap-4">
          <NodePorts ports={ports} direction="input" />
          <div className="mt-2 h-full w-px bg-stone-500/20" />
          <NodePorts ports={ports} direction="output" />
        </div>

        {footer ? <div className="mt-4 border-t border-stone-900/10 pt-3">{footer}</div> : null}
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
  const [payload, setPayload] = useState<StartupProfilesResponseData | null>(null);
  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(null);
  const [draft, setDraft] = useState<ApiStartupProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionState, setActionState] = useState<ActionState>(null);

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
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to save startup profile';
      addToast(message, 'error');
    } finally {
      setActionState(null);
    }
  };

  const handleDuplicate = async () => {
    if (!draft) return;
    setActionState('duplicate');
    try {
      const response = await duplicateStartupProfile(draft.profile_id);
      addToast('Startup profile duplicated', 'success');
      await load(response.profile.profile_id);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to duplicate startup profile';
      addToast(message, 'error');
    } finally {
      setActionState(null);
    }
  };

  const handleActivate = async () => {
    if (!draft) return;
    setActionState('activate');
    try {
      await activateStartupProfile(draft.profile_id);
      addToast('Active startup profile switched', 'success');
      await load(draft.profile_id);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to switch startup profile';
      addToast(message, 'error');
    } finally {
      setActionState(null);
    }
  };

  const handleLaunch = async () => {
    if (!draft) return;
    setActionState('launch');
    try {
      await launchStartupProfile(draft.profile_id);
      addToast('Startup profile launched', 'success');
      await load(draft.profile_id);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to launch startup profile';
      addToast(message, 'error');
    } finally {
      setActionState(null);
    }
  };

  if (loading && !payload) {
    return (
      <div className="flex flex-1 items-center justify-center bg-bg-main">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-accent" />
          <span className="text-sm text-text-muted">Loading startup profiles...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 overflow-y-auto bg-bg-main p-6 lg:p-8">
      <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-6">
        <div className="overflow-hidden rounded-[32px] border border-amber-200 bg-[linear-gradient(135deg,#fff7ed_0%,#fef3c7_45%,#ffedd5_100%)] shadow-[0_24px_80px_rgba(120,53,15,0.12)]">
          <div className="bg-[linear-gradient(rgba(251,191,36,0.12)_1px,transparent_1px),linear-gradient(90deg,rgba(251,191,36,0.12)_1px,transparent_1px)] bg-[size:28px_28px] p-6 lg:p-8">
            <div className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
              <div className="rounded-[28px] border border-white/70 bg-white/80 p-4 shadow-sm backdrop-blur">
                <div className="mb-4 flex items-center justify-between">
                  <div>
                    <div className="text-sm font-bold uppercase tracking-[0.22em] text-amber-700">PR23</div>
                    <h1 className="mt-2 text-2xl font-black tracking-tight text-stone-900">Startup Profiles</h1>
                    <p className="mt-2 text-sm leading-6 text-stone-600">
                      `start` only, `defaultspack` as the reference contract pack, and slot swaps guarded by contracts.
                    </p>
                  </div>
                </div>

                <Button onClick={handleCreate} className="mb-4 w-full gap-2" disabled={actionState === 'create'}>
                  {actionState === 'create' ? <Loader2 className="h-4 w-4 animate-spin" /> : <PackagePlus className="h-4 w-4" />}
                  New Profile
                </Button>

                <div className="space-y-3">
                  {payload?.profiles.map((profile) => {
                    const isActive = payload.active_profile_id === profile.profile_id;
                    const isSelected = selectedProfileId === profile.profile_id;
                    return (
                      <button
                        key={profile.profile_id}
                        onClick={() => setSelectedProfileId(profile.profile_id)}
                        className={`w-full rounded-2xl border p-4 text-left transition ${
                          isSelected
                            ? 'border-amber-400 bg-amber-50 shadow-sm'
                            : 'border-stone-200 bg-white/70 hover:border-amber-200 hover:bg-white'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <div className="text-sm font-bold text-stone-900">{profile.name}</div>
                            <div className="mt-1 text-xs text-stone-500">{profile.profile_id}</div>
                          </div>
                          {isActive ? <Badge>Active</Badge> : null}
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <Badge variant="secondary">{profile.standard_pack_id}</Badge>
                          <Badge variant="outline">{Object.keys(profile.slots).length} slots</Badge>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="flex flex-col gap-6">
                {draft && catalog ? (
                  <>
                    <div className="rounded-[28px] border border-white/70 bg-white/80 p-5 shadow-sm backdrop-blur">
                      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <Badge variant="outline">Official start only</Badge>
                            <Badge variant="secondary">{draft.standard_pack_id}</Badge>
                            {payload?.active_profile_id === draft.profile_id ? <Badge>Current</Badge> : null}
                            {payload?.last_launched_profile_id === draft.profile_id ? <Badge variant="outline">Last launched</Badge> : null}
                          </div>
                          <p className="mt-3 text-sm leading-6 text-stone-600">
                            Contract mismatch never becomes a connection candidate. Each slot is filtered against its required contract before you can save or launch.
                          </p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <Button variant="outline" onClick={handleDuplicate} disabled={!draft || actionState === 'duplicate'} className="gap-2">
                            {actionState === 'duplicate' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Copy className="h-4 w-4" />}
                            Duplicate
                          </Button>
                          <Button variant="outline" onClick={handleActivate} disabled={!draft || actionState === 'activate'} className="gap-2">
                            {actionState === 'activate' ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                            Switch
                          </Button>
                          <Button onClick={handleLaunch} disabled={!draft || actionState === 'launch'} className="gap-2">
                            {actionState === 'launch' ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />}
                            Launch
                          </Button>
                        </div>
                      </div>
                    </div>

                    <div className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
                      <div className="rounded-[28px] border border-white/70 bg-white/80 p-5 shadow-sm backdrop-blur">
                        <div className="mb-5 flex items-center justify-between gap-3">
                          <div>
                            <h2 className="text-xl font-black tracking-tight text-stone-900">Profile Editor</h2>
                            <p className="mt-2 text-sm text-stone-600">Save multiple launch presets like a modpack selector.</p>
                          </div>
                          <Button onClick={handleSave} disabled={!isDirty || actionState === 'save'} className="gap-2">
                            {actionState === 'save' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                            Save
                          </Button>
                        </div>

                        <div className="grid gap-4 md:grid-cols-2">
                          <div className="space-y-2">
                            <label className="text-xs font-bold uppercase tracking-[0.18em] text-stone-500">Profile Name</label>
                            <Input
                              value={draft.name}
                              onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                            />
                          </div>
                          <div className="space-y-2">
                            <label className="text-xs font-bold uppercase tracking-[0.18em] text-stone-500">Standard Pack</label>
                            <select
                              value={draft.standard_pack_id}
                              onChange={(event) => setDraft({ ...draft, standard_pack_id: event.target.value })}
                              className="h-10 w-full rounded-xl border border-border bg-white px-3 text-sm text-text-main focus:outline-none focus:ring-2 focus:ring-amber-300"
                            >
                              {standardPacks.map((pack) => (
                                <option key={pack.pack_id} value={pack.pack_id} disabled={!pack.available}>
                                  {pack.display_name}{pack.available ? '' : ' (unavailable)'}
                                </option>
                              ))}
                            </select>
                          </div>
                        </div>

                        <div className="mt-5 grid gap-4 lg:grid-cols-2">
                          {slotSpecs.map((slot) => {
                            const candidates = catalog.slot_candidates[slot.slot_id] ?? [];
                            const selectedCandidate = selectedCandidatesBySlot[slot.slot_id];
                            return (
                              <div key={slot.slot_id} className="rounded-[24px] border border-amber-100 bg-amber-50/60 p-4">
                                <div className="flex items-start justify-between gap-3">
                                  <div>
                                    <div className="text-base font-black tracking-tight text-stone-900">{slot.label}</div>
                                    <p className="mt-1 text-sm leading-6 text-stone-600">{slot.description}</p>
                                  </div>
                                  <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-amber-200 bg-white text-base font-black text-stone-900">
                                    {slot.character}
                                  </div>
                                </div>

                                <div className="mt-3">
                                  {renderContracts([slot.contract])}
                                  <div className="mt-2 text-[11px] font-medium uppercase tracking-[0.18em] text-stone-500">
                                    {slot.interface_key}
                                  </div>
                                </div>

                                <div className="mt-4 space-y-2">
                                  <label className="text-xs font-bold uppercase tracking-[0.18em] text-stone-500">Connected Pack</label>
                                  <select
                                    value={draft.slots[slot.slot_id] ?? ''}
                                    onChange={(event) =>
                                      setDraft({
                                        ...draft,
                                        slots: {
                                          ...draft.slots,
                                          [slot.slot_id]: event.target.value,
                                        },
                                      })
                                    }
                                    className="h-10 w-full rounded-xl border border-border bg-white px-3 text-sm text-text-main focus:outline-none focus:ring-2 focus:ring-amber-300"
                                  >
                                    {candidates.map((candidate) => (
                                      <option key={`${slot.slot_id}-${candidate.pack_id}`} value={candidate.pack_id}>
                                        {candidate.display_name}
                                      </option>
                                    ))}
                                  </select>
                                </div>

                                <div className="mt-4 rounded-2xl border border-white/80 bg-white/80 p-3">
                                  <div className="flex items-center gap-2 text-sm font-semibold text-stone-900">
                                    <PlugZap className="h-4 w-4 text-amber-600" />
                                    {selectedCandidate?.display_name ?? 'No candidate'}
                                  </div>
                                  <p className="mt-2 text-sm leading-6 text-stone-600">
                                    {selectedCandidate?.description ?? 'This slot currently has no contract-compatible pack.'}
                                  </p>
                                  <div className="mt-3 flex flex-wrap gap-2">
                                    {(selectedCandidate?.component_types ?? []).map((componentType) => (
                                      <Badge key={`${slot.slot_id}-${componentType}`} variant="outline">{componentType}</Badge>
                                    ))}
                                  </div>
                                  <div className="mt-3 flex flex-wrap gap-2">
                                    {(selectedCandidate?.provides ?? []).slice(0, 3).map((provide) => (
                                      <Badge key={`${slot.slot_id}-${provide}`} variant="secondary">{summarizeProvide(provide)}</Badge>
                                    ))}
                                  </div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>

                      <div className="rounded-[28px] border border-white/70 bg-white/80 p-5 shadow-sm backdrop-blur">
                        <div className="mb-5">
                          <h2 className="text-xl font-black tracking-tight text-stone-900">Contract Graph</h2>
                          <p className="mt-2 text-sm text-stone-600">
                            Generic nodes render arbitrary ports. The current profile is just one graph over the same contract system.
                          </p>
                        </div>

                        <div className="space-y-5">
                          <div className="grid gap-4 lg:grid-cols-[240px_1fr]">
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
                              subtitle={selectedStandardPack?.description ?? 'Reference pack that exposes the standard startup slots.'}
                              character={selectedStandardPack?.character ?? 'D'}
                              ports={buildStandardPackPorts(catalog)}
                              tone="amber"
                              footer={
                                <div className="space-y-2">
                                  <div className="text-xs font-bold uppercase tracking-[0.18em] text-stone-500">Pack Identity</div>
                                  <div className="text-sm text-stone-700">{selectedStandardPack?.pack_identity || 'Unavailable in this workspace'}</div>
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
                                      <div className="text-xs text-stone-600">
                                        Connected from <span className="font-semibold text-stone-900">{draft.standard_pack_id}.{slot.slot_id}</span>
                                      </div>
                                    </div>
                                  }
                                />
                              );
                            })}
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="rounded-[28px] border border-white/70 bg-white/80 p-5 shadow-sm backdrop-blur">
                      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                        <div>
                          <h2 className="text-lg font-black tracking-tight text-stone-900">Profile Lifecycle</h2>
                          <p className="mt-2 text-sm text-stone-600">
                            Updated {formatTimestamp(draft.updated_at)}. Created {formatTimestamp(draft.created_at)}.
                          </p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <Badge variant="outline">{draft.profile_id}</Badge>
                          <Badge variant="secondary">{draft.standard_pack_id}</Badge>
                          <Badge variant="outline">{isDirty ? 'Unsaved changes' : 'Saved'}</Badge>
                        </div>
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="rounded-[28px] border border-white/70 bg-white/80 p-10 text-center shadow-sm backdrop-blur">
                    <Rocket className="mx-auto h-10 w-10 text-amber-500" />
                    <h2 className="mt-4 text-xl font-black tracking-tight text-stone-900">No profile selected</h2>
                    <p className="mt-2 text-sm text-stone-600">Create a startup profile to begin wiring `start` to a standards pack.</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
