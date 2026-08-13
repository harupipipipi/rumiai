import {Button} from '@/src/components/ui/Button';
import type {DefaultsSetupState} from '@/src/lib/defaultsSetup';

type Props = {
  readonly setup: DefaultsSetupState | null;
  readonly reviewed: boolean;
  readonly activating: boolean;
  readonly activationCommitted?: boolean;
  readonly error: string | null;
  readonly reconfirmationRequired?: boolean;
  readonly onRecover?: () => void;
  readonly onReviewedChange: (reviewed: boolean) => void;
  readonly onActivate: () => void;
};

export function DefaultsReview({
  setup,
  reviewed,
  activating,
  activationCommitted = false,
  error,
  reconfirmationRequired = false,
  onRecover = () => undefined,
  onReviewedChange,
  onActivate,
}: Props) {
  const profile = setup?.recommended_default_profile;
  const packCount = profile?.packs.length ?? 0;

  return <section className="rounded-[18px] border border-border bg-bg-card p-5 shadow-lg sm:p-7" aria-labelledby="defaults-review-title">
    <header className="flex flex-col gap-4 border-b border-border pb-5 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        <p className="text-xs font-medium uppercase tracking-wider text-text-muted">Defaults v4 bootstrap</p>
        <h1 id="defaults-review-title" className="mt-3 text-2xl font-semibold tracking-tight text-text-main">
          {reconfirmationRequired ? 'Profile reconfirmation required' : 'Activate Defaults Profile'}
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-text-muted">
          {reconfirmationRequired
            ? 'The Host has withheld the verified dispatch map. Review the exact Defaults v4 transaction below to restore local operations.'
            : 'Review the verified local composition before enabling it. Activation occurs only after this exact confirmation.'}
        </p>
      </div>
      {profile && <div className="rounded-lg border border-accent/30 bg-accent/5 px-3 py-2 text-sm sm:shrink-0">
        <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Profile</p>
        <p className="mt-0.5 font-medium text-text-main">{profile.name}</p>
      </div>}
    </header>

    {activationCommitted && setup?.state !== 'active' && <div role="alert" className="mt-6 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-text-main">
      <p className="font-medium">Activation was submitted; verification is required.</p>
      <p className="mt-2 leading-6 text-text-muted">Tobkiri will re-read the Host-owned Setup state. The previous confirmation will not be submitted again.</p>
      <div className="mt-4"><Button variant="outline" onClick={onRecover} loading={activating}>Verify activation</Button></div>
    </div>}

    {!setup && !error && <div role="status" className="mt-6 rounded-xl border border-border bg-bg-main p-4 text-sm text-text-muted">
      Loading verified catalog…
    </div>}

    {profile && <div className="mt-6 space-y-6">
      <dl className="grid gap-3" aria-label="Defaults Profile composition">
        <Identity label="Base" value={profile.base_pack} />
        <Identity label="Shell" value={profile.shell.provider_id} />
        <Identity label="Conversation provider" value={profile.conversation_provider} />
      </dl>

      <section className="rounded-xl border border-border bg-bg-main p-4" aria-labelledby="selected-packs-title">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="selected-packs-title" className="text-sm font-medium text-text-main">Selected Packs</h2>
          <span className="rounded-full border border-border bg-bg-card px-2 py-0.5 text-xs tabular-nums text-text-muted" aria-label={`${packCount} selected packs`}>
            {packCount} {packCount === 1 ? 'pack' : 'packs'}
          </span>
        </div>
        <ul className="mt-3 grid gap-2 sm:grid-cols-2">
          {profile.packs.map((pack) => <li key={pack.pack_id} className="min-w-0 rounded-lg border border-border bg-bg-card px-3 py-2.5">
            <p className="truncate text-sm font-medium text-text-main" title={pack.display_name}>{pack.display_name}</p>
            <code className="mt-1 block truncate text-xs text-text-muted" title={pack.pack_id}>{pack.pack_id}</code>
          </li>)}
        </ul>
      </section>

      <section className="rounded-xl border border-border bg-bg-main p-4" aria-labelledby="activation-ceremony-title">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="activation-ceremony-title" className="text-sm font-medium text-text-main">Host activation ceremony</h2>
          <span className="text-xs text-text-muted">{setup.required_transaction.length} verified steps</span>
        </div>
        <ol aria-label="Defaults v4 activation ceremony" className="mt-3 grid gap-2 sm:grid-cols-2">
          {setup.required_transaction.map((step, index) => <li key={step} className="flex min-w-0 items-center gap-2 rounded-lg bg-bg-card px-3 py-2 text-sm text-text-main">
            <span aria-hidden="true" className="flex size-5 shrink-0 items-center justify-center rounded-full border border-border text-xs tabular-nums text-text-muted">{index + 1}</span>
            <code className="truncate text-xs sm:text-sm">{step}</code>
          </li>)}
        </ol>
        <p className="mt-3 text-xs leading-5 text-text-muted">
          Resolve, review, approve, activate, and capture are performed by the Host-owned transaction. This screen only submits the exact confirmation it issued.
        </p>
      </section>

      <div className="rounded-xl border border-border bg-bg-main p-1">
        <label className="flex cursor-pointer items-start gap-3 rounded-lg p-3 text-text-main transition-colors hover:bg-bg-hover has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-[var(--ring-color)] has-[:focus-visible]:ring-offset-2 has-[:focus-visible]:ring-offset-[var(--bg-main)]">
          <input
            type="checkbox"
            checked={reviewed}
            onChange={(event) => onReviewedChange(event.target.checked)}
            className="mt-0.5 size-4 shrink-0 accent-[var(--accent)]"
            aria-describedby="defaults-review-confirmation"
          />
          <span className="min-w-0">
            <span className="block text-sm font-medium">I have reviewed this exact Profile activation.</span>
            <span id="defaults-review-confirmation" className="mt-1 block text-xs leading-5 text-text-muted">
              This confirms the catalog and Profile revisions, provider operations, Authority snapshot, and SecurityEpoch shown by the Host.
            </span>
          </span>
        </label>
      </div>

      <div>
        <Button size="lg" className="w-full" disabled={!reviewed || activating || activationCommitted} loading={activating} onClick={onActivate} aria-describedby="defaults-activation-note">
          Activate Defaults Profile
        </Button>
        <p id="defaults-activation-note" className="mt-2 text-center text-xs leading-5 text-text-muted">
          Activation sends only the exact Host-issued confirmation above.
        </p>
      </div>
    </div>}

    {error && <p role="alert" className="mt-6 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm leading-6 text-red-500">{error}</p>}
  </section>;
}

function Identity({label, value}: {readonly label: string; readonly value: string}) {
  return <div className="grid gap-2 rounded-xl border border-border bg-bg-main p-4 sm:grid-cols-[minmax(10rem,0.8fr)_minmax(0,1.2fr)] sm:items-center sm:gap-4">
    <dt className="text-sm text-text-muted">{label}</dt>
    <dd><code className="block break-all text-left text-xs text-text-main sm:text-right">{value}</code></dd>
  </div>;
}
