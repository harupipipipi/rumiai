import {
  ApiRequestTimeoutError,
  fetchFrontendContractOperation,
  invokeFrontendCapability,
  type FrontendContractMethod,
} from './api';
import {
  generatedTargetFor,
  VERIFIED_GENERATED_RUNTIME_TARGETS,
  type VerifiedGeneratedTarget,
} from './generatedFrontendContractMap';

/** Canonical Launcher projection envelope exposed by the generated v4 map. */
export const RUNTIME_SURFACE_API_VERSION =
  'io.tobkiri.launcher.runtime-surface.v4' as const;

export const CANONICAL_RUNTIME_SURFACES = [
  'profile',
  'settings',
  'packs',
  'contracts',
  'operations',
  'principals',
] as const;

export type RuntimeSurfaceId = typeof CANONICAL_RUNTIME_SURFACES[number];

export type RuntimeSurfaceState = 'ready' | 'stale' | 'blocked';

export interface RuntimeSurfaceRecordRef {
  digest: string;
  source_ref: string;
}

/** Digest/source evidence refs for the captured canonical records. */
export interface RuntimeSurfaceRecords {
  profile_lock: RuntimeSurfaceRecordRef;
  resolved_plan: RuntimeSurfaceRecordRef;
  activation_record: RuntimeSurfaceRecordRef;
  authority_snapshot: RuntimeSurfaceRecordRef;
}

export interface RuntimeProfileSettingsProjection {
  scope: 'runtime_profile';
  mutable_via_profile_activation: true;
  profile_id: string;
  profile_revision: string;
  catalog_revision: string;
  plan_digest: string;
  lock_digest: string;
  security_epoch: number;
}

export interface RuntimeSurfaceEnvelope<T> {
  runtime_surface_api_version: typeof RUNTIME_SURFACE_API_VERSION;
  surface: RuntimeSurfaceId;
  state: RuntimeSurfaceState;
  profile_id: string;
  profile_revision: string;
  catalog_revision: string;
  plan_digest: string;
  records: RuntimeSurfaceRecords;
  data: T;
}

export interface RuntimeSurfaceTarget {
  method: FrontendContractMethod;
  logical_target: string;
  contract_id: string;
  operation_id: string;
  contribution_id: string;
  provider_id: string;
  function_id: string;
  allowed_payload_keys: string[];
  map_artifact_digest: string;
  source_ref: string;
  read_guards?: boolean;
}

export interface RuntimePlanBinding {
  binding_id: string;
  source_principal_id: string;
  target_principal_id: string;
  target_contract_id: string;
  operation_id: string;
  owner_pack_id: string;
  edge_digest: string;
  authority_reference: string;
}

export interface RuntimeRequestedEdge {
  caller_function_id: string;
  target_provider_id: string;
  contract_id: string;
  operation_id: string;
  requested_scope_template: Record<string, unknown>;
  authority_reference?: string | null;
}

export interface RuntimeJsonSchema {
  type?: string;
  title?: string;
  description?: string;
  properties?: Record<string, RuntimeJsonSchema>;
  required?: string[];
  enum?: unknown[];
  items?: RuntimeJsonSchema;
  default?: unknown;
}

/** Exact operation metadata published by the v4 operation catalog. */
export interface RuntimeOperationDescriptor {
  operation_id: string;
  contract_id: string;
  owner_pack_id: string;
  contribution_id: string;
  target_provider_id: string;
  artifact_digest: string;
  invocation_contribution_id: string | null;
  invocation_owner_pack_id: string | null;
  invocation_catalog_hash: string | null;
  invocation_reason: string | null;
  invokable: boolean;
  catalog_digest: string;
  function_id: string;
  schema: Record<string, unknown>;
  label?: string;
  provider_id?: string;
  input_schema?: RuntimeJsonSchema;
  provider_semantics?: Record<string, unknown> | null;
  route?: Record<string, unknown>;
}

export interface RuntimePackDescriptor {
  pack_id: string;
  role: string;
  kind: string;
  version: string;
  display_name: string;
  artifact_digest: string;
  artifact_ref: string;
  installed: boolean;
  enabled: boolean;
  approved: boolean;
  required: boolean;
  invokable_operations: string[];
  reason?: string | null;
}

/** Exact route metadata published by the v4 contract map projection. */
export interface RuntimeRouteDescriptor {
  route_id: string;
  method: string;
  logical_target: string;
  contract_id: string;
  operation_id: string;
  provider_id: string;
  function_id: string;
  frontend_map_digest: string;
  contribution_id: string;
  presentation: string;
  owner_pack_id: string;
  manifest_digest: string;
  function_principal_id: string;
  allowed_payload_keys: string[];
  security: {
    transport: string;
    panel_authentication_required: boolean;
    broker_authority_required: boolean;
    csrf_required: boolean;
    request_id_required: boolean;
    replay_protection_required: boolean;
  };
}

