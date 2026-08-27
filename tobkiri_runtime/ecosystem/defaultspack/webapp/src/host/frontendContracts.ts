export type FrontendContributionKind =
  | "route"
  | "renderer"
  | "shell_region"
  | "action"
  | "data_source"
  | "settings"
  | "command";

export type FrontendContributionMode =
  | "declarative"
  | "isolated"
  | "same_origin_builtin";

/** A canonical SHA-256 digest exchanged with the verified frontend host. */
export type Sha256Digest = `sha256:${string}`;

const SHA256_DIGEST_PATTERN = /^sha256:[0-9a-f]{64}$/;

/** Return whether an untrusted value is a canonical SHA-256 digest. */
export function isSha256Digest(value: unknown): value is Sha256Digest {
  return typeof value === "string" && SHA256_DIGEST_PATTERN.test(value);
}

export type VerifiedFrontendContribution = {
  contribution_id: string;
  kind: FrontendContributionKind;
  mode: FrontendContributionMode;
  label: string;
  description?: string | null;
  priority: number;
  owner_pack_id: string;
  owner_pack_hash: Sha256Digest;
  build_identity: string;
  resolved_profile_revision: string;
  resolved_plan_hash: Sha256Digest;
  descriptor_hash: Sha256Digest;
  route?: string | null;
  region?: string | null;
  renderer?: string | null;
  action_contract?: string | null;
  data_source_contract?: string | null;
  schema?: Record<string, unknown> | null;
  view?: Record<string, unknown> | null;
  module?: {
    path: string;
    export: string;
    content_hash: Sha256Digest;
  } | null;
  isolated?: {
    path: string;
    rpc_contracts: string[];
  } | null;
  localization: Record<string, string>;
  accessibility: {
    name: string;
    keyboard: boolean;
    live?: "off" | "polite" | "assertive";
  };
};

export type FrontendCatalog = {
  version: "tobkiri.ui.contribution.v1";
  profile_id: string;
  profile_revision: string;
  plan_hash: Sha256Digest;
  contributions: VerifiedFrontendContribution[];
  diagnostics: Array<{
    code: string;
    severity: string;
    message: string;
    owner_pack_id?: string | null;
    contribution_id?: string | null;
  }>;
  quarantined_pack_ids: string[];
  catalog_hash: Sha256Digest;
};

export type CapabilityInvocation = {
  contractId: string;
  payload: Record<string, unknown>;
  contributionId: string;
  ownerPackId: string;
  planHash: Sha256Digest;
  catalogHash: Sha256Digest;
};

export type FrontendCapabilityClient = {
  invokeAction: (request: CapabilityInvocation) => Promise<unknown>;
  readDataSource: (request: CapabilityInvocation) => Promise<unknown>;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isStringRecord(value: unknown): value is Record<string, string> {
  return isRecord(value)
    && Object.values(value).every((item) => typeof item === "string");
}

function isVerifiedContribution(value: unknown): value is VerifiedFrontendContribution {
  if (!isRecord(value)) return false;
  const module = value.module;
  const isolated = value.isolated;
  const accessibility = value.accessibility;
  return typeof value.contribution_id === "string"
    && typeof value.kind === "string"
    && typeof value.mode === "string"
    && typeof value.label === "string"
    && typeof value.priority === "number"
    && typeof value.owner_pack_id === "string"
    && isSha256Digest(value.owner_pack_hash)
    && typeof value.build_identity === "string"
    && typeof value.resolved_profile_revision === "string"
    && isSha256Digest(value.resolved_plan_hash)
    && isSha256Digest(value.descriptor_hash)
    && isStringRecord(value.localization)
    && isRecord(accessibility)
    && typeof accessibility.name === "string"
    && typeof accessibility.keyboard === "boolean"
    && (accessibility.live === undefined
      || accessibility.live === "off"
      || accessibility.live === "polite"
      || accessibility.live === "assertive")
    && (module === undefined || module === null || (
      isRecord(module)
      && typeof module.path === "string"
      && typeof module.export === "string"
      && isSha256Digest(module.content_hash)
    ))
    && (isolated === undefined || isolated === null || (
      isRecord(isolated)
      && typeof isolated.path === "string"
      && Array.isArray(isolated.rpc_contracts)
      && isolated.rpc_contracts.every((item) => typeof item === "string")
    ));
}

/** Validate the backend-owned catalog before it enters the React host. */
export function isFrontendCatalog(value: unknown): value is FrontendCatalog {
  if (!isRecord(value)) return false;
  return value.version === "tobkiri.ui.contribution.v1"
    && typeof value.profile_id === "string"
    && typeof value.profile_revision === "string"
    && isSha256Digest(value.plan_hash)
    && Array.isArray(value.contributions)
    && value.contributions.every(isVerifiedContribution)
    && Array.isArray(value.diagnostics)
    && Array.isArray(value.quarantined_pack_ids)
    && value.quarantined_pack_ids.every((item) => typeof item === "string")
    && isSha256Digest(value.catalog_hash);
}
