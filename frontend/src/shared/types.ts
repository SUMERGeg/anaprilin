export type IntakeStatus = "pending" | "confirmed" | "skipped";

export interface ScheduleDto {
  id: string | null;
  slots: string[];
  active_from: string;
}

export interface EventDto {
  id: string;
  user_id: number;
  day_key: string;
  slot: string;
  status: IntakeStatus;
  sent_at: string | null;
  acted_at: string | null;
  source: string;
  revision: number;
  debug: boolean;
}

export interface SyncPullResponse {
  cursor_revision: number;
  events: EventDto[];
  schedule_slots: string[];
  schedule_active_from: string | null;
}

export interface DeviceLoginResponse {
  user_id: number;
  device_id: string;
  timezone: string;
  note: string;
}

export interface LocalEvent {
  id: string;
  dayKey: string;
  slot: string;
  status: IntakeStatus;
  revision: number;
  sentAt: string | null;
  actedAt: string | null;
  source: string;
  debug: boolean;
  updatedAt: string;
}

export interface LocalSchedule {
  id: number;
  slots: string[];
  activeFrom: string;
  updatedAt: string;
}

