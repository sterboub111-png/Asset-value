import { api, lookups } from "../../core/api.js";
import { t } from "../../core/i18n.js";
import type { Col, Rec } from "../../core/types.js";
import { DataGrid, combo, Form, onSave, redirectIf, clear, confirmDialog, dialog, fail, fastTab, fmtDate, guard, h, nm, page, pill, ribbon, toast, today } from "../../ui/index.js";
import { employeeOptions, quickEmployee } from "./employees.js";

type Args = { args: string[]; query: URLSearchParams };

export const custodyStatus = (c: Rec): Node => pill(c.Status === "Issued" ? "Issued" : "Returned", c.Status === "Issued" ? "warn" : "");

/** Grid of custody records (used on the employee, asset and custody pages). */
export function custodyGrid(rows: Rec[], o: { showEmployee?: boolean; showAsset?: boolean } = {}): Node {
  const cols: Col[] = [{ key: "CustodyNo", label: "Custody", link: (r) => `#/custody/${r.CustodyID}` }];
  if (o.showEmployee !== false) cols.push({ key: "EmployeeName", label: "Employee", link: (r) => `#/employees/${r.EmployeeID}` });
  if (o.showAsset !== false) cols.push({ key: "AssetCode", label: "Asset", link: (r) => `#/assets/${r.AssetID}` }, { key: "AssetName", label: "Name" });
  cols.push({ key: "IssueDate", label: "Issued", type: "date" }, { key: "ReturnDate", label: "Returned", type: "date" }, { key: "Status", label: "Status", render: custodyStatus },
    { key: "AttachmentCount", label: "Signed form", render: (r) => (r.AttachmentCount ? pill("Attached", "ok") : pill("Missing", r.Status === "Issued" ? "warn" : "")) });
  return new DataGrid({ columns: cols, rows, search: false, maxHeight: "300px", empty: "No custody records." }).el;
}

/** Dialog that hands an asset to an employee and opens the new custody record (to print the handover form). */
export async function issueDialog(L: Rec, prefill: Rec, onDone: (c: Rec) => void): Promise<void> {
  const assets = (await api.get<Rec[]>("/api/assets").catch(() => [] as Rec[])).filter((a) => a.AssetStatus !== "Disposed" && (!a.CustodianName || a.AssetID === prefill.AssetID));
  const form = new Form([
    { name: "AssetID", label: "Asset", type: "select", required: true, wide: true, options: assets.map((a) => ({ value: a.AssetID, label: `${a.AssetCode} — ${a.AssetName}` })) },
    { name: "EmployeeID", label: "Employee", type: "select", required: true, wide: true, options: employeeOptions(L) },
    { name: "IssueDate", label: "Issue date", type: "date", required: true },
    { name: "IssuedBy", label: "Issued by", maxlength: 120 },
    { name: "ConditionOnIssue", label: "Condition on issue", wide: true, maxlength: 160 },
    { name: "Accessories", label: "Accessories / included items", wide: true, maxlength: 240 },
    { name: "Notes", label: "Notes", type: "textarea", wide: true },
  ], { IssueDate: today(), ConditionOnIssue: t("Good"), ...prefill });
  const link = h("a", { href: "javascript:void(0)", style: "font-size:12px", onclick: (e: Event) => {
    e.preventDefault();
    void quickEmployee(async (emp) => { const fresh = await lookups(true); form.setOptions("EmployeeID", employeeOptions(fresh, emp.EmployeeID)); form.set("EmployeeID", emp.EmployeeID); });
  } }, "+ ", t("New employee"));
  form.wrapOf("EmployeeID").append(link);
  dialog(t("Issue asset to employee"), form.el, [
    { label: t("Issue"), primary: true, onClick: async () => {
        if (!form.validate()) return false;
        const c = await api.post<Rec>("/api/custody", form.get()); toast(t("Custody {0} created", c.CustodyNo), "ok"); onDone(c);
    } },
    { label: t("Cancel") },
  ], { wide: true });
}

