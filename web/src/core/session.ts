import { getLang } from "./i18n.js";

export interface Me {
  UserID: number; UserName: string; FullName: string; FullNameAr?: string | null; Email?: string | null; Phone?: string | null;
  RoleID: number; RoleName: string; RoleNameAr?: string | null; IsAdmin: number; MustChangePassword: number;
  Language?: string | null; Theme?: string | null; permissions: string[];
}

let me: Me | null = null;
export const getMe = (): Me | null => me;
export const setMe = (m: Me | null): void => { me = m; };

/** Does the signed-in user hold this permission? (administrators hold all; no permission = any signed-in user) */
export const can = (perm?: string | null): boolean => !perm || (!!me && (me.IsAdmin === 1 || me.permissions.includes(perm)));

export const userTitle = (m: Me | null): string => (m ? (getLang() === "ar" && m.FullNameAr ? m.FullNameAr : m.FullName) : "");
export const roleTitle = (m: { RoleName: string; RoleNameAr?: string | null } | null): string => (m ? (getLang() === "ar" && m.RoleNameAr ? m.RoleNameAr : m.RoleName) : "");
export const initials = (name: string): string => {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] || "?") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
};

export function getTheme(): string { try { return localStorage.getItem("gooya.theme") === "dark" ? "dark" : "light"; } catch { return "light"; } }
export function setTheme(v: string): void { document.documentElement.dataset.theme = v; try { localStorage.setItem("gooya.theme", v); } catch { /* ignore */ } }
