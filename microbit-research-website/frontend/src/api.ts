import { TASK_VERSION } from "./tasks";
export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
export const MAKECODE_URL = import.meta.env.VITE_MAKECODE_URL || "http://localhost:3232";
const QUEUE_KEY = "microbit-research:event-queue";
const LOCAL_EVENTS_KEY = "microbit-research:local-events";

export type SessionState = { sessionId: string; participantId: string; startedAt: string; screen: string; stepIndex: number; counts: Record<string, number>; offline?: boolean; taskStartedAt?: string; stepStartedAt?: string; freeStartedAt?: string; freeIdea?: string; freeSummary?: string; freeStatus?: string; exportDir?: string };
export type LogEvent = { event_id: string; participant_id: string; session_id: string; task_id: string | null; step_id: string | null; event_type: string; client_timestamp: string; elapsed_ms: number; task_version: string; metadata: Record<string, unknown> };
export const api = async <T>(path: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(`${API_URL}${path}`, { ...init, headers: { "Content-Type": "application/json", ...init?.headers } });
  if (!response.ok) { const body = await response.json().catch(() => null); throw new Error(typeof body?.detail === "string" ? body.detail : JSON.stringify(body?.detail || body || response.statusText)); }
  return response.json();
};
const readQueue = (): LogEvent[] => JSON.parse(localStorage.getItem(QUEUE_KEY) || "[]");
const writeQueue = (events: LogEvent[]) => localStorage.setItem(QUEUE_KEY, JSON.stringify(events));
export const makeEvent = (session: SessionState, eventType: string, taskId: string | null, stepId: string | null, metadata: Record<string, unknown> = {}): LogEvent => ({
  event_id: crypto.randomUUID(), participant_id: session.participantId, session_id: session.sessionId, task_id: taskId, step_id: stepId,
  event_type: eventType, client_timestamp: new Date().toISOString(), elapsed_ms: Math.max(0, Date.now() - Date.parse(session.startedAt)), task_version: TASK_VERSION, metadata,
});
export const enqueue = (event: LogEvent) => { const queue = readQueue(); queue.push(event); writeQueue(queue); return flushQueue(); };
export const flushQueue = async () => {
  const queue = readQueue();
  if (!queue.length) return true;
  const sessions = new Map<string, LogEvent[]>();
  for (const event of queue) {
    const events = sessions.get(event.session_id) || [];
    events.push(event);
    sessions.set(event.session_id, events);
  }

  let allSaved = true;
  for (const events of sessions.values()) {
    try {
      await api("/api/events/batch", { method: "POST", body: JSON.stringify({ events }) });
      const sentIds = new Set(events.map((event) => event.event_id));
      writeQueue(readQueue().filter((event) => !sentIds.has(event.event_id)));
    } catch {
      allSaved = false;
    }
  }
  return allSaved;
};
export const queuedCount = () => readQueue().length;
export const saveLocalEvent = (event: LogEvent) => {
  const events: LogEvent[] = JSON.parse(localStorage.getItem(LOCAL_EVENTS_KEY) || "[]");
  events.push(event);
  localStorage.setItem(LOCAL_EVENTS_KEY, JSON.stringify(events));
};
export const saveSnapshot = (sessionId: string) => api<{ export_dir: string; saved_at: string }>(`/api/sessions/${sessionId}/snapshot`, { method: "POST" });
export const downloadLocalEvents = (sessionId: string) => {
  const events: LogEvent[] = JSON.parse(localStorage.getItem(LOCAL_EVENTS_KEY) || "[]");
  const content = JSON.stringify(events.filter((event) => event.session_id === sessionId), null, 2);
  const url = URL.createObjectURL(new Blob([content], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `${sessionId}-problem-events.json`;
  link.click();
  URL.revokeObjectURL(url);
};

