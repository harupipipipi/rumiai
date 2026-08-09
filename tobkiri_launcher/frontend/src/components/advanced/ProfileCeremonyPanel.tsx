import {useEffect, useMemo, useRef, useState} from 'react';
import {ArrowRight, CheckCircle2, LockKeyhole, ShieldCheck, XCircle} from 'lucide-react';

import {Badge} from '@/src/components/ui/Badge';
import {Button} from '@/src/components/ui/Button';
import {Card, CardContent, CardDescription, CardHeader, CardTitle} from '@/src/components/ui/Card';
import {broadcastRuntimeSurfaceRefresh, type RuntimeSurfaceState} from '@/src/hooks/useRuntimeSurface';
import {
  classifyRuntimeSurfaceError,
  extractExactProfileSelectablePackIds,
  runtimeSurfaceErrorMessage,
  RuntimeSurfaceError,
  type RuntimeSurfaceErrorCode,
} from '@/src/lib/runtimeSurface';
import {
  defaultProfileCeremonyClient,
  snapshotForProfileCeremony,
  type ProfileActivateResult,
  type ProfileApproveResult,
  type ProfileCeremonyClient,
  type ProfileResolveResult,
  type ProfileReviewResult,
} from '@/src/lib/profileCeremony';
import type {Pack} from '@/src/store';

type CeremonyState = 'idle' | 'resolving' | 'resolved' | 'reviewing' | 'reviewed' | 'approving' | 'approved' | 'activating' | 'active' | 'error';

function recordDigest(record: unknown, keys: string[]): string {
  if (!record || typeof record !== 'object' || Array.isArray(record)) return 'not published';
  const value = record as Record<string, unknown>;
  const key = keys.find((candidate) => typeof value[candidate] === 'string');
  return key ? String(value[key]) : 'not published';
}

function snapshotKey(snapshot: {profile_id: string; profile_revision: string; plan_digest: string}): string {
  return `${snapshot.profile_id}:${snapshot.profile_revision}:${snapshot.plan_digest}`;
}

