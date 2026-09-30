import { api, invalidateLookups, lookups } from "../../core/api.js";
import { t } from "../../core/i18n.js";
import { DataGrid, Form, nm, pill, clear, confirmDialog, fail, guard, h, icon, opts, page, ribbon, toast } from "../../ui/index.js";
const gl = (L, type, keep = []) => opts(L.glaccounts.filter((g) => (g.IsActive || keep.includes(g.GLAccountID)) && (!type || type.test(g.AccountType || ""))), "GLAccountID", (g) => `${g.AccountCode} — ${nm(g, "AccountName")}`);
const active = { name: "IsActive", label: "Active", type: "checkbox" };
let defaultCurrency = "";
export const MASTERS = {
    currencies: {
        title: "Currencies", entity: "currencies", pk: "CurrencyID", defaults: { IsActive: true },
        cols: [{ key: "CurrencyCode", label: "Code" }, { key: "CurrencyName", label: "Name" }, { key: "CurrencyNameAr", label: "Name (Arabic)" }, { key: "Symbol", label: "Symbol" },
            { key: "IsDefault", label: "Default", render: (r) => (r.CurrencyCode === defaultCurrency ? pill("Default", "ok") : "") }, { key: "IsActive", label: "Active", type: "bool" }],
        fields: () => [{ name: "CurrencyCode", label: "Code", required: true, maxlength: 3, hint: "3-letter ISO 4217 code, e.g. SAR." }, { name: "CurrencyName", label: "Name", required: true },
            { name: "CurrencyNameAr", label: "Name (Arabic)" }, { name: "Symbol", label: "Symbol" }, active],
    },
    categories: {
        title: "Fixed asset groups", entity: "categories", pk: "CategoryID", defaults: { IsActive: true, MethodID: 1 },
        cols: [{ key: "CategoryCode", label: "Group" }, { key: "CategoryName", label: "Name" }, { key: "CategoryNameAr", label: "Name (Arabic)" }, { key: "UsefulLifeYears", label: "Life (years)", type: "int" },
            { key: "DepreciationRate", label: "Rate %", type: "pct" }, { key: "IsActive", label: "Active", type: "bool" }],
        fields: (L, rec) => [
            { name: "CategoryCode", label: "Group", required: true }, { name: "CategoryName", label: "Name", required: true }, { name: "CategoryNameAr", label: "Name (Arabic)" },
            { name: "UsefulLifeYears", label: "Useful life (years)", type: "number", step: "0.01" }, { name: "DepreciationRate", label: "Annual rate (%)", type: "number", step: "0.01", hint: "Left blank = 100 / life." },
            { name: "MethodID", label: "Depreciation method", type: "select", options: opts(L.methods.filter((m) => m.IsActive || m.MethodID === rec?.MethodID), "MethodID", (m) => nm(m, "MethodName")) },
            { name: "AssetAccountID", label: "Fixed asset account", type: "select", options: gl(L, undefined, [rec?.AssetAccountID]) },
            { name: "AccumDepAccountID", label: "Accumulated depreciation account", type: "select", options: gl(L, undefined, [rec?.AccumDepAccountID]) },
            { name: "DepExpenseAccountID", label: "Depreciation expense account", type: "select", options: gl(L, undefined, [rec?.DepExpenseAccountID]) },
            { name: "GainAccountID", label: "Gain on disposal account", type: "select", options: gl(L, undefined, [rec?.GainAccountID]) },
            { name: "LossAccountID", label: "Loss on disposal account", type: "select", options: gl(L, undefined, [rec?.LossAccountID]) }, active
        ],
    },
    locations: {
        title: "Locations", entity: "locations", pk: "LocationID", defaults: { IsActive: true },
        cols: [{ key: "LocationCode", label: "Code" }, { key: "LocationName", label: "Name" }, { key: "LocationNameAr", label: "Name (Arabic)" }, { key: "IsActive", label: "Active", type: "bool" }],
        fields: () => [{ name: "LocationCode", label: "Code", required: true }, { name: "LocationName", label: "Name", required: true }, { name: "LocationNameAr", label: "Name (Arabic)" }, active],
    },
    costcenters: {
        title: "Cost centers", entity: "costcenters", pk: "CostCenterID", defaults: { IsActive: true },
        cols: [{ key: "CostCenterCode", label: "Code" }, { key: "CostCenterName", label: "Name" }, { key: "CostCenterNameAr", label: "Name (Arabic)" }, { key: "IsActive", label: "Active", type: "bool" }],
        fields: () => [{ name: "CostCenterCode", label: "Code", required: true }, { name: "CostCenterName", label: "Name", required: true }, { name: "CostCenterNameAr", label: "Name (Arabic)" }, active],
    },
    glaccounts: {
        title: "Ledger accounts", entity: "glaccounts", pk: "GLAccountID", defaults: { IsActive: true },
        cols: [{ key: "AccountCode", label: "Account" }, { key: "AccountName", label: "Name" }, { key: "AccountNameAr", label: "Name (Arabic)" }, { key: "AccountType", label: "Type", render: (r) => t(r.AccountType || "") }, { key: "IsActive", label: "Active", type: "bool" }],
        fields: () => [{ name: "AccountCode", label: "Account", required: true }, { name: "AccountName", label: "Name", required: true }, { name: "AccountNameAr", label: "Name (Arabic)" },
            { name: "AccountType", label: "Type", type: "select", options: ["FIXED ASSET", "ACCUMULATED DEPRECIATION", "EXPENSE", "OTHER INCOME", "OTHER EXPENSE", "CLEARING"].map((x) => ({ value: x, label: x })) }, active],
    },
    methods: {
        title: "Depreciation methods", entity: "methods", pk: "MethodID", defaults: { IsActive: true },
        cols: [{ key: "MethodCode", label: "Code" }, { key: "MethodName", label: "Name" }, { key: "MethodNameAr", label: "Name (Arabic)" }, { key: "IsActive", label: "Active", type: "bool" }],
        fields: () => [{ name: "MethodCode", label: "Code", required: true, hint: "SL = straight line (the only method that calculates; any other code = no depreciation)." },
            { name: "MethodName", label: "Name", required: true }, { name: "MethodNameAr", label: "Name (Arabic)" }, active],
    },
};
export async function masterPage(root, a) {
    const cfg = MASTERS[a.args[0]];
    if (!cfg) {
        location.hash = "#/";
        return;
    }
    let L = await lookups(true);
    defaultCurrency = L.settings.DefaultCurrency || "";
    const grid = new DataGrid({ columns: cfg.cols, rows: [], exportName: cfg.entity, limit: 1000, onOpen: (r) => edit(r) });
    let panel = null;
    const holder = h("div", { class: "split-side" });
    const closePanel = () => { panel?.remove(); panel = null; };
    const load = async () => { try {
        invalidateLookups();
        grid.setRows(await api.get(`/api/master/${cfg.entity}`));
    }
    catch (e) {
        fail(e);
    } };
    function edit(rec) {
        closePanel();
        const form = new Form(cfg.fields(L, rec ?? undefined), rec || cfg.defaults || {});
        const save = guard(async () => {
            if (!form.validate())
                return;
            const body = form.get();
            if (rec)
                await api.put(`/api/master/${cfg.entity}/${rec[cfg.pk]}`, body);
            else
                await api.post(`/api/master/${cfg.entity}`, body);
            toast(t("Saved"), "ok");
            closePanel();
            await load();
        });
        panel = h("aside", { class: "side-panel inline", role: "dialog" }, h("header", null, h("span", null, rec ? t("Edit") : t("New")), h("button", { class: "tb-btn", style: "color:var(--ink);height:28px", onclick: closePanel, "aria-label": t("Close") }, icon("x"))), h("div", { class: "dbody" }, form.el), h("footer", null, h("button", { class: "btn primary", onclick: save }, t("Save")), h("button", { class: "btn", onclick: closePanel }, t("Cancel"))));
        holder.append(panel);
        form.el.querySelector("input,select")?.focus();
    }
    const rb = ribbon([
        [{ perm: "settings.manage", label: t("New"), icon: "plus", primary: true, onClick: () => edit(null) },
            { label: t("Edit"), icon: "edit", onClick: () => { const r = grid.selected(); if (r)
                    edit(r);
                else
                    toast(t("Select a record first.")); } },
            { perm: "settings.manage", label: t("Delete"), icon: "trash", danger: true, onClick: guard(async () => {
                    const r = grid.selected();
                    if (!r) {
                        toast(t("Select a record first."));
                        return;
                    }
                    if (await confirmDialog(t("Delete this record?"), { danger: true, ok: t("Delete") })) {
                        await api.del(`/api/master/${cfg.entity}/${r[cfg.pk]}`);
                        toast(t("Deleted"), "ok");
                        await load();
                    }
                }) }],
        [{ label: t("Refresh"), icon: "refresh", onClick: load }],
        ...(cfg.entity === "currencies" ? [[{ perm: "settings.manage", label: t("Set as default"), icon: "check", onClick: guard(async () => {
                        const r = grid.selected();
                        if (!r) {
                            toast(t("Select a record first."));
                            return;
                        }
                        await api.put("/api/settings", { DefaultCurrency: r.CurrencyCode });
                        L = await lookups(true);
                        defaultCurrency = r.CurrencyCode;
                        toast(t("Default currency is now {0}", r.CurrencyCode), "ok");
                        await load();
                    }) }]] : []),
    ]);
    clear(root);
    root.append(page({ title: t(cfg.title), subtitle: t("Settings"), ribbon: rb.el }, h("div", { class: "split" }, h("div", { class: "split-main" }, grid.el), holder)).el);
    window.addEventListener("hashchange", closePanel, { once: true });
    await load();
}
export async function parametersPage(root, _a) {
    const L = await lookups(true);
    const s = L.settings;
    const form = new Form([
        { name: "CompanyName", label: "Company name", wide: true },
        { name: "FiscalYearStartMonth", label: "Fiscal year start month", type: "select", required: true, options: Array.from({ length: 12 }, (_, i) => ({ value: i + 1, label: new Date(2000, i, 1).toLocaleString(t("en-US"), { month: "long" }) })) },
        { name: "DisposalClearingAccountID", label: "Disposal proceeds (clearing) account", type: "select", options: gl(L, undefined, [Number(s.DisposalClearingAccountID) || null]) },
        { name: "BackupFolder", label: "Backup folder", wide: true, hint: "Leave blank to use the 'backups' folder next to the application. A cloud or network folder is recommended." },
        { name: "AttachmentFolder", label: "Attachments folder", wide: true, hint: "Leave blank to use the 'attachments' folder next to the application." },
    ], s);
    const save = guard(async () => {
        if (!form.validate())
            return;
        await api.put("/api/settings", form.get());
        invalidateLookups();
        toast(t("Parameters saved"), "ok");
    });
    const rb = ribbon([[{ perm: "settings.manage", label: t("Save"), icon: "save", primary: true, onClick: save }]]);
    clear(root);
    root.append(page({ title: t("Fixed asset parameters"), subtitle: t("Settings"), ribbon: rb.el }, h("div", { class: "fasttab open" }, h("div", { class: "content", style: "display:block" }, form.el))).el);
}
export async function taxPage(root, _a) {
    const L = await lookups(true);
    const yesNo = [{ value: "1", label: t("Yes") }, { value: "0", label: t("No") }];
    const form = new Form([
        { name: "VATEnabled", label: "Track VAT on asset purchases", type: "select", options: yesNo, required: true },
        { name: "VATRate", label: "Standard VAT rate (%)", type: "number", step: "0.01", required: true },
        { name: "VATNumber", label: "Company VAT registration number" },
        { name: "VATDefaultApplicable", label: "New assets are purchased with VAT", type: "select", options: yesNo },
        { name: "VATDefaultInclusive", label: "Invoice amounts include VAT", type: "select", options: [{ value: "1", label: t("Inclusive of VAT") }, { value: "0", label: t("Exclusive of VAT") }] },
    ], L.settings);
    const save = guard(async () => {
        if (!form.validate())
            return;
        await api.put("/api/settings", form.get());
        invalidateLookups();
        toast(t("Tax settings saved"), "ok");
    });
    const rb = ribbon([[{ perm: "settings.manage", label: t("Save"), icon: "save", primary: true, onClick: save }]]);
    clear(root);
    root.append(page({ title: t("Tax (VAT)"), subtitle: t("Settings"), ribbon: rb.el }, h("div", { class: "fasttab open" }, h("div", { class: "content", style: "display:block" }, form.el))).el);
}
