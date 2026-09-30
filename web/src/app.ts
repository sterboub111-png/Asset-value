import { api, lookups } from "./api.js";
import { applyLang, getLang, setLang, t } from "./i18n.js";
import { assetFormPage, assetsListPage } from "./pages/assets.js";
import { dashboardPage } from "./pages/dashboard.js";
import { auditPage, depreciationPage, journalPage, periodsPage, transactionsPage } from "./pages/depreciation.js";
import { maintenanceFormPage, maintenanceListPage } from "./pages/maintenance.js";
import { REPORT_INFO, reportPage, reportsHubPage } from "./pages/reports.js";
import { custodyFormPage, custodyListPage, handoverFormPage } from "./pages/custody.js";
import { employeeFormPage, employeesListPage } from "./pages/employees.js";
import { supplierFormPage, suppliersListPage } from "./pages/suppliers.js";
import { runBackup } from "./pages/backup.js";
import { settingsPage } from "./pages/settings.js";
import { clear, fail, h, icon } from "./ui.js";

type PageFn = (root: HTMLElement, a: { args: string[]; query: URLSearchParams }) => Promise<void>;
interface Route { re: RegExp; fn: PageFn; nav: string; crumb: string; }

const ROUTES: Route[] = [
  { re: /^$/, fn: dashboardPage, nav: "#/", crumb: "Workspace" },
  { re: /^assets$/, fn: assetsListPage, nav: "#/assets", crumb: "All fixed assets" },
  { re: /^assets\/(new|\d+)$/, fn: assetFormPage, nav: "#/assets", crumb: "Fixed asset" },
  { re: /^maintenance$/, fn: maintenanceListPage, nav: "#/maintenance", crumb: "Maintenance orders" },
  { re: /^maintenance\/(new|\d+)$/, fn: maintenanceFormPage, nav: "#/maintenance", crumb: "Maintenance order" },
  { re: /^employees$/, fn: employeesListPage, nav: "#/employees", crumb: "Employees" },
  { re: /^employees\/(new|\d+)$/, fn: employeeFormPage, nav: "#/employees", crumb: "Employee" },
  { re: /^custody$/, fn: custodyListPage, nav: "#/custody", crumb: "Asset custody" },
  { re: /^custody\/(\d+)$/, fn: custodyFormPage, nav: "#/custody", crumb: "Custody record" },
  { re: /^custody\/(\d+)\/form$/, fn: handoverFormPage, nav: "#/custody", crumb: "Handover form" },
  { re: /^suppliers$/, fn: suppliersListPage, nav: "#/suppliers", crumb: "Suppliers" },
  { re: /^suppliers\/(new|\d+)$/, fn: supplierFormPage, nav: "#/suppliers", crumb: "Supplier" },
  { re: /^depreciation$/, fn: depreciationPage, nav: "#/depreciation", crumb: "Depreciation run" },
  { re: /^periods$/, fn: periodsPage, nav: "#/periods", crumb: "Depreciation periods" },
  { re: /^journal$/, fn: journalPage, nav: "#/journal", crumb: "Fixed asset journal" },
  { re: /^transactions$/, fn: transactionsPage, nav: "#/transactions", crumb: "Fixed asset transactions" },
  { re: /^audit$/, fn: auditPage, nav: "#/audit", crumb: "Audit log" },
  { re: /^reports$/, fn: reportsHubPage, nav: "#/reports", crumb: "Fixed asset reports" },
  { re: /^reports\/([\w-]+)$/, fn: reportPage, nav: "#/reports", crumb: "Fixed asset reports" },
  { re: /^settings(?:\/(\w+))?$/, fn: settingsPage, nav: "#/settings", crumb: "Settings" },
];

interface NavItem { label: string; icon: string; href: string; }
interface NavSection { id: string; section: string; items: NavItem[]; reports?: boolean; }

