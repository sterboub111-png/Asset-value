import { AR } from "./ar.js";

export type Lang = "en" | "ar";
let lang: Lang = "en";
try { lang = (localStorage.getItem("gooya.lang") as Lang) === "ar" ? "ar" : "en"; } catch { /* storage unavailable */ }

export const getLang = () => lang;

export function applyLang(): void {
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
}

export function setLang(l: Lang): void {
  lang = l;
  try { localStorage.setItem("gooya.lang", l); } catch { /* ignore */ }
  applyLang();
}

/** Translate an English UI string; `{0}` style placeholders are replaced by args. */
export function t(text: string, ...args: (string | number)[]): string {
  let s = lang === "ar" ? (AR[text] ?? text) : text;
  args.forEach((a, i) => { s = s.split(`{${i}}`).join(String(a)); });
  return s;
}
