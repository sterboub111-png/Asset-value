import { api, lookups } from "../../core/api.js";
import { addSupplierShortcut, supplierOptions } from "../contacts/suppliers.js";
import { can } from "../../core/session.js";
import { custodyGrid, issueDialog } from "../contacts/custody.js";
import { t } from "../../core/i18n.js";
import type { Col, Rec } from "../../core/types.js";
import {
  DataGrid, Form, FieldDef, nm, onSave, redirectIf, clear, confirmDialog, dialog, fail, fastTab, fmtDate, fmtMoney, guard, h, opts, page, pill,
  ribbon, toast, today,
} from "../../ui/index.js";

type Args = { args: string[]; query: URLSearchParams };

// ================================================================ list
export async function assetsListPage(root: HTMLElement, _a: Args): Promise<void> {
  const L = await lookups();
  let assets: Rec[] = [];
  const cols: Col[] = [
    { key: "AssetCode", label: "Asset", link: (r) => `#/assets/${r.AssetID}`, width: 90 },
    { key: "AssetName", label: "Name", width: 180 },
    { key: "CategoryName", label: "Group" },
    { key: "AssetStatus", label: "Status", type: "status" },
    { key: "CustodianName", label: "Held by", hidden: true },
    { key: "VatApplicable", label: "VAT", hidden: true, render: (r) => (r.VatApplicable ? t("With VAT") : t("No VAT")) },
    { key: "AcquisitionDate", label: "Acquired", type: "date" },
    { key: "LocationName", label: "Location" },
    { key: "CostCenterName", label: "Cost center", hidden: true },
    { key: "AcquisitionCost", label: "Cost", type: "money" },
    { key: "AccumDep", label: "Accum. depreciation", type: "money" },
    { key: "NBV", label: "Net book value", type: "money" },
  ];
  const statusSel = h("select", { class: "gt-input", style: "width:170px", "aria-label": t("Status") },
    h("option", { value: "" }, t("All statuses")), ...[...L.statuses, "Disposed"].map((s) => h("option", { value: s }, t(s))));
  const catSel = h("select", { class: "gt-input", style: "width:200px", "aria-label": t("Group") },
    h("option", { value: "" }, t("All groups")), ...L.categories.map((c) => h("option", { value: c.CategoryID }, nm(c, "CategoryName"))));
  const grid = new DataGrid({ columns: cols, rows: [], totals: ["AcquisitionCost", "AccumDep", "NBV"], exportName: "fixed-assets",
    tools: [statusSel, catSel], onOpen: (r) => (location.hash = `#/assets/${r.AssetID}`), empty: "No fixed assets match the filter." });
  const load = async () => {
    try {
      assets = await api.get(`/api/assets?status=${encodeURIComponent(statusSel.value)}&category=${catSel.value}`);
      grid.setRows(assets);
    } catch (e) { fail(e); }
  };
  statusSel.onchange = catSel.onchange = load;
  const open = () => { const r = grid.selected(); if (r) location.hash = `#/assets/${r.AssetID}`; else toast(t("Select an asset first.")); };
  const rb = ribbon([[
    { perm: "assets.edit", label: t("New"), icon: "plus", primary: true, onClick: () => (location.hash = "#/assets/new") },
    { label: t("Edit"), icon: "edit", onClick: open },
  ], [{ label: t("Refresh"), icon: "refresh", onClick: load }]], [t("Fixed assets"), t("View")]);
  const pg = page({ title: t("All fixed assets"), subtitle: t("Fixed assets"), ribbon: rb.el }, grid.el);
  clear(root); root.append(pg.el);
  await load();
}

// ================================================================ form
const money2 = (v: any) => fmtMoney(v);