export interface RuntimeFlowDescriptor {
  flow_id: string;
  label?: string;
  state: string;
  operation_ids: string[];
}

export interface RuntimeArtifactEntry {
  entry_id: string;
  owner_pack_id: string;
  path: string;
  kind: string;
  artifact_digest: string;
}

/**
 * These are the logical targets declared by the digest-pinned frontend map;
 * the physical request still goes through /api/contracts/defaultspack/.
 */
function generatedRuntimeTarget(
  method: FrontendContractMethod,
  logicalTarget: string,
  readGuards?: boolean,
): RuntimeSurfaceTarget {
  const target = generatedTargetFor(
    VERIFIED_GENERATED_RUNTIME_TARGETS,
    method,
    logicalTarget,
  );
  return {...target, ...(readGuards === undefined ? {} : {read_guards: readGuards})};
}

export const RUNTIME_SURFACE_TARGETS: Partial<Record<RuntimeSurfaceId, RuntimeSurfaceTarget>> = {
  profile: generatedRuntimeTarget('GET', '/api/runtime-surface/profile', true),
  settings: generatedRuntimeTarget('GET', '/api/runtime-surface/settings', false),
  packs: generatedRuntimeTarget('GET', '/api/runtime-surface/topology/packs', true),
  contracts: generatedRuntimeTarget('GET', '/api/runtime-surface/topology/contracts', true),
  operations: generatedRuntimeTarget('GET', '/api/runtime-surface/topology/operations', true),
  principals: generatedRuntimeTarget('GET', '/api/runtime-surface/topology/principals', true),
};

export const RUNTIME_PROFILE_CEREMONY_TARGETS = {
  resolve: generatedRuntimeTarget('POST', '/api/runtime-surface/profile-change/resolve'),
  review: generatedRuntimeTarget('POST', '/api/runtime-surface/profile-change/review'),
  approve: generatedRuntimeTarget('POST', '/api/runtime-surface/profile-change/approve'),
  activate: generatedRuntimeTarget('POST', '/api/runtime-surface/profile-change/activate'),
};

export interface RuntimeSurfaceTransport {
  read<T>(target: RuntimeSurfaceTarget, input: {
    expected_profile_revision?: string;
    expected_plan_digest?: string;
  }): Promise<T>;
}

const canonicalTransport: RuntimeSurfaceTransport = {
  read: <T>(target: RuntimeSurfaceTarget, input: {
    expected_profile_revision?: string;
    expected_plan_digest?: string;
  }) => (
    assertVerifiedRuntimeTarget(target),
    assertTargetPayload(target, input),
    fetchFrontendContractOperation<T>(target.method, target.logical_target, input)
  ),
};

export type RuntimeSurfaceErrorCode =
  | 'UNAVAILABLE'
  | 'PROFILE_NOT_ACTIVE'
  | 'TIMEOUT'
  | 'STALE'
  | 'DIGEST_MISMATCH'
  | 'APPROVAL_DENIED'
  | 'INVALID'
  | 'FAILED';

export class RuntimeSurfaceError extends Error {
  readonly code: RuntimeSurfaceErrorCode;

  constructor(code: RuntimeSurfaceErrorCode, message: string) {
    super(message);
    this.name = 'RuntimeSurfaceError';
    this.code = code;
  }
}

