import {
  authoritativeOperationKey,
} from './advancedSurfaces';
import {
  extractExactOperationDescriptors,
  extractExactPackDescriptors,
  type RuntimeJsonSchema,
  type RuntimeOperationDescriptor,
  type RuntimePackDescriptor,
} from './runtimeSurface';

export type ProviderConnectionStatus =
  | 'not_configured'
  | 'connected'
  | 'healthy'
  | 'degraded'
  | 'error'
  | 'unavailable';

export type ProviderConnectionAction =
  | 'configure'
  | 'set_credential'
  | 'connect_oauth'
  | 'test'
  | 'health'
  | 'refresh_models'
  | 'delete_credential'
  | 'delete_instance'
  | 'create_instance'
  | 'select_profile';

export interface ProviderConnectionProjection {
  instanceId: string;
  displayName: string;
  description: string | null;
  iconId: string | null;
  pack: RuntimePackDescriptor;
  contracts: string[];
  authModes: string[];
  settingsSchema: RuntimeJsonSchema;
  secretFields: string[];
  uiHints: Record<string, string>;
  endpointRequirements: {networkRequired: boolean | null; localAllowed: boolean | null};
  multiInstance: boolean;
  instanceField: string | null;
  configured: boolean;
  credentialPresent: boolean;
  status: ProviderConnectionStatus;
  diagnosticCode: string | null;
  modelCount: number | null;
  lastRefreshAt: string | null;
  selectedBy: string[];
  operationIds: Partial<Record<ProviderConnectionAction, string>>;
  operations: Partial<Record<ProviderConnectionAction, RuntimeOperationDescriptor>>;
}

const ACTIONS: readonly ProviderConnectionAction[] = [
  'configure',
  'set_credential',
  'connect_oauth',
  'test',
  'health',
  'refresh_models',
  'delete_credential',
  'delete_instance',
  'create_instance',
  'select_profile',
];

const STATUSES = new Set<ProviderConnectionStatus>([
  'not_configured',
  'connected',
  'healthy',
  'degraded',
  'error',
  'unavailable',
]);

const OAUTH_BROKER_OWNED_FIELDS = /^(?:access_token|refresh_token|id_token|authorization_code|oauth_token)$/i;

const CONNECTION_FIELDS = new Set([
  'kind',
  'instance_id',
  'display_name',
  'description',
  'icon_id',
  'auth_modes',
  'settings_schema',
  'ui_hints',
  'secret_fields',
  'endpoint_requirements',
  'operations',
  'multi_instance',
  'instance_field',
  'configured',
  'credential_present',
  'status',
  'diagnostic_code',
  'model_count',
  'last_refresh_at',
]);

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function stringArray(value: unknown): string[] | null {
  return Array.isArray(value)
    && value.every((item) => typeof item === 'string' && item.length > 0)
    && new Set(value).size === value.length
    ? value
    : null;
}

function safeHints(value: unknown): Record<string, string> | null {
  const candidate = record(value);
  if (!candidate) return value === undefined ? {} : null;
  if (Object.values(candidate).some((item) => typeof item !== 'string' || item.length === 0)) {
    return null;
  }
  return candidate as Record<string, string>;
}

function operationMap(value: unknown): Partial<Record<ProviderConnectionAction, string>> | null {
  const candidate = record(value);
  if (!candidate || Object.keys(candidate).some((key) => !ACTIONS.includes(key as ProviderConnectionAction))) {
    return null;
  }
  const result: Partial<Record<ProviderConnectionAction, string>> = {};
  for (const action of ACTIONS) {
    const operationId = candidate[action];
    if (operationId === undefined) continue;
    if (typeof operationId !== 'string' || operationId.length === 0) return null;
    result[action] = operationId;
  }
  return result;
}

function extractContractRows(value: unknown): Record<string, unknown>[] {
  const container = record(value);
  if (!container || !Array.isArray(container.contracts)) return [];
  return container.contracts
    .map((item) => record(item))
    .filter((item): item is Record<string, unknown> => item !== null);
}

/**
 * Build the provider list solely from verified Contract metadata and captured
 * Pack/operation rows. Malformed metadata is omitted fail-closed; no vendor ID
 * or protocol family is recognized here.
 */
