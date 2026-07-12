import { useEffect, useMemo, useState } from 'react';
import { Database, FileCode2, FolderOpen, RefreshCw, ShieldCheck } from 'lucide-react';
import { Button } from '@/src/components/ui/Button';
import { Badge } from '@/src/components/ui/Badge';
import type { ApiProfileWorkspaceDetail, StartupProfilesResponseData } from '@/src/lib/apiTypes';
import { fetchActiveProfileWorkspace, fetchProfileWorkspace } from '@/src/lib/profileWorkspaceApi';
import { useAppStore } from '@/src/store';
import { FlowViewer } from './FlowViewer';
import { InlineLoadError } from '@/src/components/ui/InlineLoadError';

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-56 overflow-auto bg-bg-hover p-3 text-xs text-text-main">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function PathRow({ label, value }: { label: string; value?: string }) {
  return (
    <div className="grid gap-1 border-b border-border py-2 sm:grid-cols-[180px_minmax(0,1fr)]">
      <div className="text-xs font-medium uppercase text-text-muted">{label}</div>
      <div className="min-w-0 break-all font-mono text-xs text-text-main">{value || '--'}</div>
    </div>
  );
}

export function ProfileWorkspace() {
  const addToast = useAppStore((state) => state.addToast);
  const runtimeReady = useAppStore((state) => state.runtimeReady);
  const runtimeStatus = useAppStore((state) => state.runtimeStatus);
  const runtimeError = useAppStore((state) => state.runtimeError);
  const refreshRuntimeHealth = useAppStore((state) => state.refreshRuntimeHealth);
  const [startupProfiles, setStartupProfiles] = useState<StartupProfilesResponseData | null>(null);
  const [workspace, setWorkspace] = useState<ApiProfileWorkspaceDetail | null>(null);
  const [selectedProfileId, setSelectedProfileId] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadWorkspace = async (profileId?: string) => {
    setLoading(true);
    try {
      if (profileId) {
        const nextWorkspace = await fetchProfileWorkspace(profileId);
        setWorkspace(nextWorkspace);
        setSelectedProfileId(profileId);
      } else {
        const response = await fetchActiveProfileWorkspace();
        setStartupProfiles(response.startupProfiles);
        setWorkspace(response.workspace);
        setSelectedProfileId(response.activeProfile?.profile_id ?? '');
      }
      setError(null);
    } catch (loadError) {
      const message = loadError instanceof Error ? loadError.message : 'Failed to load profile workspace';
      setError(message);
      addToast(message, 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!runtimeReady) return;
    void loadWorkspace();
  }, [runtimeReady]);

  const profiles = startupProfiles?.profiles ?? [];
  const manifestItems = useMemo(() => {
    const items = workspace?.resource_snapshot_manifest?.items;
    return Array.isArray(items) ? items as Array<Record<string, unknown>> : [];
  }, [workspace]);

  return (
    <div className="flex h-full flex-col overflow-hidden bg-bg-main">
      <div className="border-b border-border px-6 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold text-text-main">Profile Workspace</h1>
            <div className="mt-1 text-sm text-text-muted">{workspace?.profile.name ?? 'No active profile'}</div>
          </div>
          <div className="flex items-center gap-2">
            <select
              className="h-9 rounded-md border border-border bg-bg-main px-3 text-sm text-text-main"
              value={selectedProfileId}
              onChange={(event) => void loadWorkspace(event.target.value)}
            >
              {profiles.map((profile) => (
                <option key={profile.profile_id} value={profile.profile_id}>{profile.name}</option>
              ))}
            </select>
            <Button variant="secondary" size="sm" onClick={() => void loadWorkspace(selectedProfileId)}>
              <RefreshCw className="h-4 w-4" />
              Refresh
            </Button>
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-6">
        {!runtimeReady ? (
          <InlineLoadError
            title={runtimeStatus === 'error' ? 'Runtime failed to start' : 'Runtime is not ready'}
            message={runtimeError || 'Profile workspace data becomes available after the local runtime is ready.'}
            onRetry={() => void refreshRuntimeHealth()}
          />
        ) : null}
        {loading && <div className="text-sm text-text-muted">Loading workspace...</div>}
        {error && runtimeReady ? (
          <InlineLoadError
            title="Profile workspace could not be loaded"
            message={error}
            onRetry={() => void loadWorkspace(selectedProfileId || undefined)}
            retrying={loading}
            stale={Boolean(workspace)}
          />
        ) : null}
        {workspace && (
          <div className="space-y-6">
            <section className="border border-border bg-bg-main p-4">
              <div className="mb-3 flex items-center gap-2">
                <FolderOpen className="h-4 w-4 text-accent" />
                <h2 className="text-sm font-semibold text-text-main">Workspace Paths</h2>
                <Badge variant="success">{workspace.profile.profile_id}</Badge>
              </div>
              <PathRow label="profile_workspace_path" value={workspace.profile_workspace.root} />
              <PathRow label="profile_file" value={workspace.profile_workspace.profile_file} />
              <PathRow label="database_path" value={workspace.profile_workspace.database_path} />
              <PathRow label="user_data_dir" value={workspace.profile_workspace.user_data_dir} />
              <PathRow label="startup_dir" value={workspace.profile_workspace.startup_dir} />
              <PathRow label="flows_dir" value={workspace.profile_workspace.flows_dir} />
              <PathRow label="prompts_dir" value={workspace.profile_workspace.prompts_dir} />
              <PathRow label="permissions_dir" value={workspace.profile_workspace.permissions_dir} />
            </section>

            <div className="grid gap-6 xl:grid-cols-2">
              <section className="border border-border bg-bg-main p-4">
                <div className="mb-3 flex items-center gap-2">
                  <Database className="h-4 w-4 text-accent" />
                  <h2 className="text-sm font-semibold text-text-main">Startup Config</h2>
                </div>
                <JsonBlock value={workspace.startup_config} />
              </section>

              <section className="border border-border bg-bg-main p-4">
                <div className="mb-3 flex items-center gap-2">
                  <ShieldCheck className="h-4 w-4 text-accent" />
                  <h2 className="text-sm font-semibold text-text-main">Permissions Files</h2>
                </div>
                <div className="space-y-2">
                  {Object.entries(workspace.permissions).map(([name, status]) => (
                    <div key={name} className="flex items-center justify-between gap-3 border border-border p-2">
                      <div className="min-w-0">
                        <div className="font-mono text-xs text-text-main">{name}</div>
                        <div className="truncate text-xs text-text-muted">{status.path}</div>
                      </div>
                      <Badge variant={status.exists ? 'success' : 'warning'}>{status.exists ? 'present' : 'missing'}</Badge>
                    </div>
                  ))}
                </div>
              </section>
            </div>

            <div className="grid gap-6 xl:grid-cols-2">
              <section className="border border-border bg-bg-main p-4">
                <div className="mb-3 flex items-center gap-2">
                  <FileCode2 className="h-4 w-4 text-accent" />
                  <h2 className="text-sm font-semibold text-text-main">Profile Flows</h2>
                </div>
                <JsonBlock value={workspace.flows} />
              </section>
              <section className="border border-border bg-bg-main p-4">
                <div className="mb-3 flex items-center gap-2">
                  <FileCode2 className="h-4 w-4 text-accent" />
                  <h2 className="text-sm font-semibold text-text-main">Profile Rule Prompts</h2>
                </div>
                <JsonBlock value={workspace.prompts} />
              </section>
            </div>

            <section className="border border-border bg-bg-main p-4">
              <div className="mb-3 flex items-center justify-between gap-3">
                <h2 className="text-sm font-semibold text-text-main">Resource Snapshot Manifest</h2>
                <Badge variant={manifestItems.length ? 'success' : 'warning'}>{manifestItems.length} items</Badge>
              </div>
              <JsonBlock value={workspace.resource_snapshot_manifest} />
            </section>

            <FlowViewer
              yamlContent={workspace.flow_yaml.yaml_content}
              sourcePath={workspace.flow_yaml.path}
            />
          </div>
        )}
      </div>
    </div>
  );
}
