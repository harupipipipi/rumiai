import {
  fetchFrontendContractOperation,
} from './api';
import {
  assertVerifiedRuntimeTarget,
  RUNTIME_PROFILE_CEREMONY_TARGETS as GENERATED_PROFILE_CEREMONY_TARGETS,
  RuntimeSurfaceError,
  RUNTIME_SURFACE_API_VERSION,
  validateRuntimeSurfaceEnvelope,
  type RuntimeSurfaceEnvelope,
  type RuntimeSurfaceTarget,
} from './runtimeSurface';

export type ProfileCeremonyStep = 'resolve' | 'review' | 'approve' | 'activate';

export interface ProfileCeremonyTargets {
  resolve?: RuntimeSurfaceTarget;
  review?: RuntimeSurfaceTarget;
  approve?: RuntimeSurfaceTarget;
  activate?: RuntimeSurfaceTarget;
}

/** Profile ceremony targets are generated from the verified frontend map. */
export const RUNTIME_PROFILE_CEREMONY_TARGETS: ProfileCeremonyTargets = GENERATED_PROFILE_CEREMONY_TARGETS;

export interface ProfileResolveInput {
  profile_id: string;
  expected_profile_revision: string;
  expected_plan_digest: string;
  desired_pack_ids: string[];
}

export interface ProfileReviewInput {
  candidate_id: string;
  candidate_digest: string;
}

export interface ProfileApproveInput {
  candidate_id: string;
  candidate_digest: string;
}

export interface ProfileActivateInput {
  approval_id: string;
  approval_digest: string;
}

export interface ProfileResolveResult {
  state: 'resolved';
  candidate_id: string;
  candidate_digest: string;
  expires_in: number;
  review: {
    profile: unknown;
    profile_lock: unknown;
    resolved_plan: unknown;
    predecessor: unknown;
  };
  next_action: 'review';
  write_set: unknown[];
}

export interface ProfileReviewResult {
  state: 'reviewed';
  candidate_id: string;
  candidate_digest: string;
  next_action: 'approval';
  write_set: unknown[];
  review?: ProfileResolveResult['review'];
}

export interface ProfileApproveResult {
  state: 'approved';
  approval_id: string;
  approval_digest: string;
  expires_in: number;
  next_action: 'activation';
  write_set: unknown[];
  authority_approval: {
    approval_id: string;
    approval_digest: string;
    decision: string;
    security_epoch: number;
  };
}

export interface ProfileActivateResult {
  state: 'active';
  profile_id: string;
  activation_id: string;
  plan_digest: string;
  security_epoch: number;
  fencing_token: number;
  authoritative_snapshot: RuntimeSurfaceEnvelope<unknown>;
}

export interface ProfileCeremonyErrorData {
  runtime_surface_api_version?: string;
  state: 'error';
  code: 'PROFILE_NOT_ACTIVE' | 'STALE_REVISION' | 'DIGEST_MISMATCH' | 'UNAPPROVED' | 'TIMEOUT' | 'INVALID_REQUEST' | 'API_FAILURE';
  message: string;
  retryable: boolean;
  write_set: unknown[];
}

export interface ProfileCeremonyTransport {
  write<T>(target: RuntimeSurfaceTarget, payload: Record<string, unknown>): Promise<T>;
}

const canonicalTransport: ProfileCeremonyTransport = {
  write: <T>(target: RuntimeSurfaceTarget, payload: Record<string, unknown>) => (
    fetchFrontendContractOperation<T>(target.method, target.logical_target, payload)
  ),
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function requiredString(value: unknown, field: string): string {
  if (typeof value !== 'string' || value.length === 0) {
    throw new RuntimeSurfaceError('INVALID', `Profile ceremony response is missing ${field}.`);
  }
  return value;
}

function requiredNumber(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) {
    throw new RuntimeSurfaceError('INVALID', `Profile ceremony response is missing ${field}.`);
  }
  return value;
}