export async function assetFormPage(root: HTMLElement, a: Args): Promise<void> {
  const at = location.hash;
  const idArg = a.args[0];
  const isNew = idArg === "new";
  const L = await lookups(true);
  let asset: Rec | null = null;
  if (!isNew) {
    try { asset = await api.get(`/api/assets/${idArg}`); } catch (e) { fail(e); redirectIf(at, "#/assets"); return; }
  }
  const disposed = asset?.AssetStatus === "Disposed";
  const locked = !!asset?.has_posted;
  const code = isNew ? "" : asset!.AssetCode;

  const catOpts = opts(L.categories.filter((c) => c.IsActive || c.CategoryID === asset?.CategoryID), "CategoryID", (c) => `${c.CategoryCode} — ${nm(c, "CategoryName")}`);
  const locOpts = opts(L.locations.filter((c) => c.IsActive || c.LocationID === asset?.LocationID), "LocationID", (c) => `${c.LocationCode} — ${nm(c, "LocationName")}`);
  const ccOpts = opts(L.costcenters.filter((c) => c.IsActive || c.CostCenterID === asset?.CostCenterID), "CostCenterID", (c) => `${c.CostCenterCode} — ${nm(c, "CostCenterName")}`);
  const methOpts = opts(L.methods.filter((c) => c.IsActive || c.MethodID === asset?.MethodID), "MethodID", (c) => nm(c, "MethodName"));

  const v = asset || { AcquisitionDate: today(), ResidualValue: 0, OpeningAccumDep: 0 };
  const general: FieldDef[] = [
    { name: "AssetCode", label: "Asset number", readonly: true, hint: isNew ? "Assigned automatically from the fixed asset group." : undefined },
    { name: "AssetName", label: "Name", required: true, maxlength: 120 },
    { name: "AssetNameAr", label: "Name (Arabic)", maxlength: 120 },
    { name: "CategoryID", label: "Fixed asset group", type: "select", options: catOpts, required: true, readonly: locked || disposed,
      onChange: (val) => applyCategory(val) },
    { name: "AssetDescription", label: "Description", type: "textarea", wide: true },
  ];
  const settings = L.settings;
  const vatOn = settings.VATEnabled !== "0";
  const yesNo = [{ value: "1", label: t("Yes") }, { value: "0", label: t("No") }];
  // Books always carry the NET cost; VAT only records whether the asset was bought with VAT.
  function recalcVat(f: Form) {
    if (!vatOn) return;
    const amount = Number(f.value("PurchaseAmount") || 0);
    const applicable = vatOn && f.value("VatApplicable") === "1";
    const rate = Number(f.value("VatRate") || 0);
    const incl = f.value("VatInclusive") === "1";
    let net = amount, vat = 0;
    if (applicable) { net = incl ? Math.round((amount / (1 + rate / 100)) * 100) / 100 : amount; vat = incl ? Math.round((amount - net) * 100) / 100 : Math.round(net * rate / 100 * 100) / 100; }
    f.set("AcquisitionCost", net.toFixed(2)); f.set("VatAmount", vat.toFixed(2));
    for (const n of ["VatInclusive", "VatRate", "VatAmount"]) f.wrapOf(n).style.display = applicable ? "" : "none";
  }
  function vatFields(): FieldDef[] {
    return [
      { name: "VatApplicable", label: "Purchased with VAT", type: "select", options: yesNo, required: true, readonly: locked, onChange: (_v, f) => recalcVat(f) },
      { name: "VatInclusive", label: "Invoice amount is", type: "select", options: [{ value: "1", label: t("Inclusive of VAT") }, { value: "0", label: t("Exclusive of VAT") }], readonly: locked, onChange: (_v, f) => recalcVat(f) },
      { name: "VatRate", label: "VAT rate (%)", type: "number", step: "0.01", readonly: locked, onChange: (_v, f) => recalcVat(f) },
      { name: "PurchaseAmount", label: "Invoice amount", type: "number", step: "0.01", required: true, readonly: locked, onChange: (_v, f) => recalcVat(f) },
      { name: "VatAmount", label: "VAT amount (not part of cost)", type: "number", readonly: true },
      { name: "AcquisitionCost", label: "Net cost (recorded in books)", type: "number", readonly: true, hint: "Cost, depreciation and reports always use the net value, excluding VAT." },
    ];
  }
  const cost: FieldDef[] = [
    { name: "AcquisitionDate", label: "Acquisition date", type: "date", required: true, readonly: locked },
    ...(vatOn ? vatFields() : [{ name: "PurchaseAmount", label: "Acquisition cost", type: "number" as const, step: "0.01", required: true, readonly: locked, onChange: (_v: string, f: Form) => recalcVat(f) }]),
    { name: "ResidualValue", label: "Residual (salvage) value", type: "number", step: "0.01", readonly: locked },
    { name: "InServiceDate", label: "In-service date", type: "date", readonly: locked, onChange: (val, f) => { if (!f.value("DepreciationStartDate") || lastStart === f.value("DepreciationStartDate")) { f.set("DepreciationStartDate", val); lastStart = val; } } },
    { name: "DepreciationStartDate", label: "Depreciation start date", type: "date", readonly: locked, hint: "Depreciation is proposed from the period containing this date." },
    { name: "OpeningAccumDep", label: "Opening accumulated depreciation", type: "number", step: "0.01", readonly: locked, hint: "Only for assets brought in with prior depreciation." },
  ];
  const dep: FieldDef[] = [
    { name: "MethodID", label: "Depreciation method", type: "select", options: methOpts, readonly: locked },
    { name: "UsefulLifeYears", label: "Useful life (years)", type: "number", step: "0.01", readonly: locked,
      onChange: (val, f) => { const n = Number(val); if (n > 0) f.set("DepreciationRate", Math.round((100 / n) * 10000) / 10000); } },
    { name: "DepreciationRate", label: "Annual rate (%)", type: "number", step: "0.01", readonly: locked },
  ];
  const place: FieldDef[] = [
    { name: "LocationID", label: "Location", type: "select", options: locOpts, readonly: !isNew },
    { name: "CostCenterID", label: "Cost center", type: "select", options: ccOpts, readonly: !isNew },
    { name: "ResponsiblePerson", label: "Responsible person", maxlength: 120 },
  ];
  const purchase: FieldDef[] = [
    { name: "SupplierID", label: "Supplier", type: "select", options: supplierOptions(L, asset?.SupplierID) }, { name: "InvoiceNumber", label: "Invoice number" },
    { name: "PurchaseOrderNumber", label: "Purchase order" }, { name: "WarrantyExpiryDate", label: "Warranty expiry", type: "date" },
  ];
  const ident: FieldDef[] = [{ name: "Manufacturer", label: "Manufacturer" }, { name: "ModelNumber", label: "Model" }, { name: "SerialNumber", label: "Serial number" }];
  const notes: FieldDef[] = [{ name: "Notes", label: "Notes", type: "textarea", wide: true }];

  let lastStart = v.DepreciationStartDate || v.InServiceDate || "";
  const newDefaults = { VatApplicable: settings.VATDefaultApplicable ?? "1", VatInclusive: settings.VATDefaultInclusive ?? "0", VatRate: settings.VATRate ?? "15" };
  const init = { ...v, AssetCode: code, ...(isNew ? newDefaults : { VatApplicable: v.VatApplicable ? "1" : "0", VatInclusive: v.VatInclusive ? "1" : "0", VatRate: v.VatRate ?? settings.VATRate ?? "15", PurchaseAmount: vatOn ? (v.PurchaseAmount ?? v.AcquisitionCost) : v.AcquisitionCost }) };
  const forms = [general, cost, dep, place, purchase, ident, notes].map((defs) => new Form(defs, init));
  recalcVat(forms[1]);
  addSupplierShortcut(forms[4], "SupplierID");
  const byName = (n: string) => forms.find((f) => f.defs.some((d) => d.name === n))!;
  if (disposed) forms.forEach((f) => f.defs.forEach((d) => f.setReadonly(d.name, true)));

  let lastCategory = "";
  function applyCategory(val: string) {
    if (!isNew || val === lastCategory) return;   // a new asset takes the group's defaults; an existing one keeps its own life and rate
    lastCategory = val;
    byName("AssetCode").set("AssetCode", "");
    if (val) api.get(`/api/assets/next-code?category=${val}`).then((r) => { if (lastCategory === val) byName("AssetCode").set("AssetCode", r.code); }).catch(fail);
    const c = L.categories.find((x) => String(x.CategoryID) === val);
    if (!c) return;
    byName("UsefulLifeYears").set("UsefulLifeYears", c.UsefulLifeYears);
    byName("DepreciationRate").set("DepreciationRate", c.DepreciationRate);
    byName("MethodID").set("MethodID", c.MethodID);
  }

  const pending: File[] = [];
  const collect = (): Rec => Object.assign({}, ...forms.map((f) => f.get()));
  const save = async () => {
    if (!forms.every((f) => f.validate())) return;
    const body = collect();
    const res: Rec = isNew ? await api.post("/api/assets", body) : await api.put(`/api/assets/${asset!.AssetID}`, body);
    toast(t("Saved {0}", res.AssetCode), "ok");
    if (isNew && pending.length) {
      let failed = 0;
      for (const f of pending) {
        try { await api.upload(`/api/assets/${res.AssetID}/attachments`, f, { title: f.name }); } catch (e) { failed++; fail(e); }
      }
      toast(failed ? t("{0} file(s) could not be attached", failed) : t("{0} file(s) attached", pending.length), failed ? "err" : "ok");
    }
    if (isNew) location.hash = `#/assets/${res.AssetID}`; else await assetFormPage(root, a);
  };

  // ---- action pane
  const id = asset?.AssetID;
  const saveG = guard(save);
  onSave(root, () => { if (disposed) return; void saveG(); });
  const rb = ribbon([
    [{ perm: "assets.edit", label: t("Save"), icon: "save", primary: true, onClick: saveG, disabled: disposed },
     { perm: "assets.edit", label: t("New"), icon: "plus", onClick: () => (location.hash = "#/assets/new") },
     { perm: "assets.delete", label: t("Delete"), icon: "trash", danger: true, disabled: isNew,
       onClick: guard(async () => {
         if (await confirmDialog(t("Delete asset {0}? This cannot be undone.", code), { danger: true, ok: t("Delete") })) {
           await api.del(`/api/assets/${id}`); toast(t("Asset deleted"), "ok"); location.hash = "#/assets";
         }
       }) }],
    [{ perm: "assets.edit", label: t("Transfer"), icon: "transfer", disabled: isNew || disposed, onClick: () => transferDialog(asset!, L, () => assetFormPage(root, a)) },
     { perm: "assets.edit", label: t("Change status"), icon: "edit", disabled: isNew || disposed, onClick: () => statusDialog(asset!, L, () => assetFormPage(root, a)) },
     { perm: "custody.manage", label: t("Issue to employee"), icon: "user", disabled: isNew || disposed || !!asset?.custody?.some((c: Rec) => c.Status === "Issued"), onClick: () => issueDialog(L, { AssetID: asset!.AssetID }, (c) => (location.hash = `#/custody/${c.CustodyID}`)) },
     { perm: "assets.dispose", label: t("Dispose"), icon: "dispose", danger: true, disabled: isNew || disposed, onClick: () => disposeDialog(asset!, () => assetFormPage(root, a)) }],
    [{ perm: "maintenance.edit", label: t("New maintenance"), icon: "wrench", disabled: isNew || disposed, onClick: () => (location.hash = `#/maintenance/new?asset=${id}`) }],
    [{ label: t("Refresh"), icon: "refresh", disabled: isNew, onClick: () => assetFormPage(root, a) },
     { label: t("Back to list"), icon: "back", onClick: () => (location.hash = "#/assets") }],
  ], [t("Fixed asset"), t("Manage"), t("Maintenance"), t("View")]);

  // ---- fasttabs
  const tabs: Node[] = [
    fastTab(t("General"), forms[0].el, { open: true, summary: isNew ? "" : `${asset!.CategoryName || ""}` }),
    fastTab(t("Acquisition and cost"), forms[1].el, { open: true, summary: isNew ? "" : `${money2(asset!.AcquisitionCost)} · ${fmtDate(asset!.AcquisitionDate)}` }),
    fastTab(t("Depreciation"), forms[2].el, { open: true, summary: isNew ? "" : `${asset!.MethodName || ""} · ${asset!.UsefulLifeYears ?? ""} ${t("years")}` }),
    fastTab(t("Location and responsibility"), forms[3].el, { open: true, summary: isNew ? "" : [asset!.LocationName, asset!.CostCenterName].filter(Boolean).join(" · ") }),
    fastTab(t("Purchase and warranty"), forms[4].el, { summary: isNew ? "" : asset!.SupplierName || "" }),
    fastTab(t("Identification"), forms[5].el, { summary: isNew ? "" : asset!.SerialNumber || "" }),
    fastTab(t("Notes"), forms[6].el),
  ];
  if (locked && !disposed) tabs.unshift(h("div", { class: "msgbar" }, t("Depreciation has been posted for this asset, so cost, life, method and dates are locked.")));
  if (disposed) tabs.unshift(h("div", { class: "msgbar warn" }, t("This asset was disposed on {0} and is read-only.", fmtDate(asset!.DisposalDate))));

  if (isNew) tabs.push(fastTab(t("Attachments"), pendingPanel(pending), { open: true, summary: t("Files are attached when you save.") }));
  if (!isNew) {
    tabs.push(fastTab(t("Depreciation history"), depHistory(asset!), { summary: t("{0} lines", asset!.depreciation.length) }));
    tabs.push(fastTab(t("Transactions"), txGrid(asset!), { summary: t("{0} lines", asset!.transactions.length) }));
    tabs.push(fastTab(t("Custody"), custodyGrid(asset!.custody, { showAsset: false }), { summary: t("{0} lines", asset!.custody.length) }));
    tabs.push(fastTab(t("Maintenance"), maintGrid(asset!), { summary: t("{0} orders", asset!.maintenance.length) }));
    tabs.push(fastTab(t("Attachments"), attachmentsPanel(asset!, () => assetFormPage(root, a)), { summary: t("{0} files", asset!.attachments.length) }));
  }

  // ---- factbox
  const kv = (k: string, val: any, cls = "") => h("div", { class: cls }, h("span", { class: "k" }, t(k)), h("span", { class: "v" }, val));
  const fb = h("div", null,
    h("div", { class: "fb" }, h("h4", null, t("Book value")),
      h("div", { class: "kv" }, kv("Acquisition cost", money2(asset?.AcquisitionCost ?? 0)), vatOn ? kv("VAT (not in cost)", asset?.VatApplicable ? money2(asset.VatAmount) : t("No VAT")) : null, kv("Accumulated depreciation", money2(asset?.AccumDep ?? 0)), h("hr"),
        kv("Net book value", money2(asset?.NBV ?? 0), "big"))),
    h("div", { class: "fb" }, h("h4", null, t("Status")),
      h("div", { class: "kv" }, kv("Status", asset ? pill(asset.AssetStatus) : pill("Draft")), kv("In service", fmtDate(asset?.InServiceDate) || "—"),
        kv("Held by", asset?.CustodianName || "—"), kv("Attachments", asset ? asset.attachments.length : 0), kv("Last depreciation", lastPosted(asset) || "—"))));

  const pg = page({ title: isNew ? t("New fixed asset") : `${asset!.AssetCode} : ${nm(asset, "AssetName")}`, subtitle: t("Fixed assets"),
    pills: asset ? [pill(asset.AssetStatus)] : [], ribbon: rb.el, factbox: fb }, ...tabs);
  clear(root); root.append(pg.el);
}

