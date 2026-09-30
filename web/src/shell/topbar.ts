/** Top bar: navigation toggle, brand, breadcrumb, asset search, language, backup, theme and the account menu. */
import { api } from "../core/api.js";
import { getLang, setLang, t } from "../core/i18n.js";
import { can, getMe, getTheme, setMe, setTheme } from "../core/session.js";
import { runBackup } from "../pages/settings/backup.js";
import { clear, h, icon } from "../ui/index.js";
import { userMenu } from "./account.js";
import { toggleNav } from "./nav.js";

export interface TopbarDeps {
  sig: { signal: AbortSignal };
  restart: () => void;     // re-run the boot sequence (language changed)
  signOut: () => void;
}

export function buildTopbar({ sig, restart, signOut }: TopbarDeps): { el: HTMLElement; crumb: HTMLElement } {
  const search = h("input", { type: "search", placeholder: t("Go to asset…"), "aria-label": t("Search assets"), autocomplete: "off" });
  const results = h("div", { class: "tb-results", style: "display:none" });
  let timer: number | undefined;
  let searchSeq = 0;
  search.addEventListener("input", () => {
    clearTimeout(timer);
    timer = window.setTimeout(async () => {
      const q = search.value.trim();
      const my = ++searchSeq;
      if (!q) { results.style.display = "none"; return; }
      try {
        const rows: any[] = await api.get(`/api/assets?q=${encodeURIComponent(q)}`);
        if (my !== searchSeq) return;   // a newer search is already on its way
        clear(results);
        if (!rows.length) results.append(h("div", { class: "empty" }, t("No matches")));
        rows.slice(0, 8).forEach((r) => results.append(h("a", { href: `#/assets/${r.AssetID}`, onclick: () => { results.style.display = "none"; search.value = ""; } },
          `${r.AssetCode} · ${r.AssetName}`, h("small", null, `${r.CategoryName || ""} · ${r.AssetStatus}`))));
        results.style.display = "block";
      } catch { /* ignore */ }
    }, 200);
  });
  document.addEventListener("click", (e) => { if (!(e.target as HTMLElement).closest(".tb-search")) results.style.display = "none"; }, sig);

  const crumb = h("span", { class: "crumb" });
  const langBtn = h("button", { class: "tb-btn", "data-act": "lang", title: t("Language"), onclick: async () => { const next = getLang() === "ar" ? "en" : "ar"; setLang(next); try { await api.put("/api/auth/profile", { Language: next }); } catch { /* keep the local choice */ } setMe({ ...getMe()!, Language: next }); restart(); } }, icon("globe"), getLang() === "ar" ? "English" : "العربية");
  const backupBtn = h("button", { class: "tb-btn", "data-act": "backup", title: t("Backup now"), "aria-label": t("Backup now"), onclick: async () => { backupBtn.disabled = true; await runBackup(); backupBtn.disabled = false; } }, icon("db"));
  const themeBtn = h("button", { class: "tb-btn", "data-act": "theme", title: t("Dark mode"), "aria-label": t("Dark mode"), onclick: () => { setTheme(getTheme() === "dark" ? "light" : "dark"); void api.put("/api/auth/profile", { Theme: getTheme() }).catch(() => undefined); themeBtn.replaceChildren(icon(getTheme() === "dark" ? "sun" : "moon")); } }, icon(getTheme() === "dark" ? "sun" : "moon"));
  const el = h("header", { class: "topbar" },
    h("button", { class: "tb-btn", "data-act": "nav", "aria-label": t("Navigation"), title: t("Navigation"), onclick: toggleNav }, icon("menu")),
    h("div", { class: "brand" }, h("span", { class: "logo" }, icon("asset")), t("Usool")), h("span", { class: "sep" }), crumb,
    h("span", { class: "spacer" }), h("div", { class: "tb-search" }, search, h("span", { class: "ic-wrap" }, icon("search")), results), langBtn,
    can("backup.manage") ? backupBtn : null, themeBtn, userMenu(sig, signOut));
  return { el, crumb };
}
