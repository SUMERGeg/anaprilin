import Dexie, { type Table } from "dexie";
import type { IntakeStatus, LocalEvent, LocalSchedule } from "../types";

export type OutboxOpType = "event_write" | "schedule_write";
export type OutboxStatus = "pending" | "failed" | "done";

export interface OutboxEntry {
  id?: number;
  opType: OutboxOpType;
  payload: unknown;
  idempotencyKey: string;
  status: OutboxStatus;
  tries: number;
  lastError: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface SyncMeta {
  key: string;
  value: string;
}

class AnaprilinDB extends Dexie {
  local_schedule!: Table<LocalSchedule, number>;
  local_events!: Table<LocalEvent, string>;
  outbox!: Table<OutboxEntry, number>;
  sync_meta!: Table<SyncMeta, string>;

  constructor() {
    super("anaprilin_pwa_db");
    this.version(1).stores({
      local_schedule: "id, activeFrom, updatedAt",
      local_events: "id, dayKey, slot, status, updatedAt",
      outbox: "++id, opType, status, createdAt, updatedAt",
      sync_meta: "key"
    });
  }
}

export const db = new AnaprilinDB();

export function eventKey(dayKey: string, slot: string): string {
  return `${dayKey}:${slot}`;
}

export async function upsertLocalEvent(input: {
  dayKey: string;
  slot: string;
  status: IntakeStatus;
  revision?: number;
  sentAt?: string | null;
  actedAt?: string | null;
  source?: string;
  debug?: boolean;
}): Promise<void> {
  const key = eventKey(input.dayKey, input.slot);
  const existing = await db.local_events.get(key);
  const now = new Date().toISOString();

  await db.local_events.put({
    id: key,
    dayKey: input.dayKey,
    slot: input.slot,
    status: input.status,
    revision: input.revision ?? (existing?.revision ?? 0) + 1,
    sentAt: input.sentAt ?? existing?.sentAt ?? null,
    actedAt: input.actedAt ?? existing?.actedAt ?? (input.status !== "pending" ? now : null),
    source: input.source ?? existing?.source ?? "client",
    debug: input.debug ?? existing?.debug ?? false,
    updatedAt: now
  });
}

export async function setLocalSchedule(slots: string[]): Promise<void> {
  await db.local_schedule.put({
    id: 1,
    slots,
    activeFrom: new Date().toISOString().slice(0, 10),
    updatedAt: new Date().toISOString()
  });
}

export async function getCursorRevision(): Promise<number> {
  const row = await db.sync_meta.get("cursor_revision");
  return row ? Number(row.value) : 0;
}

export async function setCursorRevision(revision: number): Promise<void> {
  await db.sync_meta.put({ key: "cursor_revision", value: String(revision) });
}

export async function setLastSyncNow(): Promise<void> {
  await db.sync_meta.put({ key: "last_success_at", value: new Date().toISOString() });
}