function returnDialog(cu: Rec, done: () => void) {
  const form = new Form([
    { name: "ReturnDate", label: "Return date", type: "date", required: true },
    { name: "ConditionOnReturn", label: "Condition on return", wide: true, maxlength: 160 },
    { name: "ReturnNotes", label: "Notes", type: "textarea", wide: true },
  ], { ReturnDate: today(), ConditionOnReturn: t("Good") });
  dialog(t("Return asset {0}", cu.AssetCode), form.el, [
    { label: t("Return asset"), primary: true, onClick: async () => { if (!form.validate()) return false; await api.post(`/api/custody/${cu.CustodyID}/return`, form.get()); toast(t("Asset returned"), "ok"); done(); } },
    { label: t("Cancel") },
  ]);
}

async function attachSigned(cu: Rec, done: () => void) {
  const input = h("input", { type: "file", multiple: true, accept: ".pdf,.png,.jpg,.jpeg,.tif,.tiff,.heic,.doc,.docx", style: "display:none" });
  document.body.appendChild(input);
  input.addEventListener("cancel", () => input.remove());   // the picker was closed without a file
  input.addEventListener("change", async () => {
    const files = Array.from(input.files || []); input.remove();
    if (!files.length) return;
    let ok = 0;
    for (const f of files) {
      try { await api.upload(`/api/custody/${cu.CustodyID}/attachments`, f, { title: `${t("Signed form")} ${cu.CustodyNo}`, type: "Custody form" }); ok++; } catch (e) { fail(e); }
    }
    if (ok) { toast(t("{0} file(s) attached", ok), "ok"); done(); }
  });
  input.click();
}

// ================================================================ list
export async function custodyListPage(root: HTMLElement, a: Args): Promise<void> {
  const L = await lookups(true);
  const statusSel = combo([{ value: "Issued", label: t("Issued") }, { value: "Returned", label: t("Returned") }], { placeholder: t("All statuses"), label: t("Status"), width: 170 });
  statusSel.value = a.query.get("status") ?? "Issued";
  const empSel = combo(employeeOptions(L), { placeholder: t("All employees"), label: t("Employee"), width: 240 });
  const cols: Col[] = [
    { key: "CustodyNo", label: "Custody", link: (r) => `#/custody/${r.CustodyID}` }, { key: "EmployeeName", label: "Employee", link: (r) => `#/employees/${r.EmployeeID}` },
    { key: "Department", label: "Department" }, { key: "AssetCode", label: "Asset", link: (r) => `#/assets/${r.AssetID}` }, { key: "AssetName", label: "Name" },
    { key: "CategoryName", label: "Group" }, { key: "IssueDate", label: "Issued", type: "date" }, { key: "ReturnDate", label: "Returned", type: "date" },
    { key: "Status", label: "Status", render: custodyStatus },
    { key: "AttachmentCount", label: "Signed form", render: (r) => (r.AttachmentCount ? pill("Attached", "ok") : pill("Missing", r.Status === "Issued" ? "warn" : "")) },
  ];
  const grid = new DataGrid({ columns: cols, rows: [], exportName: "custody", tools: [statusSel, empSel], onOpen: (r) => (location.hash = `#/custody/${r.CustodyID}`), empty: "No custody records match the filter." });
  const load = async () => { try { grid.setRows(await api.get(`/api/custody?status=${statusSel.value}&employee=${empSel.value}`)); } catch (e) { fail(e); } };
  statusSel.onchange = empSel.onchange = load;
  const sel = (fn: (r: Rec) => void) => () => { const r = grid.selected(); if (r) fn(r); else toast(t("Select a custody record first.")); };
  const rb = ribbon([
    [{ perm: "custody.manage", label: t("Issue asset"), icon: "plus", primary: true, onClick: () => issueDialog(L, {}, (c) => (location.hash = `#/custody/${c.CustodyID}`)) },
     { label: t("Open"), icon: "edit", onClick: sel((r) => (location.hash = `#/custody/${r.CustodyID}`)) }],
    [{ label: t("Print handover form"), icon: "print", onClick: sel((r) => (location.hash = `#/custody/${r.CustodyID}/form`)) },
     { perm: "custody.manage", label: t("Return asset"), icon: "back", onClick: sel((r) => (r.Status === "Issued" ? returnDialog(r, load) : toast(t("This asset was already returned")))) }],
    [{ label: t("Refresh"), icon: "refresh", onClick: load }, { label: t("Reports"), icon: "report", onClick: () => (location.hash = "#/reports/custody-by-employee") }],
  ], [t("Custody"), t("Forms"), t("View")]);
  clear(root); root.append(page({ title: t("Asset custody"), subtitle: t("Contacts"), ribbon: rb.el }, grid.el).el);
  await load();
}