function lastPosted(a: Rec | null): string {
  const p = (a?.depreciation || []).filter((d: Rec) => d.PostingStatus === "POSTED");
  return p.length ? p[p.length - 1].PeriodName : "";
}

function depHistory(a: Rec): Node {
  const grid = new DataGrid({
    search: false, exportName: `depreciation-${a.AssetCode}`, maxHeight: "300px", empty: "No depreciation lines.",
    totals: ["PeriodDepreciation"], rows: a.depreciation,
    columns: [
      { key: "PeriodName", label: "Period" }, { key: "OpeningAccumDep", label: "Opening accum. dep.", type: "money" },
      { key: "PeriodDepreciation", label: "Depreciation", type: "money" }, { key: "ClosingAccumDep", label: "Closing accum. dep.", type: "money" },
      { key: "ClosingNBV", label: "Net book value", type: "money" }, { key: "PostingStatus", label: "Status", type: "status" },
    ],
  });
  return grid.el;
}

function maintGrid(a: Rec): Node {
  const cost = (a.maintenance as Rec[]).filter((m) => m.Status === "Completed").reduce((s, m) => s + (m.Cost || 0), 0);
  const grid = new DataGrid({
    search: false, maxHeight: "300px", empty: "No maintenance orders.", rows: a.maintenance, totals: ["Cost"],
    columns: [
      { key: "MaintenanceNo", label: "Order", link: (r) => `#/maintenance/${r.MaintenanceID}` }, { key: "ScheduledDate", label: "Scheduled", type: "date" },
      { key: "MaintenanceType", label: "Type", render: (r) => t(r.MaintenanceType) }, { key: "Title", label: "Title" },
      { key: "Status", label: "Status", type: "status" }, { key: "Cost", label: "Cost", type: "money" },
    ],
  });
  return h("div", null, h("div", { class: "msgbar" }, t("Completed maintenance cost: {0}", fmtMoney(cost))), grid.el);
}

