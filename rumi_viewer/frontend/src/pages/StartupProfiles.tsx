import {useEffect, useMemo, useState} from 'react';
import {
  AlertTriangle,
  Boxes,
  CheckCircle2,
  Copy,
  Loader2,
  PackagePlus,
  Play,
  Plus,
  Rocket,
  ShieldCheck,
  Trash2,
} from 'lucide-react';

import {
  activateStartupProfile,
  compileStartupProfilePreview,
  createStartupProfile,
  deleteStartupProfile,
  duplicateStartupProfile,
  fetchStartupProfiles,
  launchStartupProfile,
  updateStartupProfile,
} from '@/src/lib/api';
import type {
  ApiStartupCatalog,
  ApiStartupNodeDefinition,
  ApiStartupNodePort,
  ApiStartupPack,
  ApiStartupProfile,
  StartupProfileCompilePreviewResponseData,
} from '@/src/lib/apiTypes';
import {
  buildAddStartupProfilePackPatch,
  buildRemoveStartupProfilePackPatch,
  buildSetStartupProfileBasePackPatch,
  buildStartupProfileView,
  describeStartupActionError,
  filterAndSortStartupProfiles,
  isStartupFrontendNode,
  packLabel,
  startupPacksForRole,
  type StartupProfileView,
} from '@/src/lib/startupProfiles';
import {Badge} from '@/src/components/ui/Badge';
import {Button} from '@/src/components/ui/Button';
import {Card, CardContent, CardHeader, CardTitle, CardDescription} from '@/src/components/ui/Card';
import {Input} from '@/src/components/ui/Input';
import {Switch} from '@/src/components/ui/Switch';
import {cn} from '@/src/lib/utils';
import {useAppStore} from '@/src/store';

interface FrontendSurfaceCandidate {
  label: string;
  node: ApiStartupNodeDefinition;
  nodeId: string;
  pack: ApiStartupPack;
  packId: string;
}

interface StartupProfilesShellProps {
  activeProfileId: string | null;
  catalog: ApiStartupCatalog;
  loading?: boolean;
  lastLaunchedProfileId: string | null;
  preview: StartupProfileCompilePreviewResponseData | null;
  profiles: ApiStartupProfile[];
  savingAction?: string | null;
  selectedProfileId: string;
  onActivate: (profileId: string) => void;
  onAddPack: (profileId: string, packId: string) => void;
  onCreateProfile: () => void;
  onDeleteProfile: (profileId: string) => void;
  onDuplicateProfile: (profileId: string) => void;
  onLaunch: (profileId: string) => void;
  onPreview: (profileId: string) => void;
  onRemovePack: (profileId: string, packId: string) => void;
  onSelectBasePack: (profile: ApiStartupProfile, packId: string) => void;
  onSelectFrontend: (profile: ApiStartupProfile, nodeId: string) => void;
  onSelectProfile: (profileId: string) => void;
  onToggleLaunchCompile: (profile: ApiStartupProfile, enabled: boolean) => void;
  onTogglePolicy: (profile: ApiStartupProfile, key: string, enabled: boolean) => void;
}

function displayName(value?: Record<string, string>, fallback = ''): string {
  return value?.en || value?.ja || Object.values(value ?? {})[0] || fallback;
}

function portStandards(port: ApiStartupNodePort | undefined): string[] {
  return [
    ...(Array.isArray(port?.standards) ? port.standards : []),
    ...(Array.isArray(port?.contracts) ? port.contracts : []),
  ];
}

function frontendSurfaceCandidates(catalog: ApiStartupCatalog): FrontendSurfaceCandidate[] {
  return startupPacksForRole(catalog, 'frontend')
    .flatMap((pack) => pack.nodes.filter(isStartupFrontendNode).map((node) => ({
      pack,
      packId: pack.pack_id,
      node,
      nodeId: node.node_id,
      label: `${packLabel(pack)} / ${displayName(node.display_name, node.title || node.node_id)}`,
    })))
    .sort((left, right) => left.label.localeCompare(right.label));
}

function frontendPortKey(profile: ApiStartupProfile): string | null {
  const match = profile.graph_ports.find((port) => portStandards(port.target_port).includes('rumi.surface'));
  return match?.port_key ?? null;
}

