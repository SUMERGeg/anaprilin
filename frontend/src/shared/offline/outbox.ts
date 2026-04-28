import { postEvent, putSchedule } from "../api/client";
import type { IntakeStatus } from "../types";
import { db, setLocalSchedule, upsertLocalEvent, type OutboxEntry } from "./db";

function nowIso(): string {
  return new Date().toISOString();
}

export function makeIdempotencyKey(prefix: string): string {
  const rand = Math.random().toString(36).slice(2, 10);
  return `${prefix}-${Date.now()}-${rand}`;
}

export async function enqueueEventWrite(input: {
  dayKey: string;
  slot: string;
  status: IntakeStatus;
}): Promise<void> {
  await upsertLocalEvent({
    dayKey: input.dayKey,
    slot: input.slot,
    status: input.status,
    source: "client"
  });

  const entry: OutboxEntry = {
    opType: "event_write",
    payload: {
      day_key: input.dayKey,
      slot: input.slot,
      status: input.status,
      source: "client"
    },
    idempotencyKey: makeIdempotencyKey("evt"),
    status: "pending",
    tries: 0,
    lastError: null,
    createdAt: nowIso(),
    updatedAt: nowIso()
  };
  await db.outbox.add(entry);
}

export async function enqueueScheduleWrite(slots: string[]): Promise<void> {
  await setLocalSchedule(slots);
  const entry: OutboxEntry = {
    opType: "schedule_write",
    payload: { slots },
    idempotencyKey: makeIdempotencyKey("sch"),
    status: "pending",
    tries: 0,
    lastError: null,
    createdAt: nowIso(),
    updatedAt: nowIso()
  };
  await db.outbox.add(entry);
}

export async function flushOutbox(): Promise<{ success: number; failed: number }> {
  const entries = await db.outbox.where("status").anyOf("pending", "failed").sortBy("createdAt");
  let success = 0;
  let failed = 0;

  for (const entry of entries) {
    try {
      if (entry.opType === "event_write") {
        const payload = entry.payload as {
          day_key: string;
          slot: string;
          status: IntakeStatus;
          source: string;
        };
        const result = await postEvent(payload, entry.idempotencyKey);
        await upsertLocalEvent({
          dayKey: result.day_key,
          slot: result.slot,
          status: result.status,
          revision: result.revision,
          sentAt: result.sent_at,
          actedAt: result.acted_at,
          source: result.source,
          debug: result.debug
        });
      } else if (entry.opType === "schedule_write") {
        const payload = entry.payload as { slots: string[] };
        const remote = await putSchedule(payload.slots);
        await setLocalSchedule(remote.slots);
      }

      await db.outbox.update(entry.id ?? 0, {
        status: "done",
        tries: entry.tries + 1,
        lastError: null,
        updatedAt: nowIso()
      });
      success += 1;
    } catch (error) {
      await db.outbox.update(entry.id ?? 0, {
        status: "failed",
        tries: entry.tries + 1,
        lastError: error instanceof Error ? error.message : "unknown error",
        updatedAt: nowIso()
      });
      failed += 1;
    }
  }

  return { success, failed };
}

