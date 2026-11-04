"use client";

export class ApiError extends Error {
  constructor(public code: string, public status: number, message: string, public details: Record<string, unknown> = {}) {
    super(message); this.name = "ApiError";
  }
}
let csrf: { token: string; expires: number } | undefined;
let pendingCsrf: Promise<string> | undefined;
async function csrfToken(): Promise<string> {
  if (csrf && csrf.expires > Date.now() + 10_000) return csrf.token;
  if (!pendingCsrf) pendingCsrf = fetch("/api/v1/auth/csrf", { credentials: "same-origin", cache: "no-store" })
    .then(async response => {
      if (!response.ok) throw new ApiError("csrf_unavailable", response.status, "");
      const body = await response.json();
      csrf = { token: body.csrf_token, expires: body.expires_at * 1000 };
      return csrf.token;
    }).finally(() => { pendingCsrf = undefined; });
  return pendingCsrf;
}
export function clearSessionClient() {
  csrf = undefined;
  window.dispatchEvent(new Event("wm:session-ended"));
}
async function errorOf(response: Response): Promise<{ code: string; message: string; details: Record<string, unknown> }> {
  const body = await response.json().catch(() => ({}));
  return {
    code: body.error?.code ?? "request_failed",
    message: body.error?.message ?? "",
    details: body.error?.details ?? {},
  };
}
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  if (!path.startsWith("/") || path.startsWith("//")) throw new Error("API path must be relative");
  const headers = new Headers(options.headers);
  const method = (options.method ?? "GET").toUpperCase();
  const safe = ["GET", "HEAD", "OPTIONS"].includes(method);
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const send = async (): Promise<Response> => {
    if (!safe) headers.set("X-CSRF-Token", await csrfToken());
    try { return await fetch(`/api/v1${path}`, { ...options, method, headers, credentials: "same-origin", cache: "no-store" }); }
    catch { throw new ApiError("network_unavailable", 0, ""); }
  };
  let response = await send();
  // A stale security token is recoverable exactly once: drop it and retry the same request.
  if (!response.ok && !safe && response.status === 403) {
    const failure = await errorOf(response.clone());
    if (failure.code === "csrf_invalid") { csrf = undefined; response = await send(); }
  }
  if (!response.ok) {
    const failure = await errorOf(response);
    // Signing out is the session owner's decision: clear the client session and
    // let the auth provider navigate once, instead of forcing a full reload here.
    if (response.status === 401 && !["/auth/login", "/auth/register", "/auth/me"].includes(path)) {
      clearSessionClient();
    }
    throw new ApiError(failure.code, response.status, failure.message, failure.details);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
export function safeReturnTo(value: string | null | undefined): string {
  if (!value || /[\\\u0000-\u0020]/.test(value)) return "/app";
  if (value === "/app" || value.startsWith("/app/") || value.startsWith("/app?")) {
    try {
      const url = new URL(value, window.location.origin);
      if (url.origin === window.location.origin && (url.pathname === "/app" || url.pathname.startsWith("/app/"))) return url.pathname + url.search + url.hash;
    } catch { /* Reject invalid navigation. */ }
  }
  return "/app";
}
