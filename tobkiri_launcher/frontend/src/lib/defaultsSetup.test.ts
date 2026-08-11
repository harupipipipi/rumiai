import assert from 'node:assert/strict';
import test from 'node:test';
import {
  parseDefaultsActivationResponse,
  parseDefaultsSetupState,
  type DefaultsConfirmation,
} from './defaultsSetup';

function state() {
  return {
    setup_api_version: 'io.tobkiri.setup-state.v4',
    state: 'review_required',
    denial_diagnostic: null,
    packs: [{pack_id: 'defaultspack', display_name: 'Tobkiri Defaults'}],
    required_transaction: [
      'catalog.verify',
      'profile.resolve',
      'authority.snapshot',
      'activation.prepare',
      'activation.commit',
      'runtime.capture',
    ],
    recommended_default_profile: {
      available: true,
      profile_id: 'defaults',
      name: 'Tobkiri Defaults',
      base_pack: 'defaults-basepack',
      shell: {provider_id: 'shell.tauri.default', contract_id: 'app.shell.v1'},
      pack_ids: ['defaultspack'],
      packs: [{pack_id: 'defaultspack', display_name: 'Tobkiri Defaults'}],
      conversation_provider: 'defaultspack.conversation',
      confirmation: {
        confirmation_api_version: 'io.tobkiri.defaults-confirmation.v1',
        operation_id: 'defaults.activate',
        profile_id: 'defaults',
        catalog_revision: `sha256:${'1'.repeat(64)}`,
        profile_revision: `sha256:${'2'.repeat(64)}`,
        plan_digest: `sha256:${'3'.repeat(64)}`,
        authority_snapshot_digest: `sha256:${'4'.repeat(64)}`,
        security_epoch: 1,
        base: {
          pack_id: 'defaults-basepack',
          artifact_digest: `sha256:${'6'.repeat(64)}`,
          definition_digest: `sha256:${'7'.repeat(64)}`,
        },
        shell: {
          provider_id: 'shell.tauri.default',
          pack_id: 'shell.tauri.default',
          artifact_digest: `sha256:${'8'.repeat(64)}`,
          executable_artifact_digest: `sha256:${'e'.repeat(64)}`,
          contract_id: 'app.shell.v1',
          definition_digest: `sha256:${'9'.repeat(64)}`,
        },
        bindings: [{
          caller_function_id: 'shell.tauri.default',
          pack_id: 'defaultspack',
          artifact_digest: `sha256:${'a'.repeat(64)}`,
          contract_id: 'conversation.turn.v1',
          operation_id: 'complete',
          domain_kind: 'pack_vm',
          function_principal: {
            parent_artifact_digest: `sha256:${'a'.repeat(64)}`,
            function_implementation_digest: `sha256:${'b'.repeat(64)}`,
            function_id: 'defaultspack.conversation',
            contract_revision_digest: `sha256:${'c'.repeat(64)}`,
            operation_id: 'complete',
          },
          authority_reference: `authority-ref:${'f'.repeat(64)}`,
          requested_scope_digest: `sha256:${'d'.repeat(64)}`,
          adapter_digests: [],
        }],
        confirmation_digest: `sha256:${'5'.repeat(64)}`,
      },
    },
  };
}