// ================================================================ record
export async function custodyFormPage(root: HTMLElement, a: Args): Promise<void> {
  const at = location.hash;
  const id = Number(a.args[0]);
  let cu: Rec;
  try { cu = await api.get(`/api/custody/${id}`); } catch (e) { fail(e); redirectIf(at, "#/custody"); return; }
  const open = cu.Status === "Issued";
  const again = () => custodyFormPage(root, a);
  const fields = new Form([
    { name: "IssueDate", label: "Issue date", type: "date", required: true, readonly: !open },
    { name: "IssuedBy", label: "Issued by", readonly: !open, maxlength: 120 },
    { name: "ConditionOnIssue", label: "Condition on issue", wide: true, readonly: !open, maxlength: 160 },
    { name: "Accessories", label: "Accessories / included items", wide: true, readonly: !open, maxlength: 240 },
    { name: "Notes", label: "Notes", type: "textarea", wide: true, readonly: !open },
  ], cu);
  const info = new Form([
    { name: "EmployeeName", label: "Employee", readonly: true }, { name: "Department", label: "Department", readonly: true },
    { name: "AssetCode", label: "Asset", readonly: true }, { name: "AssetName", label: "Asset name", readonly: true },
    { name: "SerialNumber", label: "Serial number", readonly: true }, { name: "CategoryName", label: "Group", readonly: true },
  ], { ...cu, EmployeeName: nm(cu, "EmployeeName"), AssetName: nm(cu, "AssetName"), CategoryName: nm(cu, "CategoryName") });
  const ret = new Form([
    { name: "ReturnDate", label: "Return date", type: "date", readonly: true }, { name: "ConditionOnReturn", label: "Condition on return", readonly: true, wide: true },
    { name: "ReturnNotes", label: "Notes", type: "textarea", readonly: true, wide: true },
  ], cu);
  const save = async () => { if (!fields.validate()) return; await api.put(`/api/custody/${id}`, fields.get()); toast(t("Saved {0}", cu.CustodyNo), "ok"); await again(); };
  const saveG = guard(save);
  onSave(root, () => { if (open) void saveG(); });
  const rb = ribbon([
    [{ perm: "custody.manage", label: t("Save"), icon: "save", primary: true, disabled: !open, onClick: saveG },
     { perm: "custody.manage", label: t("Delete"), icon: "trash", danger: true, disabled: !open || cu.AttachmentCount > 0, onClick: guard(async () => {
         if (await confirmDialog(t("Delete custody {0}?", cu.CustodyNo), { danger: true, ok: t("Delete") })) { await api.del(`/api/custody/${id}`); toast(t("Custody deleted"), "ok"); location.hash = "#/custody"; }
       }) }],
    [{ label: t("Print handover form"), icon: "print", primary: open && !cu.AttachmentCount, onClick: () => (location.hash = `#/custody/${id}/form`) },
     { perm: "custody.manage", label: t("Attach signed form"), icon: "attach", onClick: () => void attachSigned(cu, again) },
     { label: t("Print return form"), icon: "print", disabled: open, onClick: () => (location.hash = `#/custody/${id}/form?type=return`) }],
    [{ perm: "custody.manage", label: t("Return asset"), icon: "back", disabled: !open, onClick: () => returnDialog(cu, again) }],
    [{ label: t("Back to list"), icon: "back", onClick: () => (location.hash = "#/custody") }],
  ], [t("Custody"), t("Forms"), t("Return"), t("View")]);
  const kv = (k: string, val: any) => h("div", null, h("span", { class: "k" }, t(k)), h("span", { class: "v" }, val));
  const fb = h("div", { class: "fb" }, h("h4", null, t("Summary")), h("div", { class: "kv" },
    kv("Status", custodyStatus(cu)), kv("Employee", h("a", { href: `#/employees/${cu.EmployeeID}` }, cu.EmployeeCode)), kv("Asset", h("a", { href: `#/assets/${cu.AssetID}` }, cu.AssetCode)),
    kv("Issued", fmtDate(cu.IssueDate)), kv("Returned", fmtDate(cu.ReturnDate) || "—"), kv("Signed form", cu.attachments.length ? pill("Attached", "ok") : pill("Missing", "warn"))));
  const docs = new DataGrid({ columns: [
    { key: "DocumentTitle", label: "Title", render: (r) => h("a", { href: `/api/attachments/${r.AttachmentID}/download`, target: "_blank", class: "lnk" }, r.DocumentTitle || r.FileName) },
    { key: "FileName", label: "File" }, { key: "CreatedAt", label: "Added", type: "date" }, { key: "CreatedBy", label: "User" },
    { key: "AttachmentID", label: "", render: (r) => h("button", { class: "btn sm", type: "button", onclick: guard(async () => {
        if (await confirmDialog(t("Remove this attachment?"), { danger: true, ok: t("Remove") })) { await api.del(`/api/attachments/${r.AttachmentID}`); toast(t("Attachment removed"), "ok"); await again(); } }) }, t("Remove")) },
  ], rows: cu.attachments, search: false, maxHeight: "240px", empty: "No signed documents yet." }).el;
  const tabs: Node[] = [];
  if (open && !cu.attachments.length) tabs.push(h("div", { class: "msgbar warn" }, t("Print the handover form, get it signed, then attach the signed copy here.")));
  tabs.push(fastTab(t("Employee and asset"), info.el, { open: true, summary: `${nm(cu, "EmployeeName")} · ${cu.AssetCode}` }),
    fastTab(t("Handover details"), fields.el, { open: true }));
  if (!open) tabs.push(fastTab(t("Return details"), ret.el, { open: true, summary: fmtDate(cu.ReturnDate) }));
  tabs.push(fastTab(t("Signed documents"), docs, { open: true, summary: t("{0} files", cu.attachments.length) }));
  clear(root);
  root.append(page({ title: `${cu.CustodyNo} : ${nm(cu, "EmployeeName")}`, subtitle: t("Asset custody"), pills: [custodyStatus(cu)], ribbon: rb.el, factbox: fb }, ...tabs).el);
}