const NAV: NavSection[] = [
  { id: "ws", section: "Workspaces", items: [{ label: "Fixed assets", icon: "home", href: "#/" }] },
  { id: "common", section: "Common", items: [{ label: "All fixed assets", icon: "asset", href: "#/assets" }, { label: "New fixed asset", icon: "plus", href: "#/assets/new" }] },
  { id: "contacts", section: "Contacts", items: [
    { label: "Suppliers", icon: "truck", href: "#/suppliers" }, { label: "New supplier", icon: "plus", href: "#/suppliers/new" },
    { label: "Employees", icon: "user", href: "#/employees" }, { label: "New employee", icon: "plus", href: "#/employees/new" },
    { label: "Asset custody", icon: "transfer", href: "#/custody" }] },
  { id: "maint", section: "Maintenance", items: [{ label: "Maintenance orders", icon: "wrench", href: "#/maintenance" }, { label: "New maintenance order", icon: "plus", href: "#/maintenance/new" }] },
  { id: "periodic", section: "Periodic tasks", items: [{ label: "Depreciation run", icon: "calc", href: "#/depreciation" }, { label: "Depreciation periods", icon: "calendar", href: "#/periods" }] },
  { id: "inq", section: "Inquiries", items: [{ label: "Fixed asset journal", icon: "journal", href: "#/journal" }, { label: "Fixed asset transactions", icon: "list", href: "#/transactions" }, { label: "Audit log", icon: "audit", href: "#/audit" }] },
  { id: "reports", section: "Reports", reports: true, items: [{ label: "All reports", icon: "report", href: "#/reports" }] },
  { id: "setup", section: "Setup", items: [{ label: "Settings", icon: "setup", href: "#/settings" }] },
];

// ---- navigation pane state (collapsed sections are remembered)
const navKey = "gooya.nav.state";
const navState = (): Record<string, boolean> => { try { return JSON.parse(localStorage.getItem(navKey) || "{}"); } catch { return {}; } };
const isOpen = (id: string, def: boolean): boolean => navState()[id] ?? def;
const setOpen = (id: string, open: boolean) => { try { localStorage.setItem(navKey, JSON.stringify({ ...navState(), [id]: open })); } catch { /* ignore */ } };
let reportGroups: { group: string; items: NavItem[] }[] = [];

async function loadReportGroups(): Promise<void> {
  try {
    const list: { id: string; group: string }[] = await api.get("/api/reports");
    const order: string[] = [];
    const map = new Map<string, NavItem[]>();
    for (const r of list) {
      if (!map.has(r.group)) { map.set(r.group, []); order.push(r.group); }
      map.get(r.group)!.push({ label: REPORT_INFO[r.id]?.title || r.id, icon: "report", href: `#/reports/${r.id}` });
    }
    reportGroups = order.map((g) => ({ group: g, items: map.get(g)! }));
  } catch { reportGroups = []; }
}

function chevronBtn(cls: string, id: string, title: string, open: boolean, onToggle: (open: boolean) => void): HTMLElement {
  const b = h("button", { class: `${cls} ${open ? "open" : ""}`, type: "button", "aria-expanded": String(open) }, icon("chevron"), h("span", null, title));
  b.addEventListener("click", () => {
    const now = !b.classList.contains("open");
    b.classList.toggle("open", now); b.setAttribute("aria-expanded", String(now));
    setOpen(id, now);
    onToggle(now);
  });
  return b;
}

