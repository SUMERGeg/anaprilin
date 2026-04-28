import { ensureDeviceLogin, fetchSchedule, syncPull } from "../api/client";
import { db, getCursorRevision, setCursorRevision, setLastSyncNow, setLocalSchedule, upsertLocalEvent } from "./db";
import { flushOutbox } from "./outbox";

export async function syncNow(): Promise<void> {
  await ensureDeviceLogin();

  await flushOutbox();

  const cursorRevision = await getCursorRevision();
  const pulled = await syncPull(cursorRevision);
  for (const event of pulled.events) {
    await upsertLocalEvent({
      dayKey: event.day_key,
      slot: event.slot,
      status: event.status,
      revision: event.revision,
      sentAt: event.sent_at,
      actedAt: event.acted_at,
      source: event.source,
      debug: event.debug
    });
  }

  if (pulled.schedule_slots.length > 0) {
    await setLocalSchedule(pulled.schedule_slots);
  } else {
    const remoteSchedule = await fetchSchedule();
    await setLocalSchedule(remoteSchedule.slots);
  }

  await setCursorRevision(pulled.cursor_revision);
  await setLastSyncNow();
}

let syncInProgress = false;

export async function syncNowSafely(): Promise<void> {
  if (syncInProgress) {
    return;
  }
  syncInProgress = true;
  try {
    await syncNow();
  } finally {
    syncInProgress = false;
  }
}

export function setupOnlineSync(): void {
  window.addEventListener("online", () => {
    void syncNowSafely();
  });
}

export async function clearDoneOutbox(): Promise<void> {
  const doneRows = await db.outbox.where("status").equals("done").toArray();
  await Promise.all(doneRows.map((row) => db.outbox.delete(row.id ?? 0)));
}

