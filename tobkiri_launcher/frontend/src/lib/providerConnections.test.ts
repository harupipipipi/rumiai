import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';

import {
  projectProviderConnections,
  providerOperationSchema,
  providerSecretSchema,
} from './providerConnections';
import type {RuntimeOperationDescriptor} from './runtimeSurface';

const digest = (character: string): string => `sha256:${character.repeat(64)}`;

function pack(packId: string, overrides: Record<string, unknown> = {}) {
  return {
    pack_id: packId,
    role: 'provider',
    kind: 'normal_sandbox',
    version: '1.0.0',
    display_name: `Fixture ${packId}`,
    artifact_digest: digest(packId === 'fixture-provider-a' ? 'a' : 'b'),
    artifact_ref: `pack-v4://${packId}@${digest(packId === 'fixture-provider-a' ? 'a' : 'b')}`,
    installed: true,
    enabled: true,
    approved: true,
    required: false,
    invokable_operations: [
      `rumi.service.ai.connection.v1::${packId}.configure`,
      `rumi.service.ai.connection.v1::${packId}.refresh-models`,
      `rumi.service.ai.connection.v1::${packId}.set-credential`,
      `rumi.service.ai.connection.v1::${packId}.connect-oauth`,
    ],
    reason: null,
    ...overrides,
  };
}

function operation(packId: string, operationId: string): RuntimeOperationDescriptor {
  const artifactDigest = packId === 'fixture-provider-a' ? digest('a') : digest('b');
  return {
    action: 'contract_invoke',
    operation_id: operationId,
    contract_id: 'rumi.service.ai.connection.v1',
    owner_pack_id: packId,
    contribution_id: `${operationId}.contribution`,
    target_provider_id: `${packId}.instance`,
    artifact_digest: artifactDigest,
    invocation_contribution_id: `${operationId}.invoke`,
    invocation_owner_pack_id: packId,
    invocation_catalog_hash: digest('c'),
    invocation_reason: null,
    invokable: true,
    catalog_digest: digest('c'),
    function_id: operationId,
    function_principal_id: `${operationId}.principal`,
    caller_function_id: 'tobkiri.launcher.providers',
    authority_reference: `authority://${packId}/${operationId}`,
    schema: {
      input_schema: {
        type: 'object',
        properties: {
          provider_instance_id: {type: 'string', title: 'Provider instance'},
          api_key: {type: 'string', title: 'API key', default: 'must-not-survive'},
          endpoint: {type: 'string', title: 'Endpoint'},
        },
      },
    },
    input_schema: {
      type: 'object',
      properties: {
        provider_instance_id: {type: 'string', title: 'Provider instance'},
        api_key: {type: 'string', title: 'API key', default: 'must-not-survive'},
        endpoint: {type: 'string', title: 'Endpoint'},
      },
    },
    route: {
      contract_id: 'rumi.service.ai.connection.v1',
      operation_id: operationId,
      function_id: operationId,
      provider_pack_id: packId,
    },
  };
}

function contract(packId: string, instanceId: string, authModes: string[], overrides: Record<string, unknown> = {}) {
  return {
    pack_id: packId,
    contract_id: 'rumi.service.ai.connection.v1',
    revision_digest: digest(packId === 'fixture-provider-a' ? 'd' : 'e'),
    provider_semantics: {
      provider_id: instanceId,
      connection: {
        kind: 'ai_provider',
        instance_id: instanceId,
        display_name: `Connection ${instanceId}`,
        description: 'Fixture connection declared by its Pack.',
        auth_modes: authModes,
        settings_schema: {
          type: 'object',
          properties: {endpoint: {type: 'string'}},
        },
        ui_hints: {endpoint: 'Provider endpoint'},
        secret_fields: authModes.includes('api_key') ? ['api_key'] : [],
        operations: {
          configure: `${packId}.configure`,
          refresh_models: `${packId}.refresh-models`,
        },
        multi_instance: true,
        instance_field: 'provider_instance_id',
        configured: authModes.includes('none'),
        credential_present: false,
        status: authModes.includes('none') ? 'healthy' : 'not_configured',
        model_count: 7,
        last_refresh_at: '2026-08-23T00:00:00Z',
        ...overrides,
      },
    },
  };
}

function fixtureData(contracts: unknown[], packs: unknown[]) {
  const operations = packs.flatMap((item) => {
    const packId = (item as {pack_id: string}).pack_id;
    return [
      operation(packId, `${packId}.configure`),
      operation(packId, `${packId}.refresh-models`),
      operation(packId, `${packId}.set-credential`),
      operation(packId, `${packId}.connect-oauth`),
    ];
  });
  return {
    contractsData: {contracts, packs},
    operationsData: {operations, packs},
  };
}

test('projects API-key, OAuth, local, and non-protocol-specific provider fixtures without vendor code', () => {
  const firstPack = pack('fixture-provider-a');
  const secondPack = pack('fixture-provider-b');
  const projected = projectProviderConnections(fixtureData([
    contract('fixture-provider-a', 'fixture.api-key', ['api_key']),
    contract('fixture-provider-a', 'fixture.oauth', ['oauth']),
    contract('fixture-provider-a', 'fixture.local', ['none']),
    contract('fixture-provider-b', 'fixture.custom-semantics', ['api_key']),
  ], [firstPack, secondPack]));
  assert.deepEqual(projected.map((provider) => provider.instanceId), [
    'fixture.api-key',
    'fixture.custom-semantics',
    'fixture.local',
    'fixture.oauth',
  ]);
  assert.equal(projected.filter((provider) => provider.pack.pack_id === 'fixture-provider-a').length, 3);
  assert.equal(projected.find((provider) => provider.instanceId === 'fixture.local')?.status, 'healthy');
  assert.ok(projected.every((provider) => provider.operations.configure?.owner_pack_id === provider.pack.pack_id));
});

