import type {
  ApiPackVMConsent,
  ApiPackVMCleanupResult,
  ApiPackVMDoctor,
  ApiPackVMOperation,
  ApiPackVMOperationState,
  ApiPackVMProvisioningPlan,
} from './apiTypes';

export const PACKVM_OPERATION_STORAGE_KEY = 'tobkiri-launcher-packvm-operation';

const SAFE_IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const SHA256_DIGEST = /^sha256:[0-9a-f]{64}$/i;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const OPERATION_STATES: readonly ApiPackVMOperationState[] = [
  'queued',
  'running',
  'succeeded',
  'failed',
  'cancelled',
  'interrupted',
];

export class PackVMLifecycleProtocolError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'PackVMLifecycleProtocolError';
  }
}

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new PackVMLifecycleProtocolError('Tobkiri returned an invalid PackVM lifecycle response.');
  }
  return value as Record<string, unknown>;
}

function stringField(
  value: Record<string, unknown>,
  key: string,
  options: {allowEmpty?: boolean; identifier?: boolean; digest?: boolean} = {},
): string {
  const field = value[key];
  if (typeof field !== 'string') {
    throw new PackVMLifecycleProtocolError(`Tobkiri returned an invalid PackVM ${key}.`);
  }
  if (!options.allowEmpty && field.length === 0) {
    throw new PackVMLifecycleProtocolError(`Tobkiri returned an empty PackVM ${key}.`);
  }
  if (options.identifier && !SAFE_IDENTIFIER.test(field)) {
    throw new PackVMLifecycleProtocolError(`Tobkiri returned an invalid PackVM ${key}.`);
  }
  if (options.digest && !SHA256_DIGEST.test(field)) {
    throw new PackVMLifecycleProtocolError(`Tobkiri returned an invalid PackVM ${key} digest.`);
  }
  return field;
}

function nullableStringField(value: Record<string, unknown>, key: string): string | null {
  const field = value[key];
  if (field !== null && typeof field !== 'string') {
    throw new PackVMLifecycleProtocolError(`Tobkiri returned an invalid PackVM ${key}.`);
  }
  return field as string | null;
}

function booleanField(value: Record<string, unknown>, key: string): boolean {
  if (typeof value[key] !== 'boolean') {
    throw new PackVMLifecycleProtocolError(`Tobkiri returned an invalid PackVM ${key}.`);
  }
  return value[key] as boolean;
}

function positiveIntegerField(value: Record<string, unknown>, key: string): number {
  const field = value[key];
  if (typeof field !== 'number' || !Number.isSafeInteger(field) || field <= 0) {
    throw new PackVMLifecycleProtocolError(`Tobkiri returned an invalid PackVM ${key}.`);
  }
  return field;
}

function safeHttpsUrl(value: Record<string, unknown>, key: string): string {
  const source = stringField(value, key);
  let parsed: URL;
  try {
    parsed = new URL(source);
  } catch {
    throw new PackVMLifecycleProtocolError(`Tobkiri returned an invalid PackVM ${key}.`);
  }
  if (parsed.protocol !== 'https:' || parsed.username || parsed.password) {
    throw new PackVMLifecycleProtocolError(`Tobkiri returned an unsafe PackVM ${key}.`);
  }
  return parsed.toString();
}

function optionalDigest(value: Record<string, unknown>, key: string): string | null {
  const field = value[key];
  if (field === null || field === undefined) return null;
  if (typeof field !== 'string' || !SHA256_DIGEST.test(field)) {
    throw new PackVMLifecycleProtocolError(`Tobkiri returned an invalid PackVM ${key} digest.`);
  }
  return field;
}

export function isCanonicalPackVMOperationId(value: string): boolean {
  return UUID.test(value);
}

export function normalizePackVMPlan(value: unknown): ApiPackVMProvisioningPlan {
  const payload = record(value);
  const imageDownloadRequired = booleanField(payload, 'image_download_required');
  return {
    backend_id: stringField(payload, 'backend_id', {identifier: true}),
    instance: stringField(payload, 'instance', {identifier: true}),
    launcher_reason: nullableStringField(payload, 'launcher_reason'),
    architecture: stringField(payload, 'architecture', {identifier: true}),
    image_source: safeHttpsUrl(payload, 'image_source'),
    image_digest: stringField(payload, 'image_digest', {digest: true}),
    image_size_bytes: positiveIntegerField(payload, 'image_size_bytes'),
    image_download_required: imageDownloadRequired,
    config_digest: stringField(payload, 'config_digest', {digest: true}),
    guest_runner_digest: stringField(payload, 'guest_runner_digest', {digest: true}),
    host_build_digest: stringField(payload, 'host_build_digest', {digest: true}),
    ceremony_nonce: stringField(payload, 'ceremony_nonce'),
    plan_digest: stringField(payload, 'plan_digest', {digest: true}),
    confirmation: stringField(payload, 'confirmation'),
  };
}

