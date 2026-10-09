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

// ---- appearance: light, dark, or "system" (follows the operating system and changes with it), like Claude Code
export type ThemePref = "light" | "dark" | "system";
const THEMES: ThemePref[] = ["light", "dark", "system"];
const darkQuery = matchMedia("(prefers-color-scheme: dark)");
export function getTheme(): ThemePref {
  try { const v = localStorage.getItem("gooya.theme") as ThemePref; return THEMES.includes(v) ? v : "system"; } catch { return "system"; }
}
export const resolvedTheme = (p: ThemePref = getTheme()): "light" | "dark" => (p === "system" ? (darkQuery.matches ? "dark" : "light") : p);
export function applyTheme(): void { document.documentElement.dataset.theme = resolvedTheme(); }
export function setTheme(v: string): void {
  try { localStorage.setItem("gooya.theme", THEMES.includes(v as ThemePref) ? v : "system"); } catch { /* ignore */ }
  applyTheme();
}
/** Light -> dark -> system -> light (the top-bar and sign-in buttons). */
export const nextTheme = (): ThemePref => THEMES[(THEMES.indexOf(getTheme()) + 1) % THEMES.length];
export const themeIcon = (p: ThemePref = getTheme()): string => (p === "light" ? "sun" : p === "dark" ? "moon" : "monitor");
export const themeLabel = (p: ThemePref = getTheme()): string => (p === "light" ? "Light" : p === "dark" ? "Dark" : "Automatic (system)");
darkQuery.addEventListener("change", () => { if (getTheme() === "system") applyTheme(); });
