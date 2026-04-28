import { useMemo, useState } from "react";

interface ScheduleSettingsScreenProps {
  slots: string[];
  onSave: (slots: string[]) => Promise<void>;
  onEnablePush: () => Promise<void>;
}

function normalizeSlots(raw: string[]): string[] {
  return raw
    .map((slot) => slot.trim())
    .filter(Boolean)
    .sort();
}

function validTime(value: string): boolean {
  return /^\d{2}:\d{2}$/.test(value);
}

export function ScheduleSettingsScreen({ slots, onSave, onEnablePush }: ScheduleSettingsScreenProps) {
  const [local, setLocal] = useState<string[]>(slots.length ? slots : ["09:00", "15:00", "21:00"]);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const validationError = useMemo(() => {
    const normalized = normalizeSlots(local);
    if (normalized.length !== 3) return "Нужно ровно 3 слота.";
    if (!normalized.every(validTime)) return "Формат времени должен быть HH:MM.";
    if (new Set(normalized).size !== 3) return "Времена не должны повторяться.";
    return null;
  }, [local]);

  async function handleSave() {
    if (validationError) {
      setMessage(validationError);
      return;
    }
    setSaving(true);
    setMessage(null);
    try {
      const normalized = normalizeSlots(local);
      await onSave(normalized);
      setMessage("Сохранено локально и добавлено в очередь синхронизации.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Ошибка сохранения.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="card">
      <h2>Настройки расписания</h2>
      <p className="muted">Три ежедневных слота.</p>
      <div className="stack">
        {local.map((value, idx) => (
          <label key={idx} className="field">
            <span>Слот {idx + 1}</span>
            <input
              value={value}
              onChange={(e) => {
                const next = [...local];
                next[idx] = e.target.value;
                setLocal(next);
              }}
              placeholder="09:00"
            />
          </label>
        ))}
      </div>
      {message ? <p className="notice">{message}</p> : null}
      <button disabled={saving} onClick={() => void handleSave()}>
        {saving ? "Сохраняю..." : "Сохранить"}
      </button>
      <button className="ghost" onClick={() => void onEnablePush()}>
        Включить Push на этом устройстве
      </button>
    </section>
  );
}
