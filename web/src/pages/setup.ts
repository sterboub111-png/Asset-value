import { api, invalidateLookups, lookups } from "../api.js";
import { t } from "../i18n.js";
import type { Col, Lookups, Rec } from "../types.js";
import { DataGrid, FieldDef, Form, nm, clear, confirmDialog, fail, guard, h, icon, opts, page, ribbon, toast } from "../ui.js";

type Args = { args: string[]; query: URLSearchParams };

interface MasterCfg { title: string; entity: string; pk: string; cols: Col[]; fields: (L: Lookups) => FieldDef[]; defaults?: Rec; }

const gl = (L: Lookups, type?: RegExp) => opts(L.glaccounts.filter((g) => g.IsActive && (!type || type.test(g.AccountType || ""))), "GLAccountID", (g) => `${g.AccountCode} — ${nm(g, "AccountName")}`);
const active = { name: "IsActive", label: "Active", type: "checkbox" as const };

export const MASTERS: Record<string, MasterCfg> = {
  categories: {
    title: "Fixed asset groups", entity: "categories", pk: "CategoryID", defaults: { IsActive: true, MethodID: 1 },
    cols: [{ key: "CategoryCode", label: "Group" }, { key: "CategoryName", label: "Name" }, { key: "CategoryNameAr", label: "Name (Arabic)" }, { key: "UsefulLifeYears", label: "Life (years)", type: "int" },
      { key: "DepreciationRate", label: "Rate %", type: "pct" }, { key: "IsActive", label: "Active", type: "bool" }],
    fields: (L) => [
      { name: "CategoryCode", label: "Group", required: true }, { name: "CategoryName", label: "Name", required: true }, { name: "CategoryNameAr", label: "Name (Arabic)" },
      { name: "UsefulLifeYears", label: "Useful life (years)", type: "number", step: "0.01" }, { name: "DepreciationRate", label: "Annual rate (%)", type: "number", step: "0.01", hint: "Left blank = 100 / life." },
      { name: "MethodID", label: "Depreciation method", type: "select", options: opts(L.methods.filter((m) => m.IsActive), "MethodID", (m) => nm(m, "MethodName")) },
      { name: "AssetAccountID", label: "Fixed asset account", type: "select", options: gl(L) },
      { name: "AccumDepAccountID", label: "Accumulated depreciation account", type: "select", options: gl(L) },
      { name: "DepExpenseAccountID", label: "Depreciation expense account", type: "select", options: gl(L) },
      { name: "GainAccountID", label: "Gain on disposal account", type: "select", options: gl(L) },
      { name: "LossAccountID", label: "Loss on disposal account", type: "select", options: gl(L) }, active],
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
    cols: [{ key: "AccountCode", label: "Account" }, { key: "AccountName", label: "Name" }, { key: "AccountNameAr", label: "Name (Arabic)" }, { key: "AccountType", label: "Type" }, { key: "IsActive", label: "Active", type: "bool" }],
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

export async function masterPage(root: HTMLElement, a: Args): Promise<void> {
  const cfg = MASTERS[a.args[0]];
  if (!cfg) { location.hash = "#/"; return; }
  const L = await lookups(true);
  const grid = new DataGrid({ columns: cfg.cols, rows: [], exportName: cfg.entity, limit: 1000, onOpen: (r) => edit(r) });
  let panel: HTMLElement | null = null;
  const holder = h("div", { class: "split-side" });
  const closePanel = () => { panel?.remove(); panel = null; };
  const load = async () => { try { invalidateLookups(); grid.setRows(await api.get(`/api/master/${cfg.entity}`)); } catch (e) { fail(e); } };

  function edit(rec: Rec | null) {
    closePanel();
    const form = new Form(cfg.fields(L), rec || cfg.defaults || {});
    const save = guard(async () => {
      if (!form.validate()) return;
      const body = form.get();
      if (rec) await api.put(`/api/master/${cfg.entity}/${rec[cfg.pk]}`, body); else await api.post(`/api/master/${cfg.entity}`, body);
      toast(t("Saved"), "ok"); closePanel(); await load();
    });
    panel = h("aside", { class: "side-panel inline", role: "dialog" },
      h("header", null, h("span", null, rec ? t("Edit") : t("New")), h("button", { class: "tb-btn", style: "color:var(--ink);height:28px", onclick: closePanel, "aria-label": t("Close") }, icon("x"))),
      h("div", { class: "dbody" }, form.el), h("footer", null, h("button", { class: "btn primary", onclick: save }, t("Save")), h("button", { class: "btn", onclick: closePanel }, t("Cancel"))));
    holder.append(panel);
    (form.el.querySelector("input,select") as HTMLElement | null)?.focus();
  }
  const rb = ribbon([
    [{ label: t("New"), icon: "plus", primary: true, onClick: () => edit(null) },
     { label: t("Edit"), icon: "edit", onClick: () => { const r = grid.selected(); if (r) edit(r); else toast(t("Select a record first.")); } },
     { label: t("Delete"), icon: "trash", danger: true, onClick: guard(async () => {
         const r = grid.selected(); if (!r) { toast(t("Select a record first.")); return; }
         if (await confirmDialog(t("Delete this record?"), { danger: true, ok: t("Delete") })) { await api.del(`/api/master/${cfg.entity}/${r[cfg.pk]}`); toast(t("Deleted"), "ok"); await load(); }
       }) }],
    [{ label: t("Refresh"), icon: "refresh", onClick: load }],
  ]);
  clear(root); root.append(page({ title: t(cfg.title), subtitle: t("Settings"), ribbon: rb.el }, h("div", { class: "split" }, h("div", { class: "split-main" }, grid.el), holder)).el);
  root.addEventListener("pagehide", closePanel);
  window.addEventListener("hashchange", closePanel, { once: true });
  await load();
}

export async function parametersPage(root: HTMLElement, _a: Args): Promise<void> {
  const L = await lookups(true);
  const s = L.settings;
  const form = new Form([
    { name: "CompanyName", label: "Company name", wide: true }, { name: "DefaultCurrency", label: "Currency" },
    { name: "FiscalYearStartMonth", label: "Fiscal year start month", type: "select", required: true, options: Array.from({ length: 12 }, (_, i) => ({ value: i + 1, label: new Date(2000, i, 1).toLocaleString(t("en-US"), { month: "long" }) })) },
    { name: "DisposalClearingAccountID", label: "Disposal proceeds (clearing) account", type: "select", options: gl(L) },
    { name: "AttachmentFolder", label: "Attachments folder", wide: true, hint: "Leave blank to use the 'attachments' folder next to the application." },
  ], s);
  const save = guard(async () => {
    if (!form.validate()) return;
    await api.put("/api/settings", form.get()); invalidateLookups(); toast(t("Parameters saved"), "ok");
  });
  const rb = ribbon([[{ label: t("Save"), icon: "save", primary: true, onClick: save }]]);
  clear(root);
  root.append(page({ title: t("Fixed asset parameters"), subtitle: t("Settings"), ribbon: rb.el },
    h("div", { class: "fasttab open" }, h("div", { class: "content", style: "display:block" }, form.el))).el);
}
