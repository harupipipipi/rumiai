import {apiFetch} from './api';

export type DefaultsBinding = {
  readonly pack_id: string;
  readonly artifact_digest: string;
  readonly contract_id: string;
  readonly operation_id: string;
  readonly domain_kind: string;
  readonly caller_function_id: string;
  readonly authority_reference: string;
  readonly requested_scope_digest: string;
  readonly adapter_digests: readonly string[];
  readonly function_principal: {
    readonly parent_artifact_digest: string;
    readonly function_implementation_digest: string;
    readonly function_id: string;
    readonly contract_revision_digest: string;
    readonly operation_id: string;
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
  readonly denial_diagnostic: string | null;
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
  readonly required_transaction: readonly string[];
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

function nonEmptyString(value: unknown, label: string): void {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new Error(`${label} is invalid`);
  }
}

function positiveSafeInteger(value: unknown, label: string): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 1) {
    throw new Error(`${label} is invalid`);
  }
  return value;
}

function activationId(value: unknown, label: string): string {
  nonEmptyString(value, label);
  if (!/^activation:[a-z0-9][a-z0-9._-]{7,127}$/.test(value as string)) {
    throw new Error(`${label} is invalid`);
  }
  return value as string;
}

function reservationId(value: unknown, label: string): string {
  nonEmptyString(value, label);
  if (!/^activation-reservation:[A-Za-z0-9_-]+$/.test(value as string)) {
    throw new Error(`${label} is invalid`);
  }
  return value as string;
}

const REQUIRED_TRANSACTION = [
  'catalog.verify',
  'profile.resolve',
  'authority.snapshot',
  'activation.prepare',
  'activation.commit',
  'runtime.capture',
] as const;

