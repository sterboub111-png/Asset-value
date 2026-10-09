import { getLang } from "./i18n.js";
import { markClean } from "./dirty.js";
export class ApiError extends Error {
}
/** Set by the app shell: called when the session has ended (401) or a password change is required (403). */
export const hooks = { onUnauthorized: null, onMustChange: null };
/** The branch picker's choice ('' = everything the user may see, 'country:SA', 'branch:12'); the server applies it to every call. */
const SCOPE_KEY = "usool.scope";
export function getScope() { try {
    return localStorage.getItem(SCOPE_KEY) || "";
}
catch {
    return "";
} }
export function setScope(v) { try {
    localStorage.setItem(SCOPE_KEY, v);
}
catch { /* ignore */ } }
async function call(method, url, body, headers = {}) {
    const init = { method, headers: { "X-Lang": getLang(), "X-Requested-With": "GooyaAsset", "X-Scope": getScope(), ...headers } };
    if (body instanceof ArrayBuffer || body instanceof Blob) {
        init.body = body;
    }
    else if (body !== undefined) {
        init.headers["Content-Type"] = "application/json";
        init.body = JSON.stringify(body);
    }
    let res;
    try {
        res = await fetch(url, init);
    }
    catch {
        throw new ApiError("Cannot reach the Usool server. Is it still running?");
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        if (res.status === 401 && data.auth === "required")
            hooks.onUnauthorized?.();
        if (res.status === 403 && data.auth === "password")
            hooks.onMustChange?.();
        throw new ApiError(data.error || `Request failed (${res.status})`);
    }
    if (method !== "GET")
        markClean(); // a saved form has nothing left to lose
    return data;
}
export const api = {
    get: (url) => call("GET", url),
    post: (url, body = {}) => call("POST", url, body),
    put: (url, body = {}) => call("PUT", url, body),
    del: (url) => call("DELETE", url),
    upload: (url, file, meta) => call("POST", url, file, {
        "X-File-Name": encodeURIComponent(file.name),
        "X-Doc-Title": encodeURIComponent(meta.title || ""),
        "X-Doc-Type": encodeURIComponent(meta.type || ""),
        "X-Doc-Notes": encodeURIComponent(meta.notes || ""),
    }),
};
let cache = null;
export async function lookups(force = false) {
    if (!cache || force)
        cache = await api.get("/api/lookups");
    return cache;
}
export const invalidateLookups = () => { cache = null; };