function realActivationFixture(): {
  confirmation: DefaultsConfirmation;
  response: Record<string, unknown>;
} {
  const confirmation = {
    ...state().recommended_default_profile.confirmation,
    profile_revision: 'sha256:03eee62aa3851951d7bfe8ecfc4e64defc848e97cfe1ba96ace8e1a78d2cb164',
    plan_digest: 'sha256:8c02ac80815e6189b96d780ae969cb9c2b12af7cc156334de45c4767f9ce78d6',
    authority_snapshot_digest: 'sha256:a13c3777a0c41098a4d4a1b787c315756c5776c359719b369723ee1f96d10e22',
  } as DefaultsConfirmation;
  return {
    confirmation,
    response: {
      activation_id: 'activation:defaults-8c02ac80815e6189',
      audit_receipt: {
        activation_id: 'activation:defaults-8c02ac80815e6189',
        fencing_token: 1,
        reservation_id: 'activation-reservation:oJfXu2HtwTfNe-aRjwbgL19agiZWQHuk',
        state: 'committed',
      },
      authority_snapshot_digest: confirmation.authority_snapshot_digest,
      fencing_token: 1,
      plan_digest: confirmation.plan_digest,
      profile_id: 'defaults',
      profile_revision: confirmation.profile_revision,
      restart_required: false,
      security_epoch: 1,
      setup_api_version: 'io.tobkiri.setup-state.v4',
      state: 'active',
    },
  };
}

test('packaged authenticated setup payload shape accepts the v4 binding fields', () => {
  const parsed = parseDefaultsSetupState(state());
  assert.equal(parsed.state, 'review_required');
  assert.equal(parsed.denial_diagnostic, null);
  assert.deepEqual(parsed.required_transaction, [
    'catalog.verify',
    'profile.resolve',
    'authority.snapshot',
    'activation.prepare',
    'activation.commit',
    'runtime.capture',
  ]);
  assert.equal(
    parsed.recommended_default_profile.confirmation.shell.executable_artifact_digest,
    `sha256:${'e'.repeat(64)}`,
  );
  assert.equal(
    parsed.recommended_default_profile.confirmation.bindings[0].authority_reference,
    `authority-ref:${'f'.repeat(64)}`,
  );
});

test('typed setup contract requires a valid executable artifact digest', () => {
  const missing = state();
  delete (missing.recommended_default_profile.confirmation.shell as Record<string, unknown>)
    .executable_artifact_digest;
  assert.throws(
    () => parseDefaultsSetupState(missing),
    /Confirmed Shell has unknown or missing fields/,
  );

  const invalid = state();
  (invalid.recommended_default_profile.confirmation.shell as Record<string, unknown>)
    .executable_artifact_digest = 'sha256:not-a-digest';
  assert.throws(
    () => parseDefaultsSetupState(invalid),
    /Confirmed Shell executable artifact digest is invalid/,
  );
});

test('typed setup contract rejects extra confirmation shell fields', () => {
  const extra = state();
  (extra.recommended_default_profile.confirmation.shell as Record<string, unknown>)
    .untrusted_digest = `sha256:${'f'.repeat(64)}`;
  assert.throws(
    () => parseDefaultsSetupState(extra),
    /Confirmed Shell has unknown or missing fields/,
  );
});

test('packaged setup parser rejects binding field drift and projection tampering', () => {
  const extra = state();
  (extra.recommended_default_profile.confirmation.bindings[0] as Record<string, unknown>)
    .provider_authority_digest = `sha256:${'f'.repeat(64)}`;
  assert.throws(
    () => parseDefaultsSetupState(extra),
    /Defaults binding has unknown or missing fields/,
  );

  const missing = state();
  delete (missing.recommended_default_profile.confirmation.bindings[0] as Record<string, unknown>)
    .requested_scope_digest;
  assert.throws(
    () => parseDefaultsSetupState(missing),
    /Defaults binding has unknown or missing fields/,
  );

  const invalidAuthority = state();
  invalidAuthority.recommended_default_profile.confirmation.bindings[0].authority_reference = 'authority-ref:test';
  assert.throws(
    () => parseDefaultsSetupState(invalidAuthority),
    /Defaults binding authority reference is invalid/,
  );

  const projection = state();
  projection.packs[0].display_name = 'Tampered Pack';
  assert.throws(
    () => parseDefaultsSetupState(projection),
    /Defaults setup Pack projection does not match the Profile/,
  );
});

