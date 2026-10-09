/** Navigation pane: a "+ New" menu, a few accounting tasks that open to show their pages, Settings at the foot,
 *  and the icon rail on wide screens. */
import { api, lookups } from "../core/api.js";
import { t } from "../core/i18n.js";
import { can } from "../core/session.js";
import { issueDialog } from "../pages/contacts/custody.js";
import { h, icon } from "../ui/index.js";
import { NAV, NAV_BOTTOM, permFor } from "./routes.js";
let navEl = null;
// ---- wide screens fold the pane to an icon rail, narrow screens slide it in and out
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
export function toggleNav() {
    if (narrow())
        document.body.classList.toggle("nav-collapsed");
    else
        setRail(!isRail());
}
let wasNarrow = narrow();
addEventListener("resize", () => {
    const now = narrow();
    if (now !== wasNarrow)
        document.body.classList.toggle("nav-collapsed", now); // wide screens use the icon rail instead
    wasNarrow = now;
});
// ---- report groups (the reports center lists them; kept here because the shell loads them once per session)
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
// ---- which task groups the user opened (remembered)
const openKey = "usool.nav.open";
const opened = () => { try {
    return JSON.parse(localStorage.getItem(openKey) || "[]");
}
catch {
    return [];
} };
const remember = (href, open) => {
    const set = new Set(opened());
    if (open)
        set.add(href);
    else
        set.delete(href);
    try {
        localStorage.setItem(openKey, JSON.stringify([...set]));
    }
    catch { /* ignore */ }
};
/** The "+ New" menu: every record the user may create, from anywhere. */
function newMenu() {
    const items = [
        ["New fixed asset", "assets.edit", "#/assets/new"],
        ["New maintenance order", "maintenance.edit", "#/maintenance/new"],
        ["Issue to employee", "custody.manage", () => void lookups().then((L) => issueDialog(L, {}, (c) => (location.hash = `#/custody/${c.CustodyID}`)))],
        ["New supplier", "contacts.edit", "#/suppliers/new"],
        ["New employee", "contacts.edit", "#/employees/new"],
        ["Run depreciation", "depreciation.run", "#/depreciation"],
    ];
    const mine = items.filter(([, perm]) => can(perm));
    if (!mine.length)
        return null;
    const menu = h("div", { class: "nn-menu", role: "menu" });
    const btn = h("button", { class: "nn-btn", type: "button", "aria-haspopup": "menu", "aria-expanded": "false" }, icon("plus"), h("span", null, t("New")));
    const wrap = h("div", { class: "nn" }, btn, menu);
    const close = () => { wrap.classList.remove("open"); btn.setAttribute("aria-expanded", "false"); document.removeEventListener("mousedown", outside); };
    const outside = (e) => { if (!wrap.contains(e.target))
        close(); };
    for (const [label, , go] of mine) {
        menu.append(h(typeof go === "string" ? "a" : "button", { class: "nn-item", role: "menuitem", ...(typeof go === "string" ? { href: go } : { type: "button" }),
            onclick: () => { close(); if (typeof go !== "string")
                go(); } }, t(label)));
    }
    btn.addEventListener("click", () => {
        const open = !wrap.classList.contains("open");
        wrap.classList.toggle("open", open);
        btn.setAttribute("aria-expanded", String(open));
        if (open) {
            document.addEventListener("mousedown", outside);
            menu.firstElementChild?.focus();
        }
        else
            close();
    });
    menu.addEventListener("keydown", (e) => {
        const list = [...menu.querySelectorAll(".nn-item")];
        const i = list.indexOf(document.activeElement);
        if (e.key === "Escape") {
            close();
            btn.focus();
        }
        else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            e.preventDefault();
            list[(i + (e.key === "ArrowDown" ? 1 : -1) + list.length) % list.length]?.focus();
        }
    });
    return wrap;
}
function navItem(item) {
    const kids = (item.children || []).filter((c) => can(permFor(c.href)));
    if (!kids.length && (item.children?.length || !can(permFor(item.href))))
        return null;
    const top = h("a", { class: "nav-top", href: kids.length ? kids[0].href : item.href, "data-href": item.href, title: t(item.label) }, icon(item.icon), h("span", { class: "nav-label" }, t(item.label)));
    if (!kids.length)
        return h("div", { class: "nav-group" }, top);
    const body = h("div", { class: "nav-kids" }, ...kids.map((c) => h("a", { class: "nav-kid", href: c.href, "data-href": c.href }, t(c.label))));
    const caret = h("button", { class: "nav-caret", type: "button", "aria-label": t(item.label), "aria-expanded": "false" }, icon("chevron"));
    const group = h("div", { class: "nav-group has-kids" }, h("div", { class: "nav-row" }, top, caret), body);
    const set = (open, keep = true) => { group.classList.toggle("open", open); caret.setAttribute("aria-expanded", String(open)); if (keep)
        remember(item.href, open); };
    caret.addEventListener("click", () => set(!group.classList.contains("open")));
    set(opened().includes(item.href), false);
    return group;
}
export function buildNav() {
    const nav = h("nav", { class: "nav", "aria-label": t("Navigation") });
    const nn = newMenu();
    if (nn)
        nav.append(nn);
    nav.append(h("div", { class: "nav-list" }, ...NAV.map(navItem)), h("div", { class: "nav-foot" }, ...NAV_BOTTOM.map(navItem)));
    nav.addEventListener("click", (e) => { if (narrow() && e.target.closest("a"))
        document.body.classList.add("nav-collapsed"); });
    navEl = nav;
    return nav;
}
/** Highlight the page on screen and the task it belongs to (its group opens). */
export function markActive(href) {
    if (!navEl)
        return;
    navEl.querySelectorAll(".active").forEach((n) => n.classList.remove("active"));
    const link = navEl.querySelector(`.nav-kid[data-href="${href}"]`) || navEl.querySelector(`.nav-top[data-href="${href}"]`);
    if (!link)
        return;
    link.classList.add("active");
    const group = link.closest(".nav-group");
    group?.classList.add("active");
    if (group?.classList.contains("has-kids") && !group.classList.contains("open")) {
        group.classList.add("open");
        group.querySelector(".nav-caret")?.setAttribute("aria-expanded", "true");
    }
}