function buildNav(): HTMLElement {
  const nav = h("nav", { class: "nav", "aria-label": t("Navigation") });
  const filter = h("input", { type: "search", placeholder: t("Search for a page"), "aria-label": t("Search for a page"), autocomplete: "off" });
  nav.append(h("div", { class: "nav-search" }, h("span", { class: "ic-wrap" }, icon("search")), filter));
  const link = (i: NavItem, sub = false) => h("a", { href: i.href, class: `nav-item ${sub ? "sub" : ""}`, "data-label": t(i.label).toLowerCase() }, icon(i.icon), h("span", null, t(i.label)));
  for (const s of NAV) {
    const body = h("div", { class: "nav-body" });
    const secOpen = isOpen(s.id, true);
    body.style.display = secOpen ? "" : "none";
    nav.append(chevronBtn("nav-sec", s.id, t(s.section), secOpen, (o) => { body.style.display = o ? "" : "none"; }), body);
    s.items.forEach((i) => body.append(link(i)));
    if (s.reports) {
      for (const g of reportGroups) {
        const gid = `rep:${g.group}`;
        const gbody = h("div", { class: "nav-body grp" });
        const grpOpen = isOpen(gid, false);
        gbody.style.display = grpOpen ? "" : "none";
        const btn = chevronBtn("nav-grp", gid, t(g.group), grpOpen, (o) => { gbody.style.display = o ? "" : "none"; });
        btn.dataset.group = gid;
        body.append(btn, gbody);
        g.items.forEach((i) => gbody.append(link(i, true)));
      }
    }
  }
  // live filter: show only matching pages, expand their sections
  filter.addEventListener("input", () => {
    const q = filter.value.trim().toLowerCase();
    nav.querySelectorAll<HTMLElement>(".nav-item").forEach((a) => { a.style.display = !q || (a.dataset.label || "").includes(q) ? "" : "none"; });
    nav.querySelectorAll<HTMLElement>(".nav-body").forEach((b) => {
      if (q) b.style.display = b.querySelector(".nav-item:not([style*='none'])") ? "" : "none";
      else { const btn = b.previousElementSibling as HTMLElement | null; b.style.display = btn && btn.classList.contains("open") ? "" : "none"; }
    });
    nav.querySelectorAll<HTMLElement>(".nav-sec, .nav-grp").forEach((b) => { const body = b.nextElementSibling as HTMLElement; b.style.display = !q || (body && body.style.display !== "none") ? "" : "none"; });
  });
  nav.addEventListener("click", (e) => { if (innerWidth < 900 && (e.target as HTMLElement).closest("a")) document.body.classList.add("nav-collapsed"); });
  return nav;
}

function markActive(href: string): void {
  navEl.querySelectorAll<HTMLElement>("a.nav-item").forEach((a) => a.classList.toggle("active", a.getAttribute("href") === href));
  const active = navEl.querySelector<HTMLElement>(`a.nav-item[href="${href}"]`);
  // make sure the section (and report group) that holds the current page is visible
  let body = active?.parentElement || null;
  while (body && body.classList.contains("nav-body")) {
    const btn = body.previousElementSibling as HTMLElement | null;
    if (btn && !btn.classList.contains("open")) { btn.classList.add("open"); btn.setAttribute("aria-expanded", "true"); }
    body.style.display = "";
    body = body.parentElement;
  }
}

function getTheme(): string { try { return localStorage.getItem("gooya.theme") === "dark" ? "dark" : "light"; } catch { return "light"; } }
function setTheme(v: string): void { document.documentElement.dataset.theme = v; try { localStorage.setItem("gooya.theme", v); } catch { /* ignore */ } }
document.documentElement.dataset.theme = getTheme();

let mainEl: HTMLElement; let navEl: HTMLElement; let crumbEl: HTMLElement; let seq = 0;

