import {Button} from '@/src/components/ui/Button';
import type {DefaultsSetupState} from '@/src/lib/defaultsSetup';

type Props = {
  readonly setup: DefaultsSetupState | null;
  readonly reviewed: boolean;
  readonly activating: boolean;
  readonly error: string | null;
  readonly onReviewedChange: (reviewed: boolean) => void;
  readonly onActivate: () => void;
};

export function DefaultsReview({
  setup,
  reviewed,
  activating,
  error,
  onReviewedChange,
  onActivate,
}: Props) {
  return <section className="rounded-[18px] border border-border bg-bg-card p-7 shadow-lg">
    <p className="text-xs font-medium uppercase tracking-wider text-text-muted">Defaults v4 bootstrap</p>
    <h1 className="mt-3 text-2xl font-semibold text-text-main">Activate Defaults Profile</h1>
    <p className="mt-2 text-sm leading-6 text-text-muted">Review the finite local composition. Activation occurs only after this exact confirmation.</p>
    {!setup && !error && <p role="status" className="mt-6 text-sm text-text-muted">Loading verified catalog…</p>}
    {setup && <div className="mt-6 space-y-3 text-sm">
      <Identity label="Base" value={setup.recommended_default_profile.base_pack} />
      <Identity label="Shell" value={setup.recommended_default_profile.shell.provider_id} />
      <Identity label="Conversation provider" value={setup.recommended_default_profile.conversation_provider} />
      <div className="rounded-lg border border-border bg-bg-main p-4">
        <p className="text-xs font-medium text-text-muted">Selected Packs</p>
        <ul className="mt-2 space-y-1 text-text-main">{setup.recommended_default_profile.packs.map((pack) => <li key={pack.pack_id}>{pack.display_name} <span className="text-xs text-text-muted">({pack.pack_id})</span></li>)}</ul>
      </div>
      <label className="flex items-start gap-3 rounded-lg border border-border p-4 text-text-main">
        <input type="checkbox" checked={reviewed} onChange={(event) => onReviewedChange(event.target.checked)} className="mt-1" />
        <span>I confirm this exact catalog/profile revision, provider operations, Authority snapshot, and SecurityEpoch.</span>
      </label>
      <Button size="lg" className="w-full" disabled={!reviewed || activating} loading={activating} onClick={onActivate}>Activate Defaults Profile</Button>
    </div>}
    {error && <p role="alert" className="mt-4 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-500">{error}</p>}
  </section>;
}

function Identity({label, value}: {readonly label: string; readonly value: string}) {
  return <div className="flex items-center justify-between gap-4 rounded-lg border border-border bg-bg-main p-4">
    <span className="text-text-muted">{label}</span><code className="break-all text-right text-xs text-text-main">{value}</code>
  </div>;
}
