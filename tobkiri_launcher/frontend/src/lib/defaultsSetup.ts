import {apiFetch} from './api';

export type DefaultsBinding = {
  readonly pack_id: string;
  readonly contract_id: string;
  readonly operation_id: string;
  readonly function_principal: {
    readonly function_id: string;
  };
};

export type DefaultsConfirmation = {
  readonly confirmation_api_version: 'io.tobkiri.defaults-confirmation.v1';
  readonly operation_id: 'defaults.activate';
  readonly profile_id: 'defaults';
  readonly catalog_revision: string;
  readonly profile_revision: string;
  readonly plan_digest: string;
  readonly authority_snapshot_digest: string;
  readonly security_epoch: number;
  readonly base: {
    readonly pack_id: 'defaults-basepack';
    readonly artifact_digest: string;
    readonly definition_digest: string;
  };
  readonly shell: {
    readonly provider_id: 'shell.tauri.default';
    readonly pack_id: string;
    readonly artifact_digest: string;
    readonly executable_artifact_digest: string;
    readonly contract_id: 'app.shell.v1';
    readonly definition_digest: string;
  };
  readonly bindings: readonly DefaultsBinding[];
  readonly confirmation_digest: string;
};

export type DefaultsSetupState = {
  readonly setup_api_version: 'io.tobkiri.setup-state.v4';
  readonly state: 'review_required' | 'active';
  readonly recommended_default_profile: {
    readonly profile_id: 'defaults';
    readonly name: string;
    readonly base_pack: 'defaults-basepack';
    readonly shell: {
      readonly provider_id: 'shell.tauri.default';
      readonly contract_id: 'app.shell.v1';
    };
    readonly pack_ids: readonly string[];
    readonly packs: readonly {readonly pack_id: string; readonly display_name: string}[];
    readonly conversation_provider: string;
    readonly confirmation: DefaultsConfirmation;
  };
};

export type DefaultsActivation = {
  readonly setup_api_version: 'io.tobkiri.setup-state.v4';
  readonly state: 'active';
  readonly profile_id: 'defaults';
  readonly profile_revision: string;
  readonly plan_digest: string;
  readonly activation_id: string;
  readonly security_epoch: number;
  readonly fencing_token: number;
  readonly authority_snapshot_digest: string;
  readonly audit_receipt: {
    readonly reservation_id: string;
    readonly state: 'committed';
    readonly activation_id: string;
    readonly fencing_token: number;
  };
  readonly restart_required: false;
};

