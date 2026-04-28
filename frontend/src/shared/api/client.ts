import type { DeviceLoginResponse, EventDto, ScheduleDto, SyncPullResponse } from "../types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api/v1";
const USER_ID_KEY = "anaprilin_user_id";
const DEVICE_ID_KEY = "anaprilin_device_id";

function getUserId(): string | null {
  return localStorage.getItem(USER_ID_KEY);
}

function getDeviceId(): string | null {
  return localStorage.getItem(DEVICE_ID_KEY);
}

function setAuth(userId: number, deviceId: string): void {
  localStorage.setItem(USER_ID_KEY, String(userId));
  localStorage.setItem(DEVICE_ID_KEY, deviceId);
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  extraHeaders: Record<string, string> = {}
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  const userId = getUserId();
  const deviceId = getDeviceId();
  if (userId) {
    headers.set("X-User-Id", userId);
  }
  if (deviceId) {
    headers.set("X-Device-Id", deviceId);
  }
  Object.entries(extraHeaders).forEach(([key, value]) => headers.set(key, value));

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function ensureDeviceLogin(): Promise<void> {
  if (getUserId() && getDeviceId()) {
    return;
  }
  const payload = { name: "Liza", timezone: "Europe/Moscow", platform: "ios-web", app_version: "0.1.0" };
  const data = await fetch(`${API_BASE}/auth/device-login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!data.ok) {
    throw new Error("Не удалось выполнить device-login.");
  }
  const json = (await data.json()) as DeviceLoginResponse;
  setAuth(json.user_id, json.device_id);
}

export async function fetchSchedule(): Promise<ScheduleDto> {
  return request<ScheduleDto>("/me/schedule");
}

export async function putSchedule(slots: string[]): Promise<ScheduleDto> {
  return request<ScheduleDto>("/me/schedule", {
    method: "PUT",
    body: JSON.stringify({ slots })
  });
}

export async function fetchEvents(dayFrom: string, dayTo: string): Promise<EventDto[]> {
  return request<EventDto[]>(`/me/events?from=${dayFrom}&to=${dayTo}`);
}

export async function postEvent(event: {
  day_key: string;
  slot: string;
  status: "pending" | "confirmed" | "skipped";
  source?: string;
  revision?: number;
  debug?: boolean;
}, idempotencyKey: string): Promise<EventDto> {
  return request<EventDto>(
    "/me/events",
    {
      method: "POST",
      body: JSON.stringify({
        ...event,
        source: event.source ?? "client"
      })
    },
    { "Idempotency-Key": idempotencyKey }
  );
}

export async function postPushSubscribe(payload: {
  endpoint: string;
  p256dh: string;
  auth: string;
  enabled?: boolean;
}): Promise<{ id: string }> {
  return request<{ id: string }>("/me/push/subscribe", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function syncPull(cursorRevision: number): Promise<SyncPullResponse> {
  return request<SyncPullResponse>("/sync/pull", {
    method: "POST",
    body: JSON.stringify({ cursor_revision: cursorRevision, limit: 500 })
  });
}

