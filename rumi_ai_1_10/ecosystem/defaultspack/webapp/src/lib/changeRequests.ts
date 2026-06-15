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

function normalizeSnapshot(value: unknown): ChangeRequestSnapshot | undefined {
  const record = asRecord(value);
  if (!record) return undefined;
  return {
    id: readString(record, ["id", "snapshot_id"]),
    created_at: readString(record, ["created_at", "createdAt"]),
    signature: readString(record, ["signature", "tree_signature", "working_tree_signature", "working_tree_hash"]),
    diff: readString(record, ["diff", "patch", "normalized_patch"]),
    stat: readString(record, ["stat", "diff_stat"]),
    files: normalizeFiles(record.files ?? record.file_stats),
  };
}

function normalizeReview(value: unknown): ChangeRequestRecord | null {
  const record = asRecord(value);
  if (!record) return null;
  const id = readString(record, ["id", "change_request_id", "cr_id", "review_id"]);
  if (!id) return null;
  const status = readString(record, ["status", "state"]) ?? "open";
  const snapshot = normalizeSnapshot(record.snapshot ?? record.latest_snapshot ?? record.base_snapshot);
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
    files: normalizeFiles(record.files).concat(snapshot?.files ?? []),
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

export async function refreshChangeRequest(reviewId: string, payload: { workspace_id?: string | null }): Promise<ChangeRequestRecord | null> {
  const result = await requestChangeRequest<unknown>(`/api/change-requests/${encodeURIComponent(reviewId)}/refresh`, {
    method: "POST",
    body: JSON.stringify({ workspace_id: payload.workspace_id }),
  });
  const record = asRecord(result);
  return normalizeReview(record?.review ?? record?.change_request ?? result);
}
