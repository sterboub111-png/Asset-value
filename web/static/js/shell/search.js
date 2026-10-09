/** Search everything from the top bar ("/" or Ctrl+K): pages and actions, assets, suppliers, employees and reports.
 *  Results are grouped, filtered by the user's permissions, and opened with Enter or a click. */
import { api, lookups } from "../core/api.js";
import { t } from "../core/i18n.js";
import { can } from "../core/session.js";
import { REPORT_INFO } from "../pages/reports/reports.js";
import { clear, fold, h, icon, nm } from "../ui/index.js";
import { NAV, NAV_BOTTOM, permFor } from "./routes.js";
import { reportGroups } from "./nav.js";
/** Pages and the most common actions, by their translated names. */
function places() {
    const out = [];
    for (const n of [...NAV, ...NAV_BOTTOM]) {
        if (n.children)
            n.children.forEach((c) => can(permFor(c.href)) && out.push({ label: t(c.label), sub: t(n.label), href: c.href }));
        else if (can(permFor(n.href)))
            out.push({ label: t(n.label), href: n.href });
    }
    const acts = [["New fixed asset", "assets.edit", "#/assets/new"], ["New maintenance order", "maintenance.edit", "#/maintenance/new"],
        ["New supplier", "contacts.edit", "#/suppliers/new"], ["New employee", "contacts.edit", "#/employees/new"], ["Keyboard shortcuts", "", "#/settings/shortcuts"]];
    acts.forEach(([l, perm, href]) => can(perm || null) && out.push({ label: t(l), sub: t("Action"), href }));
    return out;
}
export function globalSearch(sig) {
    const input = h("input", { type: "search", placeholder: t("Search everything…"), "aria-label": t("Search everything"), autocomplete: "off", role: "combobox", "aria-expanded": "false" });
    const panel = h("div", { class: "gs-panel", role: "listbox" });
    const box = h("div", { class: "tb-search gs" }, h("span", { class: "ic-wrap" }, icon("search")), input, h("kbd", { class: "gs-key" }, "Ctrl K"), panel);
    let hits = [];
    let hi = 0, seq = 0, timer;
    const close = () => { panel.style.display = "none"; input.setAttribute("aria-expanded", "false"); };
    const go = (href) => { close(); input.value = ""; input.blur(); location.hash = href; };
    const mark = () => hits.forEach((n, i) => { n.classList.toggle("hi", i === hi); if (i === hi)
        n.scrollIntoView({ block: "nearest" }); });
    const render = (groups) => {
        clear(panel);
        hits = [];
        const filled = groups.filter(([, list]) => list.length);
        if (!filled.length)
            panel.append(h("div", { class: "gs-none" }, t("No matches")));
        for (const [title, list] of filled) {
            panel.append(h("div", { class: "gs-head" }, title));
            for (const x of list) {
                const a = h("a", { class: "gs-item", href: x.href, role: "option", onclick: (e) => { e.preventDefault(); go(x.href); } }, h("span", null, x.label), x.sub ? h("small", null, x.sub) : null);
                hits.push(a);
                panel.append(a);
            }
        }
        hi = 0;
        mark();
        panel.style.display = "block";
        input.setAttribute("aria-expanded", "true");
    };
    const run = async () => {
        const raw = input.value.trim(), q = fold(raw), my = ++seq;
        if (!q) {
            close();
            return;
        }
        const match = (s) => fold(s).includes(q);
        const pages = places().filter((p) => match(p.label)).slice(0, 5);
        const reports = reportGroups.flatMap((g) => g.ids).filter((id) => match(t(REPORT_INFO[id]?.title || id)) || match(t(REPORT_INFO[id]?.desc || "")))
            .slice(0, 5).map((id) => ({ label: t(REPORT_INFO[id]?.title || id), sub: t("Report"), href: `#/reports/${id}` }));
        let suppliers = [], employees = [], assets = [];
        const L = await lookups().catch(() => null);
        if (L && can("contacts.view")) {
            suppliers = L.suppliers.filter((s) => match(`${s.SupplierCode} ${s.SupplierName} ${s.SupplierNameAr || ""}`)).slice(0, 4)
                .map((s) => ({ label: nm(s, "SupplierName"), sub: s.SupplierCode, href: `#/suppliers/${s.SupplierID}` }));
            employees = L.employees.filter((e) => match(`${e.EmployeeCode} ${e.EmployeeName} ${e.EmployeeNameAr || ""}`)).slice(0, 4)
                .map((e) => ({ label: nm(e, "EmployeeName"), sub: [e.EmployeeCode, e.Department].filter(Boolean).join(" · "), href: `#/employees/${e.EmployeeID}` }));
        }
        if (can("assets.view")) {
            try {
                const rows = await api.get(`/api/assets?q=${encodeURIComponent(raw)}`);
                assets = rows.slice(0, 6).map((r) => ({ label: `${r.AssetCode} · ${r.AssetName}`, sub: `${r.CategoryName || ""} · ${t(r.AssetStatus)}`, href: `#/assets/${r.AssetID}` }));
            }
            catch { /* the other groups still show */ }
        }
        if (my !== seq)
            return; // a newer search is already on its way
        render([[t("Fixed assets"), assets], [t("Pages"), pages], [t("Reports"), reports], [t("Suppliers"), suppliers], [t("Employees"), employees]]);
    };
    input.addEventListener("input", () => { clearTimeout(timer); timer = window.setTimeout(run, 160); });
    input.addEventListener("focus", () => { if (input.value.trim())
        void run(); });
    input.addEventListener("keydown", (e) => {
        if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            if (!hits.length)
                return;
            e.preventDefault();
            hi = (hi + (e.key === "ArrowDown" ? 1 : -1) + hits.length) % hits.length;
            mark();
        }
        else if (e.key === "Enter") {
            const a = hits[hi];
            if (a) {
                e.preventDefault();
                go(a.getAttribute("href"));
            }
        }
        else if (e.key === "Escape") {
            close();
            input.blur();
        }
    });
    document.addEventListener("mousedown", (e) => { if (!box.contains(e.target))
        close(); }, sig);
    return box;
}