function txGrid(a: Rec): Node {
  const grid = new DataGrid({
    search: false, maxHeight: "300px", empty: "No transactions.", rows: a.transactions,
    columns: [
      { key: "TransactionDate", label: "Date", type: "date" }, { key: "TransactionType", label: "Type", type: "status" },
      { key: "Amount", label: "Amount", type: "money" }, { key: "FromLocation", label: "From location" }, { key: "ToLocation", label: "To location" },
      { key: "DisposalProceeds", label: "Proceeds", type: "money" }, { key: "ReferenceNumber", label: "Reference" }, { key: "Notes", label: "Notes" }, { key: "CreatedBy", label: "User" },
    ],
  });
  return grid.el;
}

function attachmentsPanel(a: Rec, reload: () => void): Node {
  const disposed = a.AssetStatus === "Disposed" || !can("assets.edit");
  const grid = new DataGrid({
    search: false, maxHeight: "260px", empty: "No attachments.", rows: a.attachments,
    columns: [
      { key: "DocumentTitle", label: "Title", render: (r) => h("a", { href: `/api/attachments/${r.AttachmentID}/download`, target: "_blank", class: "lnk" }, r.DocumentTitle || r.FileName) },
      { key: "DocumentType", label: "Type" }, { key: "FileName", label: "File" }, { key: "CreatedAt", label: "Added", type: "date" }, { key: "CreatedBy", label: "User" },
      { key: "AttachmentID", label: "", render: (r) => h("button", { class: "btn sm", type: "button", onclick: guard(async () => {
          if (await confirmDialog(t("Remove this attachment?"), { danger: true, ok: t("Remove") })) { await api.del(`/api/attachments/${r.AttachmentID}`); toast(t("Attachment removed"), "ok"); reload(); }
        }) }, t("Remove")) },
    ],
  });
  const file = h("input", { type: "file", multiple: true, style: "display:none" });
  const drop = h("div", { class: "drop", tabindex: 0, role: "button" }, t("Drop files here or click to attach (PDF, images, Excel, CSV, any type)"));
  const pick = () => file.click();
  drop.addEventListener("click", pick);
  drop.addEventListener("keydown", (e) => { const k = (e as KeyboardEvent).key; if (k === "Enter" || k === " ") { e.preventDefault(); pick(); } });
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  const send = async (fl: FileList | null) => {
    if (!fl || !fl.length) return;
    if (fl.length === 1) return attachDialog(a, fl[0], reload);
    for (const f of Array.from(fl)) { try { await api.upload(`/api/assets/${a.AssetID}/attachments`, f, { title: f.name }); } catch (e) { fail(e); } }
    toast(t("{0} file(s) attached", fl.length), "ok"); reload();
  };
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); send((e as DragEvent).dataTransfer?.files ?? null); });
  file.addEventListener("change", () => { send(file.files); file.value = ""; });
  return h("div", null, disposed ? null : drop, file, h("div", { style: "margin-top:10px" }, grid.el));
}