function object(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${label} is not a JSON object`);
  }
  return value as Record<string, unknown>;
}

function exactString(value: unknown, expected: string, label: string): void {
  if (value !== expected) throw new Error(`${label} is unsupported`);
}

function exactKeys(value: Record<string, unknown>, keys: readonly string[], label: string): void {
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    throw new Error(`${label} has unknown or missing fields`);
  }
}

function digest(value: unknown, label: string): void {
  if (typeof value !== 'string' || !/^sha256:[0-9a-f]{64}$/.test(value)) {
    throw new Error(`${label} is invalid`);
  }
}

export function parseDefaultsSetupState(value: unknown): DefaultsSetupState {
  const state = object(value, 'Defaults setup response');
  exactKeys(state, [
    'setup_api_version', 'state', 'packs', 'recommended_default_profile',
    'required_transaction',
  ], 'Defaults setup response');
  exactString(state.setup_api_version, 'io.tobkiri.setup-state.v4', 'Defaults setup API');
  if (state.state !== 'review_required' && state.state !== 'active') {
    throw new Error('Defaults setup state is invalid');
  }
  const profile = object(state.recommended_default_profile, 'Defaults Profile');
  exactKeys(profile, [
    'available', 'profile_id', 'name', 'base_pack', 'shell', 'pack_ids',
    'packs', 'conversation_provider', 'confirmation',
  ], 'Defaults Profile');
  exactString(profile.profile_id, 'defaults', 'Defaults Profile identity');
  exactString(profile.base_pack, 'defaults-basepack', 'Defaults base identity');
  const shell = object(profile.shell, 'Defaults Shell');
  exactString(shell.provider_id, 'shell.tauri.default', 'Defaults Shell provider');
  exactString(shell.contract_id, 'app.shell.v1', 'Defaults Shell contract');
  const confirmation = object(profile.confirmation, 'Defaults confirmation');
  exactKeys(confirmation, [
    'confirmation_api_version', 'operation_id', 'profile_id', 'catalog_revision',
    'profile_revision', 'plan_digest', 'authority_snapshot_digest',
    'security_epoch', 'base', 'shell', 'bindings', 'confirmation_digest',
  ], 'Defaults confirmation');
  exactString(
    confirmation.confirmation_api_version,
    'io.tobkiri.defaults-confirmation.v1',
    'Defaults confirmation API',
  );
  exactString(confirmation.operation_id, 'defaults.activate', 'Defaults operation');
  exactString(confirmation.profile_id, 'defaults', 'Confirmed Profile');
  for (const field of [
    'catalog_revision', 'profile_revision', 'plan_digest',
    'authority_snapshot_digest', 'confirmation_digest',
  ]) digest(confirmation[field], `Defaults ${field}`);
  if (!Number.isSafeInteger(confirmation.security_epoch) || Number(confirmation.security_epoch) < 1) {
    throw new Error('Defaults SecurityEpoch is invalid');
  }
  const base = object(confirmation.base, 'Confirmed base');
  exactKeys(base, ['pack_id', 'artifact_digest', 'definition_digest'], 'Confirmed base');
  exactString(base.pack_id, 'defaults-basepack', 'Confirmed base identity');
  digest(base.artifact_digest, 'Confirmed base artifact digest');
  digest(base.definition_digest, 'Confirmed base definition digest');
  const confirmedShell = object(confirmation.shell, 'Confirmed Shell');
  exactKeys(confirmedShell, [
    'provider_id', 'pack_id', 'artifact_digest', 'executable_artifact_digest',
    'contract_id', 'definition_digest',
  ], 'Confirmed Shell');
  exactString(confirmedShell.provider_id, 'shell.tauri.default', 'Confirmed Shell provider');
  exactString(confirmedShell.pack_id, 'shell.tauri.default', 'Confirmed Shell identity');
  exactString(confirmedShell.contract_id, 'app.shell.v1', 'Confirmed Shell contract');
  digest(confirmedShell.artifact_digest, 'Confirmed Shell artifact digest');
  digest(
    confirmedShell.executable_artifact_digest,
    'Confirmed Shell executable artifact digest',
  );
  digest(confirmedShell.definition_digest, 'Confirmed Shell definition digest');
  const bindings = confirmation.bindings;
  if (!Array.isArray(bindings)) throw new Error('Defaults bindings are invalid');
  const conversation = bindings.filter((item) => {
    const binding = object(item, 'Defaults binding');
    exactKeys(binding, [
      'pack_id', 'artifact_digest', 'function_principal', 'contract_id',
      'operation_id', 'domain_kind',
    ], 'Defaults binding');
    const principal = object(binding.function_principal, 'Defaults function principal');
    exactKeys(principal, [
      'parent_artifact_digest', 'function_implementation_digest', 'function_id',
      'contract_revision_digest', 'operation_id',
    ], 'Defaults function principal');
    return binding.contract_id === 'conversation.turn.v1' && binding.operation_id === 'complete';
  });
  if (conversation.length !== 1) {
    throw new Error('Defaults Profile must contain exactly one conversation provider');
  }
  if (!Array.isArray(profile.pack_ids) || !Array.isArray(profile.packs)) {
    throw new Error('Defaults Profile selection is invalid');
  }
  return value as DefaultsSetupState;
}

export async function fetchDefaultsSetupState(): Promise<DefaultsSetupState> {
  return parseDefaultsSetupState(await apiFetch<unknown>('/api/setup/packs'));
}

export async function activateDefaultsProfile(
  confirmation: DefaultsConfirmation,
): Promise<DefaultsActivation> {
  const value = object(await apiFetch<unknown>('/api/setup/packs/install', {
    method: 'POST',
    body: JSON.stringify({
      setup_api_version: 'io.tobkiri.setup-state.v4',
      operation_id: 'defaults.activate',
      confirmed: true,
      confirmation,
    }),
  }), 'Defaults activation response');
  exactKeys(value, [
    'setup_api_version', 'state', 'profile_id', 'profile_revision', 'plan_digest',
    'activation_id', 'security_epoch', 'fencing_token',
    'authority_snapshot_digest', 'audit_receipt', 'restart_required',
  ], 'Defaults activation response');
  exactString(value.setup_api_version, 'io.tobkiri.setup-state.v4', 'Defaults activation API');
  exactString(value.state, 'active', 'Defaults activation state');
  exactString(value.profile_id, 'defaults', 'Activated Profile');
  const audit = object(value.audit_receipt, 'Defaults activation audit');
  exactKeys(audit, [
    'reservation_id', 'state', 'activation_id', 'fencing_token',
  ], 'Defaults activation audit');
  exactString(audit.state, 'committed', 'Defaults activation audit state');
  if (audit.activation_id !== value.activation_id || audit.fencing_token !== value.fencing_token) {
    throw new Error('Defaults activation audit binding is invalid');
  }
  if (value.restart_required !== false) throw new Error('Unexpected Defaults restart contract');
  return value as DefaultsActivation;
}