function requiredDigest(value: unknown, field: string): string {
  const digest = requiredString(value, field);
  if (!/^sha256:[0-9a-f]{64}$/.test(digest)) {
    throw new RuntimeSurfaceError('INVALID', `Profile ceremony response has an invalid ${field}.`);
  }
  return digest;
}

function requiredInteger(value: unknown, field: string): number {
  const number = requiredNumber(value, field);
  if (!Number.isInteger(number)) {
    throw new RuntimeSurfaceError('INVALID', `Profile ceremony response is missing ${field}.`);
  }
  return number;
}

function requiredWriteSet(value: unknown): unknown[] {
  if (!Array.isArray(value)) {
    throw new RuntimeSurfaceError('INVALID', 'Profile ceremony response has no write_set.');
  }
  return value;
}

function responseRecord(value: unknown): Record<string, unknown> {
  if (!isRecord(value)) {
    throw new RuntimeSurfaceError('INVALID', 'Profile ceremony response is not an object.');
  }
  if (value.state === 'error') {
    const code = value.code;
    const message = value.message;
    if (
      value.runtime_surface_api_version === RUNTIME_SURFACE_API_VERSION
      && typeof code === 'string'
      && typeof message === 'string'
      && typeof value.retryable === 'boolean'
      && Array.isArray(value.write_set)
    ) {
      const mapped = code === 'STALE_REVISION'
        ? 'STALE'
        : code === 'DIGEST_MISMATCH'
          ? 'DIGEST_MISMATCH'
          : code === 'PROFILE_NOT_ACTIVE'
            ? 'PROFILE_NOT_ACTIVE'
            : code === 'UNAPPROVED'
              ? 'APPROVAL_DENIED'
              : code === 'TIMEOUT'
                ? 'TIMEOUT'
                : code === 'INVALID_REQUEST'
                  ? 'INVALID'
                  : 'FAILED';
      throw new RuntimeSurfaceError(mapped, message);
    }
    throw new RuntimeSurfaceError('FAILED', 'The Profile ceremony failed closed.');
  }
  if (value.runtime_surface_api_version !== RUNTIME_SURFACE_API_VERSION) {
    throw new RuntimeSurfaceError('INVALID', 'Profile ceremony response has an invalid API version.');
  }
  return value;
}

function exactMutationPayload(step: ProfileCeremonyStep, value: unknown): Record<string, unknown> {
  if (!isRecord(value)) {
    throw new RuntimeSurfaceError('INVALID', `Profile ${step} request is not an object.`);
  }
  const expectedKeys = step === 'resolve'
    ? ['profile_id', 'expected_profile_revision', 'expected_plan_digest', 'desired_pack_ids']
    : step === 'activate'
      ? ['approval_id', 'approval_digest']
      : ['candidate_id', 'candidate_digest'];
  const keys = Object.keys(value).sort();
  if (keys.length !== expectedKeys.length || keys.some((key, index) => key !== [...expectedKeys].sort()[index])) {
    throw new RuntimeSurfaceError('INVALID', `Profile ${step} request contains an unknown field.`);
  }
  if (step === 'resolve') {
    if (value.profile_id !== 'defaults'
      || !isSha256(value.expected_profile_revision)
      || !isSha256(value.expected_plan_digest)
      || !Array.isArray(value.desired_pack_ids)
      || value.desired_pack_ids.length === 0
      || value.desired_pack_ids.some((item) => !validRequestString(item))) {
      throw new RuntimeSurfaceError('INVALID', 'Profile resolve request is invalid.');
    }
  } else if (step === 'activate') {
    if (!validRequestString(value.approval_id) || !isSha256(value.approval_digest)) {
      throw new RuntimeSurfaceError('INVALID', 'Profile activation request is invalid.');
    }
  } else if (!validRequestString(value.candidate_id) || !isSha256(value.candidate_digest)) {
    throw new RuntimeSurfaceError('INVALID', `Profile ${step} request is invalid.`);
  }
  return value;
}