function pendingPanel(files: File[]): Node {
  const list = h("div", { class: "mini-list", style: "margin-top:10px" });
  const draw = () => {
    clear(list);
    files.forEach((f, i) => list.append(h("div", { class: "row" }, h("span", null, f.name, " ", h("small", { style: "color:var(--ink-3)" }, `(${Math.max(1, Math.round(f.size / 1024))} KB)`)),
      h("button", { class: "btn sm", type: "button", onclick: () => { files.splice(i, 1); draw(); } }, t("Remove")))));
  };
  const add = (fl: FileList | null) => { if (fl) { files.push(...Array.from(fl)); draw(); } };
  const input = h("input", { type: "file", multiple: true, style: "display:none" });
  const drop = h("div", { class: "drop", tabindex: 0, role: "button" }, t("Drop files here or click to attach (PDF, images, Excel, CSV, any type)"));
  drop.addEventListener("click", () => input.click());
  drop.addEventListener("keydown", (e) => { const k = (e as KeyboardEvent).key; if (k === "Enter" || k === " ") { e.preventDefault(); input.click(); } });
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); add((e as DragEvent).dataTransfer?.files ?? null); });
  input.addEventListener("change", () => { add(input.files); input.value = ""; });
  return h("div", null, drop, input, list);
}

function attachDialog(a: Rec, f: File, reload: () => void) {
  const form = new Form([
    { name: "title", label: "Title", wide: true }, { name: "type", label: "Document type", type: "select", options: ["Invoice", "Warranty", "Contract", "Photo", "Manual", "Other"].map((x) => ({ value: x, label: t(x) })) },
    { name: "notes", label: "Notes", wide: true },
  ], { title: f.name });
  dialog(t("Attach file"), h("div", null, h("p", { style: "margin-top:0" }, `${f.name} (${Math.max(1, Math.round(f.size / 1024))} KB)`), form.el), [
    { label: t("Attach"), primary: true, onClick: async () => { await api.upload(`/api/assets/${a.AssetID}/attachments`, f, form.get() as Record<string, string>); toast(t("Attachment added"), "ok"); reload(); } },
    { label: t("Cancel") },
  ]);
}

