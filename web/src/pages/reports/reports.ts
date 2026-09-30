import { api, lookups } from "../../core/api.js";
import { t } from "../../core/i18n.js";
import { getMe, userTitle } from "../../core/session.js";
import type { Rec, ReportResult } from "../../core/types.js";
import { FieldDef, Form, nm, cellValue, csvText, clear, dialog, downloadCsv, fail, h, opts, page, ribbon, today } from "../../ui/index.js";

type Args = { args: string[]; query: URLSearchParams };

export const REPORT_INFO: Record<string, { title: string; desc: string }> = {
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

export const groupSlug = (g: string) => g.toLowerCase().replace(/\s+/g, "-");

/** "Reports" without a group: go to the first group (there is no all-reports hub). */
export async function reportsIndexPage(_root: HTMLElement, _a: Args): Promise<void> {
  const list: Rec[] = await api.get("/api/reports");
  location.hash = list.length ? `#/reports/g/${groupSlug(list[0].group)}` : "#/";
}

/** A report group (Depreciation, Maintenance ...): its reports sit in the action pane and are listed below. */
export async function reportsGroupPage(root: HTMLElement, a: Args): Promise<void> {
  const list: Rec[] = await api.get("/api/reports");
  const group = list.map((r) => r.group).find((g, i, all) => all.indexOf(g) === i && groupSlug(g) === a.args[0]);
  if (!group) { location.hash = "#/reports"; return; }
  const items = list.filter((r) => r.group === group);
  const rb = ribbon([items.map((r) => ({ label: t(REPORT_INFO[r.id]?.title || r.id), icon: "report", onClick: () => (location.hash = `#/reports/${r.id}`) }))]);
  const body = h("div", { class: "hub" }, ...items.map((r) => h("a", { href: `#/reports/${r.id}` },
    h("b", null, t(REPORT_INFO[r.id]?.title || r.id)), h("span", null, t(REPORT_INFO[r.id]?.desc || "")))));
  clear(root); root.append(page({ title: t(group), subtitle: t("Reports"), ribbon: rb.el }, body).el);
}

async function paramDefs(ids: string[]): Promise<FieldDef[]> {
  const L = await lookups();
  const map: Record<string, FieldDef> = {
    as_of: { name: "as_of", label: "As of date", type: "date" },
    from: { name: "from", label: "From date", type: "date" }, to: { name: "to", label: "To date", type: "date" },
    account: { name: "account", label: "Account name", type: "select", options: L.glaccounts.map((g: Rec) => ({ value: g.GLAccountID, label: `${g.AccountCode} — ${nm(g, "AccountName")}` })) },
    category: { name: "category", label: "Fixed asset group", type: "select", options: opts(L.categories, "CategoryID", (c) => nm(c, "CategoryName")) },
    location: { name: "location", label: "Location", type: "select", options: opts(L.locations, "LocationID", (c) => nm(c, "LocationName")) },
    costcenter: { name: "costcenter", label: "Cost center", type: "select", options: opts(L.costcenters, "CostCenterID", (c) => nm(c, "CostCenterName")) },
    status: { name: "status", label: "Status", type: "select", options: [...L.statuses, "Disposed"].map((s) => ({ value: s, label: t(s) })) },
    group_by: { name: "group_by", label: "Group by", type: "select", required: true, options: [
      { value: "category", label: t("Fixed asset group") }, { value: "location", label: t("Location") }, { value: "costcenter", label: t("Cost center") }] },
    fiscal_year: { name: "fiscal_year", label: "Fiscal year", type: "number", step: "1", required: true },
    type: { name: "type", label: "Transaction type", type: "select", options: ["ACQUISITION", "TRANSFER", "STATUS", "DISPOSAL"].map((s) => ({ value: s, label: t(s) })) },
    vat: { name: "vat", label: "VAT status", type: "select", options: [{ value: "1", label: t("With VAT") }, { value: "0", label: t("No VAT") }] },
    employee: { name: "employee", label: "Employee", type: "select", options: L.employees.map((e: Rec) => ({ value: e.EmployeeID, label: `${e.EmployeeCode} — ${nm(e, "EmployeeName")}` })) },
    cstatus: { name: "cstatus", label: "Custody status", type: "select", options: [{ value: "Issued", label: t("Issued") }, { value: "Returned", label: t("Returned") }] },
    sactive: { name: "sactive", label: "Status", type: "select", options: [{ value: "1", label: t("Active") }, { value: "0", label: t("Inactive") }] },
    stype: { name: "stype", label: "Supplier type", type: "select", options: L.supplier_types.map((s: string) => ({ value: s, label: t(s) })) },
    supplier: { name: "supplier", label: "Supplier", type: "select", options: L.suppliers.map((s: Rec) => ({ value: s.SupplierID, label: `${s.SupplierCode} — ${nm(s, "SupplierName")}` })) },
    mstatus: { name: "mstatus", label: "Order status", type: "select", options: L.maint_statuses.map((s: string) => ({ value: s, label: t(s) })) },
    mtype: { name: "mtype", label: "Maintenance type", type: "select", options: L.maint_types.map((s: string) => ({ value: s, label: t(s) })) },
    mgroup: { name: "mgroup", label: "Group by", type: "select", required: true, options: [
      { value: "asset", label: t("Asset") }, { value: "category", label: t("Fixed asset group") }, { value: "type", label: t("Type") }] },
    days: { name: "days", label: "Days ahead", type: "number", step: "1" },
  };
  return ids.map((i) => map[i]);
}

export async function reportPage(root: HTMLElement, a: Args): Promise<void> {
  const id = a.args[0];
  const list: Rec[] = await api.get("/api/reports");
  const meta = list.find((r) => r.id === id);
  if (!meta) { location.hash = "#/reports"; return; }
  const title = t(REPORT_INFO[id]?.title || id);
  const defs = await paramDefs(meta.params);
  const L = await lookups();
  const defaults: Record<string, string> = { as_of: today(), from: yearStart(), to: today(), fiscal_year: String(new Date().getFullYear()), group_by: "category", mgroup: "asset", days: "30" };
  const params: Record<string, string> = {};
  for (const d of defs) params[d.name] = a.query.get(d.name) ?? (a.query.has("run") ? "" : defaults[d.name] ?? "");
  const hasRun = a.query.has("run");

  const run = (p: Record<string, string>) => {
    const qs = new URLSearchParams({ run: "1", ...Object.fromEntries(Object.entries(p).filter(([, v]) => v !== "")) });
    location.hash = `#/reports/${id}?${qs}`;
  };
  const askParams = () => {
    const form = new Form(defs, params);
    dialog(title, h("div", null, h("div", { class: "msgbar" }, t(REPORT_INFO[id]?.desc || "")), form.el), [
      { label: t("OK"), primary: true, onClick: () => { if (!form.validate()) return false; run(form.get() as Record<string, string>); } },
      { label: t("Cancel"), onClick: () => { if (!hasRun) location.hash = `#/reports/g/${groupSlug(meta.group)}`; } },
    ]);
  };

  let res: ReportResult | null = null;
  const paper = h("div", { class: "paper" }, h("div", { class: "loading" }, t("Loading…")));
  const rb = ribbon([
    [{ label: t("Parameters"), icon: "filter", primary: true, onClick: askParams },
     { label: t("Print"), icon: "print", onClick: () => window.print() },
     { label: t("Export to Excel"), icon: "download", onClick: () => res && exportCsv(res, title) }],
    list.filter((r) => r.group === meta.group).map((r) => ({ label: t(REPORT_INFO[r.id]?.title || r.id), icon: "report", active: r.id === id, onClick: () => (location.hash = `#/reports/${r.id}`) })),
  ]);
  clear(root); root.append(page({ title, subtitle: t("Reports"), ribbon: rb.el }, paper).el);
  if (!hasRun) { paper.innerHTML = ""; paper.append(h("div", { class: "empty" }, t("Set the report parameters to run it."))); askParams(); return; }
  try {
    const q = new URLSearchParams(Object.fromEntries(Object.entries(params).filter(([, v]) => v !== "")));
    res = await api.get<ReportResult>(`/api/reports/${id}?${q}`);
  } catch (e) { fail(e); paper.innerHTML = ""; paper.append(h("div", { class: "msgbar err" }, e instanceof Error ? t(e.message) : String(e))); return; }
  const lines = defs.filter((d) => params[d.name]).map((d) => {
    const opt = d.options?.find((o) => String(o.value) === params[d.name]);
    return { label: t(d.label), value: opt ? opt.label : params[d.name] };
  });
  clear(paper); paper.append(renderReport(res, title, lines, userTitle(getMe()) || L.user));
}

/** Report sub-titles arrive as short English phrases with dates and numbers inside; translate the words around them. */
function subtitleText(sub: string): string {
  let m: RegExpMatchArray | null;
  const word = (w: string) => (w === "Beginning" || w === "today" ? t(w) : w);
  if ((m = sub.match(/^As of (.+)$/))) return `${t("As of")} ${m[1]}`;
  if ((m = sub.match(/^Fixed asset postings as of (.+)$/))) return `${t("Fixed asset postings as of")} ${m[1]}`;
  if ((m = sub.match(/^(\S+) to (\S+)$/))) return `${word(m[1])} ${t("to")} ${word(m[2])}`;
  if ((m = sub.match(/^Fiscal year (\d+)$/))) return `${t("Fiscal year")} ${m[1]}`;
  if ((m = sub.match(/^Due within (\d+) days$/))) return t("Due within {0} days", m[1]);
  if ((m = sub.match(/^Expiring within (\d+) days$/))) return t("Expiring within {0} days", m[1]);
  if ((m = sub.match(/^(\d+) suppliers$/))) return t("{0} suppliers", m[1]);
  if ((m = sub.match(/^(\d+) employees$/))) return t("{0} employees", m[1]);
  return t(sub);
}
const ENUM_COLS = new Set(["SupplierType", "VatStatus", "Basis", "Status", "MaintenanceType", "Priority", "Timing", "Source", "TransactionType", "PostingStatus", "JournalType"]);
const isNum = (type: string) => type === "money" || type === "int" || type === "pct";

function renderReport(r: ReportResult, title: string, paramLines: { label: string; value: string }[], user: string): HTMLElement {
  const cols = r.columns;
  const totalKeys = r.totals || [];
  const sum = (rows: Rec[], key: string) => rows.reduce((s, x) => s + Number(x[key] || 0), 0);
  const tr = (cls: string, cells: any[]) => h("tr", { class: cls }, ...cells);
  const tbody = h("tbody");
  const ENUM = new Set(["SupplierType", "VatStatus", "Basis", "Status", "MaintenanceType", "Priority", "Timing", "Source", "TransactionType", "PostingStatus", "JournalType"]);
  const cell = (c: { key: string; type: string }, row: Rec) => h("td", { class: isNum(c.type) ? "num" : "" }, ENUM.has(c.key) ? t(String(row[c.key] ?? "")) : cellValue(c, row[c.key]));
  const totalsRow = (cls: string, label: string, rows: Rec[], keys: string[]) =>
    tr(cls, cols.map((c, i) => h("td", { class: isNum(c.type) ? "num" : "" }, keys.includes(c.key) ? cellValue(c, sum(rows, c.key)) : i === 0 ? label : "")));

  if (!r.rows.length) tbody.append(tr("", [h("td", { colspan: cols.length, class: "empty" }, t("No data for these parameters."))]));
  if (r.group_by) {
    const gk = r.group_by; const order: string[] = []; const map = new Map<string, Rec[]>();
    for (const row of r.rows) { const k = String(row[gk] ?? "—"); if (!map.has(k)) { map.set(k, []); order.push(k); } map.get(k)!.push(row); }
    for (const k of order) {
      const rows = map.get(k)!;
      tbody.append(tr("grp", [h("td", { colspan: cols.length }, `${cols.find((c) => c.key === gk)?.label ? t(cols.find((c) => c.key === gk)!.label) : ""}: ${k}`)]));
      rows.forEach((row) => tbody.append(tr("", cols.map((c) => cell(c, row)))));
      const subKeys = r.subtotal_only || totalKeys;
      if (subKeys.length) tbody.append(totalsRow("sub", `${t("Subtotal")} ${k}`, rows, subKeys));
    }
  } else r.rows.forEach((row) => tbody.append(tr("", cols.map((c) => cell(c, row)))));
  if (totalKeys.length && r.rows.length) tbody.append(totalsRow("tot", t("Total"), r.rows, totalKeys));

  const thead = h("thead", null, tr("", cols.map((c) => h("th", { class: isNum(c.type) ? "num" : "" }, t(c.label)))));
  const when = new Date();
  const stamp = `${r.generated} ${String(when.getHours()).padStart(2, "0")}:${String(when.getMinutes()).padStart(2, "0")}`;
  const period = r.subtitle ? subtitleText(r.subtitle) : "";
  return h("div", { class: "rpt-doc" },
    h("div", { class: "rh" },
      h("div", { class: "rh-l" }, h("div", { class: "co" }, r.company || t("Usool")), h("h2", null, title),
        period && !paramLines.length ? h("div", { class: "period" }, period) : null,
        paramLines.length ? h("div", { class: "params" }, ...paramLines.map((p) => h("span", null, h("b", null, `${p.label}: `), p.value))) : null),
      h("div", { class: "meta" }, h("div", null, h("span", null, `${t("Printed")}: `), stamp), h("div", null, h("span", null, `${t("Printed by")}: `), user),
        h("div", null, h("span", null, `${t("Currency")}: `), r.currency))),
    h("div", { style: "overflow:auto" }, h("table", { class: "rpt" }, thead, tbody)),
    h("div", { class: "rpt-foot" }, h("span", null, `${t("Usool")} · ${t("{0} records", r.rows.length)}`), h("span", null, title)));
}

function exportCsv(r: ReportResult, title: string) {
  const lines = [r.columns.map((c) => csvText(t(c.label))).join(",")];
  for (const row of r.rows) lines.push(r.columns.map((c) => (isNum(c.type) ? String(row[c.key] ?? "") : csvText(ENUM_COLS.has(c.key) ? t(String(row[c.key] ?? "")) : cellValue(c, row[c.key])))).join(","));
  downloadCsv(title.replace(/[^\w؀-ۿ-]+/g, "-"), lines.join("\r\n"));
}
