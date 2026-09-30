import { api, lookups } from "../api.js";
import { addSupplierShortcut, supplierOptions } from "./suppliers.js";
import { t } from "../i18n.js";
import { DataGrid, Form, clear, confirmDialog, dialog, fail, fastTab, fmtDate, fmtMoney, guard, h, page, pill, ribbon, toast, today } from "../ui.js";
const typeOpts = (L) => L.maint_types.map((x) => ({ value: x, label: t(x) }));
const prioOpts = (L) => L.maint_priorities.map((x) => ({ value: x, label: t(x) }));
export function statusPill(m) {
    return h("span", null, pill(m.Status), m.IsOverdue ? " " : "", m.IsOverdue ? pill("Overdue", "err") : null);
}
// ---- dialogs shared by list and form
function completeDialog(m, L, done) {
    const form = new Form([
        { name: "CompletionDate", label: "Completion date", type: "date", required: true },
        { name: "Cost", label: "Cost", type: "number", step: "0.01" },
        { name: "SupplierID", label: "Vendor", type: "select", options: supplierOptions(L, m.SupplierID) }, { name: "PerformedBy", label: "Performed by" }, { name: "InvoiceNumber", label: "Invoice number" },
        { name: "NextDueDate", label: "Next due date", type: "date", hint: "Optional: schedules the next service for this asset." },
        { name: "Notes", label: "Notes", type: "textarea", wide: true },
    ], { ...m, CompletionDate: today(), Cost: m.Cost || "" });
    addSupplierShortcut(form, "SupplierID");
    dialog(t("Complete {0}", m.MaintenanceNo), form.el, [
        { label: t("Complete"), primary: true, onClick: async () => { if (!form.validate())
                return false; await api.post(`/api/maintenance/${m.MaintenanceID}/complete`, form.get()); toast(t("Maintenance completed"), "ok"); done(); } },
        { label: t("Cancel") },
    ]);
}
const startOrder = (m, done) => guard(async () => { await api.post(`/api/maintenance/${m.MaintenanceID}/start`, {}); toast(t("Work started"), "ok"); done(); })();
const cancelOrder = (m, done) => guard(async () => {
    if (await confirmDialog(t("Cancel order {0}?", m.MaintenanceNo), { danger: true, ok: t("Cancel order") })) {
        await api.post(`/api/maintenance/${m.MaintenanceID}/cancel`, {});
        toast(t("Order cancelled"), "ok");
        done();
    }
})();
// ================================================================ list
export async function maintenanceListPage(root, a) {
    const L = await lookups(true);
    const cols = [
        { key: "MaintenanceNo", label: "Order", link: (r) => `#/maintenance/${r.MaintenanceID}` },
        { key: "ScheduledDate", label: "Scheduled", type: "date" },
        { key: "AssetCode", label: "Asset", link: (r) => `#/assets/${r.AssetID}` }, { key: "AssetName", label: "Name" },
        { key: "MaintenanceType", label: "Type", render: (r) => t(r.MaintenanceType) }, { key: "Title", label: "Title" },
        { key: "Priority", label: "Priority", render: (r) => pill(r.Priority) },
        { key: "Status", label: "Status", render: statusPill }, { key: "Vendor", label: "Vendor" }, { key: "Cost", label: "Cost", type: "money" },
    ];
    const statusSel = h("select", { class: "gt-input", style: "width:170px", "aria-label": t("Status") }, h("option", { value: "Open" }, t("Open orders")), h("option", { value: "" }, t("All statuses")), ...L.maint_statuses.map((s) => h("option", { value: s }, t(s))));
    statusSel.value = a.query.get("status") ?? "Open";
    const typeSel = h("select", { class: "gt-input", style: "width:160px", "aria-label": t("Type") }, h("option", { value: "" }, t("All types")), ...typeOpts(L).map((o) => h("option", { value: o.value }, o.label)));
    const grid = new DataGrid({ columns: cols, rows: [], totals: ["Cost"], exportName: "maintenance", tools: [statusSel, typeSel], onOpen: (r) => (location.hash = `#/maintenance/${r.MaintenanceID}`), empty: "No maintenance orders match the filter." });
    const load = async () => { try {
        grid.setRows(await api.get(`/api/maintenance?status=${statusSel.value}&type=${typeSel.value}`));
    }
    catch (e) {
        fail(e);
    } };
    statusSel.onchange = typeSel.onchange = load;
    const sel = (fn) => () => { const r = grid.selected(); if (r)
        fn(r);
    else
        toast(t("Select an order first.")); };
    const rb = ribbon([
        [{ label: t("New"), icon: "plus", primary: true, onClick: () => (location.hash = "#/maintenance/new") },
            { label: t("Edit"), icon: "edit", onClick: sel((r) => (location.hash = `#/maintenance/${r.MaintenanceID}`)) }],
        [{ label: t("Start work"), icon: "play", onClick: sel((r) => startOrder(r, load)) }, { label: t("Complete"), icon: "check", onClick: sel((r) => completeDialog(r, L, load)) },
            { label: t("Cancel order"), icon: "x", danger: true, onClick: sel((r) => cancelOrder(r, load)) }],
        [{ label: t("Refresh"), icon: "refresh", onClick: load }, { label: t("Reports"), icon: "report", onClick: () => (location.hash = "#/reports/maintenance-history") }],
    ], [t("Maintenance"), t("Work order"), t("View")]);
    clear(root);
    root.append(page({ title: t("Maintenance orders"), subtitle: t("Maintenance"), ribbon: rb.el }, grid.el).el);
    await load();
}
// ================================================================ form
export async function maintenanceFormPage(root, a) {
    const isNew = a.args[0] === "new";
    const L = await lookups(true);
    let m = null;
    if (!isNew) {
        try {
            m = await api.get(`/api/maintenance/${a.args[0]}`);
        }
        catch (e) {
            fail(e);
            location.hash = "#/maintenance";
            return;
        }
    }
    const assets = (await api.get("/api/assets")).filter((x) => x.AssetStatus !== "Disposed" || x.AssetID === m?.AssetID);
    const closed = !!m && (m.Status === "Completed" || m.Status === "Cancelled");
    const started = !!m && m.Status !== "Planned";
    const pre = a.query.get("asset");
    const v = m || { MaintenanceType: "Corrective", Priority: "Medium", ScheduledDate: today(), OutOfService: true, AssetID: pre || "" };
    const general = [
        { name: "MaintenanceNo", label: "Order number", readonly: true },
        { name: "AssetID", label: "Asset", type: "select", required: true, readonly: started || closed, options: assets.map((x) => ({ value: x.AssetID, label: `${x.AssetCode} — ${x.AssetName}` })) },
        { name: "MaintenanceType", label: "Type", type: "select", required: true, options: typeOpts(L), onChange: (val, f) => { if (isNew)
                f.set("OutOfService", val === "Corrective"); } },
        { name: "Priority", label: "Priority", type: "select", required: true, options: prioOpts(L) },
        { name: "Title", label: "Title", required: true, wide: true, maxlength: 160 },
        { name: "Description", label: "Description", type: "textarea", wide: true },
        { name: "OutOfService", label: "Asset is out of service during the work (status becomes Under Repair)", type: "checkbox", wide: true },
    ];
    const schedule = [
        { name: "ScheduledDate", label: "Scheduled date", type: "date", required: true },
        { name: "StartDate", label: "Start date", type: "date", readonly: true }, { name: "CompletionDate", label: "Completion date", type: "date", readonly: true },
        { name: "NextDueDate", label: "Next due date", type: "date", hint: "For recurring maintenance; appears in the schedule report." },
    ];
    const cost = [
        { name: "SupplierID", label: "Vendor", type: "select", options: supplierOptions(L, m?.SupplierID) }, { name: "PerformedBy", label: "Performed by" }, { name: "InvoiceNumber", label: "Invoice number" },
        { name: "Cost", label: "Cost", type: "number", step: "0.01", hint: "Maintenance cost is an expense; it does not change the asset cost." },
    ];
    const notes = [{ name: "Notes", label: "Notes", type: "textarea", wide: true }];
    const init = { ...v, MaintenanceNo: m?.MaintenanceNo || t("(assigned on save)") };
    const forms = [general, schedule, cost, notes].map((d) => new Form(d, init));
    addSupplierShortcut(forms[2], "SupplierID");
    if (closed)
        forms.forEach((f) => f.defs.forEach((d) => f.setReadonly(d.name, true)));
    const collect = () => Object.assign({}, ...forms.map((f) => f.get()));
    const save = async () => {
        if (!forms.every((f) => f.validate()))
            return;
        const res = isNew ? await api.post("/api/maintenance", collect()) : await api.put(`/api/maintenance/${m.MaintenanceID}`, collect());
        toast(t("Saved {0}", res.MaintenanceNo), "ok");
        if (isNew)
            location.hash = `#/maintenance/${res.MaintenanceID}`;
        else
            await maintenanceFormPage(root, a);
    };
    const onKey = (e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        if (!closed)
            void guard(save)();
    } };
    document.addEventListener("keydown", onKey);
    window.addEventListener("hashchange", () => document.removeEventListener("keydown", onKey), { once: true });
    const again = () => maintenanceFormPage(root, a);
    const rb = ribbon([
        [{ label: t("Save") + " (Ctrl+S)", icon: "save", primary: true, disabled: closed, onClick: guard(save) },
            { label: t("New"), icon: "plus", onClick: () => (location.hash = "#/maintenance/new") },
            { label: t("Delete"), icon: "trash", danger: true, disabled: isNew || !(m?.Status === "Planned" || m?.Status === "Cancelled"), onClick: guard(async () => {
                    if (await confirmDialog(t("Delete order {0}?", m.MaintenanceNo), { danger: true, ok: t("Delete") })) {
                        await api.del(`/api/maintenance/${m.MaintenanceID}`);
                        toast(t("Order deleted"), "ok");
                        location.hash = "#/maintenance";
                    }
                }) }],
        [{ label: t("Start work"), icon: "play", disabled: isNew || m?.Status !== "Planned", onClick: () => startOrder(m, again) },
            { label: t("Complete"), icon: "check", disabled: isNew || closed, onClick: () => completeDialog(m, L, again) },
            { label: t("Cancel order"), icon: "x", danger: true, disabled: isNew || closed, onClick: () => cancelOrder(m, again) }],
        [{ label: t("Back to list"), icon: "back", onClick: () => (location.hash = "#/maintenance") }],
    ], [t("Maintenance"), t("Work order"), t("View")]);
    const kv = (k, val) => h("div", null, h("span", { class: "k" }, t(k)), h("span", { class: "v" }, val));
    const fb = h("div", { class: "fb" }, h("h4", null, t("Summary")), h("div", { class: "kv" }, kv("Status", m ? statusPill(m) : pill("Planned")), kv("Asset", m ? h("a", { href: `#/assets/${m.AssetID}` }, m.AssetCode) : "—"), kv("Scheduled date", fmtDate(m?.ScheduledDate) || "—"), kv("Cost", fmtMoney(m?.Cost || 0))));
    const tabs = [
        fastTab(t("General"), forms[0].el, { open: true, summary: m ? `${m.AssetCode} · ${t(m.MaintenanceType)}` : "" }),
        fastTab(t("Schedule"), forms[1].el, { open: true }), fastTab(t("Cost and vendor"), forms[2].el, { open: true }), fastTab(t("Notes"), forms[3].el),
    ];
    if (m?.IsOverdue)
        tabs.unshift(h("div", { class: "msgbar warn" }, t("This order is overdue (scheduled {0}).", fmtDate(m.ScheduledDate))));
    if (closed)
        tabs.unshift(h("div", { class: "msgbar" }, t("This order is {0} and is read-only.", t(m.Status))));
    clear(root);
    root.append(page({ title: isNew ? t("New maintenance order") : `${m.MaintenanceNo} : ${m.Title}`, subtitle: t("Maintenance"), pills: m ? [pill(m.Status)] : [], ribbon: rb.el, factbox: fb }, ...tabs).el);
}
