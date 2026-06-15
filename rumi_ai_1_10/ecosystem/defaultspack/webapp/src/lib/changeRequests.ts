import { defaultspackApiFetch, explainDefaultspackApiError } from "./api";

export type ChangeRequestStatus = "open" | "closed" | "draft" | "stale" | string;

export type ChangeRequestCheckSummary = {
  total?: number;
  passed?: number;
  failed?: number;
  pending?: number;
  skipped?: number;
  label?: string;
};

export type ChangeRequestFile = {
  path: string;
  status?: string;
  additions?: number;
  deletions?: number;
  binary?: boolean;
  untracked?: boolean;
  generated?: boolean;
  docs?: boolean;
  test?: boolean;
  highRisk?: boolean;
  large?: boolean;
};

export type ChangeRequestSnapshot = {
  id?: string;
  created_at?: string;
  signature?: string;
  diff?: string;
  stat?: string;
  files?: ChangeRequestFile[];
};

export type ChangeRequestDrift = {
  changed?: boolean;
  stale?: boolean;
  has_drift?: boolean;
  mismatched?: boolean;
  base_changed?: boolean;
  previous_working_tree_hash?: string;
  current_working_tree_hash?: string;
  snapshot_working_tree_hash?: string;
  added_paths?: string[];
  removed_paths?: string[];
  changed_paths?: string[];
};

export type ChangeRequestRecord = {
  id: string;
  status: ChangeRequestStatus;
  title?: string;
  summary?: string;
  created_at?: string;
  updated_at?: string;
  workspace_id?: string | null;
  check_summary?: ChangeRequestCheckSummary;
  snapshot?: ChangeRequestSnapshot;
  drift?: ChangeRequestDrift;
  is_stale?: boolean;
  current_working_tree_hash?: string;
  snapshot_working_tree_hash?: string;
  files?: ChangeRequestFile[];
};

export type ChangeRequestListResponse = {
  reviews: ChangeRequestRecord[];
  open: ChangeRequestRecord[];
  closed: ChangeRequestRecord[];
  apiAvailable: boolean;
};

type ApiEnvelope<T> = { status?: string; data?: T; error?: { code?: string; message?: string } };

function withQuery(path: string, params?: Record<string, unknown>): string {
  if (!params) return path;
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    query.set(key, String(value));
  }
  const suffix = query.toString();
  return suffix ? `${path}?${suffix}` : path;
}

function readString(record: Record<string, unknown>, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return undefined;
}

function readNumber(record: Record<string, unknown>, keys: string[]): number | undefined {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
  }
  return undefined;
}

function readBoolean(record: Record<string, unknown>, keys: string[]): boolean | undefined {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "boolean") return value;
  }
  return undefined;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function normalizeCheckSummary(value: unknown): ChangeRequestCheckSummary | undefined {
  const record = asRecord(value);
  if (!record) return undefined;
  return {
    total: readNumber(record, ["total", "count"]),
    passed: readNumber(record, ["passed", "ok", "success"]),
    failed: readNumber(record, ["failed", "failures", "error"]),
    pending: readNumber(record, ["pending", "running"]),
    skipped: readNumber(record, ["skipped"]),
    label: readString(record, ["label", "summary", "status"]),
  };
}

function normalizeFile(value: unknown): ChangeRequestFile | null {
  if (typeof value === "string") return { path: value };
  const record = asRecord(value);
  if (!record) return null;
  const path = readString(record, ["path", "file", "name"]);
  if (!path) return null;
  return {
    path,
    status: readString(record, ["status", "change_type", "kind"]),
    additions: readNumber(record, ["additions", "added"]),
    deletions: readNumber(record, ["deletions", "deleted"]),
    binary: record.binary === true,
    untracked: record.untracked === true,
    generated: record.generated === true,
    docs: record.docs === true,
    test: record.test === true,
    highRisk: record.high_risk === true || record.highRisk === true,
    large: record.large === true,
  };
}

function normalizeFiles(value: unknown): ChangeRequestFile[] {
  return Array.isArray(value) ? value.map(normalizeFile).filter((file): file is ChangeRequestFile => file !== null) : [];
}

function mergeFiles(...groups: Array<ChangeRequestFile[] | undefined>): ChangeRequestFile[] {
  const byPath = new Map<string, ChangeRequestFile>();
  for (const group of groups) {
    for (const file of group ?? []) {
      byPath.set(file.path, { ...byPath.get(file.path), ...file });
    }
  }
  return [...byPath.values()];
}

function normalizeStringList(value: unknown): string[] | undefined {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && item.length > 0) : undefined;
}

function normalizeSnapshot(value: unknown): ChangeRequestSnapshot | undefined {
  const record = asRecord(value);
  if (!record) return undefined;
  const signature = readString(record, ["signature", "tree_signature", "working_tree_signature", "working_tree_hash"]);
  const diff = readString(record, ["diff", "patch", "normalized_patch"]);
  const stat = readString(record, ["stat", "diff_stat"]);
  const files = normalizeFiles(record.files ?? record.file_stats);
  if (!signature && !diff && !stat && files.length === 0) return undefined;
  return {
    id: readString(record, ["id", "snapshot_id"]),
    created_at: readString(record, ["created_at", "createdAt"]),
    signature,
    diff,
    stat,
    files,
  };
}

