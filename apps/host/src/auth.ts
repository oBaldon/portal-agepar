export async function fetchMe(signal?: AbortSignal) {
  const res = await fetch("/api/me", { credentials: "include", signal });
  if (res.status === 401) return null;
  if (!res.ok) throw new Error("Falha ao obter sessão");
  return res.json();
}
export function login() {
  window.location.href = "/api/auth/login";
}
export async function logout() {
  await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
  window.location.href = "/";
}