function validRequestString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

function isSha256(value: unknown): value is string {
  return typeof value === 'string' && /^sha256:[0-9a-f]{64}$/.test(value);
}

function targetFor(targets: ProfileCeremonyTargets, step: ProfileCeremonyStep): RuntimeSurfaceTarget {
  const target = targets[step];
  if (!target) {
    throw new RuntimeSurfaceError('UNAVAILABLE', 'Profile ceremony is not exposed by the generated Protocol v4 map yet.');
  }
  if (target.method !== 'POST') {
    throw new RuntimeSurfaceError('INVALID', 'Profile ceremony mutation target must be POST.');
  }
  assertVerifiedRuntimeTarget(target);
  return target;
}

function validateResolve(value: unknown): ProfileResolveResult {
  const result = responseRecord(value);
  if (result.state !== 'resolved' || !isRecord(result.review) || result.next_action !== 'review') {
    throw new RuntimeSurfaceError('INVALID', 'Profile resolve returned an invalid ceremony state.');
  }
  const reviewKeys = ['profile', 'profile_lock', 'resolved_plan', 'predecessor'];
  if (reviewKeys.some((key) => !Object.prototype.hasOwnProperty.call(result.review, key))) {
    throw new RuntimeSurfaceError('INVALID', 'Profile resolve did not publish the exact candidate review records.');
  }
  return {
    state: 'resolved',
    candidate_id: requiredString(result.candidate_id, 'candidate_id'),
    candidate_digest: requiredDigest(result.candidate_digest, 'candidate_digest'),
    expires_in: requiredNumber(result.expires_in, 'expires_in'),
    review: {
      profile: result.review.profile,
      profile_lock: result.review.profile_lock,
      resolved_plan: result.review.resolved_plan,
      predecessor: result.review.predecessor,
    },
    next_action: 'review',
    write_set: requiredWriteSet(result.write_set),
  };
}

function validateReview(value: unknown): ProfileReviewResult {
  const result = responseRecord(value);
  if (result.state !== 'reviewed' || result.next_action !== 'approval') {
    throw new RuntimeSurfaceError('INVALID', 'Profile review returned an invalid ceremony state.');
  }
  return {
    state: 'reviewed',
    candidate_id: requiredString(result.candidate_id, 'candidate_id'),
    candidate_digest: requiredDigest(result.candidate_digest, 'candidate_digest'),
    next_action: 'approval',
    write_set: requiredWriteSet(result.write_set),
    ...(isRecord(result.review) ? {review: result.review as ProfileResolveResult['review']} : {}),
  };
}

function validateApprove(value: unknown): ProfileApproveResult {
  const result = responseRecord(value);
  if (result.state !== 'approved' || result.next_action !== 'activation') {
    throw new RuntimeSurfaceError('INVALID', 'Profile approval returned an invalid ceremony state.');
  }
  return {
    state: 'approved',
    approval_id: requiredString(result.approval_id, 'approval_id'),
    approval_digest: requiredDigest(result.approval_digest, 'approval_digest'),
    expires_in: requiredNumber(result.expires_in, 'expires_in'),
    next_action: 'activation',
    write_set: requiredWriteSet(result.write_set),
    authority_approval: (() => {
      if (!isRecord(result.authority_approval)) {
        throw new RuntimeSurfaceError('INVALID', 'Profile approval has no Authority Kernel record.');
      }
      return {
        approval_id: (() => {
          const approvalId = requiredString(result.authority_approval.approval_id, 'authority_approval.approval_id');
          if (approvalId !== result.approval_id) {
            throw new RuntimeSurfaceError('DIGEST_MISMATCH', 'Authority approval is bound to a different approval id.');
          }
          return approvalId;
        })(),
        approval_digest: (() => {
          const approvalDigest = requiredDigest(result.authority_approval.approval_digest, 'authority_approval.approval_digest');
          if (approvalDigest !== result.approval_digest) {
            throw new RuntimeSurfaceError('DIGEST_MISMATCH', 'Authority approval digest does not match the activation credential.');
          }
          return approvalDigest;
        })(),
        decision: (() => {
          const decision = requiredString(result.authority_approval.decision, 'authority_approval.decision');
          if (decision !== 'approved') {
            throw new RuntimeSurfaceError('APPROVAL_DENIED', 'Authority Kernel did not approve this Profile candidate.');
          }
          return decision;
        })(),
        security_epoch: requiredInteger(result.authority_approval.security_epoch, 'authority_approval.security_epoch'),
      };
    })(),
  };
}

