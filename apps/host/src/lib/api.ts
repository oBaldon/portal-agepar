// apps/host/src/lib/api.ts
import type { User } from "@/types";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${txt || res.statusText}`);
  }
  return (await res.json()) as T;
}

/* =========================
 * Auth (real, server-side)
 * ========================= */

export async function getMe(): Promise<User> {
  const res = await fetch(`${API_BASE}/me`, {
    method: "GET",
    credentials: "include",
  });
  return j<User>(res);
}

/** Logout real (POST 204 No Content) */
export async function logout(): Promise<void> {
  const res = await fetch(`${API_BASE}/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${txt || res.statusText}`);
  }
}

/** Login real (POST /api/auth/login) */
export async function loginWithPassword(params: {
  identifier: string;
  password: string;
  remember_me?: boolean;
}): Promise<User> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      identifier: params.identifier,
      password: params.password,
      remember_me: !!params.remember_me,
    }),
  });
  return j<User>(res);
}

export type RegisterResponse = {
  id: string;
  name: string;
  email?: string | null;
  cpf?: string | null;
  status: string;
};

/** Registro (POST /api/auth/register) */
export async function registerUser(params: {
  name: string;
  email?: string;
  cpf?: string;
  password: string;
}): Promise<RegisterResponse> {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  return j<RegisterResponse>(res);
}

/* =========================
 * Sessões de conta
 * ========================= */

export type SessionItem = {
  id: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  revoked_at: string | null;
  ip: string | null;
  user_agent: string | null;
  current: boolean;
};

export async function listSessions(): Promise<SessionItem[]> {
  const res = await fetch(`${API_BASE}/auth/sessions`, {
    credentials: "include",
  });
  return j<SessionItem[]>(res);
}

export async function revokeSession(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/auth/sessions/${id}/revoke`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${txt || res.statusText}`);
  }
}

/* =========================
 * Ping / utilidades
 * ========================= */

export async function pingEProtocolo(): Promise<{ actor: string; ep_mode: string; ok: boolean }> {
  const res = await fetch(`${API_BASE}/eprotocolo/ping`, {
    method: "GET",
    credentials: "include",
  });
  return j(res);
}

/* =========================
 * Automações
 * ========================= */

export async function listAutomations() {
  const r = await fetch(`${API_BASE}/automations`, { credentials: "include" });
  return j<{ items: Array<{ kind: string; version: string; title: string }> }>(r);
}

export async function getAutomationSchema(kind: string) {
  const r = await fetch(`${API_BASE}/automations/${kind}/schema`, { credentials: "include" });
  return j(r);
}

export async function submitAutomation(kind: string, data: any) {
  const r = await fetch(`${API_BASE}/automations/${kind}/submit`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return j<{ submissionId: string; status: string }>(r);
}

export async function getSubmission(kind: string, id: string) {
  const r = await fetch(`${API_BASE}/automations/${kind}/submissions/${id}`, {
    credentials: "include",
  });
  return j(r);
}

export async function listSubmissions(kind: string, limit = 20, offset = 0) {
  const r = await fetch(
    `${API_BASE}/automations/${kind}/submissions?limit=${limit}&offset=${offset}`,
    { credentials: "include" }
  );
  return j(r);
}

export async function downloadSubmission(kind: string, id: string) {
  const r = await fetch(`${API_BASE}/automations/${kind}/submissions/${id}/download`, {
    method: "POST",
    credentials: "include",
  });
  if (!r.ok) throw new Error(`${kind} download: ${r.status}`);
  const blob = await r.blob();
  const cd = r.headers.get("content-disposition") || "";
  const m = /filename="?([^"]+)"?/.exec(cd);
  const filename = m?.[1] || `${kind}.json`;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
}
