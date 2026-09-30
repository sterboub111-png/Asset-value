import { getLang } from "./i18n.js";
import type { Lookups, Rec } from "./types.js";

export class ApiError extends Error {}

async function call<T>(method: string, url: string, body?: unknown, headers: Record<string, string> = {}): Promise<T> {
  const init: RequestInit = { method, headers: { "X-Lang": getLang(), ...headers } };
  if (body instanceof ArrayBuffer || body instanceof Blob) {
    init.body = body;
  } else if (body !== undefined) {
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch {
    throw new ApiError("Cannot reach the Gooya Asset server. Is it still running?");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError((data as Rec).error || `Request failed (${res.status})`);
  return data as T;
}

export const api = {
  get: <T = any>(url: string) => call<T>("GET", url),
  post: <T = any>(url: string, body: unknown = {}) => call<T>("POST", url, body),
  put: <T = any>(url: string, body: unknown = {}) => call<T>("PUT", url, body),
  del: <T = any>(url: string) => call<T>("DELETE", url),
  upload: <T = any>(url: string, file: File, meta: Record<string, string>) =>
    call<T>("POST", url, file, {
      "X-File-Name": encodeURIComponent(file.name),
      "X-Doc-Title": encodeURIComponent(meta.title || ""),
      "X-Doc-Type": encodeURIComponent(meta.type || ""),
      "X-Doc-Notes": encodeURIComponent(meta.notes || ""),
    }),
};

let cache: Lookups | null = null;
export async function lookups(force = false): Promise<Lookups> {
  if (!cache || force) cache = await api.get<Lookups>("/api/lookups");
  return cache;
}
export const invalidateLookups = () => { cache = null; };
