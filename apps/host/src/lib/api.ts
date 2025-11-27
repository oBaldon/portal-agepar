// apps/host/src/lib/api.ts
import type { User } from "@/types";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";
const ENABLE_SELF_REGISTER = import.meta.env.VITE_ENABLE_SELF_REGISTER === "true";
export const SELF_REGISTER_ENABLED = ENABLE_SELF_REGISTER;

/**
 * Utilitários de API do aplicativo host.
 *
 * Propósito
 * ---------
 * - Centralizar chamadas HTTP para o BFF (`/api/*`) com tratamento consistente de erros.
 * - Expor helpers tipados para autenticação, sessões, automações e utilidades.
 * - Fornecer ganchos globais para 401/403 para o app reagir (ex.: redirecionar ao login).
 *
 * Modelo de Erro
 * --------------
 * - Em respostas não-2xx, as funções lançam `{ status: number, data: any }`.
 * - `data` é o JSON parseado quando possível; caso contrário `{ detail: string }` ou `null`.
 *
 * Referências
 * -----------
 * - Fetch API: https://developer.mozilla.org/docs/Web/API/Fetch_API
 * - Semântica de status HTTP: https://developer.mozilla.org/docs/Web/HTTP/Status
 * - FastAPI (negociação de resposta): https://fastapi.tiangolo.com/advanced/response-change-status-code/
 */

/* =========================
 * Interceptadores globais
 * ========================= */
let onUnauthorized: ((status: number) => void) | null = null;
let onForbidden: (() => void) | null = null;

/**
 * Registra handlers globais para respostas 401 e 403.
 * @param opts.onUnauthorized Chamado em 401 (a menos que suprimido pelo caller).
 * @param opts.onForbidden    Chamado em 403 (a menos que suprimido pelo caller).
 */
export function configureApiHandlers(opts: {
  onUnauthorized?: (status: number) => void;
  onForbidden?: () => void;
} = {}) {
  if (opts.onUnauthorized) onUnauthorized = opts.onUnauthorized;
  if (opts.onForbidden) onForbidden = opts.onForbidden;
}

/* =========================
 * Helpers HTTP
 * ========================= */

type HttpError = { status: number; data: any };

/**
 * Tenta parsear JSON quando o Content-Type indica JSON.
 * Nunca lança; retorna `null` quando o parse não é possível.
 */
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
 * Garante `res.ok`. Se for falso:
 * - dispara callbacks globais para 401/403 (salvo se suprimidos),
 * - lança `{ status, data }`, onde `data` é o JSON parseado quando possível
 *   ou `{ detail: string }`/`null` nos demais casos.
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

/**
 * Retorna JSON somente quando a resposta é OK. Caso contrário lança `{ status, data }`.
 * Protege chamadores de corpos vazios retornando `null` quando não for JSON.
 */
async function jsonOrThrow<T>(
  res: Response,
  opts?: { suppress401?: boolean; suppress403?: boolean }
): Promise<T> {
  await ensureOkOrThrow(res, opts);
  const ct = res.headers.get("content-type") || "";
  if (!ct.toLowerCase().includes("application/json")) {
    // @ts-expect-error – pode ser vazio/null quando o caller não espera corpo
    return null;
  }
  return (await res.json()) as T;
}

/* =========================
 * Auth (lado servidor)
 * ========================= */

/** GET `/api/me` — retorna o snapshot do usuário autenticado. */
export async function getMe(): Promise<User> {
  const res = await fetch(`${API_BASE}/me`, {
    method: "GET",
    credentials: "include",
  });
  return jsonOrThrow<User>(res);
}

/** POST `/api/auth/logout` — encerra a sessão atual (204 No Content). */
export async function logout(): Promise<void> {
  const res = await fetch(`${API_BASE}/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
  await ensureOkOrThrow(res);
}

/**
 * POST `/api/auth/login` — login por senha.
 * Observações
 * -----------
 * - Suprime o handler global de 401 (credenciais inválidas não devem causar logout global).
 */
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
  return jsonOrThrow<User>(res, { suppress401: true });
}

/**
 * POST `/api/auth/change-password` — troca a senha e retorna o mesmo payload do login.
 * Semântica de erros (backend):
 * - 401: `{ detail: "invalid_credentials" }` → senha/PIN atual incorreto.
 * - 422: `{ detail: { confirm: "..." } }`   → confirmação não confere.
 * - 400: `{ detail: { password: [...] } }`  → viola políticas.
 * Suprime o handler global de 401 para evitar logout ao errar a senha atual.
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
 * POST `/api/auth/register` — auto-registro (protegido por feature flag).
 * @deprecated Desativado por padrão; controlado por `VITE_ENABLE_SELF_REGISTER`.
 * Lança `{ status: 410 }` quando desativado para melhor UX sem ida à rede.
 */
export async function registerUser(params: {
  name: string;
  email?: string;
  cpf?: string;
  password: string;
}): Promise<RegisterResponse> {
  if (!ENABLE_SELF_REGISTER) {
    throw { status: 410, data: { detail: "Auto-registro desativado." } } as HttpError;
  }
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  return jsonOrThrow<RegisterResponse>(res, { suppress401: true });
}

/* =========================
 * Sessões da conta
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

/** GET `/api/auth/sessions` — lista sessões do usuário atual. */
export async function listSessions(): Promise<SessionItem[]> {
  const res = await fetch(`${API_BASE}/auth/sessions`, {
    credentials: "include",
  });
  return jsonOrThrow<SessionItem[]>(res);
}

/** POST `/api/auth/sessions/{id}/revoke` — revoga uma sessão específica. */
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

/** GET `/api/eprotocolo/ping` — verificação simples da camada de integração. */
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

/** GET `/api/automations` — lista automações disponíveis. */
export async function listAutomations() {
  const r = await fetch(`${API_BASE}/automations`, { credentials: "include" });
  return jsonOrThrow<{ items: Array<{ kind: string; version: string; title: string }> }>(r);
}

/** GET `/api/automations/{kind}/schema` — obtém schema/metadados de uma automação. */
export async function getAutomationSchema(kind: string) {
  const r = await fetch(`${API_BASE}/automations/${kind}/schema`, { credentials: "include" });
  return jsonOrThrow(r);
}

/** POST `/api/automations/{kind}/submit` — envia um payload para a automação. */
export async function submitAutomation(kind: string, data: any) {
  const r = await fetch(`${API_BASE}/automations/${kind}/submit`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return jsonOrThrow<{ submissionId: string; status: string }>(r);
}

/** GET `/api/automations/{kind}/submissions/{id}` — busca uma submissão específica. */
export async function getSubmission(kind: string, id: string) {
  const r = await fetch(`${API_BASE}/automations/${kind}/submissions/${id}`, {
    credentials: "include",
  });
  return jsonOrThrow(r);
}

/** GET `/api/automations/{kind}/submissions?limit&offset` — lista submissões por automação. */
export async function listSubmissions(kind: string, limit = 20, offset = 0) {
  const r = await fetch(
    `${API_BASE}/automations/${kind}/submissions?limit=${limit}&offset=${offset}`,
    { credentials: "include" }
  );
  return jsonOrThrow(r);
}

/**
 * POST `/api/automations/{kind}/submissions/{id}/download` — baixa artefato da submissão.
 * O nome do arquivo é derivado do cabeçalho `Content-Disposition`, com fallback `{kind}.json`.
 */
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
