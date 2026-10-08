/** Navigation pane: sections, live filter, report groups, and the collapsible icon rail. */
import { api } from "../core/api.js";
import { t } from "../core/i18n.js";
import { can } from "../core/session.js";
import { groupSlug } from "../pages/reports/reports.js";
import { h, icon } from "../ui/index.js";
import { NAV, permFor } from "./routes.js";
let navEl;
// ---- navigation pane: wide screens fold it to an icon rail, narrow screens slide it in and out
export const railKey = "gooya.nav.rail";
export const narrow = () => innerWidth < 900;
const isRail = () => document.body.classList.contains("nav-rail");
function setRail(on) {
    document.body.classList.toggle("nav-rail", on);
    try {
        localStorage.setItem(railKey, on ? "1" : "0");
    }
    catch { /* ignore */ }
}
// a window that becomes narrow folds the pane away instead of letting it cover the page
let wasNarrow = narrow();
addEventListener("resize", () => {
    const now = narrow();
    if (now !== wasNarrow)
        document.body.classList.toggle("nav-collapsed", now); // wide screens use the icon rail instead
    wasNarrow = now;
});
export function toggleNav() {
    if (narrow())
        document.body.classList.toggle("nav-collapsed");
    else
        setRail(!isRail());
}
// ---- navigation pane state (collapsed sections are remembered)
const navKey = "gooya.nav.state";
const navState = () => { try {
    return JSON.parse(localStorage.getItem(navKey) || "{}");
}
catch {
    return {};
} };
const isOpen = (id, def) => navState()[id] ?? def;
const setOpen = (id, open) => { try {
    localStorage.setItem(navKey, JSON.stringify({ ...navState(), [id]: open }));
}
catch { /* ignore */ } };
export let reportGroups = [];
export async function loadReportGroups() {
    try {
        const list = await api.get("/api/reports");
        const map = new Map();
        for (const r of list)
            map.set(r.group, [...(map.get(r.group) || []), r.id]);
        reportGroups = [...map.entries()].map(([group, ids]) => ({ group, ids }));
    }
    catch {
        reportGroups = [];
    }
}
function chevronBtn(cls, id, title, open, onToggle) {
    const b = h("button", { class: `${cls} ${open ? "open" : ""}`, type: "button", "aria-expanded": String(open) }, icon("chevron"), h("span", null, title));
    b.addEventListener("click", () => {
        const now = !b.classList.contains("open");
        b.classList.toggle("open", now);
        b.setAttribute("aria-expanded", String(now));
        setOpen(id, now);
        onToggle(now);
    });
    return b;
}
export function buildNav() {
    const nav = h("nav", { class: "nav", "aria-label": t("Navigation") });
    const filter = h("input", { type: "search", placeholder: t("Search for a page"), "aria-label": t("Search for a page"), autocomplete: "off" });
    const searchBox = h("div", { class: "nav-search" }, h("span", { class: "ic-wrap" }, icon("search")), filter);
    searchBox.addEventListener("click", () => { if (isRail()) {
        setRail(false);
        filter.focus();
    } }); // a folded pane opens when the search is used
    nav.append(searchBox);
    const link = (i, sub = false) => h("a", { href: i.href, class: `nav-item ${sub ? "sub" : ""}`, "data-label": t(i.label).toLowerCase(), title: t(i.label) }, icon(i.icon), h("span", null, t(i.label)));
    for (const s of NAV) {
        const items = s.items.filter((i) => can(permFor(i.href)));
        if (!items.length && !(s.reports && can("reports.view") && reportGroups.length))
            continue;
        const body = h("div", { class: "nav-body" });
        const secOpen = isOpen(s.id, true);
        body.style.display = secOpen ? "" : "none";
        nav.append(chevronBtn("nav-sec", s.id, t(s.section), secOpen, (o) => { body.style.display = o ? "" : "none"; }), body);
        items.forEach((i) => body.append(link(i)));
        if (s.reports && can("reports.view"))
            reportGroups.forEach((g) => body.append(link({ label: g.group, icon: "report", href: `#/reports/g/${groupSlug(g.group)}` })));
    }
    // live filter: show only matching pages, expand their sections
    filter.addEventListener("input", () => {
        const q = filter.value.trim().toLowerCase();
        nav.querySelectorAll(".nav-item").forEach((a) => { a.style.display = !q || (a.dataset.label || "").includes(q) ? "" : "none"; });
        nav.querySelectorAll(".nav-body").forEach((b) => {
            if (q)
                b.style.display = b.querySelector(".nav-item:not([style*='none'])") ? "" : "none";
            else {
                const btn = b.previousElementSibling;
                b.style.display = btn && btn.classList.contains("open") ? "" : "none";
            }
        });
        nav.querySelectorAll(".nav-sec, .nav-grp").forEach((b) => { const body = b.nextElementSibling; b.style.display = !q || (body && body.style.display !== "none") ? "" : "none"; });
    });
    nav.addEventListener("click", (e) => { if (innerWidth < 900 && e.target.closest("a"))
        document.body.classList.add("nav-collapsed"); });
    navEl = nav;
    return nav;
}
export function markActive(href) {
    if (!navEl)
        return;
    navEl.querySelectorAll("a.nav-item").forEach((a) => a.classList.toggle("active", a.getAttribute("href") === href));
    const active = navEl.querySelector(`a.nav-item[href="${href}"]`);
    // make sure the section (and report group) that holds the current page is visible
    let body = active?.parentElement || null;
    while (body && body.classList.contains("nav-body")) {
        const btn = body.previousElementSibling;
        if (btn && !btn.classList.contains("open")) {
            btn.classList.add("open");
            btn.setAttribute("aria-expanded", "true");
        }
        body.style.display = "";
        body = body.parentElement;
    }
}