export function projectProviderConnections(input: {
  contractsData: unknown;
  operationsData: unknown;
  activeProfileId?: string | null;
  selectedByInstance?: Readonly<Record<string, readonly string[]>>;
}): ProviderConnectionProjection[] {
  const packs = extractExactPackDescriptors(input.contractsData);
  const operations = extractExactOperationDescriptors(input.operationsData);
  const operationPacks = extractExactPackDescriptors(input.operationsData);
  const operationPackIds = new Set(operationPacks.map((pack) => pack.pack_id));
  const byInstance = new Map<string, ProviderConnectionProjection>();
  const conflictingInstances = new Set<string>();

  for (const row of extractContractRows(input.contractsData)) {
    if (
      typeof row.pack_id !== 'string'
      || typeof row.contract_id !== 'string'
      || typeof row.revision_digest !== 'string'
      || !/^sha256:[0-9a-f]{64}$/.test(row.revision_digest)
    ) continue;
    const semantics = record(row.provider_semantics);
    const connection = semantics ? record(semantics.connection) : null;
    if (!semantics || !connection || connection.kind !== 'ai_provider') continue;
    if (Object.keys(connection).some((key) => !CONNECTION_FIELDS.has(key))) continue;
    const pack = packs.find((candidate) => candidate.pack_id === row.pack_id);
    const authModes = stringArray(connection.auth_modes);
    const secretFields = stringArray(connection.secret_fields);
    const settingsSchema = record(connection.settings_schema);
    const uiHints = safeHints(connection.ui_hints);
    const declaredOperations = operationMap(connection.operations);
    const endpointRequirements = record(connection.endpoint_requirements);
    const status = connection.status;
    const instanceField = typeof connection.instance_field === 'string'
      && /^[a-z][a-z0-9_]{0,63}$/.test(connection.instance_field)
      ? connection.instance_field
      : null;
    if (
      !pack
      || typeof connection.instance_id !== 'string'
      || connection.instance_id.length === 0
      || typeof connection.display_name !== 'string'
      || connection.display_name.length === 0
      || !authModes
      || !secretFields
      || !settingsSchema
      || settingsSchema.type !== 'object'
      || !uiHints
      || !declaredOperations
      || typeof connection.multi_instance !== 'boolean'
      || (connection.multi_instance === true && !instanceField)
      || (connection.endpoint_requirements !== undefined && !endpointRequirements)
      || (status !== undefined && !STATUSES.has(status as ProviderConnectionStatus))
    ) continue;

    if (conflictingInstances.has(connection.instance_id)) continue;
    const existing = byInstance.get(connection.instance_id);
    if (existing && existing.pack.pack_id !== pack.pack_id) {
      byInstance.delete(connection.instance_id);
      conflictingInstances.add(connection.instance_id);
      continue;
    }
    const resolvedOperations: Partial<Record<ProviderConnectionAction, RuntimeOperationDescriptor>> = {};
    for (const action of ACTIONS) {
      const operationId = declaredOperations[action];
      if (!operationId) continue;
      const matches = operations.filter((operation) => (
        operation.owner_pack_id === pack.pack_id
        && operation.operation_id === operationId
        && operationPacks.some((operationPack) => (
          operationPack.pack_id === operation.owner_pack_id
          && operationPack.artifact_digest === operation.artifact_digest
          && operationPack.invokable_operations.includes(
            authoritativeOperationKey(operation.contract_id, operation.operation_id),
          )
        ))
      ));
      if (matches.length === 1) {
        const operation = matches[0];
        const inputProperties = operation.input_schema?.properties ?? {};
        const safelyBindsInstance = action === 'create_instance'
          || !instanceField
          || inputProperties[instanceField] !== undefined;
        const safelyBindsCredential = action !== 'set_credential'
          || secretFields.some((field) => inputProperties[field] !== undefined);
        const oauthRemainsBrokerOwned = action !== 'connect_oauth'
          || !Object.keys(inputProperties).some((field) => OAUTH_BROKER_OWNED_FIELDS.test(field));
        if (safelyBindsInstance && safelyBindsCredential && oauthRemainsBrokerOwned) {
          resolvedOperations[action] = operation;
        }
      }
    }
    const declaredStatus = status as ProviderConnectionStatus | undefined;
    const trusted = pack.installed && pack.enabled && pack.approved && operationPackIds.has(pack.pack_id);
    const normalizedStatus: ProviderConnectionStatus = !trusted
      ? 'unavailable'
      : declaredStatus ?? (connection.configured === true ? 'connected' : 'not_configured');
    const projection: ProviderConnectionProjection = existing ?? {
      instanceId: connection.instance_id,
      displayName: connection.display_name,
      description: typeof connection.description === 'string' ? connection.description : null,
      iconId: typeof connection.icon_id === 'string' ? connection.icon_id : null,
      pack,
      contracts: [],
      authModes,
      settingsSchema: settingsSchema as RuntimeJsonSchema,
      secretFields,
      uiHints,
      endpointRequirements: {
        networkRequired: typeof endpointRequirements?.network_required === 'boolean'
          ? endpointRequirements.network_required
          : null,
        localAllowed: typeof endpointRequirements?.local_allowed === 'boolean'
          ? endpointRequirements.local_allowed
          : null,
      },
      multiInstance: connection.multi_instance,
      instanceField,
      configured: connection.configured === true,
      credentialPresent: connection.credential_present === true,
      status: normalizedStatus,
      diagnosticCode: trustDiagnostic(pack)
        ?? (typeof connection.diagnostic_code === 'string'
          ? connection.diagnostic_code
          : null),
      modelCount: Number.isInteger(connection.model_count) && Number(connection.model_count) >= 0
        ? Number(connection.model_count)
        : null,
      lastRefreshAt: typeof connection.last_refresh_at === 'string'
        && Number.isFinite(Date.parse(connection.last_refresh_at))
        ? connection.last_refresh_at
        : null,
      selectedBy: [...(
        input.selectedByInstance?.[connection.instance_id]
        ?? (input.activeProfileId ? [input.activeProfileId] : [])
      )],
      operationIds: declaredOperations,
      operations: resolvedOperations,
    };
    projection.contracts = [...new Set([...projection.contracts, row.contract_id])].sort();
    projection.operations = {...projection.operations, ...resolvedOperations};
    byInstance.set(connection.instance_id, projection);
  }
  return [...byInstance.values()].sort((left, right) => (
    left.displayName.localeCompare(right.displayName) || left.instanceId.localeCompare(right.instanceId)
  ));
}

