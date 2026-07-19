import assert from "node:assert/strict";
import test from "node:test";

import {
  beginCalendarMutation,
  cancelCalendarMutation,
  CALENDAR_DOCUMENT_KEY,
  CALENDAR_JOURNAL_KEY,
  CALENDAR_LEGACY_KEY,
  CALENDAR_RECOVERY_KEY,
  CalendarPersistenceError,
  loadCalendarDocument,
  reconcileCalendarSchedules,
  settleCalendarMutation,
  type DurableCalendarItem,
} from "./calendarDurability";

class MemoryStorage implements Storage {
  values = new Map<string, string>();
  failReads = false;
  failWrites = false;
  get length() { return this.values.size; }
  clear() { this.values.clear(); }
  getItem(key: string) {
    if (this.failReads) throw new DOMException("denied", "SecurityError");
    return this.values.get(key) ?? null;
  }
  key(index: number) { return [...this.values.keys()][index] ?? null; }
  removeItem(key: string) { this.values.delete(key); }
  setItem(key: string, value: string) {
    if (this.failWrites) throw new DOMException("quota", "QuotaExceededError");
    this.values.set(key, value);
  }
}

const item: DurableCalendarItem = {
  id: "calendar-1",
  date: "2026-07-20",
  kind: "task",
  title: "Daily review",
  time: "09:00",
};

test("legacy items migrate without deleting the original record", () => {
  const storage = new MemoryStorage();
  storage.setItem(CALENDAR_LEGACY_KEY, JSON.stringify([item]));
  const loaded = loadCalendarDocument(storage, "tab-a");
  assert.equal(loaded.status, "migrated");
  assert.deepEqual(loaded.document.items, [item]);
  assert.ok(storage.getItem(CALENDAR_LEGACY_KEY));
  assert.equal(storage.getItem(CALENDAR_DOCUMENT_KEY), null);
});

test("corrupt data is preserved and cannot be silently overwritten", () => {
  const storage = new MemoryStorage();
  storage.setItem(CALENDAR_LEGACY_KEY, "{broken calendar");
  const loaded = loadCalendarDocument(storage, "tab-a");
  assert.equal(loaded.status, "corrupt");
  assert.equal(loaded.recoveryRaw, "{broken calendar");
  assert.match(storage.getItem(CALENDAR_RECOVERY_KEY) ?? "", /broken calendar/);
  assert.throws(
    () => beginCalendarMutation(storage, loaded.document, { mutationId: "m1", operation: "upsert", proposedItems: [item] }),
    (error: unknown) => error instanceof CalendarPersistenceError && error.code === "CORRUPT",
  );
  assert.equal(storage.getItem(CALENDAR_LEGACY_KEY), "{broken calendar");
});

test("storage denial blocks remote mutation before a draft can be lost", () => {
  const storage = new MemoryStorage();
  storage.failReads = true;
  const loaded = loadCalendarDocument(storage, "tab-a");
  assert.equal(loaded.status, "unavailable");
  assert.throws(
    () => beginCalendarMutation(storage, loaded.document, { mutationId: "m1", operation: "upsert", proposedItems: [item] }),
    (error: unknown) => error instanceof CalendarPersistenceError && error.code === "STORAGE_UNAVAILABLE",
  );
});

test("journal precedes the acknowledged document and survives quota failure", () => {
  const storage = new MemoryStorage();
  const loaded = loadCalendarDocument(storage, "tab-a");
  const mutation = beginCalendarMutation(storage, loaded.document, {
    mutationId: "m1",
    operation: "upsert",
    proposedItems: [item],
  });
  assert.ok(storage.getItem(CALENDAR_JOURNAL_KEY));
  storage.failWrites = true;
  assert.throws(
    () => settleCalendarMutation(storage, "tab-a", mutation),
    (error: unknown) => error instanceof CalendarPersistenceError && error.code === "STORAGE_UNAVAILABLE",
  );
  assert.ok(storage.getItem(CALENDAR_JOURNAL_KEY));
  storage.failWrites = false;
  const settled = settleCalendarMutation(storage, "tab-a", mutation);
  assert.equal(settled.revision, 1);
  assert.equal(settled.items[0]?.id, item.id);
  assert.equal(storage.getItem(CALENDAR_JOURNAL_KEY), null);
});