// ================================================================ dialogs
function transferDialog(a: Rec, L: Rec, done: () => void) {
  const form = new Form([
    { name: "TransactionDate", label: "Transfer date", type: "date", required: true },
    { name: "ToLocationID", label: "To location", type: "select", options: opts(L.locations.filter((x: Rec) => x.IsActive), "LocationID", (x) => nm(x, "LocationName")) },
    { name: "ToCostCenterID", label: "To cost center", type: "select", options: opts(L.costcenters.filter((x: Rec) => x.IsActive), "CostCenterID", (x) => nm(x, "CostCenterName")) },
    { name: "ResponsiblePerson", label: "Responsible person" },
    { name: "ReferenceNumber", label: "Reference" }, { name: "Notes", label: "Notes", type: "textarea", wide: true },
  ], { TransactionDate: today(), ToLocationID: a.LocationID, ToCostCenterID: a.CostCenterID, ResponsiblePerson: a.ResponsiblePerson });
  dialog(t("Transfer asset {0}", a.AssetCode), h("div", null,
    h("div", { class: "msgbar" }, t("Current: {0} / {1}", a.LocationName || "—", a.CostCenterName || "—")), form.el), [
    { label: t("Transfer"), primary: true, onClick: async () => { if (!form.validate()) return false; await api.post(`/api/assets/${a.AssetID}/transfer`, form.get()); toast(t("Asset transferred"), "ok"); done(); } },
    { label: t("Cancel") },
  ]);
}

