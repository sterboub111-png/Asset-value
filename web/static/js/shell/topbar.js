/** Top bar: navigation toggle, brand, breadcrumb, search everything, language, backup, appearance and the account menu. */
import { api } from "../core/api.js";
import { getLang, setLang, t } from "../core/i18n.js";
import { can, getMe, getTheme, nextTheme, setMe, setTheme, themeIcon, themeLabel } from "../core/session.js";
import { runBackup } from "../pages/settings/backup.js";
import { h, icon } from "../ui/index.js";
import { userMenu } from "./account.js";
import { toggleNav } from "./nav.js";
import { globalSearch } from "./search.js";
export function buildTopbar({ sig, restart, signOut }) {
    const crumb = h("span", { class: "crumb" });
    const langBtn = h("button", { class: "tb-btn", "data-act": "lang", title: t("Language"), onclick: async () => { const next = getLang() === "ar" ? "en" : "ar"; setLang(next); try {
            await api.put("/api/auth/profile", { Language: next });
        }
        catch { /* keep the local choice */ } setMe({ ...getMe(), Language: next }); restart(); } }, icon("globe"), getLang() === "ar" ? "English" : "العربية");
    const backupBtn = h("button", { class: "tb-btn", "data-act": "backup", title: t("Backup now"), "aria-label": t("Backup now"), onclick: async () => { backupBtn.disabled = true; await runBackup(); backupBtn.disabled = false; } }, icon("db"));
    const themeTitle = () => `${t("Appearance")}: ${t(themeLabel())}`;
    const themeBtn = h("button", { class: "tb-btn", "data-act": "theme", title: themeTitle(), "aria-label": themeTitle(), onclick: () => {
            setTheme(nextTheme());
            void api.put("/api/auth/profile", { Theme: getTheme() }).catch(() => undefined);
            themeBtn.replaceChildren(icon(themeIcon()));
            themeBtn.title = themeTitle();
            themeBtn.setAttribute("aria-label", themeTitle());
        } }, icon(themeIcon()));
    const el = h("header", { class: "topbar" }, h("button", { class: "tb-btn", "data-act": "nav", "aria-label": t("Navigation"), title: t("Navigation"), onclick: toggleNav }, icon("menu")), h("div", { class: "brand" }, h("span", { class: "logo" }, icon("asset")), t("Usool")), h("span", { class: "sep" }), crumb, h("span", { class: "spacer" }), globalSearch(sig), h("span", { class: "spacer" }), langBtn, can("backup.manage") ? backupBtn : null, themeBtn, userMenu(sig, signOut));
    return { el, crumb };
}