// ================================================================ printable form (bilingual)
const TERMS_EN = "I confirm that I have received the asset(s) described above in the condition stated. I am responsible for their safekeeping and proper use, will not lend them to others or take them outside the company without written approval, will report any loss or damage immediately, and will return them on request or when my employment ends. I accept responsibility for loss or damage caused by negligence or misuse.";
const TERMS_AR = "أقرّ باستلامي الأصل/الأصول الموضحة أعلاه بالحالة المذكورة، وأتحمل مسؤولية المحافظة عليها واستخدامها الاستخدام الصحيح، وألتزم بعدم إعارتها للغير أو إخراجها من المنشأة دون موافقة خطية، وبالإبلاغ الفوري عن أي فقدان أو تلف، وإعادتها عند الطلب أو عند انتهاء عملي. وأتحمل مسؤولية أي فقدان أو تلف ناتج عن الإهمال أو سوء الاستخدام.";
const TERMS_RET_EN = "The asset(s) described above were returned by the employee and received by the company in the condition stated.";
const TERMS_RET_AR = "تم إرجاع الأصل/الأصول الموضحة أعلاه من الموظف واستلامها من المنشأة بالحالة المذكورة.";

export async function handoverFormPage(root: HTMLElement, a: Args): Promise<void> {
  const at = location.hash;
  const id = Number(a.args[0]);
  const kind = a.query.get("type") === "return" ? "return" : "handover";
  let cu: Rec;
  try { cu = await api.get(`/api/custody/${id}`); } catch (e) { fail(e); redirectIf(at, "#/custody"); return; }
  if (kind === "return" && cu.Status !== "Returned") { location.hash = `#/custody/${id}/form`; return; }
  const bi = (en: string, ar: string) => h("span", { class: "bi" }, h("span", null, en), h("span", { class: "ar" }, ar));
  const row = (en: string, ar: string, value: any) => h("tr", null, h("th", null, bi(en, ar)), h("td", null, value ?? ""));
  const both = (en?: string | null, ar?: string | null) => [en, ar].filter(Boolean).join(" / ");
  const ret = kind === "return";
  const sign = (en: string, ar: string, name?: string) => h("div", { class: "sig" },
    h("div", { class: "sig-title" }, bi(en, ar)), h("div", { class: "sig-line" }), h("div", { class: "sig-row" }, h("span", null, `${t("Name")}: ${name || "____________________"}`)),
    h("div", { class: "sig-row" }, h("span", null, `${t("Signature")}: ____________________`)), h("div", { class: "sig-row" }, h("span", null, `${t("Date")}: ____ / ____ / ________`)));
  const doc = h("div", { class: "handover" },
    h("div", { class: "ho-head" },
      h("div", null, h("div", { class: "ho-co" }, cu.CompanyName || t("Usool")), h("h2", null, ret ? bi("Asset Return Form", "نموذج إرجاع عهدة") : bi("Asset Handover Form", "نموذج استلام عهدة"))),
      h("div", { class: "ho-meta" }, h("div", null, bi("Form No.", "رقم النموذج"), ` ${cu.CustodyNo}`), h("div", null, bi("Date", "التاريخ"), ` ${fmtDate(ret ? cu.ReturnDate : cu.IssueDate)}`))),
    h("h3", null, bi("Employee", "الموظف")),
    h("table", { class: "ho-tbl" }, row("Name", "الاسم", both(cu.EmployeeName, cu.EmployeeNameAr)), row("Employee no.", "الرقم الوظيفي", cu.EmployeeCode),
      row("Job title", "المسمى الوظيفي", cu.JobTitle), row("Department", "الإدارة / القسم", cu.Department), row("ID number", "رقم الهوية", cu.NationalID), row("Mobile", "الجوال", cu.Mobile)),
    h("h3", null, bi("Asset", "الأصل")),
    h("table", { class: "ho-tbl" }, row("Asset no.", "رقم الأصل", cu.AssetCode), row("Description", "الوصف", both(cu.AssetName, cu.AssetNameAr)), row("Group", "المجموعة", both(cu.CategoryName, cu.CategoryNameAr)),
      row("Manufacturer / model", "الشركة المصنعة / الموديل", [cu.Manufacturer, cu.ModelNumber].filter(Boolean).join(" · ")), row("Serial number", "الرقم التسلسلي", cu.SerialNumber),
      ret ? row("Condition on return", "الحالة عند الإرجاع", cu.ConditionOnReturn) : row("Condition on issue", "الحالة عند التسليم", cu.ConditionOnIssue),
      row("Accessories / included items", "الملحقات / المرفقات", cu.Accessories), row("Notes", "ملاحظات", ret ? cu.ReturnNotes : cu.Notes)),
    h("div", { class: "ho-terms" }, h("p", null, ret ? TERMS_RET_EN : TERMS_EN), h("p", { class: "ar" }, ret ? TERMS_RET_AR : TERMS_AR)),
    h("div", { class: "ho-sigs" }, ret ? sign("Returned by (employee)", "المُسلِّم (الموظف)", cu.EmployeeName) : sign("Received by (employee)", "المستلم (الموظف)", cu.EmployeeName),
      ret ? sign("Received by (company)", "المستلم (المنشأة)") : sign("Issued by", "المُسلِّم", cu.IssuedBy), sign("Approved by (manager)", "اعتماد المدير المباشر")),
    h("div", { class: "ho-foot" }, `${t("Usool")} · ${cu.CustodyNo}`));
  const rb = ribbon([
    [{ label: t("Print"), icon: "print", primary: true, onClick: () => window.print() },
     { perm: "custody.manage", label: t("Attach signed form"), icon: "attach", onClick: () => void attachSigned(cu, async () => { location.hash = `#/custody/${id}`; }) }],
    [{ label: t("Back to custody"), icon: "back", onClick: () => (location.hash = `#/custody/${id}`) }],
  ], [t("Form"), t("View")]);
  clear(root);
  root.append(page({ title: ret ? t("Return form") : t("Handover form"), subtitle: cu.CustodyNo, ribbon: rb.el },
    h("div", { class: "paper handover-paper" }, doc)).el);
}
