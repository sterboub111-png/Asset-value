import { getLang } from "./i18n.js";
let me = null;
export const getMe = () => me;
export const setMe = (m) => { me = m; };
/** Does the signed-in user hold this permission? (administrators hold all; no permission = any signed-in user) */
export const can = (perm) => !perm || (!!me && (me.IsAdmin === 1 || me.permissions.includes(perm)));
export const userTitle = (m) => (m ? (getLang() === "ar" && m.FullNameAr ? m.FullNameAr : m.FullName) : "");
export const roleTitle = (m) => (m ? (getLang() === "ar" && m.RoleNameAr ? m.RoleNameAr : m.RoleName) : "");
export const initials = (name) => {
    const parts = name.trim().split(/\s+/).filter(Boolean);
    return ((parts[0]?.[0] || "?") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
};
const THEMES = ["light", "dark", "system"];
const darkQuery = matchMedia("(prefers-color-scheme: dark)");
export function getTheme() {
    try {
        const v = localStorage.getItem("gooya.theme");
        return THEMES.includes(v) ? v : "system";
    }
    catch {
        return "system";
    }
}
export const resolvedTheme = (p = getTheme()) => (p === "system" ? (darkQuery.matches ? "dark" : "light") : p);
export function applyTheme() { document.documentElement.dataset.theme = resolvedTheme(); }
export function setTheme(v) {
    try {
        localStorage.setItem("gooya.theme", THEMES.includes(v) ? v : "system");
    }
    catch { /* ignore */ }
    applyTheme();
}
/** Light -> dark -> system -> light (the top-bar and sign-in buttons). */
export const nextTheme = () => THEMES[(THEMES.indexOf(getTheme()) + 1) % THEMES.length];
export const themeIcon = (p = getTheme()) => (p === "light" ? "sun" : p === "dark" ? "moon" : "monitor");
export const themeLabel = (p = getTheme()) => (p === "light" ? "Light" : p === "dark" ? "Dark" : "Automatic (system)");
darkQuery.addEventListener("change", () => { if (getTheme() === "system")
    applyTheme(); });
