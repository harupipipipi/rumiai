import assert from 'node:assert/strict';
import test from 'node:test';
import {parseDefaultsSetupState} from './defaultsSetup';

function state() {
  return {
    setup_api_version: 'io.tobkiri.setup-state.v4',
    state: 'review_required',
    packs: [{pack_id: 'defaultspack', display_name: 'Tobkiri Defaults'}],
    required_transaction: ['catalog.verify'],
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
        }],
        confirmation_digest: `sha256:${'5'.repeat(64)}`,
      },
    },
  };
}

test('typed setup contract accepts one exact conversation provider', () => {
  const parsed = parseDefaultsSetupState(state());
  assert.equal(parsed.state, 'review_required');
  assert.equal(
    parsed.recommended_default_profile.confirmation.shell.executable_artifact_digest,
    `sha256:${'e'.repeat(64)}`,
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