test('typed setup contract fails closed on provider mismatch or duplication', () => {
  const missing = state();
  missing.recommended_default_profile.confirmation.bindings = [];
  assert.throws(() => parseDefaultsSetupState(missing), /exactly one conversation provider/);

  const duplicate = state();
  duplicate.recommended_default_profile.confirmation.bindings.push(
    {...duplicate.recommended_default_profile.confirmation.bindings[0]},
  );
  assert.throws(() => parseDefaultsSetupState(duplicate), /exactly one conversation provider/);
});

test('typed setup contract rejects legacy and unknown state shapes', () => {
  assert.throws(
    () => parseDefaultsSetupState({state: 'legacy_setup_retired'}),
    /unknown or missing fields/,
  );
});

test('preserved packaged activation success is bound to the submitted confirmation', () => {
  const fixture = realActivationFixture();
  const parsed = parseDefaultsActivationResponse(fixture.response, fixture.confirmation);
  assert.equal(parsed.activation_id, 'activation:defaults-8c02ac80815e6189');
  assert.equal(parsed.audit_receipt.reservation_id, 'activation-reservation:oJfXu2HtwTfNe-aRjwbgL19agiZWQHuk');
  assert.equal(parsed.security_epoch, fixture.confirmation.security_epoch);
});

test('activation evidence rejects every digest, epoch, token, and identity tamper', () => {
  const tamperCases: Array<[string, (response: Record<string, unknown>) => void]> = [
    ['profile revision', (response) => { response.profile_revision = `sha256:${'f'.repeat(64)}`; }],
    ['plan digest', (response) => { response.plan_digest = `sha256:${'f'.repeat(64)}`; }],
    ['authority snapshot', (response) => {
      response.authority_snapshot_digest = `sha256:${'f'.repeat(64)}`;
    }],
    ['profile revision malformed', (response) => { response.profile_revision = 'sha256:not-a-digest'; }],
    ['security epoch equality', (response) => { response.security_epoch = 2; }],
    ['security epoch string', (response) => { response.security_epoch = '1'; }],
    ['security epoch negative', (response) => { response.security_epoch = -1; }],
    ['fencing token zero', (response) => { response.fencing_token = 0; }],
    ['fencing token string', (response) => { response.fencing_token = '1'; }],
    ['fencing token negative', (response) => { response.fencing_token = -1; }],
    ['activation identity empty', (response) => { response.activation_id = ''; }],
    ['activation identity noncanonical', (response) => { response.activation_id = 'activation:test'; }],
    ['reservation identity empty', (response) => {
      (response.audit_receipt as Record<string, unknown>).reservation_id = '';
    }],
    ['reservation identity noncanonical', (response) => {
      (response.audit_receipt as Record<string, unknown>).reservation_id = 'reservation:test';
    }],
    ['audit activation binding', (response) => {
      (response.audit_receipt as Record<string, unknown>).activation_id = 'activation:defaults-aaaaaaaa';
    }],
    ['audit fencing binding', (response) => {
      (response.audit_receipt as Record<string, unknown>).fencing_token = 2;
    }],
  ];

  for (const [label, mutate] of tamperCases) {
    const fixture = realActivationFixture();
    mutate(fixture.response);
    assert.throws(
      () => parseDefaultsActivationResponse(fixture.response, fixture.confirmation),
      undefined,
      label,
    );
  }
});

test('activation evidence rejects a tampered submitted confirmation', () => {
  const fields = ['profile_revision', 'plan_digest', 'authority_snapshot_digest'] as const;
  for (const field of fields) {
    const fixture = realActivationFixture();
    const confirmation = {
      ...fixture.confirmation,
      [field]: `sha256:${'f'.repeat(64)}`,
    } as DefaultsConfirmation;
    assert.throws(
      () => parseDefaultsActivationResponse(fixture.response, confirmation),
      /does not match the submitted confirmation/,
      field,
    );
  }

  const epochFixture = realActivationFixture();
  assert.throws(
    () => parseDefaultsActivationResponse(
      epochFixture.response,
      {...epochFixture.confirmation, security_epoch: 2},
    ),
    /does not match the submitted confirmation/,
  );
});
