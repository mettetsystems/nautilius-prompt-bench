/** Browser recents for this app only — PromptPiper uses prompt-piper.recent-sessions. */
export const RECENT_SESSIONS_KEY = "nautilius.recent-sessions";
export const MAX_RECENT_SESSIONS = 20;

import type { RecentSessionEntry, SessionDetailResponse } from "../api/types";

export function loadRecentSessions(): RecentSessionEntry[] {
  try {
    const raw = localStorage.getItem(RECENT_SESSIONS_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw) as RecentSessionEntry[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveRecentSessions(entries: RecentSessionEntry[]): void {
  localStorage.setItem(RECENT_SESSIONS_KEY, JSON.stringify(entries.slice(0, MAX_RECENT_SESSIONS)));
}

export function upsertRecentSession(session: SessionDetailResponse): RecentSessionEntry[] {
  const entry: RecentSessionEntry = {
    id: session.session.id,
    title: session.session.title,
    state: session.session.state,
    promptId: session.prompt_id ?? session.session.prompt_id,
    similarityWarning: session.similarity_warning,
    updatedAt: session.session.updated_at,
  };
  const existing = loadRecentSessions().filter((item) => item.id !== entry.id);
  const next = [entry, ...existing].slice(0, MAX_RECENT_SESSIONS);
  saveRecentSessions(next);
  return next;
}

export function removeRecentSession(sessionId: string): RecentSessionEntry[] {
  const next = loadRecentSessions().filter((item) => item.id !== sessionId);
  saveRecentSessions(next);
  return next;
}