test("cancel preserves the pending draft as recovery data", () => {
  const storage = new MemoryStorage();
  const loaded = loadCalendarDocument(storage, "tab-a");
  beginCalendarMutation(storage, loaded.document, { mutationId: "m1", operation: "upsert", proposedItems: [item] });
  const cancelled = cancelCalendarMutation(storage, "tab-a");
  assert.equal(cancelled.pendingMutation, null);
  assert.equal(storage.getItem(CALENDAR_JOURNAL_KEY), null);
  assert.match(storage.getItem(CALENDAR_RECOVERY_KEY) ?? "", /calendar-1/);
});

test("another tab revision prevents silent last-write-wins", () => {
  const storage = new MemoryStorage();
  const first = loadCalendarDocument(storage, "tab-a");
  const mutation = beginCalendarMutation(storage, first.document, {
    mutationId: "m1",
    operation: "upsert",
    proposedItems: [item],
  });
  settleCalendarMutation(storage, "tab-a", mutation);
  assert.throws(
    () => beginCalendarMutation(storage, first.document, { mutationId: "stale", operation: "delete", proposedItems: [] }),
    (error: unknown) => error instanceof CalendarPersistenceError && error.code === "CONFLICT",
  );
});

test("reconnect restores remote orphans and marks missing schedules", () => {
  const local: DurableCalendarItem[] = [
    { ...item, scheduleId: "sched-missing", calendarRevision: 1 },
  ];
  const remote = {
    id: "sched-remote",
    name: "Calendar: Restored task",
    status: "active",
    revision: 3,
    task: {
      message: "restore me",
      metadata: {
        source: "calendar",
        calendar_item_id: "calendar-remote",
        calendar_start_date: "2026-08-01",
        calendar_end_date: "2026-08-01",
        calendar_time: "10:30",
        calendar_revision: 2,
      },
    },
  };
  const result = reconcileCalendarSchedules(local, [remote]);
  assert.equal(result.items.length, 2);
  assert.equal(result.items.find((entry) => entry.id === item.id)?.syncState, "missing_schedule");
  assert.equal(result.items.find((entry) => entry.id === "calendar-remote")?.scheduleId, "sched-remote");
  assert.deepEqual(result.issues.map((issue) => issue.kind).sort(), ["missing_schedule", "remote_orphan"]);
});

test("newer backend revisions deterministically repair stale local records", () => {
  const result = reconcileCalendarSchedules(
    [{ ...item, title: "Old", scheduleId: "sched-1", calendarRevision: 1 }],
    [{
      id: "sched-1",
      name: "Calendar: New",
      status: "active",
      revision: 4,
      task: {
        message: "new prompt",
        metadata: {
          source: "calendar",
          calendar_item_id: item.id,
          calendar_start_date: item.date,
          calendar_time: item.time,
          calendar_revision: 2,
          calendar_item_snapshot: { ...item, title: "New", calendarRevision: 2 },
        },
      },
    }],
  );
  assert.equal(result.items[0]?.title, "New");
  assert.equal(result.items[0]?.scheduleRevision, 4);
  assert.deepEqual(result.issues, []);
});

test("a committed backend schedule completes an equal-revision pending local item", () => {
  const result = reconcileCalendarSchedules(
    [{ ...item, calendarRevision: 1, syncState: "pending" }],
    [{
      id: "sched-acknowledged",
      name: "Calendar: Daily review",
      status: "active",
      revision: 1,
      task: {
        message: "Daily review",
        metadata: {
          source: "calendar",
          calendar_item_id: item.id,
          calendar_start_date: item.date,
          calendar_time: item.time,
          calendar_revision: 1,
          calendar_item_snapshot: { ...item, calendarRevision: 1 },
        },
      },
    }],
  );
  assert.equal(result.items[0]?.scheduleId, "sched-acknowledged");
  assert.equal(result.items[0]?.syncState, "settled");
  assert.deepEqual(result.issues, []);
});
