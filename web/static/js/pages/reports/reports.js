import { api, lookups } from "../../core/api.js";
import { t } from "../../core/i18n.js";
import { getMe, userTitle } from "../../core/session.js";
import { addPin } from "./dashboard.js";
import { Analysis, Form, nm, cellValue, csvText, clear, downloadCsv, fail, fmtDate, h, opts, page, ribbon, toast, today } from "../../ui/index.js";
export const REPORT_INFO = {
    "asset-register": { title: "Fixed asset register", desc: "Cost, accumulated depreciation and net book value of every asset at a date." },
    "asset-summary": { title: "Fixed asset summary", desc: "Totals by group, location or cost center at a date." },
    rollforward: { title: "Fixed asset roll-forward", desc: "Opening balance, additions, disposals, depreciation and closing balance by group." },
    "depreciation-schedule": { title: "Depreciation schedule", desc: "Depreciation lines per asset and period for a fiscal year." },
    "depreciation-journal": { title: "Fixed asset journal postings", desc: "Posted debit and credit lines to the ledger accounts." },
    "gl-balances": { title: "Ledger account balances", desc: "Fixed asset postings summarised by ledger account." },
    disposals: { title: "Disposals and gain / loss", desc: "Assets sold or scrapped, with net book value, proceeds and result." },
    transactions: { title: "Asset transactions", desc: "Acquisitions, transfers, status changes and disposals." },
    "fully-depreciated": { title: "Fully depreciated assets", desc: "Assets still in use whose net book value reached the residual value." },
    "custody-by-employee": { title: "Custody by employee", desc: "What each employee received: assets, dates, condition and whether they are still held." },
    "employees-directory": { title: "Employees directory", desc: "All employees with their contact details and the number of assets they hold." },
    "vat-purchases": { title: "VAT on asset purchases", desc: "Net cost, VAT amount and invoice basis of every purchase, to tell VAT and non-VAT assets apart." },
    "suppliers-directory": { title: "Suppliers directory", desc: "All suppliers with their contact, tax and payment details." },
    "supplier-purchases": { title: "Purchases by supplier", desc: "Assets bought from each supplier with invoice and cost." },
    "supplier-summary": { title: "Supplier spend summary", desc: "Purchases and completed maintenance cost per supplier." },
    "maintenance-history": { title: "Maintenance history", desc: "Every maintenance order per asset with vendor and cost." },
    "maintenance-cost": { title: "Maintenance cost analysis", desc: "Completed maintenance cost and count by asset, group or type." },
    "maintenance-schedule": { title: "Maintenance schedule and overdue", desc: "Open orders and recurring due dates that are overdue or coming up." },
    "warranty-expiry": { title: "Warranty expiry", desc: "Assets whose warranty has expired or is about to." },
};
const yearStart = () => `${new Date().getFullYear()}-01-01`;
export const groupSlug = (g) => g.toLowerCase().replace(/\s+/g, "-");
/** "Reports" without a group: go to the first group (there is no all-reports hub). */
export async function reportsIndexPage(_root, _a) {
    const list = await api.get("/api/reports");
    location.hash = list.length ? `#/reports/g/${groupSlug(list[0].group)}` : "#/";
}
/** A report group (Depreciation, Maintenance ...): its reports sit in the action pane and are listed below. */
export async function reportsGroupPage(root, a) {
    const list = await api.get("/api/reports");
    const group = list.map((r) => r.group).find((g, i, all) => all.indexOf(g) === i && groupSlug(g) === a.args[0]);
    if (!group) {
        location.hash = "#/reports";
        return;
    }
    const items = list.filter((r) => r.group === group);
    const rb = ribbon([items.map((r) => ({ label: t(REPORT_INFO[r.id]?.title || r.id), icon: "report", onClick: () => (location.hash = `#/reports/${r.id}`) }))]);
    const body = h("div", { class: "hub" }, ...items.map((r) => h("a", { href: `#/reports/${r.id}` }, h("b", null, t(REPORT_INFO[r.id]?.title || r.id)), h("span", null, t(REPORT_INFO[r.id]?.desc || "")))));
    clear(root);
    root.append(page({ title: t(group), subtitle: t("Reports"), ribbon: rb.el }, body).el);
}
async function paramDefs(ids) {
    const L = await lookups();
    const map = {
        as_of: { name: "as_of", label: "As of date", type: "date" },
        from: { name: "from", label: "From date", type: "date" }, to: { name: "to", label: "To date", type: "date" },
        account: { name: "account", label: "Account name", type: "select", options: L.glaccounts.map((g) => ({ value: g.GLAccountID, label: `${g.AccountCode} — ${nm(g, "AccountName")}` })) },
        category: { name: "category", label: "Fixed asset group", type: "select", options: opts(L.categories, "CategoryID", (c) => nm(c, "CategoryName")) },
        location: { name: "location", label: "Location", type: "select", options: opts(L.locations, "LocationID", (c) => nm(c, "LocationName")) },
        costcenter: { name: "costcenter", label: "Cost center", type: "select", options: opts(L.costcenters, "CostCenterID", (c) => nm(c, "CostCenterName")) },
        status: { name: "status", label: "Status", type: "select", options: [...L.statuses, "Disposed"].map((s) => ({ value: s, label: t(s) })) },
        group_by: { name: "group_by", label: "Group by", type: "select", required: true, options: [
                { value: "category", label: t("Fixed asset group") }, { value: "location", label: t("Location") }, { value: "costcenter", label: t("Cost center") }
            ] },
        fiscal_year: { name: "fiscal_year", label: "Fiscal year", type: "number", step: "1", required: true },
        type: { name: "type", label: "Transaction type", type: "select", options: ["ACQUISITION", "TRANSFER", "STATUS", "DISPOSAL"].map((s) => ({ value: s, label: t(s) })) },
        vat: { name: "vat", label: "VAT status", type: "select", options: [{ value: "1", label: t("With VAT") }, { value: "0", label: t("No VAT") }] },
        employee: { name: "employee", label: "Employee", type: "select", options: L.employees.map((e) => ({ value: e.EmployeeID, label: `${e.EmployeeCode} — ${nm(e, "EmployeeName")}` })) },
        cstatus: { name: "cstatus", label: "Custody status", type: "select", options: [{ value: "Issued", label: t("Issued") }, { value: "Returned", label: t("Returned") }] },
        sactive: { name: "sactive", label: "Status", type: "select", options: [{ value: "1", label: t("Active") }, { value: "0", label: t("Inactive") }] },
        stype: { name: "stype", label: "Supplier type", type: "select", options: L.supplier_types.map((s) => ({ value: s, label: t(s) })) },
        supplier: { name: "supplier", label: "Supplier", type: "select", options: L.suppliers.map((s) => ({ value: s.SupplierID, label: `${s.SupplierCode} — ${nm(s, "SupplierName")}` })) },
        mstatus: { name: "mstatus", label: "Order status", type: "select", options: L.maint_statuses.map((s) => ({ value: s, label: t(s) })) },
        mtype: { name: "mtype", label: "Maintenance type", type: "select", options: L.maint_types.map((s) => ({ value: s, label: t(s) })) },
        mgroup: { name: "mgroup", label: "Group by", type: "select", required: true, options: [
                { value: "asset", label: t("Asset") }, { value: "category", label: t("Fixed asset group") }, { value: "type", label: t("Type") }
            ] },
        days: { name: "days", label: "Days ahead", type: "number", step: "1" },
    };
    return ids.map((i) => map[i]);
}
const VIEW_KEY = "usool.report.view";
// Printing: a table still wider than the A4 landscape page after the print styles is scaled down to fit, never cut off.
const PRINT_WIDTH = 1030; // 297 mm less 24 mm of margins, in CSS pixels
addEventListener("beforeprint", () => {
    const box = document.querySelector(".rp-body");
    const table = box?.querySelector("table.an-grid, table.rpt");
    if (!box || !table)
        return;
    box.classList.add("print-fit", "print-measure");
    box.style.setProperty("--fit", "1");
    const w = table.scrollWidth;
    box.classList.remove("print-measure");
    box.style.setProperty("--fit", w > PRINT_WIDTH ? String(Math.max(0.55, PRINT_WIDTH / w)) : "1");
});
addEventListener("afterprint", () => document.querySelector(".rp-body")?.classList.remove("print-fit"));
export async function reportPage(root, a) {
    const id = a.args[0];
    const list = await api.get("/api/reports");
    const meta = list.find((r) => r.id === id);
    if (!meta) {
        location.hash = "#/reports";
        return;
    }
    const title = t(REPORT_INFO[id]?.title || id);
    const defs = await paramDefs(meta.params);
    const L = await lookups();
    const defaults = { as_of: today(), from: yearStart(), to: today(), fiscal_year: String(new Date().getFullYear()), group_by: "category", mgroup: "asset", days: "30" };
    const params = {};
    // "run" marks optional fields the user left empty on purpose; required ones always fall back to their default
    for (const d of defs)
        params[d.name] = a.query.get(d.name) ?? (a.query.has("run") && !d.required ? "" : defaults[d.name] ?? "");
    // parameters sit in a bar above the data: the report runs at once with the defaults, Apply runs it again
    const form = new Form(defs, params, "fields rp-fields");
    const apply = () => {
        if (!form.validate())
            return;
        const qs = new URLSearchParams({ run: "1", ...Object.fromEntries(Object.entries(form.get()).map(([k, v]) => [k, String(v ?? "")]).filter(([, v]) => v !== "")) });
        const next = `#/reports/${id}?${qs}`;
        if (location.hash === next)
            void reportPage(root, a);
        else
            location.hash = next;
    };
    form.el.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target.tagName === "INPUT") {
        e.preventDefault();
        apply();
    } });
    const pbar = defs.length ? h("div", { class: "rp-bar" }, h("div", { class: "rp-desc" }, t(REPORT_INFO[id]?.desc || "")), form.el, h("div", { class: "rp-actions" }, h("button", { class: "btn primary", type: "button", onclick: apply }, t("Apply")), h("button", { class: "btn", type: "button", onclick: () => { if (location.hash === `#/reports/${id}`)
            void reportPage(root, a);
        else
            location.hash = `#/reports/${id}`; } }, t("Reset")))) : null;
    let mode = "analysis";
    try {
        if (localStorage.getItem(VIEW_KEY) === "layout")
            mode = "layout";
    }
    catch { /* ignore */ }
    let res = null;
    let an = null;
    const body = h("div", { class: "rp-body" }, h("div", { class: "loading" }, t("Loading…")));
    const fileName = () => title.replace(/[^\w\u0600-\u06ff-]+/g, "-");
    const rb = ribbon([
        [{ id: "analysis", label: t("Analyze"), icon: "columns", active: mode === "analysis", onClick: () => setMode("analysis") },
            { id: "layout", label: t("Report layout"), icon: "report", active: mode === "layout", onClick: () => setMode("layout") }],
        [{ label: t("Print"), icon: "print", onClick: () => window.print() },
            { label: t("Export to Excel"), icon: "download", onClick: () => { if (res)
                    mode === "analysis" && an ? an.exportCsv(fileName()) : exportCsv(res, title); } }],
        list.filter((r) => r.group === meta.group).map((r) => ({ label: t(REPORT_INFO[r.id]?.title || r.id), icon: "report", active: r.id === id, onClick: () => (location.hash = `#/reports/${r.id}`) })),
    ]);
    clear(root);
    root.append(page({ title, subtitle: t("Reports"), ribbon: rb.el }, pbar, body).el);
    const lines = () => defs.filter((d) => params[d.name]).map((d) => {
        const opt = d.options?.find((o) => String(o.value) === params[d.name]);
        return { label: t(d.label), value: opt ? opt.label : d.type === "date" ? fmtDate(params[d.name]) : params[d.name] };
    });
    const user = userTitle(getMe()) || L.user;
    const show = () => {
        if (!res)
            return;
        clear(body);
        if (mode === "layout") {
            body.append(h("div", { class: "paper" }, renderReport(res, title, lines(), user)));
            return;
        }
        an = new Analysis({ ...analysisOpts(res), onPin: (st, chartTitle) => {
                // dates left at their defaults (today, start of year) stay dynamic on the dashboard
                const keep = Object.fromEntries(Object.entries(params).filter(([k, v]) => v !== "" && v !== defaults[k]));
                addPin({ title: chartTitle, report: id, params: keep, state: st });
                toast(t("Pinned to the dashboard"), "ok");
            } });
        // on paper the analysis carries the same heading as the report layout
        body.append(h("div", { class: "paper an-print-head" }, reportHead(res, title, lines(), user)), an.el);
    };
    function setMode(m) {
        mode = m;
        try {
            localStorage.setItem(VIEW_KEY, m);
        }
        catch { /* ignore */ }
        rb.btns.analysis?.classList.toggle("active", m === "analysis");
        rb.btns.layout?.classList.toggle("active", m === "layout");
        show();
    }
    try {
        const q = new URLSearchParams(Object.fromEntries(Object.entries(params).filter(([, v]) => v !== "")));
        res = await api.get(`/api/reports/${id}?${q}`);
    }
    catch (e) {
        fail(e);
        clear(body);
        body.append(h("div", { class: "msgbar err" }, e instanceof Error ? t(e.message) : String(e)));
        return;
    }
    show();
}
/** The analysis of a report: its columns, its grouping and totals as the starting layout (also used by the dashboard). */
export function analysisOpts(r) {
    const cols = r.columns.map((c) => ({ key: c.key, label: c.label, type: c.type }));
    if (r.group_by && !cols.some((c) => c.key === r.group_by))
        cols.push({ key: r.group_by, label: r.group_by, type: "text" });
    const summed = new Set([...(r.totals || []), ...(r.subtotal_only || [])]);
    const text = (k, row) => {
        const c = cols.find((x) => x.key === k);
        return ENUM_COLS.has(k) ? t(String(row[k] ?? "")) : c ? cellValue(c, row[k]) : String(row[k] ?? "");
    };
    return {
        id: r.id, columns: cols, rows: r.rows, text, order: r.order,
        defaults: () => ({
            cols: r.columns.map((c) => c.key), groups: r.group_by ? [r.group_by] : [],
            aggs: Object.fromEntries(cols.filter((c) => isNum(c.type)).map((c) => [c.key, summed.has(c.key) ? "sum" : "none"])),
            pivotOn: false, pivot: "", filters: {}, sort: null, collapsed: [],
        }),
    };
}
/** Report sub-titles arrive as short English phrases with dates and numbers inside; translate the words around them. */
function subtitleText(raw) {
    const sub = raw.replace(/\d{4}-\d{2}-\d{2}/g, (d) => fmtDate(d));
    let m;
    const word = (w) => (w === "Beginning" || w === "today" ? t(w) : w);
    if ((m = sub.match(/^As of (.+)$/)))
        return `${t("As of")} ${m[1]}`;
    if ((m = sub.match(/^Fixed asset postings as of (.+)$/)))
        return `${t("Fixed asset postings as of")} ${m[1]}`;
    if ((m = sub.match(/^(\S+) to (\S+)$/)))
        return `${word(m[1])} ${t("to")} ${word(m[2])}`;
    if ((m = sub.match(/^Fiscal year (\d+)$/)))
        return `${t("Fiscal year")} ${m[1]}`;
    if ((m = sub.match(/^Due within (\d+) days$/)))
        return t("Due within {0} days", m[1]);
    if ((m = sub.match(/^Expiring within (\d+) days$/)))
        return t("Expiring within {0} days", m[1]);
    if ((m = sub.match(/^(\d+) suppliers$/)))
        return t("{0} suppliers", m[1]);
    if ((m = sub.match(/^(\d+) employees$/)))
        return t("{0} employees", m[1]);
    return t(sub);
}
const ENUM_COLS = new Set(["SupplierType", "VatStatus", "Basis", "Status", "MaintenanceType", "Priority", "Timing", "Source", "TransactionType", "PostingStatus", "JournalType"]);
const isNum = (type) => type === "money" || type === "int" || type === "pct";
function renderReport(r, title, paramLines, user) {
    const cols = r.columns;
    const totalKeys = r.totals || [];
    const sum = (rows, key) => rows.reduce((s, x) => s + Number(x[key] || 0), 0);
    const tr = (cls, cells) => h("tr", { class: cls }, ...cells);
    const tbody = h("tbody");
    const ENUM = new Set(["SupplierType", "VatStatus", "Basis", "Status", "MaintenanceType", "Priority", "Timing", "Source", "TransactionType", "PostingStatus", "JournalType"]);
    const cell = (c, row) => h("td", { class: isNum(c.type) ? "num" : "" }, ENUM.has(c.key) ? t(String(row[c.key] ?? "")) : cellValue(c, row[c.key]));
    const totalsRow = (cls, label, rows, keys) => tr(cls, cols.map((c, i) => h("td", { class: isNum(c.type) ? "num" : "" }, keys.includes(c.key) ? cellValue(c, sum(rows, c.key)) : i === 0 ? label : "")));
    if (!r.rows.length)
        tbody.append(tr("", [h("td", { colspan: cols.length, class: "empty" }, t("No data for these parameters."))]));
    if (r.group_by) {
        const gk = r.group_by;
        const order = [];
        const map = new Map();
        for (const row of r.rows) {
            const k = String(row[gk] ?? "—");
            if (!map.has(k)) {
                map.set(k, []);
                order.push(k);
            }
            map.get(k).push(row);
        }
        for (const k of order) {
            const rows = map.get(k);
            const glabel = cols.find((c) => c.key === gk)?.label; // the group field is not always a printed column (Employee, Supplier ...)
            tbody.append(tr("grp", [h("td", { colspan: cols.length }, glabel ? `${t(glabel)}: ${k}` : k)]));
            rows.forEach((row) => tbody.append(tr("", cols.map((c) => cell(c, row)))));
            const subKeys = r.subtotal_only || totalKeys;
            if (subKeys.length)
                tbody.append(totalsRow("sub", `${t("Subtotal")} ${k}`, rows, subKeys));
        }
    }
    else
        r.rows.forEach((row) => tbody.append(tr("", cols.map((c) => cell(c, row)))));
    if (totalKeys.length && r.rows.length)
        tbody.append(totalsRow("tot", t("Total"), r.rows, totalKeys));
    const thead = h("thead", null, tr("", cols.map((c) => h("th", { class: isNum(c.type) ? "num" : "" }, t(c.label)))));
    return h("div", { class: "rpt-doc" }, reportHead(r, title, paramLines, user), h("div", { style: "overflow:auto" }, h("table", { class: "rpt" }, thead, tbody)), h("div", { class: "rpt-foot" }, h("span", null, `${t("Usool")} · ${t("{0} records", r.rows.length)}`), h("span", null, title)));
}
/** Company, title, parameters and the printed-on / by / currency block of a report. */
function reportHead(r, title, paramLines, user) {
    const when = new Date();
    const stamp = `${fmtDate(r.generated)} ${String(when.getHours()).padStart(2, "0")}:${String(when.getMinutes()).padStart(2, "0")}`;
    const period = r.subtitle ? subtitleText(r.subtitle) : "";
    return h("div", { class: "rh" }, h("div", { class: "rh-l" }, h("div", { class: "co" }, r.company || t("Usool")), h("h2", null, title), period && !paramLines.length ? h("div", { class: "period" }, period) : null, paramLines.length ? h("div", { class: "params" }, ...paramLines.map((p) => h("span", null, h("b", null, `${p.label}: `), p.value))) : null), h("div", { class: "meta" }, h("div", null, h("span", null, `${t("Printed")}: `), stamp), h("div", null, h("span", null, `${t("Printed by")}: `), user), h("div", null, h("span", null, `${t("Currency")}: `), r.currency)));
}
function exportCsv(r, title) {
    const lines = [r.columns.map((c) => csvText(t(c.label))).join(",")];
    for (const row of r.rows)
        lines.push(r.columns.map((c) => (isNum(c.type) ? String(row[c.key] ?? "") : csvText(ENUM_COLS.has(c.key) ? t(String(row[c.key] ?? "")) : cellValue(c, row[c.key])))).join(","));
    downloadCsv(title.replace(/[^\w؀-ۿ-]+/g, "-"), lines.join("\r\n"));
}
