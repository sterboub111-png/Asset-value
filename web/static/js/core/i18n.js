import { AR } from "./ar.js";
let lang = "en";
try {
    lang = localStorage.getItem("gooya.lang") === "ar" ? "ar" : "en";
}
catch { /* storage unavailable */ }
export const getLang = () => lang;
export function applyLang() {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
}
export function setLang(l) {
    lang = l;
    try {
        localStorage.setItem("gooya.lang", l);
    }
    catch { /* ignore */ }
    applyLang();
}
/** Translate an English UI string; `{0}` style placeholders are replaced by args. */
export function t(text, ...args) {
    let s = lang === "ar" ? (AR[text] ?? text) : text;
    args.forEach((a, i) => { s = s.split(`{${i}}`).join(String(a)); });
    return s;
}