export function ProfileCeremonyPanel({
  surface,
  packs,
  packsLoading,
  loadPacks,
  client = defaultProfileCeremonyClient,
  onActivated,
}: {
  surface: RuntimeSurfaceState<unknown>;
  packs: Pack[];
  packsLoading: boolean;
  loadPacks: () => Promise<void>;
  client?: ProfileCeremonyClient;
  onActivated?: (result: ProfileActivateResult) => Promise<void>;
}) {
  const [selectedPackIds, setSelectedPackIds] = useState<string[]>([]);
  const [ceremonyState, setCeremonyState] = useState<CeremonyState>('idle');
  const [candidate, setCandidate] = useState<ProfileResolveResult | null>(null);
  const [reviewed, setReviewed] = useState<ProfileReviewResult | null>(null);
  const [approval, setApproval] = useState<ProfileApproveResult | null>(null);
  const [ceremonySnapshot, setCeremonySnapshot] = useState<string | null>(null);
  const [failure, setFailure] = useState<{code: RuntimeSurfaceErrorCode; message: string} | null>(null);
  const initialized = useRef(false);

  const closureIds = useMemo(
    () => surface.data ? extractExactProfileSelectablePackIds(surface.data.data) : null,
    [surface.data],
  );
  const profileBoundPacks = surface.data
    ? packs.filter((pack) => (
      pack.profileRevision === surface.data?.profile_revision
      && pack.planDigest === surface.data?.plan_digest
    ))
    : [];
  const selectablePacks = profileBoundPacks.filter((pack) => pack.installed && pack.approved && pack.enabled);
  const selectablePackIds = new Set(selectablePacks.map((pack) => pack.id));
  const controlCatalogRevisions = new Set(packs.map((pack) => pack.catalogRevision).filter(Boolean));
  const packCatalogBound = Boolean(
    surface.data
    && packs.length > 0
    && controlCatalogRevisions.size === 1
    && profileBoundPacks.length === packs.length,
  );
  const profilePackIdsAvailable = closureIds !== null;
  const missingClosureIds = (closureIds ?? []).filter((id) => !packs.some((pack) => pack.id === id));

  useEffect(() => {
    if (initialized.current) return;
    const initial = closureIds && closureIds.length > 0
      ? closureIds.filter((id) => selectablePacks.some((pack) => pack.id === id))
      : selectablePacks.filter((pack) => pack.required || pack.enabled).map((pack) => pack.id);
    if (initial.length > 0) {
      initialized.current = true;
      setSelectedPackIds(initial);
    }
  }, [closureIds, selectablePacks]);

  const currentSnapshot = snapshotForProfileCeremony(surface.data);
  const ceremonyIsBusy = ['resolving', 'reviewing', 'approving', 'activating'].includes(ceremonyState);
  const isRuntimeReady = surface.status === 'ready'
    && !surface.stale
    && currentSnapshot !== null
    && profilePackIdsAvailable
    && packCatalogBound
    && missingClosureIds.length === 0;
  const snapshotChanged = Boolean(
    ceremonySnapshot && currentSnapshot && ceremonySnapshot !== snapshotKey(currentSnapshot),
  );

  const resetCeremony = () => {
    setCeremonyState('idle');
    setCandidate(null);
    setReviewed(null);
    setApproval(null);
    setCeremonySnapshot(null);
    setFailure(null);
  };

  const selectPack = (pack: Pack) => {
    if (!pack.installed || !pack.approved || pack.required || ceremonyIsBusy) return;
    if (ceremonyState !== 'idle') resetCeremony();
    setSelectedPackIds((current) => {
      const next = current.includes(pack.id)
        ? current.filter((id) => id !== pack.id)
        : [...current, pack.id];
      return next;
    });
  };

  const failClosed = (error: unknown) => {
    const code = classifyRuntimeSurfaceError(error);
    const message = error instanceof Error ? error.message : runtimeSurfaceErrorMessage(code);
    setFailure({code, message});
    setCeremonyState('error');
  };

  const requireStableSnapshot = () => {
    if (!isRuntimeReady || snapshotChanged || !currentSnapshot) {
      throw new RuntimeSurfaceError('DIGEST_MISMATCH', runtimeSurfaceErrorMessage('DIGEST_MISMATCH'));
    }
    return currentSnapshot;
  };

  const resolve = async () => {
    try {
      const snapshot = requireStableSnapshot();
      if (
        selectedPackIds.length === 0
        || new Set(selectedPackIds).size !== selectedPackIds.length
        || selectedPackIds.some((id) => !selectablePackIds.has(id))
      ) {
        throw new RuntimeSurfaceError('INVALID', 'Select at least one approved Pack before resolving a candidate.');
      }
      setFailure(null);
      setCeremonyState('resolving');
      const result = await client.resolve({
        profile_id: snapshot.profile_id,
        expected_profile_revision: snapshot.profile_revision,
        expected_plan_digest: snapshot.plan_digest,
        desired_pack_ids: [...selectedPackIds],
      });
      setCandidate(result);
      setReviewed(null);
      setApproval(null);
      setCeremonySnapshot(snapshotKey(snapshot));
      setCeremonyState('resolved');
    } catch (error) {
      failClosed(error);
    }
  };

  const review = async () => {
    try {
      requireStableSnapshot();
      if (!candidate) throw new RuntimeSurfaceError('INVALID', 'No resolved candidate is available.');
      setFailure(null);
      setCeremonyState('reviewing');
      const result = await client.review({candidate_id: candidate.candidate_id, candidate_digest: candidate.candidate_digest});
      setReviewed(result);
      setCeremonyState('reviewed');
    } catch (error) {
      failClosed(error);
    }
  };

  const approve = async () => {
    try {
      requireStableSnapshot();
      if (!reviewed) throw new RuntimeSurfaceError('INVALID', 'Review must complete before approval.');
      setFailure(null);
      setCeremonyState('approving');
      const result = await client.approve({candidate_id: reviewed.candidate_id, candidate_digest: reviewed.candidate_digest});
      setApproval(result);
      setCeremonyState('approved');
    } catch (error) {
      failClosed(error);
    }
  };

  const activate = async () => {
    try {
      requireStableSnapshot();
      if (!approval) throw new RuntimeSurfaceError('INVALID', 'Kernel approval is required before activation.');
      setFailure(null);
      setCeremonyState('activating');
      const result = await client.activate({approval_id: approval.approval_id, approval_digest: approval.approval_digest});
      setCeremonyState('active');
      broadcastRuntimeSurfaceRefresh();
      await onActivated?.(result);
      await Promise.all([surface.refresh(true), loadPacks()]);
    } catch (error) {
      failClosed(error);
    }
  };

  const actionLabel = ceremonyState === 'resolved'
    ? 'Review exact candidate'
    : ceremonyState === 'reviewed'
      ? 'Request Kernel approval'
      : ceremonyState === 'approved'
        ? 'Activate approved Profile'
        : 'Resolve candidate';
  const action = ceremonyState === 'resolved' ? review : ceremonyState === 'reviewed' ? approve : ceremonyState === 'approved' ? activate : resolve;

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2"><LockKeyhole className="h-4 w-4" aria-hidden="true" />Runtime Profile change ceremony</CardTitle>
          <Badge variant={isRuntimeReady ? 'warning' : 'secondary'}>{isRuntimeReady ? 'digest-bound' : 'locked'}</Badge>
        </div>
        <CardDescription>Select an approved Pack closure, then inspect the exact diff before each one-shot server-bound step. No client approval flag is accepted.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <div className="grid gap-2 sm:grid-cols-4" aria-label="Profile change steps">
          {(['resolve', 'review', 'approval', 'activation'] as const).map((step, index) => {
            const complete = (step === 'resolve' && ['resolved', 'reviewing', 'reviewed', 'approving', 'approved', 'activating', 'active'].includes(ceremonyState))
              || (step === 'review' && ['reviewed', 'approving', 'approved', 'activating', 'active'].includes(ceremonyState))
              || (step === 'approval' && ['approved', 'activating', 'active'].includes(ceremonyState))
              || (step === 'activation' && ceremonyState === 'active');
            return (
              <div key={step} className="flex min-h-11 items-center gap-2 rounded-lg border border-border bg-bg-main px-3 py-2 text-xs">
                {complete ? <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" aria-hidden="true" /> : <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-border text-[10px]">{index + 1}</span>}
                <span className={complete ? 'font-medium text-text-main' : 'text-text-muted'}>{step}</span>
                {index < 3 ? <ArrowRight className="ml-auto hidden h-3 w-3 text-text-muted sm:block" aria-hidden="true" /> : null}
              </div>
            );
          })}
        </div>

        <div>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="text-sm font-semibold text-text-main">Desired Pack closure</h3>
            <p className="mt-1 text-xs text-text-muted">Candidates merge the Profile document provider Pack ids with the canonical Pack control catalog. Only installed, approved, enabled, revision-bound entries are selectable; required entries stay selected.</p>
            </div>
            <Badge variant="outline">{selectedPackIds.length} selected</Badge>
          </div>
          {packsLoading && packs.length === 0 ? (
            <div className="mt-3 h-24 animate-pulse rounded-lg border border-border bg-bg-main" role="status">Loading approved Packs…</div>
          ) : packs.length === 0 ? (
            <p className="mt-3 rounded-lg border border-dashed border-border px-4 py-4 text-sm text-text-muted">No Pack control catalog entries are available.</p>
          ) : (
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {packs.map((pack) => {
                const eligible = selectablePackIds.has(pack.id) && packCatalogBound;
                const checked = selectedPackIds.includes(pack.id);
                const inSnapshot = profileBoundPacks.some((candidate) => candidate.id === pack.id);
                const reason = !inSnapshot
                  ? 'Profile revision or Plan digest is stale'
                  : !pack.installed
                    ? 'Install required'
                    : !pack.approved
                      ? 'Kernel Pack approval required'
                      : !pack.enabled
                        ? 'Enable the Pack before adding it to the closure'
                        : !packCatalogBound
                          ? 'Pack catalog is not bound to the accepted snapshot'
                          : null;
                return (
                  <button
                    key={pack.id}
                    type="button"
                    className="flex min-h-11 items-center gap-3 rounded-lg border border-border bg-bg-main px-3 py-2 text-left transition-colors hover:bg-bg-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring-color)] disabled:pointer-events-none disabled:opacity-60"
                    aria-pressed={checked}
                    disabled={!eligible || pack.required || ceremonyIsBusy}
                    onClick={() => selectPack(pack)}
                  >
                    <span className={checked ? 'flex h-5 w-5 shrink-0 items-center justify-center rounded border border-accent bg-accent text-accent-fg' : 'h-5 w-5 shrink-0 rounded border border-border'} aria-hidden="true">
                      {checked ? <CheckCircle2 className="h-4 w-4" /> : null}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium text-text-main">{pack.name}</span>
                      <span className="block truncate text-xs text-text-muted">{pack.id} · {pack.enabled ? 'enabled' : 'disabled'} · {pack.approved ? 'approved' : 'not approved'} · {pack.installed ? 'installed' : 'not installed'}</span>
                    </span>
                    {pack.required ? <Badge variant="secondary">Required</Badge> : null}
                    {!pack.required && reason ? <span className="max-w-40 text-right text-[11px] text-text-muted">{reason}</span> : null}
                  </button>
                );
              })}
            </div>
          )}
          {missingClosureIds.length > 0 ? (
            <p className="mt-3 text-sm text-amber-700 dark:text-amber-300" role="alert">Active closure entries missing from the canonical Pack catalog: {missingClosureIds.join(', ')}. Refresh before changing the Profile.</p>
          ) : null}
          {surface.data && !packCatalogBound && packs.length > 0 ? (
            <p className="mt-3 text-sm text-amber-700 dark:text-amber-300" role="alert">Pack lifecycle rows are not bound to the accepted Profile revision and Plan digest, or the control catalog revision is inconsistent. Candidate actions are locked until both views refresh.</p>
          ) : null}
          {surface.data && !profilePackIdsAvailable ? (
            <p className="mt-3 text-sm text-amber-700 dark:text-amber-300" role="alert">The canonical Profile document did not publish a valid provider Pack set. Candidate selection is locked.</p>
          ) : null}
        </div>

        {failure ? (
          <div className="flex items-start gap-3 rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm" role="alert">
            <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden="true" />
            <div><p className="font-medium text-text-main">Profile ceremony stopped fail-closed</p><p className="mt-1 text-text-muted">{failure.code}: {failure.message}</p></div>
          </div>
        ) : null}

        {candidate ? (
          <div className="rounded-lg border border-border bg-bg-main p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-sm font-semibold text-text-main">Exact candidate review</h3>
              <Badge variant={ceremonyState === 'active' ? 'success' : 'warning'}>{candidate.expires_in}s TTL</Badge>
            </div>
            <dl className="mt-3 grid gap-3 sm:grid-cols-2">
              <div><dt className="text-xs text-text-muted">Candidate digest</dt><dd className="mt-1 break-all font-mono text-xs text-text-main">{candidate.candidate_digest}</dd></div>
              <div><dt className="text-xs text-text-muted">ProfileLock digest</dt><dd className="mt-1 break-all font-mono text-xs text-text-main">{recordDigest(candidate.review.profile_lock, ['lock_digest'])}</dd></div>
              <div><dt className="text-xs text-text-muted">ResolvedPlan digest</dt><dd className="mt-1 break-all font-mono text-xs text-text-main">{recordDigest(candidate.review.resolved_plan, ['plan_digest'])}</dd></div>
              <div><dt className="text-xs text-text-muted">Predecessor Plan digest</dt><dd className="mt-1 break-all font-mono text-xs text-text-main">{recordDigest(candidate.review.predecessor, ['plan_digest'])}</dd></div>
            </dl>
            <p className="mt-3 text-xs text-text-muted">Write set: {candidate.write_set.length}. Review shows canonical records and digests; no local diff is treated as authority.</p>
          </div>
        ) : null}

        {approval ? (
          <div className="rounded-lg border border-emerald-300/60 bg-emerald-50/60 p-4 dark:border-emerald-800/60 dark:bg-emerald-950/20">
            <div className="flex items-center gap-2 text-sm font-semibold text-text-main"><ShieldCheck className="h-4 w-4 text-emerald-600" aria-hidden="true" />Authority Kernel approval recorded</div>
            <p className="mt-2 break-all font-mono text-xs text-text-muted">{approval.authority_approval.approval_id} · {approval.authority_approval.approval_digest}</p>
            <p className="mt-1 text-xs text-text-muted">Decision: {approval.authority_approval.decision}; security epoch {approval.authority_approval.security_epoch}; TTL {approval.expires_in}s.</p>
          </div>
        ) : null}

        {snapshotChanged ? <p className="text-sm text-amber-700 dark:text-amber-300" role="alert">The accepted Profile snapshot changed. Refresh and resolve a new candidate.</p> : null}
        <Button
          type="button"
          className="min-h-11 self-start"
          onClick={() => void action()}
          loading={ceremonyIsBusy}
          disabled={!isRuntimeReady || snapshotChanged || selectedPackIds.length === 0 || ceremonyState === 'active'}
        >
          {actionLabel}
        </Button>
      </CardContent>
    </Card>
  );
}