export function parseDefaultsSetupState(value: unknown): DefaultsSetupState {
  const state = object(value, 'Defaults setup response');
  exactKeys(state, [
    'setup_api_version', 'state', 'denial_diagnostic', 'packs',
    'recommended_default_profile', 'required_transaction',
  ], 'Defaults setup response');
  exactString(state.setup_api_version, 'io.tobkiri.setup-state.v4', 'Defaults setup API');
  if (state.state !== 'review_required' && state.state !== 'active') {
    throw new Error('Defaults setup state is invalid');
  }
  if (state.denial_diagnostic !== null && typeof state.denial_diagnostic !== 'string') {
    throw new Error('Defaults setup denial diagnostic is invalid');
  }
  if (
    !Array.isArray(state.required_transaction)
    || state.required_transaction.length !== REQUIRED_TRANSACTION.length
    || state.required_transaction.some((step, index) => step !== REQUIRED_TRANSACTION[index])
  ) {
    throw new Error('Defaults setup transaction is invalid');
  }
  const profile = object(state.recommended_default_profile, 'Defaults Profile');
  exactKeys(profile, [
    'available', 'profile_id', 'name', 'base_pack', 'shell', 'pack_ids',
    'packs', 'conversation_provider', 'confirmation',
  ], 'Defaults Profile');
  exactString(profile.profile_id, 'defaults', 'Defaults Profile identity');
  exactString(profile.base_pack, 'defaults-basepack', 'Defaults base identity');
  if (profile.available !== true) throw new Error('Defaults Profile is unavailable');
  nonEmptyString(profile.name, 'Defaults Profile name');
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
      'caller_function_id', 'pack_id', 'artifact_digest', 'function_principal',
      'contract_id', 'operation_id', 'domain_kind', 'authority_reference',
      'requested_scope_digest', 'adapter_digests',
    ], 'Defaults binding');
    for (const field of ['pack_id', 'contract_id', 'operation_id', 'domain_kind', 'caller_function_id']) {
      nonEmptyString(binding[field], `Defaults binding ${field}`);
    }
    digest(binding.artifact_digest, 'Defaults binding artifact digest');
    if (
      typeof binding.authority_reference !== 'string'
      || !/^authority-ref:[0-9a-f]{64}$/.test(binding.authority_reference)
    ) {
      throw new Error('Defaults binding authority reference is invalid');
    }
    digest(binding.requested_scope_digest, 'Defaults binding requested scope digest');
    if (!Array.isArray(binding.adapter_digests)
      || binding.adapter_digests.some((item) => !/^sha256:[0-9a-f]{64}$/.test(String(item)))) {
      throw new Error('Defaults binding adapter digests are invalid');
    }
    const principal = object(binding.function_principal, 'Defaults function principal');
    exactKeys(principal, [
      'parent_artifact_digest', 'function_implementation_digest', 'function_id',
      'contract_revision_digest', 'operation_id',
    ], 'Defaults function principal');
    digest(principal.parent_artifact_digest, 'Defaults function parent artifact digest');
    digest(principal.function_implementation_digest, 'Defaults function implementation digest');
    nonEmptyString(principal.function_id, 'Defaults function id');
    digest(principal.contract_revision_digest, 'Defaults contract revision digest');
    if (principal.parent_artifact_digest !== binding.artifact_digest) {
      throw new Error('Defaults function parent artifact binding is invalid');
    }
    if (principal.operation_id !== binding.operation_id) {
      throw new Error('Defaults function operation binding is invalid');
    }
    return binding.contract_id === 'conversation.turn.v1' && binding.operation_id === 'complete';
  });
  if (conversation.length !== 1) {
    throw new Error('Defaults Profile must contain exactly one conversation provider');
  }
  if (!Array.isArray(profile.pack_ids)
    || profile.pack_ids.some((packId) => typeof packId !== 'string' || !packId)
    || new Set(profile.pack_ids).size !== profile.pack_ids.length
    || !Array.isArray(profile.packs)
    || profile.packs.length !== profile.pack_ids.length) {
    throw new Error('Defaults Profile selection is invalid');
  }
  const packIds = new Set(profile.pack_ids);
  const conversationBinding = object(conversation[0], 'Defaults conversation binding');
  const conversationPrincipal = object(
    conversationBinding.function_principal,
    'Defaults conversation principal',
  );
  if (
    !packIds.has(conversationBinding.pack_id as string)
    || conversationBinding.caller_function_id !== shell.provider_id
    || conversationBinding.domain_kind !== 'pack_vm'
    || conversationPrincipal.function_id !== profile.conversation_provider
  ) {
    throw new Error('Defaults conversation binding does not match the Profile');
  }
  for (const [index, item] of profile.packs.entries()) {
    const pack = object(item, 'Defaults selected Pack');
    exactKeys(pack, ['pack_id', 'display_name'], 'Defaults selected Pack');
    nonEmptyString(pack.pack_id, 'Defaults selected Pack identity');
    nonEmptyString(pack.display_name, 'Defaults selected Pack name');
    if (pack.pack_id !== profile.pack_ids[index]) {
      throw new Error('Defaults selected Pack projection is out of order');
    }
    if (!packIds.has(pack.pack_id)) throw new Error('Defaults selected Pack is not in the Profile');
  }
  const topLevelPacks = state.packs;
  if (!Array.isArray(topLevelPacks) || topLevelPacks.length !== profile.pack_ids.length) {
    throw new Error('Defaults setup Pack projection is invalid');
  }
  for (const [index, item] of topLevelPacks.entries()) {
    const pack = object(item, 'Defaults setup Pack');
    exactKeys(pack, ['pack_id', 'display_name'], 'Defaults setup Pack');
    nonEmptyString(pack.pack_id, 'Defaults setup Pack identity');
    nonEmptyString(pack.display_name, 'Defaults setup Pack name');
    const selectedPack = object(profile.packs[index], 'Defaults selected Pack');
    if (
      pack.pack_id !== selectedPack.pack_id
      || pack.display_name !== selectedPack.display_name
    ) {
      throw new Error('Defaults setup Pack projection does not match the Profile');
    }
    if (!packIds.has(pack.pack_id)) throw new Error('Defaults setup Pack is not in the Profile');
  }
  return value as DefaultsSetupState;
}

