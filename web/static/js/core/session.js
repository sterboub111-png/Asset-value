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
export function getTheme() { try {
    return localStorage.getItem("gooya.theme") === "dark" ? "dark" : "light";
}
catch {
    return "light";
} }
export function setTheme(v) { document.documentElement.dataset.theme = v; try {
    localStorage.setItem("gooya.theme", v);
}
catch { /* ignore */ } }
