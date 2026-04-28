import { format } from "date-fns";
import { useLiveQuery } from "dexie-react-hooks";
import { useEffect, useMemo, useState } from "react";
import { CalendarScreen } from "../features/calendar/CalendarScreen";
import { ScheduleSettingsScreen } from "../features/schedule/ScheduleSettingsScreen";
import { SyncStatusScreen } from "../features/sync/SyncStatusScreen";
import { TodayScreen } from "../features/today/TodayScreen";
import { ensureDeviceLogin } from "../shared/api/client";
import { db } from "../shared/offline/db";
import { enqueueEventWrite, enqueueScheduleWrite } from "../shared/offline/outbox";
import { clearDoneOutbox, setupOnlineSync, syncNowSafely } from "../shared/offline/sync";
import { subscribeWebPush } from "../shared/pwa/push";

type ScreenId = "today" | "calendar" | "settings" | "sync";

function readDeeplink(): { screen: ScreenId; day: string | null; slot: string | null } {
  const params = new URLSearchParams(window.location.search);
  const screenParam = params.get("screen");
  const screen: ScreenId =
    screenParam === "calendar" || screenParam === "settings" || screenParam === "sync"
      ? screenParam
      : "today";
  return { screen, day: params.get("day"), slot: params.get("slot") };
}

export function App() {
  const deeplink = useMemo(() => readDeeplink(), []);
  const [screen, setScreen] = useState<ScreenId>(deeplink.screen);
  const [syncing, setSyncing] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);

  const schedule = useLiveQuery(() => db.local_schedule.get(1), [], null);
  const events = useLiveQuery(() => db.local_events.toArray(), [], []);
  const outbox = useLiveQuery(() => db.outbox.toArray(), [], []);
  const lastSync = useLiveQuery(() => db.sync_meta.get("last_success_at"), [], null);

  const todayKey = format(new Date(), "yyyy-MM-dd");
  const todayEvents = events.filter((event) => event.dayKey === todayKey);
  const slots = schedule?.slots ?? ["09:00", "15:00", "21:00"];

  const pendingCount = outbox.filter((row) => row.status === "pending").length;
  const failedCount = outbox.filter((row) => row.status === "failed").length;
  const doneCount = outbox.filter((row) => row.status === "done").length;

  useEffect(() => {
    setupOnlineSync();
    void (async () => {
      await ensureDeviceLogin();
      await syncNowSafely();
    })();
  }, []);

  async function handleAction(slot: string, status: "confirmed" | "skipped") {
    await enqueueEventWrite({ dayKey: todayKey, slot, status });
  }

  async function handleSaveSchedule(newSlots: string[]) {
    await enqueueScheduleWrite(newSlots);
    if (navigator.onLine) {
      await handleSyncNow();
    }
  }

  async function handleEnablePush() {
    try {
      await subscribeWebPush();
      setBanner("Push подписка активирована.");
    } catch (error) {
      setBanner(error instanceof Error ? error.message : "Ошибка подключения push.");
    }
  }

  async function handleSyncNow() {
    setSyncing(true);
    try {
      await syncNowSafely();
    } finally {
      setSyncing(false);
    }
  }

  return (
    <div className="layout">
      <header className="header">
        <h1>Anaprilin PWA</h1>
        <p className="muted">offline-first • iPhone web app</p>
        {banner ? <p className="notice">{banner}</p> : null}
      </header>

      <nav className="tabs">
        <button className={screen === "today" ? "active" : ""} onClick={() => setScreen("today")}>
          Today
        </button>
        <button className={screen === "calendar" ? "active" : ""} onClick={() => setScreen("calendar")}>
          Calendar
        </button>
        <button className={screen === "settings" ? "active" : ""} onClick={() => setScreen("settings")}>
          Schedule
        </button>
        <button className={screen === "sync" ? "active" : ""} onClick={() => setScreen("sync")}>
          Sync
        </button>
      </nav>

      <main>
        {screen === "today" ? (
          <TodayScreen
            slots={slots}
            events={todayEvents}
            focusDay={deeplink.day}
            focusSlot={deeplink.slot}
            onConfirm={(slot) => handleAction(slot, "confirmed")}
            onSkip={(slot) => handleAction(slot, "skipped")}
          />
        ) : null}

        {screen === "calendar" ? <CalendarScreen events={events} /> : null}

        {screen === "settings" ? (
          <ScheduleSettingsScreen slots={slots} onSave={handleSaveSchedule} onEnablePush={handleEnablePush} />
        ) : null}

        {screen === "sync" ? (
          <SyncStatusScreen
            pendingCount={pendingCount}
            failedCount={failedCount}
            doneCount={doneCount}
            lastSyncAt={lastSync?.value ?? null}
            syncing={syncing}
            onSyncNow={handleSyncNow}
            onClearDone={clearDoneOutbox}
          />
        ) : null}
      </main>
    </div>
  );
}