export async function fetchDefaultsSetupState(): Promise<DefaultsSetupState> {
  return parseDefaultsSetupState(await apiFetch<unknown>('/api/setup/packs'));
}

export function parseDefaultsActivationResponse(
  value: unknown,
  confirmation: DefaultsConfirmation,
): DefaultsActivation {
  digest(confirmation.profile_revision, 'Submitted profile revision');
  digest(confirmation.plan_digest, 'Submitted plan digest');
  digest(confirmation.authority_snapshot_digest, 'Submitted authority snapshot digest');
  positiveSafeInteger(confirmation.security_epoch, 'Submitted SecurityEpoch');
  const response = object(value, 'Defaults activation response');
  const responseProfileRevision = response.profile_revision;
  const responsePlanDigest = response.plan_digest;
  const responseAuthoritySnapshot = response.authority_snapshot_digest;
  const responseSecurityEpoch = response.security_epoch;
  digest(responseProfileRevision, 'Activated profile revision');
  digest(responsePlanDigest, 'Activated plan digest');
  digest(responseAuthoritySnapshot, 'Activated authority snapshot digest');
  const activation = activationId(response.activation_id, 'Defaults activation identity');
  const securityEpoch = positiveSafeInteger(responseSecurityEpoch, 'Defaults SecurityEpoch');
  const fencingToken = positiveSafeInteger(response.fencing_token, 'Defaults fencing token');
  if (responseProfileRevision !== confirmation.profile_revision
    || responsePlanDigest !== confirmation.plan_digest
    || responseAuthoritySnapshot !== confirmation.authority_snapshot_digest
    || securityEpoch !== confirmation.security_epoch) {
    throw new Error('Defaults activation does not match the submitted confirmation');
  }
  exactKeys(response, [
    'setup_api_version', 'state', 'profile_id', 'profile_revision', 'plan_digest',
    'activation_id', 'security_epoch', 'fencing_token',
    'authority_snapshot_digest', 'audit_receipt', 'restart_required',
  ], 'Defaults activation response');
  exactString(response.setup_api_version, 'io.tobkiri.setup-state.v4', 'Defaults activation API');
  exactString(response.state, 'active', 'Defaults activation state');
  exactString(response.profile_id, 'defaults', 'Activated Profile');
  const audit = object(response.audit_receipt, 'Defaults activation audit');
  exactKeys(audit, [
    'reservation_id', 'state', 'activation_id', 'fencing_token',
  ], 'Defaults activation audit');
  exactString(audit.state, 'committed', 'Defaults activation audit state');
  const auditReservation = reservationId(
    audit.reservation_id,
    'Defaults activation reservation identity',
  );
  if (audit.activation_id !== activation || audit.fencing_token !== fencingToken) {
    throw new Error('Defaults activation audit binding is invalid');
  }
  if (response.restart_required !== false) throw new Error('Unexpected Defaults restart contract');
  return {
    setup_api_version: response.setup_api_version as 'io.tobkiri.setup-state.v4',
    state: response.state as 'active',
    profile_id: response.profile_id as 'defaults',
    profile_revision: responseProfileRevision as string,
    plan_digest: responsePlanDigest as string,
    activation_id: activation,
    security_epoch: securityEpoch,
    fencing_token: fencingToken,
    authority_snapshot_digest: responseAuthoritySnapshot as string,
    audit_receipt: {
      reservation_id: auditReservation,
      state: 'committed',
      activation_id: activation,
      fencing_token: fencingToken,
    },
    restart_required: false,
  };
}

export async function activateDefaultsProfile(
  confirmation: DefaultsConfirmation,
): Promise<DefaultsActivation> {
  return parseDefaultsActivationResponse(
    await apiFetch<unknown>('/api/setup/packs/install', {
      method: 'POST',
      body: JSON.stringify({
        setup_api_version: 'io.tobkiri.setup-state.v4',
        operation_id: 'defaults.activate',
        confirmed: true,
        confirmation,
      }),
    }),
    confirmation,
  );
}