test('attributes discovered connections to the exact active Profile closure', () => {
  const fixture = fixtureData([
    contract('fixture-provider-a', 'fixture.selected', ['none']),
  ], [pack('fixture-provider-a')]);
  const projected = projectProviderConnections({
    ...fixture,
    activeProfileId: 'defaults-profile',
  });
  assert.deepEqual(projected[0].selectedBy, ['defaults-profile']);
});

test('keeps disabled, unapproved, modified, and health failure states distinguishable', () => {
  const disabled = pack('fixture-provider-a', {enabled: false});
  const unapproved = pack('fixture-provider-b', {approved: false, reason: 'artifact_modified'});
  const projected = projectProviderConnections(fixtureData([
    contract('fixture-provider-a', 'fixture.disabled', ['none']),
    contract('fixture-provider-b', 'fixture.modified', ['api_key'], {
      status: 'degraded',
      diagnostic_code: 'health_failed',
      model_count: 11,
    }),
  ], [disabled, unapproved]));
  assert.equal(projected[0].status, 'unavailable');
  assert.equal(projected[0].diagnosticCode, 'pack_disabled');
  assert.equal(projected[1].status, 'unavailable');
  assert.equal(projected[1].diagnosticCode, 'artifact_modified');
  assert.equal(projected[1].modelCount, 11, 'last-known-good model count is retained');
});

test('malformed metadata and cross-Pack duplicate instance identities fail closed', () => {
  const firstPack = pack('fixture-provider-a');
  const secondPack = pack('fixture-provider-b');
  const malformed = contract('fixture-provider-a', 'fixture.bad', ['api_key'], {settings_schema: {type: 'array'}});
  const projected = projectProviderConnections(fixtureData([
    malformed,
    contract('fixture-provider-a', 'fixture.collision', ['none']),
    contract('fixture-provider-b', 'fixture.collision', ['oauth']),
  ], [firstPack, secondPack]));
  assert.deepEqual(projected, []);
});

test('unexpected credential-shaped metadata fails closed instead of reaching the UI', () => {
  const projected = projectProviderConnections(fixtureData([
    contract('fixture-provider-a', 'fixture.leaked', ['api_key'], {
      access_token: 'must-never-be-projected',
    }),
  ], [pack('fixture-provider-a')]));
  assert.deepEqual(projected, []);
});

test('OAuth tokens remain broker-owned and are not rendered as connection inputs', () => {
  const fixture = fixtureData([
    contract('fixture-provider-a', 'fixture.oauth-safe', ['oauth'], {
      operations: {connect_oauth: 'fixture-provider-a.connect-oauth'},
    }),
  ], [pack('fixture-provider-a')]);
  const oauthOperation = fixture.operationsData.operations.find((candidate) => (
    candidate.operation_id === 'fixture-provider-a.connect-oauth'
  ));
  assert.ok(oauthOperation?.input_schema?.properties);
  oauthOperation.input_schema.properties.access_token = {type: 'string'};
  const schemaInput = oauthOperation.schema.input_schema as RuntimeOperationDescriptor['input_schema'];
  assert.ok(schemaInput?.properties);
  schemaInput.properties.access_token = {type: 'string'};
  const projected = projectProviderConnections(fixture);
  assert.equal(projected[0].operationIds.connect_oauth, 'fixture-provider-a.connect-oauth');
  assert.equal(projected[0].operations.connect_oauth, undefined);
});

test('marks declared secret inputs write-only and removes their defaults', () => {
  const provider = projectProviderConnections(fixtureData([
    contract('fixture-provider-a', 'fixture.api-key', ['api_key']),
  ], [pack('fixture-provider-a')]))[0];
  const secured = providerSecretSchema(provider, provider.operations.configure!);
  assert.equal(secured.input_schema?.properties?.api_key.writeOnly, true);
  assert.equal(secured.input_schema?.properties?.api_key.default, undefined);
  assert.equal(secured.input_schema?.properties?.endpoint.writeOnly, undefined);
});

test('uses safe UI hints only to label declared operation fields', () => {
  const provider = projectProviderConnections(fixtureData([
    contract('fixture-provider-a', 'fixture.hints', ['api_key']),
  ], [pack('fixture-provider-a')]))[0];
  const operationWithUntitledEndpoint = {
    ...provider.operations.configure!,
    input_schema: {
      ...provider.operations.configure!.input_schema!,
      properties: {
        ...provider.operations.configure!.input_schema!.properties,
        endpoint: {type: 'string' as const},
      },
    },
  };
  const rendered = providerOperationSchema(provider, operationWithUntitledEndpoint);
  assert.equal(rendered.input_schema?.properties?.endpoint.title, 'Provider endpoint');
  assert.equal(rendered.input_schema?.properties?.api_key.writeOnly, true);
});

test('provider projection source contains no provider-vendor branches or browser storage', async () => {
  const source = await readFile(new URL('./providerConnections.ts', import.meta.url), 'utf8');
  assert.doesNotMatch(source, /openai|anthropic|ollama|localStorage|sessionStorage/i);
});

test('provider surface keeps list, actions, status, and errors keyboard-accessible', async () => {
  const source = await readFile(new URL('../pages/Providers.tsx', import.meta.url), 'utf8');
  assert.match(source, /aria-label="Provider instances"/);
  assert.match(source, /role="toolbar"/);
  assert.match(source, /role="status"/);
  assert.match(source, /role="alert"/);
  assert.match(source, /type="button"/);
  assert.match(source, /focus-visible:ring-2/);
});
