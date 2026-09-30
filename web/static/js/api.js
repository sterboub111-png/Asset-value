import { getLang } from "./i18n.js";
export class ApiError extends Error {
}
async function call(method, url, body, headers = {}) {
    const init = { method, headers: { "X-Lang": getLang(), ...headers } };
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
        throw new ApiError("Cannot reach the Gooya Asset server. Is it still running?");
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok)
        throw new ApiError(data.error || `Request failed (${res.status})`);
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