function validateActivate(value: unknown): ProfileActivateResult {
  const result = responseRecord(value);
  if (result.state !== 'active') {
    throw new RuntimeSurfaceError('INVALID', 'Profile activation returned an invalid ceremony state.');
  }
  const profileId = requiredString(result.profile_id, 'profile_id');
  const planDigest = requiredDigest(result.plan_digest, 'plan_digest');
  const activationId = requiredString(result.activation_id, 'activation_id');
  const securityEpoch = requiredInteger(result.security_epoch, 'security_epoch');
  const fencingToken = requiredInteger(result.fencing_token, 'fencing_token');
  const authoritativeSnapshot = validateRuntimeSurfaceEnvelope(
    'profile',
    result.authoritative_snapshot,
  );
  if (
    authoritativeSnapshot.profile_id !== profileId
    || authoritativeSnapshot.plan_digest !== planDigest
  ) {
    throw new RuntimeSurfaceError(
      'DIGEST_MISMATCH',
      'Profile activation snapshot does not match the activated Profile and Plan.',
    );
  }
  return {
    state: 'active',
    profile_id: profileId,
    activation_id: activationId,
    plan_digest: planDigest,
    security_epoch: securityEpoch,
    fencing_token: fencingToken,
    authoritative_snapshot: authoritativeSnapshot,
  };
}

export interface ProfileCeremonyClient {
  resolve(input: ProfileResolveInput): Promise<ProfileResolveResult>;
  review(input: ProfileReviewInput): Promise<ProfileReviewResult>;
  approve(input: ProfileApproveInput): Promise<ProfileApproveResult>;
  activate(input: ProfileActivateInput): Promise<ProfileActivateResult>;
}

export function createProfileCeremonyClient(
  targets: ProfileCeremonyTargets = RUNTIME_PROFILE_CEREMONY_TARGETS,
  transport: ProfileCeremonyTransport = canonicalTransport,
): ProfileCeremonyClient {
  const write = async <T>(step: ProfileCeremonyStep, payload: Record<string, unknown>, validate: (value: unknown) => T): Promise<T> => {
    const result = await transport.write<unknown>(targetFor(targets, step), payload);
    return validate(result);
  };
  return {
    resolve: (input) => write('resolve', exactMutationPayload('resolve', input), validateResolve),
    review: (input) => write('review', exactMutationPayload('review', input), validateReview),
    approve: (input) => write('approve', exactMutationPayload('approve', input), validateApprove),
    activate: (input) => write('activate', exactMutationPayload('activate', input), validateActivate),
  };
}

export const defaultProfileCeremonyClient = createProfileCeremonyClient();

export interface ProfileCeremonySnapshot {
  profile_id: string;
  profile_revision: string;
  plan_digest: string;
}

export function snapshotForProfileCeremony<T>(
  envelope: RuntimeSurfaceEnvelope<T> | null,
): ProfileCeremonySnapshot | null {
  if (!envelope || envelope.state !== 'ready') return null;
  return {
    profile_id: envelope.profile_id,
    profile_revision: envelope.profile_revision,
    plan_digest: envelope.plan_digest,
  };
}