export function providerSecretSchema(
  provider: ProviderConnectionProjection,
  operation: RuntimeOperationDescriptor,
): RuntimeOperationDescriptor {
  const secretFields = new Set(provider.secretFields);
  const properties = Object.fromEntries(
    Object.entries(operation.input_schema?.properties ?? {}).map(([name, schema]) => [
      name,
      secretFields.has(name) ? {...schema, writeOnly: true, default: undefined} : schema,
    ]),
  );
  return {
    ...operation,
    input_schema: operation.input_schema
      ? {...operation.input_schema, properties}
      : operation.input_schema,
  };
}

function trustDiagnostic(pack: RuntimePackDescriptor): string | null {
  if (!pack.installed) return 'pack_not_installed';
  if (!pack.approved) {
    const reason = pack.reason?.toLowerCase() ?? '';
    if (reason.includes('modified')) return 'artifact_modified';
    if (reason.includes('stale')) return 'approval_stale';
    if (reason.includes('incompatible')) return 'incompatible_contract';
    if (reason.includes('policy')) return 'policy_blocked';
    return 'pack_not_approved';
  }
  if (!pack.enabled) return 'pack_disabled';
  return null;
}

/** Apply safe presentation hints and write-only semantics to an exact action schema. */
export function providerOperationSchema(
  provider: ProviderConnectionProjection,
  operation: RuntimeOperationDescriptor,
): RuntimeOperationDescriptor {
  const secured = providerSecretSchema(provider, operation);
  const properties = Object.fromEntries(
    Object.entries(secured.input_schema?.properties ?? {}).map(([name, schema]) => [
      name,
      provider.uiHints[name] && !schema.title
        ? {...schema, title: provider.uiHints[name]}
        : schema,
    ]),
  );
  return {
    ...secured,
    input_schema: secured.input_schema
      ? {...secured.input_schema, properties}
      : secured.input_schema,
  };
}
