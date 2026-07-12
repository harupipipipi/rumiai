export function codingActionRequiresApproval(result: unknown): boolean {
  if (!result || typeof result !== "object" || Array.isArray(result)) return false;
  const record = result as Record<string, unknown>;
  return record.approval_required === true || Boolean(record.approval_request);
}

export function nextApprovalQueueRefreshSignal(current: number, result: unknown): number {
  return codingActionRequiresApproval(result) ? current + 1 : current;
}
