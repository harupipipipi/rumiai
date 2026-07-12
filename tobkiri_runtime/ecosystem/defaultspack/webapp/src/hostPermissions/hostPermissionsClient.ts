import { api, type AuthorityRequest } from "../lib/api";
import { fetchDesktopSystemInfo, type DesktopSystemInfo } from "../lib/desktopSystemInfo";
import { buildHostPermissionRows, hostPermissionSummary, type HostPermissionRow } from "./hostPermissions";

export type HostPermissionsSnapshot = {
  info: DesktopSystemInfo | null;
  authorityRequests: AuthorityRequest[];
  rows: HostPermissionRow[];
  summary: ReturnType<typeof hostPermissionSummary>;
  authorityError?: string;
};

export async function fetchHostPermissionsSnapshot(): Promise<HostPermissionsSnapshot> {
  const [info, authorityResult] = await Promise.all([
    fetchDesktopSystemInfo(),
    api.listAuthorityRequests({ status: "all" })
      .then((result) => ({ result, error: "" }))
      .catch((error) => ({
        result: { requests: [], pending: [], count: 0 },
        error: error instanceof Error ? error.message : "Authority requests are unavailable.",
      })),
  ]);
  const authorityRequests = authorityResult.result.requests;
  const rows = buildHostPermissionRows(info, authorityRequests);
  return {
    info,
    authorityRequests,
    rows,
    summary: hostPermissionSummary(rows),
    ...(authorityResult.error ? { authorityError: authorityResult.error } : {}),
  };
}
