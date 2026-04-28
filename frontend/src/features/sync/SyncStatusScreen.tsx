interface SyncStatusScreenProps {
  pendingCount: number;
  failedCount: number;
  doneCount: number;
  lastSyncAt: string | null;
  syncing: boolean;
  onSyncNow: () => Promise<void>;
  onClearDone: () => Promise<void>;
}

export function SyncStatusScreen(props: SyncStatusScreenProps) {
  return (
    <section className="card">
      <h2>Статус синхронизации</h2>
      <div className="stack">
        <div className="kv-row">
          <span>В очереди:</span>
          <strong>{props.pendingCount}</strong>
        </div>
        <div className="kv-row">
          <span>Ошибки:</span>
          <strong>{props.failedCount}</strong>
        </div>
        <div className="kv-row">
          <span>Выполнено:</span>
          <strong>{props.doneCount}</strong>
        </div>
        <div className="kv-row">
          <span>Последний успешный sync:</span>
          <strong>{props.lastSyncAt ?? "—"}</strong>
        </div>
      </div>
      <div className="row">
        <button disabled={props.syncing} onClick={() => void props.onSyncNow()}>
          {props.syncing ? "Синхронизация..." : "Retry Sync"}
        </button>
        <button className="ghost" onClick={() => void props.onClearDone()}>
          Очистить done
        </button>
      </div>
    </section>
  );
}