function parseHash(): { path: string; query: URLSearchParams } {
  const raw = location.hash.replace(/^#\/?/, "");
  const [path, qs] = raw.split("?");
  return { path: path.replace(/\/$/, ""), query: new URLSearchParams(qs || "") };
}

async function render(): Promise<void> {
  const { path, query } = parseHash();
  const my = ++seq;
  document.querySelectorAll(".side-panel, .overlay").forEach((n) => n.remove());
  for (const r of ROUTES) {
    const m = path.match(r.re);
    if (!m) continue;
    const navHref = path.startsWith("reports/") ? `#/${path}` : r.nav;
    markActive(navHref);
    crumbEl.textContent = t(r.crumb);
    clear(mainEl); mainEl.scrollTop = 0;
    const holder = h("div", null); mainEl.append(holder);
    try { await r.fn(holder, { args: m.slice(1), query }); } catch (e) { if (my === seq) { fail(e); holder.append(h("div", { class: "msgbar err", style: "margin:24px" }, e instanceof Error ? t(e.message) : String(e))); } }
    return;
  }
  location.hash = "#/";
}

function buildShell(): HTMLElement {
  const search = h("input", { type: "search", placeholder: t("Go to asset…"), "aria-label": t("Search assets"), autocomplete: "off" });
  const results = h("div", { class: "tb-results", style: "display:none" });
  let timer: number | undefined;
  search.addEventListener("input", () => {
    clearTimeout(timer);
    timer = window.setTimeout(async () => {
      const q = search.value.trim();
      if (!q) { results.style.display = "none"; return; }
      try {
        const rows: any[] = await api.get(`/api/assets?q=${encodeURIComponent(q)}`);
        clear(results);
        if (!rows.length) results.append(h("div", { class: "empty" }, t("No matches")));
        rows.slice(0, 8).forEach((r) => results.append(h("a", { href: `#/assets/${r.AssetID}`, onclick: () => { results.style.display = "none"; search.value = ""; } },
          `${r.AssetCode} · ${r.AssetName}`, h("small", null, `${r.CategoryName || ""} · ${r.AssetStatus}`))));
        results.style.display = "block";
      } catch { /* ignore */ }
    }, 200);
  });
  document.addEventListener("click", (e) => { if (!(e.target as HTMLElement).closest(".tb-search")) results.style.display = "none"; });

  crumbEl = h("span", { class: "crumb" });
  const langBtn = h("button", { class: "tb-btn", title: t("Language"), onclick: () => { setLang(getLang() === "ar" ? "en" : "ar"); boot(); } }, icon("globe"), getLang() === "ar" ? "English" : "العربية");
  const backupBtn = h("button", { class: "tb-btn", title: t("Backup now"), "aria-label": t("Backup now"), onclick: async () => { backupBtn.disabled = true; await runBackup(); backupBtn.disabled = false; } }, icon("db"));
  const themeBtn = h("button", { class: "tb-btn", title: t("Dark mode"), "aria-label": t("Dark mode"), onclick: () => { setTheme(getTheme() === "dark" ? "light" : "dark"); themeBtn.replaceChildren(icon(getTheme() === "dark" ? "sun" : "moon")); } }, icon(getTheme() === "dark" ? "sun" : "moon"));
  const top = h("header", { class: "topbar" },
    h("button", { class: "tb-btn", "aria-label": t("Navigation"), onclick: () => { document.body.classList.toggle("nav-collapsed"); try { localStorage.setItem("gooya.nav", document.body.classList.contains("nav-collapsed") ? "0" : "1"); } catch { /* ignore */ } } }, icon("menu")),
    h("div", { class: "brand" }, h("span", { class: "logo" }, icon("asset")), "Gooya Asset"), h("span", { class: "sep" }), crumbEl,
    h("span", { class: "spacer" }), h("div", { class: "tb-search" }, search, h("span", { class: "ic-wrap" }, icon("search")), results), langBtn,
    backupBtn, themeBtn);
  navEl = buildNav();
  mainEl = h("main", { class: "main", id: "main" });
  return h("div", { class: "shell" }, top, h("div", { class: "body" }, navEl, mainEl));
}

async function boot(): Promise<void> {
  applyLang();
  const app = document.getElementById("app")!;
  clear(app);
  await loadReportGroups();
  app.append(buildShell());
  try { document.body.classList.toggle("nav-collapsed", innerWidth < 900 || localStorage.getItem("gooya.nav") === "0"); } catch { /* ignore */ }
  try {
    const L = await lookups(true);
    if (L.settings.CompanyName) document.title = `Gooya Asset — ${L.settings.CompanyName}`;
  } catch (e) { fail(e); }
  await render();
}

window.addEventListener("hashchange", render);
boot();