function normalizeDrift(value: unknown): ChangeRequestDrift | undefined {
  const record = asRecord(value);
  if (!record) return undefined;
  const drift: ChangeRequestDrift = {
    changed: readBoolean(record, ["changed"]),
    stale: readBoolean(record, ["stale"]),
    has_drift: readBoolean(record, ["has_drift"]),
    mismatched: readBoolean(record, ["mismatched"]),
    base_changed: readBoolean(record, ["base_changed"]),
    previous_working_tree_hash: readString(record, ["previous_working_tree_hash", "previous_worktree_hash"]),
    current_working_tree_hash: readString(record, ["current_working_tree_hash", "current_worktree_hash"]),
    snapshot_working_tree_hash: readString(record, ["snapshot_working_tree_hash", "snapshot_worktree_hash"]),
    added_paths: normalizeStringList(record.added_paths),
    removed_paths: normalizeStringList(record.removed_paths),
    changed_paths: normalizeStringList(record.changed_paths ?? record.mismatch_paths),
  };
  return Object.values(drift).some((item) => item !== undefined) ? drift : undefined;
}

function normalizeReview(value: unknown): ChangeRequestRecord | null {
  const record = asRecord(value);
  if (!record) return null;
  const id = readString(record, ["id", "change_request_id", "cr_id", "review_id"]);
  if (!id) return null;
  const status = readString(record, ["status", "state"]) ?? "open";
  const snapshot = normalizeSnapshot(record.snapshot ?? record.latest_snapshot ?? record.base_snapshot ?? record);
  const topLevelFiles = normalizeFiles(record.files ?? record.file_stats);
  const drift = normalizeDrift(record.drift ?? record.last_drift);
  return {
    id,
    status,
    title: readString(record, ["title", "name"]),
    summary: readString(record, ["summary", "description"]),
    created_at: readString(record, ["created_at", "createdAt"]),
    updated_at: readString(record, ["updated_at", "updatedAt"]),
    workspace_id: readString(record, ["workspace_id"]) ?? null,
    check_summary: normalizeCheckSummary(record.check_summary ?? record.checks),
    snapshot,
    drift,
    is_stale: readBoolean(record, ["is_stale", "stale"]),
    current_working_tree_hash: readString(record, ["current_working_tree_hash", "current_worktree_hash"]),
    snapshot_working_tree_hash: readString(record, ["snapshot_working_tree_hash", "snapshot_worktree_hash"]),
    files: mergeFiles(topLevelFiles, snapshot?.files),
  };
}

async function decodeResponse<T>(response: Response): Promise<T> {
  let envelope: ApiEnvelope<T>;
  try {
    envelope = await response.json() as ApiEnvelope<T>;
  } catch {
    if (!response.ok) throw new Error(explainDefaultspackApiError(response.status, undefined, response.statusText));
    throw new Error("Change request API returned invalid JSON");
  }
  if (!response.ok || envelope.status === "error") {
    throw new Error(explainDefaultspackApiError(
      response.status,
      envelope.status === "error" ? envelope.error : undefined,
      response.statusText,
    ));
  }
  return (envelope.data ?? envelope) as T;
}

async function requestChangeRequest<T>(path: string, init?: RequestInit): Promise<T | null> {
  const response = await defaultspackApiFetch(path, { cache: "no-store", ...init });
  if (response.status === 404 || response.status === 405) return null;
  return decodeResponse<T>(response);
}

export async function listChangeRequests(options?: { workspace_id?: string | null }): Promise<ChangeRequestListResponse> {
  const payload = await requestChangeRequest<unknown>(
    withQuery("/api/change-requests", { workspace_id: options?.workspace_id }),
  );
  if (payload === null) return { reviews: [], open: [], closed: [], apiAvailable: false };
  const record = asRecord(payload);
  const rawReviews = Array.isArray(payload)
    ? payload
    : Array.isArray(record?.reviews)
      ? record.reviews
      : Array.isArray(record?.change_requests)
        ? record.change_requests
        : [];
  const reviews = rawReviews.map(normalizeReview).filter((review): review is ChangeRequestRecord => review !== null);
  return {
    reviews,
    open: reviews.filter((review) => !String(review.status).toLowerCase().includes("closed")),
    closed: reviews.filter((review) => String(review.status).toLowerCase().includes("closed")),
    apiAvailable: true,
  };
}

export async function createChangeRequest(payload: { workspace_id?: string | null }): Promise<ChangeRequestRecord | null> {
  const result = await requestChangeRequest<unknown>("/api/change-requests", {
    method: "POST",
    body: JSON.stringify({
      domain: "change_request",
      source: "working_tree",
      workspace_id: payload.workspace_id,
    }),
  });
  const record = asRecord(result);
  return normalizeReview(record?.review ?? record?.change_request ?? result);
}

export async function getChangeRequest(reviewId: string): Promise<ChangeRequestRecord | null> {
  const result = await requestChangeRequest<unknown>(`/api/change-requests/${encodeURIComponent(reviewId)}`);
  const record = asRecord(result);
  return normalizeReview(record?.review ?? record?.change_request ?? result);
}

export async function refreshChangeRequest(reviewId: string, payload: { workspace_id?: string | null }): Promise<ChangeRequestRecord | null> {
  const result = await requestChangeRequest<unknown>(`/api/change-requests/${encodeURIComponent(reviewId)}/refresh`, {
    method: "POST",
    body: JSON.stringify({ workspace_id: payload.workspace_id }),
  });
  const record = asRecord(result);
  const review = normalizeReview(record?.review ?? record?.change_request ?? result);
  if (!review) return null;
  return {
    ...review,
    drift: normalizeDrift(record?.drift) ?? review.drift,
    is_stale: false,
  };
}
