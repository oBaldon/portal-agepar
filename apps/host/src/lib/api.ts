import type { User } from "@/types";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${txt || res.statusText}`);
  }
  return (await res.json()) as T;
}

export async function getMe(): Promise<User> {
  const res = await fetch(`${API_BASE}/me`, {
    method: "GET",
    credentials: "include",
  });
  return j<User>(res);
}

export type LoginParams = Partial<Pick<User, "cpf" | "nome" | "email">> & {
  roles?: string[];
  unidades?: string[];
};

export async function login(params?: LoginParams): Promise<User> {
  const usp = new URLSearchParams();
  if (params?.cpf) usp.set("cpf", params.cpf);
  if (params?.nome) usp.set("nome", params.nome);
  if (params?.email) usp.set("email", params.email);
  if (params?.roles?.length) usp.set("roles", params.roles.join(","));
  if (params?.unidades?.length) usp.set("unidades", params.unidades.join(","));

  const url = usp.toString()
    ? `${API_BASE}/auth/login?${usp.toString()}`
    : `${API_BASE}/auth/login`;

  const res = await fetch(url, { method: "GET", credentials: "include" });
  return j<User>(res);
}

export async function logout(): Promise<void> {
  const res = await fetch(`${API_BASE}/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
  await j(res);
}

export async function pingEProtocolo(): Promise<{ actor: string; ep_mode: string; ok: boolean }> {
  const res = await fetch(`${API_BASE}/eprotocolo/ping`, {
    method: "GET",
    credentials: "include",
  });
  return j(res);
}

/* ---------- Automações (usando API_BASE) ---------- */

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
