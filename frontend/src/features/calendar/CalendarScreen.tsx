import { format, subDays } from "date-fns";
import type { LocalEvent } from "../../shared/types";

interface CalendarScreenProps {
  events: LocalEvent[];
  days?: number;
}

function dayEmoji(confirmed: number): string {
  if (confirmed <= 0) return "⚫";
  if (confirmed === 1) return "🔴";
  if (confirmed === 2) return "🟡";
  return "🟢";
}

export function CalendarScreen({ events, days = 14 }: CalendarScreenProps) {
  const byDay = new Map<string, LocalEvent[]>();
  for (const event of events) {
    const list = byDay.get(event.dayKey) ?? [];
    list.push(event);
    byDay.set(event.dayKey, list);
  }

  const range = Array.from({ length: days }, (_, i) => format(subDays(new Date(), i), "yyyy-MM-dd"));

  return (
    <section className="card">
      <h2>Календарь</h2>
      <p className="muted">Последние {days} дней</p>
      <div className="stack">
        {range.map((dayKey) => {
          const dayEvents = byDay.get(dayKey) ?? [];
          const confirmed = dayEvents.filter((item) => item.status === "confirmed").length;
          return (
            <div key={dayKey} className="calendar-row">
              <span>{dayEmoji(confirmed)}</span>
              <span>{dayKey}</span>
              <span>
                {confirmed}/3
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