function statusDialog(a: Rec, L: Rec, done: () => void) {
  const form = new Form([{ name: "status", label: "New status", type: "select", required: true, options: L.statuses.map((s: string) => ({ value: s, label: t(s) })) }], { status: a.AssetStatus });
  dialog(t("Change status"), form.el, [
    { label: t("OK"), primary: true, onClick: async () => { await api.post(`/api/assets/${a.AssetID}/status`, form.get()); toast(t("Status updated"), "ok"); done(); } },
    { label: t("Cancel") },
  ]);
}

function disposeDialog(a: Rec, done: () => void) {
  const form = new Form([
    { name: "TransactionDate", label: "Disposal date", type: "date", required: true, onChange: () => preview() },
    { name: "DisposalProceeds", label: "Sale proceeds", type: "number", step: "0.01", onChange: () => preview() },
    { name: "DisposalReason", label: "Reason", wide: true }, { name: "ReferenceNumber", label: "Reference" },
    { name: "Notes", label: "Notes", type: "textarea", wide: true },
  ], { TransactionDate: today(), DisposalProceeds: 0 });
  const box = h("div", { class: "msgbar warn" });
  const preview = () => {
    const p = Number(form.value("DisposalProceeds") || 0); const gain = p - a.NBV;
    box.textContent = t("Net book value {0} · proceeds {1} · {2} {3}", money2(a.NBV), money2(p), gain >= 0 ? t("gain") : t("loss"), money2(Math.abs(gain)));
  };
  preview();
  dialog(t("Dispose asset {0}", a.AssetCode), h("div", null, box, form.el), [
    { label: t("Dispose"), danger: true, onClick: async () => { if (!form.validate()) return false; await api.post(`/api/assets/${a.AssetID}/dispose`, form.get()); toast(t("Asset disposed"), "ok"); done(); } },
    { label: t("Cancel") },
  ]);
}
