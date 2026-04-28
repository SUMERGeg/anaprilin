import { format } from "date-fns";
import type { LocalEvent } from "../../shared/types";

interface TodayScreenProps {
  slots: string[];
  events: LocalEvent[];
  focusDay?: string | null;
  focusSlot?: string | null;
  onConfirm: (slot: string) => Promise<void>;
  onSkip: (slot: string) => Promise<void>;
}

function statusLabel(status: LocalEvent["status"] | "missing"): string {
  if (status === "confirmed") return "Принято";
  if (status === "skipped") return "Пропущено";
  if (status === "pending") return "Ожидает";
  return "Нет отметки";
}

export function TodayScreen({ slots, events, focusDay, focusSlot, onConfirm, onSkip }: TodayScreenProps) {
  const today = format(new Date(), "yyyy-MM-dd");
  const bySlot = new Map(events.map((event) => [event.slot, event]));
  const isDeeplinkForToday = focusDay === today;

  return (
    <section className="card">
      <h2>Сегодня</h2>
      <p className="muted">{today}</p>
      {isDeeplinkForToday && focusSlot ? (
        <p className="notice">Открыто из push: слот {focusSlot}</p>
      ) : null}
      <div className="stack">
        {slots.map((slot) => {
          const event = bySlot.get(slot);
          const status = event?.status ?? "missing";
          const highlight = isDeeplinkForToday && focusSlot === slot;
          return (
            <div className={`slot-row${highlight ? " slot-row--focus" : ""}`} key={slot}>
              <div>
                <div className="slot-time">{slot}</div>
                <div className={`status status--${status}`}>{statusLabel(status)}</div>
              </div>
              <div className="slot-actions">
                <button onClick={() => void onConfirm(slot)}>Приняла</button>
                <button className="ghost" onClick={() => void onSkip(slot)}>
                  Пропустить
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

