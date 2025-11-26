// apps/host/src/lib/api.ts
import type { User } from "@/types";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";
const ENABLE_SELF_REGISTER = import.meta.env.VITE_ENABLE_SELF_REGISTER === "true";
export const SELF_REGISTER_ENABLED = ENABLE_SELF_REGISTER;

/* =========================
 * Interceptadores globais
 * ========================= */
let onUnauthorized: ((status: number) => void) | null = null;
let onForbidden: (() => void) | null = null;

/** Permite ao app registrar handlers globais para 401/403. */
export function configureApiHandlers(opts: {
  onUnauthorized?: (status: number) => void;
  onForbidden?: () => void;
} = {}) {
  if (opts.onUnauthorized) onUnauthorized = opts.onUnauthorized;
  if (opts.onForbidden) onForbidden = opts.onForbidden;
}

/* =========================
 * Util: requisições e erros
 * ========================= */

type HttpError = { status: number; data: any };

/** Tenta parsear JSON se houver; caso contrário retorna null. Nunca lança. */
async function tryParseJson(res: Response): Promise<any> {
  const ct = res.headers.get("content-type") || "";
  if (!ct.toLowerCase().includes("application/json")) return null;
  try {
    return await res.json();
  } catch {
    return null;
  }
}

/**
 * Garante `res.ok`. Em caso de erro:
 * - dispara callbacks globais (401/403), salvo se suprimidos
 * - lança SEMPRE um objeto estruturado: `{ status, data }`
 *   onde `data` é o corpo (JSON se possível, senão `{ detail: stringDoTexto }` ou `null`)
 */
async function ensureOkOrThrow(
  res: Response,
  opts?: { suppress401?: boolean; suppress403?: boolean }
): Promise<void> {
  if (res.ok) return;

  if (res.status === 401 && !opts?.suppress401 && onUnauthorized) onUnauthorized(401);
  if (res.status === 403 && !opts?.suppress403 && onForbidden) onForbidden();

  const json = await tryParseJson(res);
  if (json !== null) {
    throw { status: res.status, data: json } as HttpError;
  }
  const text = await res.text().catch(() => "");
  throw { status: res.status, data: text ? { detail: text } : null } as HttpError;
}

/** Lê JSON quando OK. Se não OK, lança `{ status, data }`. Protege respostas vazias. */
async function jsonOrThrow<T>(res: Response, opts?: { suppress401?: boolean; suppress403?: boolean }): Promise<T> {
  await ensureOkOrThrow(res, opts);
  const ct = res.headers.get("content-type") || "";
  if (!ct.toLowerCase().includes("application/json")) {
    // @ts-expect-error – pode ser vazio/null quando o caller não espera corpo
    return null;
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
  return jsonOrThrow<User>(res);
}

/** Logout real (POST 204 No Content) */
export async function logout(): Promise<void> {
  const res = await fetch(`${API_BASE}/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
  await ensureOkOrThrow(res);
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
  // ⬇️ NÃO dispara handler global em 401 de login
  return jsonOrThrow<User>(res, { suppress401: true });
}

/**
 * Troca de senha (POST /api/auth/change-password)
 * Retorna o mesmo payload do login (já com must_change_password=false).
 * Erros tratados pelo backend:
 *  - 401: { detail: "invalid_credentials" } → senha atual incorreta
 *  - 422: { detail: { confirm: "..." } }    → confirmação não confere
 *  - 400: { detail: { password: [ ... ] } } → violações de política
 */
export async function changePassword(params: {
  current_password: string;
  new_password: string;
  new_password_confirm: string;
}): Promise<User> {
  const res = await fetch(`${API_BASE}/auth/change-password`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  // ⬇️ CRÍTICO: suprime 401 para não deslogar ao errar o PIN/senha atual
  return jsonOrThrow<User>(res, { suppress401: true });
}

export type RegisterResponse = {
  id: string;
  name: string;
  email?: string | null;
  cpf?: string | null;
  status: string;
};

/**
 * Registro (POST /api/auth/register)
 * @deprecated Auto-registro desativado por padrão. Controlado por VITE_ENABLE_SELF_REGISTER.
 */
export async function registerUser(params: {
  name: string;
  email?: string;
  cpf?: string;
  password: string;
}): Promise<RegisterResponse> {
  if (!ENABLE_SELF_REGISTER) {
    // curto-circuito para UX melhor quando a funcionalidade estiver desligada
    throw { status: 410, data: { detail: "Auto-registro desativado." } } as HttpError;
  }
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  // Em geral não queremos chutar usuário em 401 aqui também
  return jsonOrThrow<RegisterResponse>(res, { suppress401: true });
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
  return jsonOrThrow<SessionItem[]>(res);
}

export async function revokeSession(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/auth/sessions/${id}/revoke`, {
    method: "POST",
    credentials: "include",
  });
  await ensureOkOrThrow(res);
}

/* =========================
 * Ping / utilidades
 * ========================= */

export async function pingEProtocolo(): Promise<{ actor: string; ep_mode: string; ok: boolean }> {
  const res = await fetch(`${API_BASE}/eprotocolo/ping`, {
    method: "GET",
    credentials: "include",
  });
  return jsonOrThrow(res);
}

/* =========================
 * Automações
 * ========================= */

export async function listAutomations() {
  const r = await fetch(`${API_BASE}/automations`, { credentials: "include" });
  return jsonOrThrow<{ items: Array<{ kind: string; version: string; title: string }> }>(r);
}

export async function getAutomationSchema(kind: string) {
  const r = await fetch(`${API_BASE}/automations/${kind}/schema`, { credentials: "include" });
  return jsonOrThrow(r);
}

export async function submitAutomation(kind: string, data: any) {
  const r = await fetch(`${API_BASE}/automations/${kind}/submit`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return jsonOrThrow<{ submissionId: string; status: string }>(r);
}

export async function getSubmission(kind: string, id: string) {
  const r = await fetch(`${API_BASE}/automations/${kind}/submissions/${id}`, {
    credentials: "include",
  });
  return jsonOrThrow(r);
}

export async function listSubmissions(kind: string, limit = 20, offset = 0) {
  const r = await fetch(
    `${API_BASE}/automations/${kind}/submissions?limit=${limit}&offset=${offset}`,
    { credentials: "include" }
  );
  return jsonOrThrow(r);
}

export async function downloadSubmission(kind: string, id: string) {
  const r = await fetch(`${API_BASE}/automations/${kind}/submissions/${id}/download`, {
    method: "POST",
    credentials: "include",
  });
  await ensureOkOrThrow(r);
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
