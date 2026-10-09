import { api, invalidateLookups, lookups } from "../../core/api.js";
import { t } from "../../core/i18n.js";
import type { Col, Rec } from "../../core/types.js";
import { DataGrid, combo, FieldDef, Form, onSave, redirectIf, clear, confirmDialog, dialog, fail, fastTab, fmtMoney, guard, h, nm, opts, page, pill, ribbon, toast } from "../../ui/index.js";

type Args = { args: string[]; query: URLSearchParams };

const typeOpts = (L: Rec) => (L.supplier_types as string[]).map((x) => ({ value: x, label: t(x) }));

const general = (L: Rec): FieldDef[] => [
  { name: "SupplierCode", label: "Supplier code", required: true, maxlength: 20 },
  { name: "SupplierName", label: "Supplier name", required: true, maxlength: 160, wide: true },
  { name: "SupplierNameAr", label: "Name (Arabic)", maxlength: 160, wide: true },
  { name: "SupplierType", label: "Type", type: "select", required: true, options: typeOpts(L) },
  { name: "IsActive", label: "Active", type: "checkbox" },
];
const contact: FieldDef[] = [
  { name: "ContactPerson", label: "Contact person" }, { name: "Phone", label: "Phone" }, { name: "Mobile", label: "Mobile" },
  { name: "Email", label: "Email" }, { name: "Website", label: "Website" },
];
const address: FieldDef[] = [
  { name: "Address", label: "Address", wide: true }, { name: "City", label: "City" }, { name: "Country", label: "Country" },
];
const tax: FieldDef[] = [
  { name: "TaxNumber", label: "Tax (VAT) number" }, { name: "CRNumber", label: "Commercial registration" }, { name: "PaymentTerms", label: "Payment terms" },
  { name: "BankName", label: "Bank" }, { name: "IBAN", label: "IBAN", hint: "Spaces are removed automatically." },
];
const notes: FieldDef[] = [{ name: "Notes", label: "Notes", type: "textarea", wide: true }];

// ---- quick-add dialog used from the asset / maintenance forms
export async function quickSupplier(L: Rec, onSaved: (s: Rec) => void): Promise<void> {
  const code = (await api.get<Rec>("/api/suppliers/next-code")).code;
  const form = new Form([...general(L), ...contact, ...address, ...tax, ...notes], { SupplierCode: code, SupplierType: "Supplier", IsActive: true, Country: "Saudi Arabia" });
  dialog(t("New supplier"), form.el, [
    { label: t("Save"), primary: true, onClick: async () => {
        if (!form.validate()) return false;
        const s = await api.post<Rec>("/api/suppliers", form.get());
        invalidateLookups(); toast(t("Supplier {0} created", s.SupplierCode), "ok"); onSaved(s);
    } },
    { label: t("Cancel") },
  ], { wide: true });
}

export const supplierOptions = (L: Rec, keep?: number | null) =>
  opts((L.suppliers as Rec[]).filter((s) => s.IsActive || s.SupplierID === keep), "SupplierID", (s) => `${s.SupplierCode} — ${nm(s, "SupplierName")}`);

/** Adds a "+ New supplier" link under a supplier select so one can register a supplier without leaving the form. */
export function addSupplierShortcut(form: Form, name: string): void {
  const wrap = form.wrapOf(name);
  const link = h("a", { href: "javascript:void(0)", style: "font-size:12px", onclick: async (e: Event) => {
    e.preventDefault();
    const L = await lookups(true);
    quickSupplier(L, async (s) => {
      const fresh = await lookups(true);
      form.setOptions(name, supplierOptions(fresh, s.SupplierID)); form.set(name, s.SupplierID);
    });
  } }, "+ ", t("New supplier"));
  wrap.append(link);
}

// ================================================================ list
export async function suppliersListPage(root: HTMLElement, _a: Args): Promise<void> {
  const L = await lookups(true);
  const cols: Col[] = [
    { key: "SupplierCode", label: "Code", link: (r) => `#/suppliers/${r.SupplierID}` }, { key: "SupplierName", label: "Name", width: 180 },
    { key: "SupplierType", label: "Type", render: (r) => t(r.SupplierType) }, { key: "ContactPerson", label: "Contact person" },
    { key: "Phone", label: "Phone" }, { key: "Mobile", label: "Mobile" }, { key: "Email", label: "Email" }, { key: "City", label: "City" },
    { key: "AssetCount", label: "Assets", type: "int" }, { key: "PurchaseTotal", label: "Purchases", type: "money" },
    { key: "IsActive", label: "Status", render: (r) => pill(r.IsActive ? "Active" : "Inactive") },
  ];
  const typeSel = combo(typeOpts(L), { placeholder: t("All types"), label: t("Type"), width: 200 });
  const actSel = combo([{ value: "1", label: t("Active") }, { value: "0", label: t("Inactive") }], { placeholder: t("All statuses"), label: t("Status"), width: 160 });
  const grid = new DataGrid({ columns: cols, rows: [], totals: ["PurchaseTotal"], exportName: "suppliers", tools: [typeSel, actSel], onOpen: (r) => (location.hash = `#/suppliers/${r.SupplierID}`), empty: "No suppliers yet." });
  const load = async () => { try { grid.setRows(await api.get(`/api/suppliers?type=${encodeURIComponent(typeSel.value)}&active=${actSel.value}`)); } catch (e) { fail(e); } };
  typeSel.onchange = actSel.onchange = load;
  const rb = ribbon([
    [{ perm: "contacts.edit", label: t("New"), icon: "plus", primary: true, onClick: () => (location.hash = "#/suppliers/new") },
     { label: t("Edit"), icon: "edit", onClick: () => { const r = grid.selected(); if (r) location.hash = `#/suppliers/${r.SupplierID}`; else toast(t("Select a supplier first.")); } }],
    [{ label: t("Refresh"), icon: "refresh", onClick: load }, { label: t("Reports"), icon: "report", onClick: () => (location.hash = "#/reports/suppliers-directory") }],
  ], [t("Suppliers"), t("View")]);
  clear(root); root.append(page({ title: t("Suppliers"), subtitle: t("Contacts"), ribbon: rb.el }, grid.el).el);
  await load();
}