export function runtimeSurfaceErrorMessage(code: RuntimeSurfaceErrorCode): string {
  switch (code) {
    case 'UNAVAILABLE':
      return 'This surface is not exposed by the generated Protocol v4 map yet.';
    case 'TIMEOUT':
      return 'The Protocol v4 request timed out. No new data was accepted.';
    case 'PROFILE_NOT_ACTIVE':
      return 'The active Profile is unavailable. The UI remains fail-closed.';
    case 'STALE':
    case 'DIGEST_MISMATCH':
      return 'The Profile or plan digest changed. Read-only stale data is shown and actions are locked.';
    case 'APPROVAL_DENIED':
      return 'Host approval denied this operation. The UI remains fail-closed.';
    case 'INVALID':
      return 'The runtime surface returned an invalid canonical v4 projection.';
    case 'FAILED':
      return 'The runtime surface could not be loaded. Try again when the runtime is ready.';
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isSha256Digest(value: unknown): value is string {
  return typeof value === 'string' && /^sha256:[0-9a-f]{64}$/.test(value);
}

export function assertVerifiedRuntimeTarget(target: RuntimeSurfaceTarget): void {
  let expected: VerifiedGeneratedTarget;
  try {
    expected = generatedTargetFor(
      VERIFIED_GENERATED_RUNTIME_TARGETS,
      target.method,
      target.logical_target,
    );
  } catch {
    throw new RuntimeSurfaceError(
      'UNAVAILABLE',
      'The requested runtime surface target is not declared by the verified frontend Contract Map.',
    );
  }
  if (
    target.contract_id !== expected.contract_id
    || target.operation_id !== expected.operation_id
    || target.contribution_id !== expected.contribution_id
    || target.provider_id !== expected.provider_id
    || target.function_id !== expected.function_id
    || target.map_artifact_digest !== expected.map_artifact_digest
    || target.source_ref !== expected.source_ref
    || target.allowed_payload_keys.length !== expected.allowed_payload_keys.length
    || target.allowed_payload_keys.some((key, index) => key !== expected.allowed_payload_keys[index])
  ) {
    throw new RuntimeSurfaceError(
      'DIGEST_MISMATCH',
      'The runtime surface target does not match the verified frontend Contract Map.',
    );
  }
}

function assertTargetPayload(
  target: RuntimeSurfaceTarget,
  input: Record<string, unknown>,
): void {
  if (Object.keys(input).some((key) => !target.allowed_payload_keys.includes(key))) {
    throw new RuntimeSurfaceError(
      'INVALID',
      'The runtime surface request contains a key not allowed by its generated Contract Map target.',
    );
  }
}

export function validateRuntimeSurfaceEnvelope<T>(
  expectedSurface: RuntimeSurfaceId,
  value: unknown,
): RuntimeSurfaceEnvelope<T> {
  if (!isRecord(value)) {
    throw new RuntimeSurfaceError('INVALID', runtimeSurfaceErrorMessage('INVALID'));
  }
  if (value.runtime_surface_api_version === RUNTIME_SURFACE_API_VERSION && value.state === 'error') {
    const errorKeys = ['runtime_surface_api_version', 'state', 'code', 'message', 'retryable', 'write_set'];
    if (
      Object.keys(value).length !== errorKeys.length
      || errorKeys.some((key) => !Object.prototype.hasOwnProperty.call(value, key))
      || typeof value.code !== 'string'
      || typeof value.message !== 'string'
      || typeof value.retryable !== 'boolean'
      || !Array.isArray(value.write_set)
    ) {
      throw new RuntimeSurfaceError('INVALID', runtimeSurfaceErrorMessage('INVALID'));
    }
    const code = value.code;
    const message = typeof value.message === 'string' ? value.message : 'Canonical runtime surface failed closed.';
    const mapped = code === 'PROFILE_NOT_ACTIVE'
      ? 'PROFILE_NOT_ACTIVE'
      : code === 'STALE_REVISION'
        ? 'STALE'
        : code === 'DIGEST_MISMATCH'
          ? 'DIGEST_MISMATCH'
          : code === 'UNAPPROVED'
            ? 'APPROVAL_DENIED'
            : code === 'TIMEOUT'
              ? 'TIMEOUT'
              : code === 'INVALID_REQUEST'
                ? 'INVALID'
                : 'FAILED';
    throw new RuntimeSurfaceError(mapped, message);
  }
  if (
    Object.keys(value).length !== 9
    || ![
      'runtime_surface_api_version',
      'surface',
      'state',
      'profile_id',
      'profile_revision',
      'plan_digest',
      'catalog_revision',
      'records',
      'data',
    ].every((key) => Object.prototype.hasOwnProperty.call(value, key))
    || value.runtime_surface_api_version !== RUNTIME_SURFACE_API_VERSION
    || value.surface !== expectedSurface
    || (value.state !== 'ready' && value.state !== 'stale' && value.state !== 'blocked')
  ) {
    throw new RuntimeSurfaceError('INVALID', runtimeSurfaceErrorMessage('INVALID'));
  }
  const profileId = value.profile_id;
  const profileRevision = value.profile_revision;
  const catalogRevision = value.catalog_revision;
  const planDigest = value.plan_digest;
  const recordKeys = [
    'profile_lock',
    'resolved_plan',
    'activation_record',
    'authority_snapshot',
  ];
  const records = value.records;
  const recordRefsValid = isRecord(records)
    && Object.keys(records).length === recordKeys.length
    && recordKeys.every((key) => Object.prototype.hasOwnProperty.call(records, key))
    && recordKeys.every((key) => {
      const record = records[key];
      if (!isRecord(record)) return false;
      const keys = Object.keys(record);
      if (keys.length !== 2 || !keys.includes('digest') || !keys.includes('source_ref')) {
        return false;
      }
      if (!isSha256Digest(record.digest)) return false;
      if (!validString(record.source_ref)) return false;
      if (/^(?:file|https?):/i.test(record.source_ref)
        || record.source_ref.startsWith('/')
        || /^[A-Za-z]:[\\/]/.test(record.source_ref)
        || record.source_ref.includes('\\')
        || record.source_ref.includes('\0')
        || !/^[a-z][a-z0-9+.-]*:\/\//i.test(record.source_ref)) {
        return false;
      }
      return true;
    });
  if (
    typeof profileId !== 'string'
    || !profileId
    || typeof profileRevision !== 'string'
    || !profileRevision
    || typeof catalogRevision !== 'string'
    || !catalogRevision
    || typeof planDigest !== 'string'
    || !planDigest
    || !recordRefsValid
    || !isSha256Digest(profileRevision)
    || !isSha256Digest(planDigest)
    || !isSha256Digest(catalogRevision)
  ) {
    throw new RuntimeSurfaceError('INVALID', runtimeSurfaceErrorMessage('INVALID'));
  }
  const acceptedRecords = records as unknown as RuntimeSurfaceRecords;
  if (expectedSurface === 'profile') {
    const profileData = isRecord(value.data) ? value.data : null;
    const profileSummary = profileData && isRecord(profileData.profile)
      ? profileData.profile
      : null;
    const resolvedPlan = profileData && isRecord(profileData.resolved_plan)
      ? profileData.resolved_plan
      : null;
    const profileLock = profileData && isRecord(profileData.profile_lock)
      ? profileData.profile_lock
      : null;
    const authoritySnapshot = profileData && isRecord(profileData.authority_snapshot)
      ? profileData.authority_snapshot
      : null;
    if (
      !profileSummary
      || profileSummary.profile_id !== profileId
      || profileSummary.profile_revision !== profileRevision
      || profileSummary.catalog_revision !== catalogRevision
      || !resolvedPlan
      || resolvedPlan.plan_digest !== planDigest
      || !profileLock
      || profileLock.lock_digest !== acceptedRecords.profile_lock.digest
      || !authoritySnapshot
      || authoritySnapshot.profile_authority_snapshot_digest !== acceptedRecords.authority_snapshot.digest
      || !isRecord(profileData.activation_record)
    ) {
      throw new RuntimeSurfaceError('INVALID', runtimeSurfaceErrorMessage('INVALID'));
    }
  }
  if (expectedSurface === 'settings') {
    const runtimeSettings = extractRuntimeProfileSettings(value.data);
    if (
      runtimeSettings === null
      || runtimeSettings.profile_id !== profileId
      || runtimeSettings.profile_revision !== profileRevision
      || runtimeSettings.catalog_revision !== catalogRevision
      || runtimeSettings.plan_digest !== planDigest
      || runtimeSettings.lock_digest !== acceptedRecords.profile_lock.digest
    ) {
      throw new RuntimeSurfaceError('INVALID', runtimeSurfaceErrorMessage('INVALID'));
    }
  }
  if (value.state === 'stale') {
    throw new RuntimeSurfaceError('STALE', runtimeSurfaceErrorMessage('STALE'));
  }
  if (value.state === 'blocked') {
    throw new RuntimeSurfaceError('APPROVAL_DENIED', runtimeSurfaceErrorMessage('APPROVAL_DENIED'));
  }
  return {
    runtime_surface_api_version: RUNTIME_SURFACE_API_VERSION,
    surface: expectedSurface,
    state: 'ready',
    profile_id: profileId,
    profile_revision: profileRevision,
    catalog_revision: catalogRevision,
    plan_digest: planDigest,
    records: value.records as RuntimeSurfaceRecords,
    data: value.data as T,
  };
}

function validString(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0;
}

/** Read only the runtime scope; Launcher user preferences are intentionally ignored. */
export function extractRuntimeProfileSettings(value: unknown): RuntimeProfileSettingsProjection | null {
  if (!isRecord(value) || !isRecord(value.runtime_profile_settings)) return null;
  const settings = value.runtime_profile_settings;
  const expectedKeys = [
    'scope',
    'mutable_via_profile_activation',
    'profile_id',
    'profile_revision',
    'catalog_revision',
    'plan_digest',
    'lock_digest',
    'security_epoch',
  ];
  if (
    Object.keys(settings).length !== expectedKeys.length
    || expectedKeys.some((key) => !Object.prototype.hasOwnProperty.call(settings, key))
    || settings.scope !== 'runtime_profile'
    || settings.mutable_via_profile_activation !== true
    || !validString(settings.profile_id)
    || !isSha256Digest(settings.profile_revision)
    || !isSha256Digest(settings.catalog_revision)
    || !isSha256Digest(settings.plan_digest)
    || !isSha256Digest(settings.lock_digest)
    || typeof settings.security_epoch !== 'number'
    || !Number.isInteger(settings.security_epoch)
    || settings.security_epoch < 0
  ) {
    return null;
  }
  return {
    scope: 'runtime_profile',
    mutable_via_profile_activation: true,
    profile_id: settings.profile_id,
    profile_revision: settings.profile_revision,
    catalog_revision: settings.catalog_revision,
    plan_digest: settings.plan_digest,
    lock_digest: settings.lock_digest,
    security_epoch: settings.security_epoch,
  };
}

/**
 * Return bindings only when the projection contains the complete canonical
 * identity. This keeps Graph and Profile Wiring from synthesizing edges.
 */
export function extractExactPlanBindings(value: unknown): RuntimePlanBinding[] | null {
  if (!isRecord(value)) return null;
  const wiring = isRecord(value.resolved_wiring) ? value.resolved_wiring : null;
  const bindingValue = wiring?.bindings;
  if (!Array.isArray(bindingValue)) return null;
  const bindings: RuntimePlanBinding[] = [];
  for (const candidate of bindingValue) {
    if (!isRecord(candidate)) return null;
    if (
      !validString(candidate.binding_id)
      || !validString(candidate.source_principal_id)
      || !validString(candidate.target_principal_id)
      || !validString(candidate.target_contract_id)
      || !validString(candidate.operation_id)
      || !validString(candidate.owner_pack_id)
      || !validString(candidate.edge_digest)
      || !validString(candidate.authority_reference)
    ) {
      return null;
    }
    bindings.push({
      binding_id: candidate.binding_id,
      source_principal_id: candidate.source_principal_id,
      target_principal_id: candidate.target_principal_id,
      target_contract_id: candidate.target_contract_id,
      operation_id: candidate.operation_id,
      owner_pack_id: candidate.owner_pack_id,
      edge_digest: candidate.edge_digest,
      authority_reference: candidate.authority_reference,
    });
  }
  return bindings;
}

export function extractExactRequestedEdges(value: unknown): RuntimeRequestedEdge[] | null {
  if (!isRecord(value)) return null;
  const wiring = isRecord(value.resolved_wiring) ? value.resolved_wiring : null;
  const edgeValue = wiring?.requested_edges;
  if (!Array.isArray(edgeValue)) return null;
  const edges: RuntimeRequestedEdge[] = [];
  for (const candidate of edgeValue) {
    if (
      !isRecord(candidate)
      || !validString(candidate.caller_function_id)
      || !validString(candidate.target_provider_id)
      || !validString(candidate.contract_id)
      || !validString(candidate.operation_id)
      || !isRecord(candidate.requested_scope_template)
      || (candidate.authority_reference !== undefined
        && candidate.authority_reference !== null
        && !validString(candidate.authority_reference))
    ) {
      return null;
    }
    edges.push({
      caller_function_id: candidate.caller_function_id,
      target_provider_id: candidate.target_provider_id,
      contract_id: candidate.contract_id,
      operation_id: candidate.operation_id,
      requested_scope_template: candidate.requested_scope_template,
      authority_reference: candidate.authority_reference as string | null | undefined,
    });
  }
  return edges;
}

/** Return only provider Pack ids from the canonical Profile document. */
export function extractExactProfileSelectablePackIds(value: unknown): string[] | null {
  if (!isRecord(value) || !isRecord(value.profile_document) || !Array.isArray(value.profile_document.packs)) {
    return null;
  }
  const ids: string[] = [];
  for (const item of value.profile_document.packs) {
    if (
      !isRecord(item)
      || !validString(item.pack_id)
      || !['backend', 'contribution', 'provider', 'application'].includes(String(item.role))
      || (item.artifact_digest !== null && !/^sha256:[0-9a-f]{64}$/.test(String(item.artifact_digest)))
      || ids.includes(item.pack_id)
    ) {
      return null;
    }
    if (item.role !== 'application') ids.push(item.pack_id);
  }
  return ids;
}

function extractExactArray(value: unknown, key: string): Record<string, unknown>[] {
  if (!isRecord(value) || !Array.isArray(value[key])) return [];
  return value[key].filter(isRecord);
}

/** Normalize complete Pack lifecycle rows from the exact Packs projection. */
export function extractExactPackDescriptors(value: unknown): RuntimePackDescriptor[] {
  return extractExactArray(value, 'packs').flatMap((candidate) => {
    if (
      !validString(candidate.pack_id)
      || !validString(candidate.role)
      || !validString(candidate.kind)
      || !validString(candidate.version)
      || !validString(candidate.display_name)
      || !validString(candidate.artifact_digest)
      || !validString(candidate.artifact_ref)
      || typeof candidate.installed !== 'boolean'
      || typeof candidate.enabled !== 'boolean'
      || typeof candidate.approved !== 'boolean'
      || typeof candidate.required !== 'boolean'
      || !Array.isArray(candidate.invokable_operations)
      || candidate.invokable_operations.some((item) => !validString(item))
    ) {
      return [];
    }
    return [{
      pack_id: candidate.pack_id,
      role: candidate.role,
      kind: candidate.kind,
      version: candidate.version,
      display_name: candidate.display_name,
      artifact_digest: candidate.artifact_digest,
      artifact_ref: candidate.artifact_ref,
      installed: candidate.installed,
      enabled: candidate.enabled,
      approved: candidate.approved,
      required: candidate.required,
      invokable_operations: candidate.invokable_operations as string[],
      ...(candidate.reason === null || validString(candidate.reason) ? {reason: candidate.reason as string | null | undefined} : {}),
    }];
  });
}

/**
 * Normalize only complete operation rows. Partial rows are omitted instead of
 * being guessed into a Flow or AI Input item.
 */
export function extractExactOperationDescriptors(
  value: unknown,
): RuntimeOperationDescriptor[] {
  return extractExactArray(value, 'operations').flatMap((candidate) => {
    const schema = candidate.schema;
    if (
      !validString(candidate.owner_pack_id)
      || !validString(candidate.contribution_id)
      || !validString(candidate.target_provider_id)
      || !isSha256Digest(candidate.artifact_digest)
      || (candidate.invocation_contribution_id !== null && !validString(candidate.invocation_contribution_id))
      || (candidate.invocation_owner_pack_id !== null && !validString(candidate.invocation_owner_pack_id))
      || (candidate.invocation_catalog_hash !== null && !isSha256Digest(candidate.invocation_catalog_hash))
      || (candidate.invocation_reason !== null && !validString(candidate.invocation_reason))
      || !validString(candidate.operation_id)
      || !validString(candidate.contract_id)
      || !validString(candidate.function_id)
      || !isRecord(schema)
      || !isSha256Digest(candidate.catalog_digest)
      || typeof candidate.invokable !== 'boolean'
    ) {
      return [];
    }
    return [{
      operation_id: candidate.operation_id,
      contract_id: candidate.contract_id,
      owner_pack_id: candidate.owner_pack_id,
      contribution_id: candidate.contribution_id,
      target_provider_id: candidate.target_provider_id,
      artifact_digest: candidate.artifact_digest,
      invocation_contribution_id: candidate.invocation_contribution_id as string | null,
      invocation_owner_pack_id: candidate.invocation_owner_pack_id as string | null,
      invocation_catalog_hash: candidate.invocation_catalog_hash as string | null,
      invocation_reason: candidate.invocation_reason as string | null,
      invokable: candidate.invokable,
      catalog_digest: candidate.catalog_digest,
      function_id: candidate.function_id,
      schema,
      ...(validString(candidate.label) ? {label: candidate.label} : {}),
      ...(validString(candidate.provider_id) ? {provider_id: candidate.provider_id} : {}),
      ...(isRecord(schema.input_schema) && isRuntimeJsonSchema(schema.input_schema)
        ? {input_schema: schema.input_schema}
        : {}),
      ...(isRecord(candidate.provider_semantics)
        ? {provider_semantics: candidate.provider_semantics}
        : {}),
      ...(isRecord(candidate.route) ? {route: candidate.route} : {}),
    }];
  });
}

/** Read invokable operation keys only from the authoritative Packs projection. */
export function extractAuthoritativeInvokableOperationKeys(value: unknown): Set<string> | null {
  const rows = extractExactArray(value, 'packs');
  if (rows.length === 0) return null;
  const keys = new Set<string>();
  for (const row of rows) {
    if (!Array.isArray(row.invokable_operations) || row.invokable_operations.some((item) => !validString(item))) {
      return null;
    }
    for (const item of row.invokable_operations) keys.add(item);
  }
  return keys;
}

function isRuntimeJsonSchema(value: unknown): value is RuntimeJsonSchema {
  if (!isRecord(value)) return false;
  if (value.type !== undefined && typeof value.type !== 'string') return false;
  if (value.title !== undefined && typeof value.title !== 'string') return false;
  if (value.description !== undefined && typeof value.description !== 'string') return false;
  if (value.enum !== undefined && !Array.isArray(value.enum)) return false;
  if (value.required !== undefined && (
    !Array.isArray(value.required)
    || value.required.some((item) => typeof item !== 'string')
  )) return false;
  if (value.properties !== undefined) {
    if (!isRecord(value.properties)) return false;
    if (Object.values(value.properties).some((item) => !isRuntimeJsonSchema(item))) return false;
  }
  if (value.items !== undefined && !isRuntimeJsonSchema(value.items)) return false;
  return true;
}

/** Normalize complete route rows; no route is composed from an operation id. */
export function extractExactRouteDescriptors(value: unknown): RuntimeRouteDescriptor[] {
  return extractExactArray(value, 'routes').flatMap((candidate) => {
    const security = candidate.security;
    const expectedRouteKeys = [
      'route_id',
      'method',
      'logical_target',
      'contract_id',
      'operation_id',
      'contribution_id',
      'presentation',
      'owner_pack_id',
      'provider_id',
      'function_id',
      'function_principal_id',
      'manifest_digest',
      'frontend_map_digest',
      'allowed_payload_keys',
      'security',
    ];
    const expectedSecurityKeys = [
      'transport',
      'panel_authentication_required',
      'broker_authority_required',
      'csrf_required',
      'request_id_required',
      'replay_protection_required',
    ];
    if (
      Object.keys(candidate).length !== expectedRouteKeys.length
      || expectedRouteKeys.some((key) => !Object.prototype.hasOwnProperty.call(candidate, key))
      || !validString(candidate.route_id)
      || (candidate.method !== 'GET' && candidate.method !== 'POST')
      || !validString(candidate.logical_target)
      || !validString(candidate.contract_id)
      || !validString(candidate.operation_id)
      || !validString(candidate.provider_id)
      || !validString(candidate.function_id)
      || !isSha256Digest(candidate.frontend_map_digest)
      || !validString(candidate.contribution_id)
      || !validString(candidate.presentation)
      || !validString(candidate.owner_pack_id)
      || !isSha256Digest(candidate.manifest_digest)
      || !validString(candidate.function_principal_id)
      || !Array.isArray(candidate.allowed_payload_keys)
      || candidate.allowed_payload_keys.some((item) => !validString(item))
      || !isRecord(security)
      || security.transport !== 'canonical_contract'
      || typeof security.panel_authentication_required !== 'boolean'
      || typeof security.broker_authority_required !== 'boolean'
      || typeof security.csrf_required !== 'boolean'
      || typeof security.request_id_required !== 'boolean'
      || typeof security.replay_protection_required !== 'boolean'
      || Object.keys(security).length !== expectedSecurityKeys.length
      || expectedSecurityKeys.some((key) => !Object.prototype.hasOwnProperty.call(security, key))
      || security.panel_authentication_required !== true
      || security.broker_authority_required !== true
      || security.csrf_required !== (candidate.method === 'POST')
      || security.request_id_required !== (candidate.method === 'POST')
      || security.replay_protection_required !== (candidate.method === 'POST')
    ) {
      return [];
    }
    return [{
      route_id: candidate.route_id,
      method: candidate.method,
      logical_target: candidate.logical_target,
      contract_id: candidate.contract_id,
      operation_id: candidate.operation_id,
      provider_id: candidate.provider_id,
      function_id: candidate.function_id,
      frontend_map_digest: candidate.frontend_map_digest,
      contribution_id: candidate.contribution_id,
      presentation: candidate.presentation,
      owner_pack_id: candidate.owner_pack_id,
      manifest_digest: candidate.manifest_digest,
      function_principal_id: candidate.function_principal_id,
      allowed_payload_keys: candidate.allowed_payload_keys as string[],
      security: {
        transport: security.transport,
        panel_authentication_required: security.panel_authentication_required,
        broker_authority_required: security.broker_authority_required,
        csrf_required: security.csrf_required,
        request_id_required: security.request_id_required,
        replay_protection_required: security.replay_protection_required,
      },
    }];
  });
}

/** Flow rows must be declared composition records, never Pack-name matches. */
export function extractExactFlowDescriptors(value: unknown): RuntimeFlowDescriptor[] {
  return extractExactArray(value, 'flows').flatMap((candidate) => {
    if (
      !validString(candidate.flow_id)
      || !validString(candidate.state)
      || !Array.isArray(candidate.operation_ids)
      || candidate.operation_ids.some((item) => !validString(item))
    ) {
      return [];
    }
    return [{
      flow_id: candidate.flow_id,
      state: candidate.state,
      operation_ids: candidate.operation_ids as string[],
      ...(validString(candidate.label) ? {label: candidate.label} : {}),
    }];
  });
}

function isSafeRelativeArtifactPath(value: unknown): value is string {
  if (typeof value !== 'string' || !value || value.startsWith('/') || value.startsWith('file:')) return false;
  if (/^[A-Za-z]:[\\/]/.test(value) || value.includes('\\') || value.includes('\0')) return false;
  const segments = value.split('/');
  return segments.every((segment) => segment.length > 0 && segment !== '.' && segment !== '..');
}

/** Record only finite manifest artifact evidence, never a host file path. */
export function extractFiniteArtifactEntries(value: unknown): RuntimeArtifactEntry[] | null {
  if (!isRecord(value)) return null;
  const candidates = Array.isArray(value.artifact_entries)
    ? value.artifact_entries
    : Array.isArray(value.pack_closure)
      ? value.pack_closure.flatMap((pack) => isRecord(pack) && Array.isArray(pack.artifacts) ? pack.artifacts : [])
      : null;
  if (!candidates) return null;
  const entries: RuntimeArtifactEntry[] = [];
  for (const candidate of candidates) {
    if (
      !isRecord(candidate)
      || !validString(candidate.entry_id)
      || !validString(candidate.owner_pack_id)
      || !isSafeRelativeArtifactPath(candidate.path)
      || !validString(candidate.kind)
      || 'host_path' in candidate
      || !isSha256Digest(candidate.artifact_digest)
    ) {
      return null;
    }
    entries.push({
      entry_id: candidate.entry_id,
      owner_pack_id: candidate.owner_pack_id,
      path: candidate.path,
      kind: candidate.kind,
      artifact_digest: candidate.artifact_digest,
    });
  }
  return entries;
}

export interface RuntimeOperationInvocation {
  envelope: RuntimeSurfaceEnvelope<unknown>;
  operation: RuntimeOperationDescriptor;
  payload: Record<string, unknown>;
}

/**
 * Invoke one catalog-declared operation through the existing Broker-backed
 * capability path. Authority fields and client approval flags are impossible
 * to add to this request shape.
 */
export function invokeRuntimeOperation({
  envelope,
  operation,
  payload,
}: RuntimeOperationInvocation): Promise<unknown> {
  const forbiddenPayloadKeys = new Set([
    'approved',
    'approval_token',
    'caller',
    'caller_id',
    'target',
    'target_id',
    'provider',
    'provider_id',
    'authority',
    'authority_reference',
    'profile_id',
    'plan_hash',
    'catalog_hash',
  ]);
  if (Object.keys(payload).some((key) => forbiddenPayloadKeys.has(key))) {
    return Promise.reject(new RuntimeSurfaceError(
      'INVALID',
      'Operation input cannot provide authority, caller, target, provider, or approval fields.',
    ));
  }
  if (
    envelope.surface !== 'operations'
    || !operation.owner_pack_id
    || (operation.invocation_owner_pack_id !== null
      && operation.invocation_owner_pack_id !== operation.owner_pack_id)
  ) {
    return Promise.reject(new RuntimeSurfaceError(
      'DIGEST_MISMATCH',
      'The operation binding is not owned by the accepted operations snapshot.',
    ));
  }
  if (
    !operation.invokable
    || !operation.invocation_contribution_id
    || !operation.invocation_owner_pack_id
    || !operation.invocation_catalog_hash
  ) {
    return Promise.reject(new RuntimeSurfaceError(
      'APPROVAL_DENIED',
      'The selected operation is not currently invokable in the accepted snapshot.',
    ));
  }
  if (
    !envelope.catalog_revision
    || operation.catalog_digest !== envelope.catalog_revision
    || operation.invocation_catalog_hash !== envelope.catalog_revision
  ) {
    return Promise.reject(new RuntimeSurfaceError(
      'DIGEST_MISMATCH',
      runtimeSurfaceErrorMessage('DIGEST_MISMATCH'),
    ));
  }
  if (!operation.invocation_contribution_id || !operation.invocation_owner_pack_id) {
    return Promise.reject(new RuntimeSurfaceError(
      'INVALID',
      'The accepted operation has no exact frontend catalog contribution binding.',
    ));
  }
  return invokeFrontendCapability({
    profileId: envelope.profile_id,
    planHash: envelope.plan_digest,
    catalogHash: operation.invocation_catalog_hash,
    contributionId: operation.invocation_contribution_id,
    ownerPackId: operation.invocation_owner_pack_id,
    contractId: operation.contract_id,
    payload,
  });
}

export function classifyRuntimeSurfaceError(error: unknown): RuntimeSurfaceErrorCode {
  if (error instanceof RuntimeSurfaceError) return error.code;
  if (error instanceof ApiRequestTimeoutError || (error instanceof Error && error.name === 'AbortError')) {
    return 'TIMEOUT';
  }
  const errorData = isRecord(error) && isRecord(error.data) ? error.data : null;
  const typedCode = errorData && typeof errorData.code === 'string' ? errorData.code : null;
  if (typedCode === 'PROFILE_NOT_ACTIVE') return 'PROFILE_NOT_ACTIVE';
  if (typedCode === 'STALE_REVISION') return 'STALE';
  if (typedCode === 'DIGEST_MISMATCH') return 'DIGEST_MISMATCH';
  if (typedCode === 'UNAPPROVED') return 'APPROVAL_DENIED';
  if (typedCode === 'TIMEOUT') return 'TIMEOUT';
  const message = error instanceof Error ? error.message.toLowerCase() : '';
  if (message.includes('not active') || message.includes('profile_not_active')) return 'PROFILE_NOT_ACTIVE';
  if (message.includes('timeout') || message.includes('timed out')) return 'TIMEOUT';
  if (message.includes('digest') || message.includes('stale') || message.includes('revision')) {
    return 'DIGEST_MISMATCH';
  }
  if (message.includes('approval') || message.includes('denied') || message.includes('blocked')) {
    return 'APPROVAL_DENIED';
  }
  return 'FAILED';
}

export interface RuntimeSurfaceClient {
  read<T>(surface: RuntimeSurfaceId, input?: {
    expected_profile_revision?: string;
    expected_plan_digest?: string;
  }): Promise<RuntimeSurfaceEnvelope<T>>;
}

export function createRuntimeSurfaceClient(
  targets: Partial<Record<RuntimeSurfaceId, RuntimeSurfaceTarget>> = RUNTIME_SURFACE_TARGETS,
  transport: RuntimeSurfaceTransport = canonicalTransport,
): RuntimeSurfaceClient {
  return {
    read: async <T>(surface: RuntimeSurfaceId, input = {}) => {
      const target = targets[surface];
      if (!target) {
        throw new RuntimeSurfaceError('UNAVAILABLE', runtimeSurfaceErrorMessage('UNAVAILABLE'));
      }
      assertVerifiedRuntimeTarget(target);
      const requestInput = target.read_guards === false ? {} : input;
      assertTargetPayload(target, requestInput);
      const response = await transport.read<unknown>(target, requestInput);
      return validateRuntimeSurfaceEnvelope<T>(surface, response);
    },
  };
}

export const defaultRuntimeSurfaceClient = createRuntimeSurfaceClient();
