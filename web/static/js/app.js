import { api, lookups } from "./api.js";
import { applyLang, getLang, setLang, t } from "./i18n.js";
import { assetFormPage, assetsListPage } from "./pages/assets.js";
import { dashboardPage } from "./pages/dashboard.js";
import { auditPage, depreciationPage, journalPage, periodsPage, transactionsPage } from "./pages/depreciation.js";
import { maintenanceFormPage, maintenanceListPage } from "./pages/maintenance.js";
import { reportPage, reportsHubPage } from "./pages/reports.js";
import { settingsPage } from "./pages/settings.js";
import { clear, fail, h, icon } from "./ui.js";
const ROUTES = [
    { re: /^$/, fn: dashboardPage, nav: "#/", crumb: "Workspace" },
    { re: /^assets$/, fn: assetsListPage, nav: "#/assets", crumb: "All fixed assets" },
    { re: /^assets\/(new|\d+)$/, fn: assetFormPage, nav: "#/assets", crumb: "Fixed asset" },
    { re: /^maintenance$/, fn: maintenanceListPage, nav: "#/maintenance", crumb: "Maintenance orders" },
    { re: /^maintenance\/(new|\d+)$/, fn: maintenanceFormPage, nav: "#/maintenance", crumb: "Maintenance order" },
    { re: /^depreciation$/, fn: depreciationPage, nav: "#/depreciation", crumb: "Depreciation run" },
    { re: /^periods$/, fn: periodsPage, nav: "#/periods", crumb: "Depreciation periods" },
    { re: /^journal$/, fn: journalPage, nav: "#/journal", crumb: "Fixed asset journal" },
    { re: /^transactions$/, fn: transactionsPage, nav: "#/transactions", crumb: "Fixed asset transactions" },
    { re: /^audit$/, fn: auditPage, nav: "#/audit", crumb: "Audit log" },
    { re: /^reports$/, fn: reportsHubPage, nav: "#/reports", crumb: "Fixed asset reports" },
    { re: /^reports\/([\w-]+)$/, fn: reportPage, nav: "#/reports", crumb: "Fixed asset reports" },
    { re: /^settings(?:\/(\w+))?$/, fn: settingsPage, nav: "#/settings", crumb: "Settings" },
];
const NAV = [
    { section: "Workspaces", items: [{ label: "Fixed assets", icon: "home", href: "#/" }] },
    { section: "Common", items: [{ label: "All fixed assets", icon: "asset", href: "#/assets" }, { label: "New fixed asset", icon: "plus", href: "#/assets/new" }] },
    { section: "Maintenance", items: [{ label: "Maintenance orders", icon: "wrench", href: "#/maintenance" }, { label: "New maintenance order", icon: "plus", href: "#/maintenance/new" }] },
    { section: "Periodic tasks", items: [{ label: "Depreciation run", icon: "calc", href: "#/depreciation" }, { label: "Depreciation periods", icon: "calendar", href: "#/periods" }] },
    { section: "Inquiries", items: [{ label: "Fixed asset journal", icon: "journal", href: "#/journal" }, { label: "Fixed asset transactions", icon: "list", href: "#/transactions" }, { label: "Audit log", icon: "audit", href: "#/audit" }] },
    { section: "Reports", items: [{ label: "Fixed asset reports", icon: "report", href: "#/reports" }] },
    { section: "Setup", items: [{ label: "Settings", icon: "setup", href: "#/settings" }] },
];
function getTheme() { try {
    return localStorage.getItem("gooya.theme") === "dark" ? "dark" : "light";
}
catch {
    return "light";
} }
function setTheme(v) { document.documentElement.dataset.theme = v; try {
    localStorage.setItem("gooya.theme", v);
}
catch { /* ignore */ } }
document.documentElement.dataset.theme = getTheme();
let mainEl;
let navEl;
let crumbEl;
let seq = 0;
function parseHash() {
    const raw = location.hash.replace(/^#\/?/, "");
    const [path, qs] = raw.split("?");
    return { path: path.replace(/\/$/, ""), query: new URLSearchParams(qs || "") };
}
async function render() {
    const { path, query } = parseHash();
    const my = ++seq;
    document.querySelectorAll(".side-panel, .overlay").forEach((n) => n.remove());
    for (const r of ROUTES) {
        const m = path.match(r.re);
        if (!m)
            continue;
        const navHref = r.nav;
        navEl.querySelectorAll("a").forEach((a) => a.classList.toggle("active", a.getAttribute("href") === navHref));
        crumbEl.textContent = t(r.crumb);
        clear(mainEl);
        mainEl.scrollTop = 0;
        const holder = h("div", null);
        mainEl.append(holder);
        try {
            await r.fn(holder, { args: m.slice(1), query });
        }
        catch (e) {
            if (my === seq) {
                fail(e);
                holder.append(h("div", { class: "msgbar err", style: "margin:24px" }, e instanceof Error ? t(e.message) : String(e)));
            }
        }
        return;
    }
    location.hash = "#/";
}
function buildShell() {
    const search = h("input", { type: "search", placeholder: t("Go to asset…"), "aria-label": t("Search assets"), autocomplete: "off" });
    const results = h("div", { class: "tb-results", style: "display:none" });
    let timer;
    search.addEventListener("input", () => {
        clearTimeout(timer);
        timer = window.setTimeout(async () => {
            const q = search.value.trim();
            if (!q) {
                results.style.display = "none";
                return;
            }
            try {
                const rows = await api.get(`/api/assets?q=${encodeURIComponent(q)}`);
                clear(results);
                if (!rows.length)
                    results.append(h("div", { class: "empty" }, t("No matches")));
                rows.slice(0, 8).forEach((r) => results.append(h("a", { href: `#/assets/${r.AssetID}`, onclick: () => { results.style.display = "none"; search.value = ""; } }, `${r.AssetCode} · ${r.AssetName}`, h("small", null, `${r.CategoryName || ""} · ${r.AssetStatus}`))));
                results.style.display = "block";
            }
            catch { /* ignore */ }
        }, 200);
    });
    document.addEventListener("click", (e) => { if (!e.target.closest(".tb-search"))
        results.style.display = "none"; });
    crumbEl = h("span", { class: "crumb" });
    const langBtn = h("button", { class: "tb-btn", title: t("Language"), onclick: () => { setLang(getLang() === "ar" ? "en" : "ar"); boot(); } }, icon("globe"), getLang() === "ar" ? "English" : "العربية");
    const themeBtn = h("button", { class: "tb-btn", title: t("Dark mode"), "aria-label": t("Dark mode"), onclick: () => { setTheme(getTheme() === "dark" ? "light" : "dark"); themeBtn.replaceChildren(icon(getTheme() === "dark" ? "sun" : "moon")); } }, icon(getTheme() === "dark" ? "sun" : "moon"));
    const top = h("header", { class: "topbar" }, h("button", { class: "tb-btn", "aria-label": t("Navigation"), onclick: () => { document.body.classList.toggle("nav-collapsed"); try {
            localStorage.setItem("gooya.nav", document.body.classList.contains("nav-collapsed") ? "0" : "1");
        }
        catch { /* ignore */ } } }, icon("menu")), h("div", { class: "brand" }, h("span", { class: "logo" }, icon("asset")), "Gooya Asset"), h("span", { class: "sep" }), crumbEl, h("span", { class: "spacer" }), h("div", { class: "tb-search" }, search, h("span", { class: "ic-wrap" }, icon("search")), results), langBtn, themeBtn);
    navEl = h("nav", { class: "nav", "aria-label": t("Navigation") });
    for (const s of NAV) {
        navEl.append(h("h6", null, t(s.section)));
        s.items.forEach((i) => navEl.append(h("a", { href: i.href }, icon(i.icon), h("span", null, t(i.label)))));
    }
    navEl.addEventListener("click", (e) => { if (innerWidth < 900 && e.target.closest("a"))
        document.body.classList.add("nav-collapsed"); });
    mainEl = h("main", { class: "main", id: "main" });
    return h("div", { class: "shell" }, top, h("div", { class: "body" }, navEl, mainEl));
}
async function boot() {
    applyLang();
    const app = document.getElementById("app");
    clear(app);
    app.append(buildShell());
    try {
        document.body.classList.toggle("nav-collapsed", innerWidth < 900 || localStorage.getItem("gooya.nav") === "0");
    }
    catch { /* ignore */ }
    try {
        const L = await lookups(true);
        if (L.settings.CompanyName)
            document.title = `Gooya Asset — ${L.settings.CompanyName}`;
    }
    catch (e) {
        fail(e);
    }
    await render();
}
window.addEventListener("hashchange", render);
boot();
