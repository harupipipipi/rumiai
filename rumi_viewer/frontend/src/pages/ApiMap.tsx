import {useEffect, useState} from 'react';
import {Loader2, RefreshCw, Route} from 'lucide-react';

import {ProfileGraphCanvas} from '@/src/components/profile-graph/ProfileGraphCanvas';
import {Badge} from '@/src/components/ui/Badge';
import {Button} from '@/src/components/ui/Button';
import {Input} from '@/src/components/ui/Input';
import {fetchApiMap, fetchStartupProfiles} from '@/src/lib/api';
import type {ApiMapResponseData, ApiStartupProfile} from '@/src/lib/apiTypes';
import {useAppStore} from '@/src/store';

export function ApiMap() {
  const addToast = useAppStore((state) => state.addToast);
  const [profiles, setProfiles] = useState<ApiStartupProfile[]>([]);
  const [profileId, setProfileId] = useState('');
  const [focus, setFocus] = useState('');
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [data, setData] = useState<ApiMapResponseData | null>(null);
  const [loading, setLoading] = useState(true);

  const load = async (nextProfileId = profileId, nextFocus = focus) => {
    setLoading(true);
    try {
      const response = await fetchApiMap({
        profile_id: nextProfileId || undefined,
        focus: nextFocus || undefined,
      });
      setData(response);
      if (!selectedNodeId && response.nodes[0]?.id) {
        setSelectedNodeId(response.nodes[0].id);
      }
    } catch (error) {
      addToast(error instanceof Error ? error.message : 'Failed to load API map', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchStartupProfiles(), fetchApiMap()])
      .then(([startupProfiles, apiMap]) => {
        if (cancelled) {
          return;
        }
        setProfiles(startupProfiles.profiles);
        setProfileId(startupProfiles.active_profile_id || startupProfiles.profiles[0]?.profile_id || '');
        setData(apiMap);
        setSelectedNodeId(apiMap.nodes[0]?.id || null);
      })
      .catch((error) => {
        if (!cancelled) {
          addToast(error instanceof Error ? error.message : 'Failed to load API map', 'error');
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

  return (
    <div className="flex flex-1 flex-col gap-5 overflow-y-auto bg-bg-main p-6 animate-in fade-in slide-in-from-bottom-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-text-main">API Map</h1>
          <p className="mt-1 text-sm text-text-muted">
            Inspect route-to-block, tool-to-handler, webhook-to-input-profile, and profile selection edges in one map.
          </p>
        </div>
        <Button type="button" size="sm" variant="outline" onClick={() => void load()}>
          <RefreshCw className="h-4 w-4" />
          Refresh
        </Button>
      </div>

      <section className="rounded-2xl border border-border bg-bg-card p-4">
        <div className="grid gap-3 lg:grid-cols-[minmax(220px,260px)_minmax(200px,1fr)_auto]">
          <label className="text-sm text-text-muted">
            Profile
            <select
              className="mt-2 h-10 w-full rounded-lg border border-border bg-bg-main px-3 text-text-main"
              value={profileId}
              onChange={(event) => setProfileId(event.target.value)}
            >
              <option value="">Active profile</option>
              {profiles.map((profile) => (
                <option key={profile.profile_id} value={profile.profile_id}>{profile.name}</option>
              ))}
            </select>
          </label>
          <label className="text-sm text-text-muted">
            Focus node
            <Input
              className="mt-2"
              placeholder="tool:web_search or api:GET /api/panel/api-map"
              value={focus}
              onChange={(event) => setFocus(event.target.value)}
            />
          </label>
          <div className="flex items-end">
            <Button type="button" onClick={() => void load(profileId, focus)}>
              <Route className="h-4 w-4" />
              Apply Filters
            </Button>
          </div>
        </div>
      </section>

      {loading ? (
        <div className="flex min-h-[520px] items-center justify-center rounded-2xl border border-border bg-bg-card">
          <div className="flex items-center gap-3 text-text-muted">
            <Loader2 className="h-5 w-5 animate-spin" />
            <span>Loading API map</span>
          </div>
        </div>
      ) : (
        <ProfileGraphCanvas
          nodes={data?.nodes || []}
          edges={data?.edges || []}
          selectedNodeId={selectedNodeId}
          onSelectNode={setSelectedNodeId}
          emptyMessage="No API map nodes were returned."
        />
      )}

      <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <article className="rounded-2xl border border-border bg-bg-card p-4">
          <div className="mb-3 flex flex-wrap gap-2">
            <Badge variant="outline">{data?.summary.route_count || 0} routes</Badge>
            <Badge variant="outline">{data?.summary.tool_count || 0} tools</Badge>
            <Badge variant="outline">{data?.summary.webhook_count || 0} webhooks</Badge>
            <Badge variant="secondary">{data?.summary.edge_count || 0} edges</Badge>
          </div>
          <pre className="max-h-[320px] overflow-auto rounded-xl border border-border bg-bg-main/70 p-3 text-xs text-text-muted">
            {JSON.stringify(data?.summary || {}, null, 2)}
          </pre>
        </article>

        <article className="rounded-2xl border border-border bg-bg-card p-4">
          <h2 className="text-sm font-semibold text-text-main">Diagnostics</h2>
          <div className="mt-3 space-y-2">
            {data?.diagnostics?.length ? data.diagnostics.map((diagnostic, index) => (
              <div key={`${diagnostic.code}-${index}`} className="rounded-xl border border-border bg-bg-main/70 px-3 py-2 text-sm text-text-muted">
                <div className="font-medium text-text-main">{diagnostic.code}</div>
                <div className="mt-1 text-xs">{diagnostic.message}</div>
              </div>
            )) : (
              <div className="rounded-xl border border-dashed border-border px-3 py-6 text-sm text-text-muted">
                No diagnostics for the current API map view.
              </div>
            )}
          </div>
        </article>
      </section>
    </div>
  );
}
