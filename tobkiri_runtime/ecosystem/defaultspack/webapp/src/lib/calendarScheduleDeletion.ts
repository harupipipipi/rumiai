export type DeleteCalendarSchedule = (scheduleId: string) => Promise<unknown>;

/**
 * Delete the backend schedule before callers remove or detach its calendar item.
 * A rejection deliberately propagates so the editor can keep the local item and
 * offer the same action again.
 */
export async function deleteCalendarScheduleBeforeLocalChange(
  scheduleId: string | undefined,
  deleteSchedule: DeleteCalendarSchedule,
): Promise<void> {
  if (!scheduleId) return;
  await deleteSchedule(scheduleId);
}