function selectedFrontendNode(profile: ApiStartupProfile): string {
  const portKey = frontendPortKey(profile);
  const graphPort = portKey ? profile.graph_ports.find((port) => port.port_key === portKey) : null;
  return portKey ? (profile.node_overrides[portKey] || graphPort?.source_node_ref || '') : '';
}

function packHasProfileSelection(profile: ApiStartupProfile, packId: string): boolean {
  if (profile.base_pack === packId) {
    return true;
  }
  const frontendNode = selectedFrontendNode(profile);
  return Boolean(frontendNode && frontendNode.startsWith(`${packId}.`));
}

function uniqueList(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))];
}

function badgeVariant(tone: StartupProfileView['badges'][number]['tone']): 'default' | 'secondary' | 'destructive' | 'outline' | 'success' | 'warning' {
  if (tone === 'accent') return 'default';
  if (tone === 'success') return 'success';
  if (tone === 'warning') return 'warning';
  if (tone === 'danger') return 'destructive';
  return 'secondary';
}

export function StartupProfilesShell({
  activeProfileId,
  catalog,
  loading,
  lastLaunchedProfileId,
  preview,
  profiles,
  savingAction,
  selectedProfileId,
  onActivate,
  onAddPack,
  onCreateProfile,
  onDeleteProfile,
  onDuplicateProfile,
  onLaunch,
  onPreview,
  onRemovePack,
  onSelectBasePack,
  onSelectFrontend,
  onSelectProfile,
  onToggleLaunchCompile,
  onTogglePolicy,
}: StartupProfilesShellProps) {
  const [search, setSearch] = useState('');
  const [sortMode, setSortMode] = useState<'recommended' | 'recent' | 'name'>('recommended');
  const [packToAdd, setPackToAdd] = useState('');
  const views = useMemo(
    () => profiles.map((profile) => buildStartupProfileView(profile, catalog, activeProfileId, lastLaunchedProfileId)),
    [activeProfileId, catalog, lastLaunchedProfileId, profiles],
  );
  const filteredViews = useMemo(
    () => filterAndSortStartupProfiles(views, search, sortMode),
    [search, sortMode, views],
  );
  const selectedView = views.find((view) => view.profile.profile_id === selectedProfileId) || filteredViews[0] || null;
  const selectedProfile = selectedView?.profile ?? null;
  const basePacks = startupPacksForRole(catalog, 'base');
  const toolPacks = startupPacksForRole(catalog, 'tool');
  const frontendCandidates = frontendSurfaceCandidates(catalog);
  const selectedFrontend = selectedProfile ? selectedFrontendNode(selectedProfile) : '';
  const addablePacks = selectedProfile
    ? catalog.packs.filter((pack) => pack.available && !selectedProfile.packs.includes(pack.pack_id))
    : [];

  useEffect(() => {
    if (!packToAdd && addablePacks[0]) {
      setPackToAdd(addablePacks[0].pack_id);
    }
    if (packToAdd && !addablePacks.some((pack) => pack.pack_id === packToAdd)) {
      setPackToAdd(addablePacks[0]?.pack_id || '');
    }
  }, [addablePacks, packToAdd]);

  if (loading && profiles.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="flex items-center gap-3 text-text-muted">
          <Loader2 className="h-5 w-5 animate-spin text-accent" />
          <span className="text-sm">Loading profiles</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto page-enter">
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-6 py-8">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-text-main">Startup Profiles</h1>
            <p className="mt-1 text-sm text-text-muted">Choose the base pack, launch frontend, tool packs, and runtime policy for each profile.</p>
          </div>
          <Button onClick={onCreateProfile} disabled={basePacks.length === 0 || Boolean(savingAction)} loading={savingAction === 'create'}>
            <Plus className="h-4 w-4" />
            New Profile
          </Button>
        </div>

        <div className="grid gap-5 xl:grid-cols-[360px_minmax(0,1fr)]">
          <section className="flex flex-col gap-4">
            <div className="flex gap-2">
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search profiles"
                aria-label="Search profiles"
              />
              <select
                value={sortMode}
                onChange={(event) => setSortMode(event.target.value as typeof sortMode)}
                className="h-10 rounded-lg border border-border bg-bg-main px-3 text-sm text-text-main focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring-color)]"
                aria-label="Sort profiles"
              >
                <option value="recommended">Recommended</option>
                <option value="recent">Recent</option>
                <option value="name">Name</option>
              </select>
            </div>

            <div className="grid gap-3">
              {filteredViews.map((view) => (
                <button
                  key={view.profile.profile_id}
                  type="button"
                  onClick={() => onSelectProfile(view.profile.profile_id)}
                  className={cn(
                    'rounded-xl border bg-bg-card p-4 text-left shadow-[var(--shadow-sm)] transition-colors',
                    selectedProfileId === view.profile.profile_id ? 'border-accent bg-accent/8' : 'border-border hover:bg-bg-hover',
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h2 className="truncate text-sm font-semibold text-text-main">{view.profile.name}</h2>
                      <p className="mt-1 truncate text-xs text-text-muted">{view.subtitle}</p>
                    </div>
                    {view.runtimeReady ? (
                      <CheckCircle2 className="h-4 w-4 flex-shrink-0 text-emerald-500" />
                    ) : (
                      <AlertTriangle className="h-4 w-4 flex-shrink-0 text-amber-500" />
                    )}
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {view.badges.map((badge) => (
                      <Badge key={badge.label} variant={badgeVariant(badge.tone)}>{badge.label}</Badge>
                    ))}
                  </div>
                </button>
              ))}
              {filteredViews.length === 0 && (
                <div className="rounded-xl border border-dashed border-border px-4 py-10 text-center text-sm text-text-muted">
                  No matching profiles.
                </div>
              )}
            </div>
          </section>

          {selectedProfile && selectedView ? (
            <section className="flex flex-col gap-5">
              <Card>
                <CardHeader className="flex-row items-start justify-between gap-4 space-y-0">
                  <div>
                    <CardTitle>{selectedProfile.name}</CardTitle>
                    <CardDescription>{selectedProfile.profile_id}</CardDescription>
                  </div>
                  <div className="flex flex-wrap justify-end gap-2">
                    <Button variant="outline" size="sm" onClick={() => onDuplicateProfile(selectedProfile.profile_id)} loading={savingAction === 'duplicate'}>
                      <Copy className="h-3.5 w-3.5" />
                      Duplicate
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => onPreview(selectedProfile.profile_id)} loading={savingAction === 'preview'}>
                      <Play className="h-3.5 w-3.5" />
                      Preview
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => onActivate(selectedProfile.profile_id)} disabled={activeProfileId === selectedProfile.profile_id} loading={savingAction === 'activate'}>
                      <ShieldCheck className="h-3.5 w-3.5" />
                      Activate
                    </Button>
                    <Button size="sm" onClick={() => onLaunch(selectedProfile.profile_id)} loading={savingAction === 'launch'}>
                      <Rocket className="h-3.5 w-3.5" />
                      Launch
                    </Button>
                  </div>
                </CardHeader>
                <CardContent className="grid gap-4 md:grid-cols-3">
                  <div className="rounded-lg border border-border bg-bg-main/60 p-3">
                    <div className="text-xs uppercase tracking-[0.16em] text-text-muted">Base Pack</div>
                    <select
                      value={selectedProfile.base_pack}
                      onChange={(event) => onSelectBasePack(selectedProfile, event.target.value)}
                      className="mt-2 h-10 w-full rounded-lg border border-border bg-bg-main px-3 text-sm text-text-main focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring-color)]"
                      aria-label="Base pack"
                    >
                      {basePacks.map((pack) => (
                        <option key={pack.pack_id} value={pack.pack_id}>{packLabel(pack)}</option>
                      ))}
                    </select>
                  </div>
                  <div className="rounded-lg border border-border bg-bg-main/60 p-3">
                    <div className="text-xs uppercase tracking-[0.16em] text-text-muted">Runtime Graph</div>
                    <div className="mt-2 truncate text-sm font-medium text-text-main">{selectedProfile.graph_id}</div>
                    <div className="mt-1 text-xs text-text-muted">{selectedProfile.graph_ports.length} overridable ports</div>
                  </div>
                  <div className="rounded-lg border border-border bg-bg-main/60 p-3">
                    <div className="text-xs uppercase tracking-[0.16em] text-text-muted">Selected Packs</div>
                    <div className="mt-2 text-sm font-medium text-text-main">{selectedProfile.packs.length}</div>
                    <div className="mt-1 text-xs text-text-muted">{selectedProfile.packs.join(', ')}</div>
                  </div>
                </CardContent>
              </Card>

              <div className="grid gap-5 lg:grid-cols-2">
                <Card>
                  <CardHeader>
                    <CardTitle>Pack Selection</CardTitle>
                    <CardDescription>Profile-local packs are separate from the global pack enablement page.</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-5">
                    <div className="space-y-2">
                      <div className="flex items-center gap-2 text-sm font-medium text-text-main">
                        <Boxes className="h-4 w-4 text-text-muted" />
                        Launch Frontend
                      </div>
                      <select
                        value={selectedFrontend}
                        disabled={!frontendPortKey(selectedProfile) || frontendCandidates.length === 0}
                        onChange={(event) => onSelectFrontend(selectedProfile, event.target.value)}
                        className="h-10 w-full rounded-lg border border-border bg-bg-main px-3 text-sm text-text-main focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring-color)] disabled:opacity-50"
                        aria-label="Launch frontend"
                      >
                        <option value="">Default from base pack</option>
                        {frontendCandidates.map((candidate) => (
                          <option key={candidate.nodeId} value={candidate.nodeId}>{candidate.label}</option>
                        ))}
                      </select>
                      <p className="text-xs text-text-muted">
                        The launch frontend is stored as the compatible `frontend.surface` node override.
                      </p>
                    </div>

                    <div className="space-y-2">
                      <div className="text-sm font-medium text-text-main">Tool Packs</div>
                      <div className="grid gap-2">
                        {toolPacks.map((pack) => {
                          const checked = selectedProfile.packs.includes(pack.pack_id);
                          const locked = packHasProfileSelection(selectedProfile, pack.pack_id);
                          return (
                            <label key={pack.pack_id} className="flex items-start justify-between gap-3 rounded-lg border border-border bg-bg-main/50 p-3">
                              <div className="min-w-0">
                                <div className="truncate text-sm font-medium text-text-main">{packLabel(pack)}</div>
                                <div className="truncate text-xs text-text-muted">{pack.description}</div>
                              </div>
                              <Switch
                                checked={checked}
                                disabled={locked && checked}
                                onCheckedChange={(next) => next
                                  ? onAddPack(selectedProfile.profile_id, pack.pack_id)
                                  : onRemovePack(selectedProfile.profile_id, pack.pack_id)}
                                aria-label={`Toggle ${packLabel(pack)} tool pack`}
                              />
                            </label>
                          );
                        })}
                        {toolPacks.length === 0 && (
                          <div className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-sm text-text-muted">
                            No tool packs are available.
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="flex gap-2">
                      <select
                        value={packToAdd}
                        onChange={(event) => setPackToAdd(event.target.value)}
                        className="h-10 min-w-0 flex-1 rounded-lg border border-border bg-bg-main px-3 text-sm text-text-main focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring-color)]"
                        aria-label="Pack to add"
                      >
                        {addablePacks.map((pack) => (
                          <option key={pack.pack_id} value={pack.pack_id}>{packLabel(pack)}</option>
                        ))}
                      </select>
                      <Button
                        variant="outline"
                        onClick={() => packToAdd && onAddPack(selectedProfile.profile_id, packToAdd)}
                        disabled={!packToAdd}
                      >
                        <PackagePlus className="h-4 w-4" />
                        Add Pack
                      </Button>
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle>Profile Security</CardTitle>
                    <CardDescription>Policy changes stay profile-scoped and still pass through runtime approval.</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <label className="flex items-start justify-between gap-3 rounded-lg border border-border bg-bg-main/50 p-3">
                      <div>
                        <div className="text-sm font-medium text-text-main">Compile capability graph before launch</div>
                        <div className="text-xs text-text-muted">Builds the runtime graph and launch target before handing off.</div>
                      </div>
                      <Switch
                        checked={Boolean(selectedProfile.launch_capability_graph)}
                        onCheckedChange={(enabled) => onToggleLaunchCompile(selectedProfile, enabled)}
                        aria-label="Compile capability graph before launch"
                      />
                    </label>
                    <label className="flex items-start justify-between gap-3 rounded-lg border border-border bg-bg-main/50 p-3">
                      <div>
                        <div className="text-sm font-medium text-text-main">Require clean graph compile</div>
                        <div className="text-xs text-text-muted">Blocks launch when strict compile diagnostics fail.</div>
                      </div>
                      <Switch
                        checked={Boolean(selectedProfile.policy?.require_capability_graph_compile)}
                        onCheckedChange={(enabled) => onTogglePolicy(selectedProfile, 'require_capability_graph_compile', enabled)}
                        aria-label="Require clean graph compile"
                      />
                    </label>
                    <label className="flex items-start justify-between gap-3 rounded-lg border border-border bg-bg-main/50 p-3">
                      <div>
                        <div className="text-sm font-medium text-text-main">Enforce API route allowlist</div>
                        <div className="text-xs text-text-muted">Makes selected API routes an explicit runtime boundary.</div>
                      </div>
                      <Switch
                        checked={Boolean(selectedProfile.policy?.enforce_api_route_allowlist)}
                        onCheckedChange={(enabled) => onTogglePolicy(selectedProfile, 'enforce_api_route_allowlist', enabled)}
                        aria-label="Enforce API route allowlist"
                      />
                    </label>

                    <div className="rounded-lg border border-border bg-bg-main/50 p-3">
                      <div className="text-sm font-medium text-text-main">Issues</div>
                      <div className="mt-2 space-y-2">
                        {selectedView.issues.length ? selectedView.issues.map((issue) => (
                          <div key={`${issue.title}-${issue.description}`} className="rounded-md bg-bg-hover px-3 py-2 text-xs text-text-muted">
                            <span className="font-medium text-text-main">{issue.title}: </span>
                            {issue.description}
                          </div>
                        )) : (
                          <div className="text-xs text-text-muted">No profile issues detected.</div>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>

              <Card>
                <CardHeader className="flex-row items-start justify-between gap-4 space-y-0">
                  <div>
                    <CardTitle>Runtime Preview</CardTitle>
                    <CardDescription>Preview validates pack overrides, selected tools, and launch surface without changing the active runtime.</CardDescription>
                  </div>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => onDeleteProfile(selectedProfile.profile_id)}
                    disabled={profiles.length <= 1}
                    loading={savingAction === 'delete'}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    Delete
                  </Button>
                </CardHeader>
                <CardContent>
                  {preview?.profile_id === selectedProfile.profile_id ? (
                    <div className="grid gap-3 md:grid-cols-3">
                      <div className="rounded-lg border border-border bg-bg-main/60 p-3">
                        <div className="text-xs uppercase tracking-[0.16em] text-text-muted">Compile</div>
                        <Badge className="mt-2" variant={preview.ok ? 'success' : 'warning'}>
                          {preview.ok ? 'Ready' : 'Diagnostics'}
                        </Badge>
                      </div>
                      <div className="rounded-lg border border-border bg-bg-main/60 p-3">
                        <div className="text-xs uppercase tracking-[0.16em] text-text-muted">Launch Pack</div>
                        <div className="mt-2 truncate text-sm font-medium text-text-main">
                          {preview.surface_launch_target?.pack_id || preview.capability_graph?.surface_launch_target?.pack_id || '--'}
                        </div>
                      </div>
                      <div className="rounded-lg border border-border bg-bg-main/60 p-3">
                        <div className="text-xs uppercase tracking-[0.16em] text-text-muted">Tool Allowlist</div>
                        <div className="mt-2 truncate text-sm font-medium text-text-main">
                          {Array.isArray(preview.profile.policy?.tool_allowlist) ? preview.profile.policy.tool_allowlist.join(', ') : '--'}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="rounded-lg border border-dashed border-border px-4 py-8 text-center text-sm text-text-muted">
                      Run Preview to inspect the effective launch profile.
                    </div>
                  )}
                </CardContent>
              </Card>
            </section>
          ) : (
            <section className="rounded-xl border border-dashed border-border px-6 py-16 text-center text-sm text-text-muted">
              No startup profile exists yet.
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

export function StartupProfiles() {
  const addToast = useAppStore((state) => state.addToast);
  const [profiles, setProfiles] = useState<ApiStartupProfile[]>([]);
  const [catalog, setCatalog] = useState<ApiStartupCatalog>({version: 1, packs: []});
  const [activeProfileId, setActiveProfileId] = useState<string | null>(null);
  const [lastLaunchedProfileId, setLastLaunchedProfileId] = useState<string | null>(null);
  const [selectedProfileId, setSelectedProfileId] = useState('');
  const [preview, setPreview] = useState<StartupProfileCompilePreviewResponseData | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingAction, setSavingAction] = useState<string | null>(null);

  const loadProfiles = async (preferredProfileId?: string) => {
    const response = await fetchStartupProfiles();
    setProfiles(response.profiles);
    setCatalog(response.catalog);
    setActiveProfileId(response.active_profile_id);
    setLastLaunchedProfileId(response.last_launched_profile_id);
    setSelectedProfileId((current) => {
      const desired = preferredProfileId || current || response.active_profile_id || response.profiles[0]?.profile_id || '';
      return response.profiles.some((profile) => profile.profile_id === desired)
        ? desired
        : response.profiles[0]?.profile_id || '';
    });
  };

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchStartupProfiles()
      .then((response) => {
        if (cancelled) {
          return;
        }
        setProfiles(response.profiles);
        setCatalog(response.catalog);
        setActiveProfileId(response.active_profile_id);
        setLastLaunchedProfileId(response.last_launched_profile_id);
        setSelectedProfileId(response.active_profile_id || response.profiles[0]?.profile_id || '');
      })
      .catch((error) => {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : 'Failed to load startup profiles';
          addToast(describeStartupActionError(message, 'load startup profiles'), 'error');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [addToast]);

  const runAction = async (action: string, work: () => Promise<string | void>) => {
    setSavingAction(action);
    try {
      const preferredProfileId = await work();
      if (preferredProfileId) {
        setSelectedProfileId(preferredProfileId);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : `Failed to ${action}`;
      addToast(describeStartupActionError(message, action), 'error');
    } finally {
      setSavingAction(null);
    }
  };

  const handleCreateProfile = () => {
    void runAction('create', async () => {
      const base = startupPacksForRole(catalog, 'base')[0];
      if (!base) {
        throw new Error('No base pack is available');
      }
      const graphId = base.graphs[0]?.graph_id;
      const response = await createStartupProfile({
        name: `${packLabel(base)} Profile`,
        base_pack: base.pack_id,
        graph_id: graphId,
        default_graph: graphId,
        capability_profile_id: graphId,
        launch_capability_graph: true,
        policy: {require_capability_graph_compile: false},
      });
      await loadProfiles(response.profile.profile_id);
      addToast('Startup profile created.', 'success');
      return response.profile.profile_id;
    });
  };

  const handleAddPack = (profileId: string, packId: string) => {
    void runAction('add pack', async () => {
      const profile = profiles.find((candidate) => candidate.profile_id === profileId);
      if (!profile) {
        throw new Error('Profile was not found');
      }
      await updateStartupProfile(profileId, buildAddStartupProfilePackPatch(catalog, profile, packId));
      setPreview(null);
      await loadProfiles(profileId);
      addToast('Pack added to profile.', 'success');
      return profileId;
    });
  };

  const handleRemovePack = (profileId: string, packId: string) => {
    void runAction('remove pack', async () => {
      const profile = profiles.find((candidate) => candidate.profile_id === profileId);
      if (!profile) {
        throw new Error('Profile was not found');
      }
      await updateStartupProfile(profileId, buildRemoveStartupProfilePackPatch(catalog, profile, packId));
      setPreview(null);
      await loadProfiles(profileId);
      addToast('Pack removed from profile.', 'success');
      return profileId;
    });
  };

  const handleSelectBasePack = (profile: ApiStartupProfile, packId: string) => {
    void runAction('change base pack', async () => {
      const patch = buildSetStartupProfileBasePackPatch(catalog, profile, packId);
      if (!patch.graph_id) {
        throw new Error('Selected base pack has no launch graph');
      }
      await updateStartupProfile(profile.profile_id, {
        ...patch,
        default_graph: patch.graph_id,
        capability_profile_id: patch.graph_id,
      });
      setPreview(null);
      await loadProfiles(profile.profile_id);
      addToast('Base pack changed.', 'success');
      return profile.profile_id;
    });
  };

  const handleSelectFrontend = (profile: ApiStartupProfile, nodeId: string) => {
    void runAction('set launch frontend', async () => {
      const portKey = frontendPortKey(profile);
      if (!portKey) {
        throw new Error('This profile graph does not expose a frontend surface port');
      }
      const candidate = frontendSurfaceCandidates(catalog).find((item) => item.nodeId === nodeId);
      const nextOverrides = {...profile.node_overrides};
      let nextPacks = [...profile.packs];
      if (candidate) {
        nextOverrides[portKey] = nodeId;
        nextPacks = uniqueList([...nextPacks, candidate.packId]);
      } else {
        delete nextOverrides[portKey];
      }
      await updateStartupProfile(profile.profile_id, {
        packs: nextPacks,
        node_overrides: nextOverrides,
      });
      setPreview(null);
      await loadProfiles(profile.profile_id);
      addToast('Launch frontend updated.', 'success');
      return profile.profile_id;
    });
  };

  const handleToggleLaunchCompile = (profile: ApiStartupProfile, enabled: boolean) => {
    void runAction('update launch compile', async () => {
      await updateStartupProfile(profile.profile_id, {launch_capability_graph: enabled});
      await loadProfiles(profile.profile_id);
      return profile.profile_id;
    });
  };

  const handleTogglePolicy = (profile: ApiStartupProfile, key: string, enabled: boolean) => {
    void runAction('update profile policy', async () => {
      await updateStartupProfile(profile.profile_id, {
        policy: {...(profile.policy ?? {}), [key]: enabled},
      });
      await loadProfiles(profile.profile_id);
      return profile.profile_id;
    });
  };

  const handlePreview = (profileId: string) => {
    void runAction('preview', async () => {
      const response = await compileStartupProfilePreview(profileId);
      setPreview(response);
      addToast(response.ok ? 'Runtime preview ready.' : 'Runtime preview has diagnostics.', response.ok ? 'success' : 'error');
      return profileId;
    });
  };

  const handleActivate = (profileId: string) => {
    void runAction('activate', async () => {
      await activateStartupProfile(profileId);
      await loadProfiles(profileId);
      addToast('Startup profile activated.', 'success');
      return profileId;
    });
  };

  const handleLaunch = (profileId: string) => {
    void runAction('launch', async () => {
      await launchStartupProfile(profileId);
      await loadProfiles(profileId);
      addToast('Startup profile launch requested.', 'success');
      return profileId;
    });
  };

  const handleDuplicate = (profileId: string) => {
    void runAction('duplicate', async () => {
      const response = await duplicateStartupProfile(profileId);
      await loadProfiles(response.profile.profile_id);
      addToast('Startup profile duplicated.', 'success');
      return response.profile.profile_id;
    });
  };

  const handleDelete = (profileId: string) => {
    if (!window.confirm('Delete this startup profile?')) {
      return;
    }
    void runAction('delete', async () => {
      await deleteStartupProfile(profileId);
      setPreview(null);
      await loadProfiles();
      addToast('Startup profile deleted.', 'success');
    });
  };

  return (
    <StartupProfilesShell
      activeProfileId={activeProfileId}
      catalog={catalog}
      loading={loading}
      lastLaunchedProfileId={lastLaunchedProfileId}
      preview={preview}
      profiles={profiles}
      savingAction={savingAction}
      selectedProfileId={selectedProfileId}
      onActivate={handleActivate}
      onAddPack={handleAddPack}
      onCreateProfile={handleCreateProfile}
      onDeleteProfile={handleDelete}
      onDuplicateProfile={handleDuplicate}
      onLaunch={handleLaunch}
      onPreview={handlePreview}
      onRemovePack={handleRemovePack}
      onSelectBasePack={handleSelectBasePack}
      onSelectFrontend={handleSelectFrontend}
      onSelectProfile={setSelectedProfileId}
      onToggleLaunchCompile={handleToggleLaunchCompile}
      onTogglePolicy={handleTogglePolicy}
    />
  );
}