export function normalizePackVMConsent(value: unknown): ApiPackVMConsent {
  const payload = record(value);
  return {
    consent_id: stringField(payload, 'consent_id'),
    plan_digest: stringField(payload, 'plan_digest', {digest: true}),
    image_source: safeHttpsUrl(payload, 'image_source'),
    image_digest: stringField(payload, 'image_digest', {digest: true}),
    image_size_bytes: positiveIntegerField(payload, 'image_size_bytes'),
    image_download_approved: booleanField(payload, 'image_download_approved'),
  };
}

export function normalizePackVMDoctor(value: unknown): ApiPackVMDoctor {
  const payload = record(value);
  const ready = booleanField(payload, 'ready');
  const attestationDigest = optionalDigest(payload, 'attestation_digest');
  if (ready && !attestationDigest) {
    throw new PackVMLifecycleProtocolError(
      'Tobkiri reported PackVM readiness without an attestation digest.',
    );
  }
  return {
    ready,
    backend_id: stringField(payload, 'backend_id', {identifier: true}),
    platform: stringField(payload, 'platform', {identifier: true}),
    instance: stringField(payload, 'instance', {identifier: true}),
    reason: nullableStringField(payload, 'reason'),
    attestation_digest: attestationDigest,
  };
}

export function normalizePackVMOperation(value: unknown): ApiPackVMOperation {
  const payload = record(value);
  const operationId = stringField(payload, 'operation_id');
  const state = stringField(payload, 'state') as ApiPackVMOperationState;
  if (!isCanonicalPackVMOperationId(operationId) || !OPERATION_STATES.includes(state)) {
    throw new PackVMLifecycleProtocolError('Tobkiri returned an invalid PackVM operation state.');
  }
  const doctor = payload.doctor === undefined
    ? undefined
    : normalizePackVMDoctor(payload.doctor);
  if (state === 'succeeded' && !doctor) {
    throw new PackVMLifecycleProtocolError(
      'Tobkiri reported PackVM provisioning success without doctor evidence.',
    );
  }
  const error = payload.error === undefined ? undefined : stringField(payload, 'error');
  if (state === 'failed' && !error) {
    throw new PackVMLifecycleProtocolError(
      'Tobkiri reported PackVM provisioning failure without an error.',
    );
  }
  const consentDigest = payload.consent_digest === undefined
    ? undefined
    : stringField(payload, 'consent_digest', {digest: true});
  const errorType = payload.error_type === undefined
    ? undefined
    : stringField(payload, 'error_type', {identifier: true});
  return {
    operation_id: operationId,
    ...(consentDigest ? {consent_digest: consentDigest} : {}),
    state,
    plan_digest: stringField(payload, 'plan_digest', {digest: true}),
    updated_unix: positiveIntegerField(payload, 'updated_unix'),
    ...(doctor ? {doctor} : {}),
    ...(error ? {error} : {}),
    ...(errorType ? {error_type: errorType} : {}),
  };
}

export function normalizePackVMCleanup(value: unknown): ApiPackVMCleanupResult {
  const payload = record(value);
  if (booleanField(payload, 'ready')) {
    throw new PackVMLifecycleProtocolError('Tobkiri did not confirm PackVM cleanup.');
  }
  return {
    ready: false,
    instance: stringField(payload, 'instance', {identifier: true}),
    cleanup_confirmation: stringField(payload, 'cleanup_confirmation'),
  };
}

export function operationIsPolling(state: ApiPackVMOperationState): boolean {
  return state === 'queued' || state === 'running';
}

export function operationStatusLabel(state: ApiPackVMOperationState): string {
  switch (state) {
    case 'queued': return 'Queued';
    case 'running': return 'Provisioning';
    case 'succeeded': return 'Provisioned';
    case 'failed': return 'Failed';
    case 'cancelled': return 'Cancelled';
    case 'interrupted': return 'Interrupted — restart detected';
  }
}

export function formatPackVMBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KiB', 'MiB', 'GiB', 'TiB'];
  let value = bytes;
  let unit = 'B';
  for (const nextUnit of units) {
    value /= 1024;
    unit = nextUnit;
    if (value < 1024 || nextUnit === units[units.length - 1]) break;
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${unit}`;
}

export function cleanupConfirmationForInstance(instance: string): string {
  return `DELETE ${instance}`;
}

export function readPackVMOperationId(): string | null {
  try {
    const value = sessionStorage.getItem(PACKVM_OPERATION_STORAGE_KEY);
    return value && isCanonicalPackVMOperationId(value) ? value : null;
  } catch {
    return null;
  }
}

export function writePackVMOperationId(operationId: string): void {
  try {
    sessionStorage.setItem(PACKVM_OPERATION_STORAGE_KEY, operationId);
  } catch {
    // A storage failure must not change the server-owned lifecycle state.
  }
}

export function clearPackVMOperationId(): void {
  try {
    sessionStorage.removeItem(PACKVM_OPERATION_STORAGE_KEY);
  } catch {
    // Ignore unavailable browser storage.
  }
}

export function userSafePackVMError(error: unknown): string {
  const message = error instanceof Error
    ? error.message
    : typeof error === 'string'
      ? error
      : 'PackVM lifecycle request failed.';
  return message
    .replace(/(?:[A-Za-z]:[\\/]|\/)(?:[^\s"']+[\\/])+[^\s"']*/g, '[local path omitted]')
    .slice(0, 500);
}