// ================================================================ form
export async function supplierFormPage(root: HTMLElement, a: Args): Promise<void> {
  const at = location.hash;
  const isNew = a.args[0] === "new";
  const L = await lookups(true);
  let sup: Rec | null = null;
  if (!isNew) { try { sup = await api.get(`/api/suppliers/${a.args[0]}`); } catch (e) { fail(e); redirectIf(at, "#/suppliers"); return; } }
  const v: Rec = sup ? { ...sup } : { SupplierCode: (await api.get<Rec>("/api/suppliers/next-code")).code, SupplierType: "Supplier", IsActive: true, Country: "Saudi Arabia" };
  const defs = [general(L), contact, address, tax, notes];
  const forms = defs.map((d) => new Form(d, v));
  const collect = (): Rec => Object.assign({}, ...forms.map((f) => f.get()));
  const save = async () => {
    if (!forms.every((f) => f.validate())) return;
    const res: Rec = isNew ? await api.post("/api/suppliers", collect()) : await api.put(`/api/suppliers/${sup!.SupplierID}`, collect());
    invalidateLookups(); toast(t("Saved {0}", res.SupplierCode), "ok");
    if (isNew) location.hash = `#/suppliers/${res.SupplierID}`; else await supplierFormPage(root, a);
  };
  const saveG = guard(save);
  onSave(root, () => { void saveG(); });
  const rb = ribbon([
    [{ perm: "contacts.edit", label: t("Save"), icon: "save", primary: true, onClick: saveG }, { perm: "contacts.edit", label: t("New"), icon: "plus", onClick: () => (location.hash = "#/suppliers/new") },
     { perm: "contacts.edit", label: t("Delete"), icon: "trash", danger: true, disabled: isNew, onClick: guard(async () => {
         if (await confirmDialog(t("Delete supplier {0}?", sup!.SupplierCode), { danger: true, ok: t("Delete") })) { await api.del(`/api/suppliers/${sup!.SupplierID}`); invalidateLookups(); toast(t("Supplier deleted"), "ok"); location.hash = "#/suppliers"; }
       }) }],
    [{ label: t("Back to list"), icon: "back", onClick: () => (location.hash = "#/suppliers") }],
  ]);
  const kv = (k: string, val: any) => h("div", null, h("span", { class: "k" }, t(k)), h("span", { class: "v" }, val));
  const fb = h("div", { class: "fb" }, h("h4", null, t("Activity")), h("div", { class: "kv" },
    kv("Status", sup ? pill(sup.IsActive ? "Active" : "Inactive") : pill("Draft")), kv("Assets purchased", sup?.AssetCount ?? 0), kv("Purchases", fmtMoney(sup?.PurchaseTotal ?? 0)),
    kv("Maintenance orders", sup?.MaintenanceCount ?? 0), kv("Maintenance cost", fmtMoney(sup?.MaintenanceTotal ?? 0))));
  const tabs: Node[] = [
    fastTab(t("General"), forms[0].el, { open: true, summary: sup ? `${sup.SupplierCode} · ${t(sup.SupplierType)}` : "" }),
    fastTab(t("Contact"), forms[1].el, { open: true, summary: sup ? [sup.Phone || sup.Mobile, sup.Email].filter(Boolean).join(" · ") : "" }),
    fastTab(t("Address"), forms[2].el, { open: true, summary: sup ? [sup.City, sup.Country].filter(Boolean).join(", ") : "" }),
    fastTab(t("Tax and banking"), forms[3].el, { summary: sup?.TaxNumber || "" }),
    fastTab(t("Notes"), forms[4].el),
  ];
  if (sup) {
    tabs.push(fastTab(t("Assets purchased"), new DataGrid({ search: false, maxHeight: "300px", empty: "No assets purchased from this supplier.", rows: sup.assets, totals: ["AcquisitionCost"], columns: [
      { key: "AssetCode", label: "Asset", link: (r) => `#/assets/${r.AssetID}` }, { key: "AssetName", label: "Name" }, { key: "AcquisitionDate", label: "Date", type: "date" },
      { key: "InvoiceNumber", label: "Invoice" }, { key: "AcquisitionCost", label: "Cost", type: "money" }, { key: "AssetStatus", label: "Status", type: "status" }] }).el, { summary: t("{0} lines", sup.assets.length) }));
    tabs.push(fastTab(t("Maintenance orders"), new DataGrid({ search: false, maxHeight: "300px", empty: "No maintenance orders.", rows: sup.maintenance, totals: ["Cost"], columns: [
      { key: "MaintenanceNo", label: "Order", link: (r) => `#/maintenance/${r.MaintenanceID}` }, { key: "AssetCode", label: "Asset" }, { key: "ScheduledDate", label: "Scheduled", type: "date" },
      { key: "Title", label: "Title" }, { key: "Status", label: "Status", type: "status" }, { key: "Cost", label: "Cost", type: "money" }] }).el, { summary: t("{0} orders", sup.maintenance.length) }));
  }
  clear(root);
  root.append(page({ title: isNew ? t("New supplier") : `${sup!.SupplierCode} : ${nm(sup, "SupplierName")}`, subtitle: t("Contacts"), pills: sup ? [pill(sup.IsActive ? "Active" : "Inactive")] : [], ribbon: rb.el, factbox: fb }, ...tabs).el);
}
