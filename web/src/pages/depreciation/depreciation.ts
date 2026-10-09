import { api, invalidateLookups, lookups } from "../../core/api.js";
import { t } from "../../core/i18n.js";
import type { Col, Rec } from "../../core/types.js";
import { DataGrid, combo, Form, clear, confirmDialog, dialog, fail, fmtMoney, guard, h, page, pill, ribbon, toast } from "../../ui/index.js";

type Args = { args: string[]; query: URLSearchParams };

// ================================================================ depreciation run
export async function depreciationPage(root: HTMLElement, a: Args): Promise<void> {
  const L = await lookups(true);
  const periods = L.periods as Rec[];
  if (!periods.length) {
    clear(root);
    root.append(page({ title: t("Depreciation run") }, h("div", { class: "msgbar warn" }, t("No depreciation periods exist yet."), " ", h("a", { href: "#/periods" }, t("Create periods")))).el);
    return;
  }
  // default = requested, else first open period without posted lines, else first open
  const want = a.query.get("period");
  const suggested = (await api.get<Rec>("/api/depreciation/suggest")).period_id;
  let cur = periods.find((p) => String(p.PeriodID) === want) || periods.find((p) => p.PeriodID === suggested)
    || periods.find((p) => p.PeriodStatus === "OPEN") || periods[periods.length - 1];

  const sel = combo(periods.map((p) => ({ value: p.PeriodID, label: `${p.PeriodName}${p.PeriodStatus === "CLOSED" ? ` (${t("Closed")})` : ""}` })),
    { value: cur.PeriodID, allowEmpty: false, label: t("Period"), width: 240 });
  const info = h("div", { class: "msgbar" });
  const cols: Col[] = [
    { key: "AssetCode", label: "Asset", link: (r) => `#/assets/${r.AssetID}` }, { key: "AssetName", label: "Name" }, { key: "CategoryName", label: "Group" },
    { key: "AcquisitionCost", label: "Cost", type: "money" }, { key: "OpeningAccumDep", label: "Opening accum. dep.", type: "money" },
    { key: "PeriodDepreciation", label: "Depreciation", type: "money" }, { key: "ClosingAccumDep", label: "Closing accum. dep.", type: "money" },
    { key: "ClosingNBV", label: "Net book value", type: "money" },
    { key: "status", label: "Status", render: (r) => r.eligible || r.status ? pill(r.status || "NEW") : h("span", { style: "color:var(--ink-3)" }, t(r.reason)) },
  ];
  const grid = new DataGrid({ columns: cols, rows: [], totals: ["PeriodDepreciation"], exportName: "depreciation-run", empty: "No eligible assets for this period." });

  let lines: Rec[] = [];
  let refreshSeq = 0;
  const refresh = async () => {
    const my = ++refreshSeq, pid = cur.PeriodID;
    try {
      const got = await api.get<Rec[]>(`/api/depreciation/${pid}/proposal`);
      const fresh = await api.get<Rec[]>("/api/periods");
      if (my !== refreshSeq) return;   // the user already switched to another period
      lines = got; cur = fresh.find((p) => p.PeriodID === pid)!;
    } catch (e) { if (my === refreshSeq) fail(e); return; }
    grid.setRows(lines);
    const n = (s: string) => lines.filter((l) => l.status === s).length;
    const open = cur.PeriodStatus === "OPEN";
    info.className = `msgbar ${open ? "" : "warn"}`;
    clear(info);
    const other = suggested && suggested !== cur.PeriodID && open && !lines.some((l) => l.eligible || l.status === "DRAFT");
    if (other) {
      const sp = periods.find((p) => p.PeriodID === suggested)!;
      info.className = "msgbar warn";
      info.append(t("Nothing to depreciate in this period."), " ", h("a", { href: `#/depreciation?period=${suggested}` }, t("Go to {0}", sp.PeriodName)));
    } else if (open && n("POSTED") && !n("NEW") && !n("DRAFT")) {
      // the period is done: point to the next open one
      const next = periods.find((p) => p.StartDate > cur.StartDate && p.PeriodStatus === "OPEN");
      info.className = "msgbar ok";
      info.append(t("{0} is fully posted.", cur.PeriodName), " ", next ? h("a", { href: `#/depreciation?period=${next.PeriodID}` }, t("Go to {0}", next.PeriodName)) : "");
    } else info.append(open
      ? t("{0} new · {1} draft · {2} posted. Create the proposal, review it, then post.", n("NEW"), n("DRAFT"), n("POSTED"))
      : t("This period is closed. Depreciation cannot be changed."));
    const drafts = lines.some((l) => l.status === "DRAFT");
    const canRun = open && lines.some((l) => l.eligible);
    // the buttons are missing for users without the permission; only the next step is highlighted
    if (btns.run) { btns.run.disabled = !canRun; btns.run.classList.toggle("primary", canRun && !drafts); }
    if (btns.post) { btns.post.disabled = !open || !drafts; btns.post.classList.toggle("primary", open && drafts); }
    if (btns.discard) btns.discard.disabled = !open || !drafts;
  };
  sel.onchange = () => { cur = periods.find((p) => String(p.PeriodID) === sel.value)!; history.replaceState(null, "", `#/depreciation?period=${cur.PeriodID}`); refresh(); };

  const rb = ribbon([
    [{ id: "run", perm: "depreciation.run", label: t("Create proposal"), icon: "play", primary: true, onClick: guard(async () => {
        const r = await api.post(`/api/depreciation/${cur.PeriodID}/run`, {}); toast(t("{0} line(s) proposed", r.created), "ok"); await refresh(); }) },
     { id: "post", perm: "depreciation.post", label: t("Post"), icon: "check", onClick: guard(async () => {
        const n = lines.filter((l) => l.status === "DRAFT").length;
        const tot = lines.filter((l) => l.status === "DRAFT").reduce((s, l) => s + l.PeriodDepreciation, 0);
        if (await confirmDialog(t("Post {0} depreciation line(s) for {1}, total {2}?", n, cur.PeriodName, fmtMoney(tot)), { ok: t("Post") })) {
          const r = await api.post(`/api/depreciation/${cur.PeriodID}/post`, {}); toast(t("Posted {0} line(s), total {1}", r.posted, fmtMoney(r.total)), "ok"); await refresh();
        } }) },
     { id: "discard", perm: "depreciation.run", label: t("Discard proposal"), icon: "trash", danger: true, onClick: guard(async () => {
        if (await confirmDialog(t("Discard the unposted proposal?"), { danger: true, ok: t("Discard") })) { await api.del(`/api/depreciation/${cur.PeriodID}/drafts`); await refresh(); } }) }],
    [{ label: t("Journal"), icon: "journal", onClick: () => (location.hash = `#/journal?period=${cur.PeriodID}`) },
     { label: t("Refresh"), icon: "refresh", onClick: refresh }],
  ], [t("Depreciation"), t("View")]);
  const btns = rb.btns;
  const filters = h("div", { class: "filters" }, h("div", { class: "field" }, h("label", null, t("Period")), sel));
  const pg = page({ title: t("Depreciation run"), subtitle: t("Depreciation"), ribbon: rb.el }, filters, info, grid.el);
  clear(root); root.append(pg.el);
  await refresh();
}

// ================================================================ periods
export async function periodsPage(root: HTMLElement, _a: Args): Promise<void> {
  const cols: Col[] = [
    { key: "FiscalYear", label: "Fiscal year" }, { key: "PeriodNumber", label: "No.", type: "int" }, { key: "PeriodName", label: "Period" },
    { key: "StartDate", label: "Start", type: "date" }, { key: "EndDate", label: "End", type: "date" }, { key: "PeriodStatus", label: "Status", type: "status" },
  ];
  const grid = new DataGrid({ columns: cols, rows: [], exportName: "periods", limit: 1000 });
  let periods: Rec[] = [];
  const load = async () => { try { invalidateLookups(); periods = await api.get<Rec[]>("/api/periods"); grid.setRows(periods); } catch (e) { fail(e); } };
  // Close / Reopen open a dialog to choose the period (pre-selected with the highlighted row)
  const setStatus = (status: "OPEN" | "CLOSED") => () => {
    const from = status === "CLOSED" ? "OPEN" : "CLOSED";
    const choices = periods.filter((p) => p.PeriodStatus === from);
    if (!choices.length) { toast(t(status === "CLOSED" ? "There are no open periods." : "There are no closed periods.")); return; }
    const sel = grid.selected();
    const first = choices.find((p) => sel && p.PeriodID === sel.PeriodID) || (status === "CLOSED" ? choices[0] : choices[choices.length - 1]);
    const form = new Form([{ name: "PeriodID", label: "Period", type: "select", required: true,
      options: choices.map((p) => ({ value: p.PeriodID, label: `${p.PeriodName}` })) }], { PeriodID: first.PeriodID });
    dialog(t(status === "CLOSED" ? "Close period" : "Reopen period"), form.el, [
      { label: t(status === "CLOSED" ? "Close period" : "Reopen period"), primary: true, onClick: async () => {
          if (!form.validate()) return false;
          const p = choices.find((x) => String(x.PeriodID) === form.value("PeriodID"))!;
          await api.post(`/api/periods/${p.PeriodID}/status`, { status });
          toast(t("{0}: {1}", p.PeriodName, t(status === "OPEN" ? "reopened" : "closed")), "ok"); await load();
      } },
      { label: t("Cancel") },
    ]);
  };
  const rb = ribbon([
    [{ perm: "periods.manage", label: t("Generate fiscal year"), icon: "plus", primary: true, onClick: () => {
        const f = new Form([{ name: "fiscal_year", label: "Fiscal year", type: "number", step: "1", required: true }], { fiscal_year: new Date().getFullYear() });
        dialog(t("Generate periods"), f.el, [{ label: t("Generate"), primary: true, onClick: async () => { if (!f.validate()) return false; await api.post("/api/periods/generate", f.get()); toast(t("Periods generated"), "ok"); await load(); } }, { label: t("Cancel") }]);
      } }],
    [{ perm: "periods.manage", label: t("Close period"), icon: "lock", onClick: setStatus("CLOSED") }, { perm: "periods.manage", label: t("Reopen period"), icon: "unlock", onClick: setStatus("OPEN") }],
    [{ label: t("Refresh"), icon: "refresh", onClick: load }],
  ]);
  const pg = page({ title: t("Depreciation periods"), subtitle: t("Depreciation"), ribbon: rb.el },
    h("div", { class: "msgbar" }, t("Closing a period blocks any posting into it. Periods are created from the fiscal-year start month in the parameters.")), grid.el);
  clear(root); root.append(pg.el); await load();
}

// ================================================================ inquiries
export async function journalPage(root: HTMLElement, a: Args): Promise<void> {
  const L = await lookups(true);
  const per = combo(L.periods.map((p) => ({ value: p.PeriodID, label: p.PeriodName })), { value: a.query.get("period") ?? "", placeholder: t("All periods"), label: t("Period"), width: 210 });
  const typ = combo([{ value: "DEPRECIATION", label: t("Depreciation") }, { value: "DISPOSAL", label: t("Disposal") }], { placeholder: t("All types"), label: t("Type"), width: 170 });
  const grid = new DataGrid({ rows: [], tools: [per, typ], exportName: "fixed-asset-journal", totals: ["DebitAmount", "CreditAmount"], columns: [
    { key: "JournalDate", label: "Date", type: "date" }, { key: "JournalType", label: "Type", render: (r) => t(r.JournalType) }, { key: "PeriodName", label: "Period" },
    { key: "Reference", label: "Asset", link: (r) => (r.AssetID ? `#/assets/${r.AssetID}` : null) }, { key: "AccountCode", label: "Account" }, { key: "AccountName", label: "Account name" },
    { key: "DebitAmount", label: "Debit", type: "money" }, { key: "CreditAmount", label: "Credit", type: "money" }, { key: "Description", label: "Description" },
  ] });
  const load = async () => { try { grid.setRows(await api.get(`/api/journal?period=${per.value}&type=${typ.value}`)); } catch (e) { fail(e); } };
  per.onchange = typ.onchange = load;
  const rb = ribbon([[{ label: t("Refresh"), icon: "refresh", onClick: load }]]);
  clear(root); root.append(page({ title: t("Fixed asset journal"), subtitle: t("Accounting"), ribbon: rb.el }, grid.el).el); await load();
}

export async function transactionsPage(root: HTMLElement, _a: Args): Promise<void> {
  const grid = new DataGrid({ rows: [], exportName: "asset-transactions", columns: [
    { key: "TransactionDate", label: "Date", type: "date" }, { key: "TransactionType", label: "Type", type: "status" },
    { key: "AssetCode", label: "Asset", link: (r) => `#/assets/${r.AssetID}` }, { key: "AssetName", label: "Name" },
    { key: "Amount", label: "Amount", type: "money" }, { key: "DisposalProceeds", label: "Proceeds", type: "money" },
    { key: "ReferenceNumber", label: "Reference" }, { key: "Notes", label: "Notes" }, { key: "CreatedBy", label: "User" },
  ] });
  const load = async () => { try { grid.setRows(await api.get("/api/transactions")); } catch (e) { fail(e); } };
  clear(root); root.append(page({ title: t("Fixed asset transactions"), subtitle: t("Accounting"), ribbon: ribbon([[{ label: t("Refresh"), icon: "refresh", onClick: load }]]).el }, grid.el).el);
  await load();
}

export async function auditPage(root: HTMLElement, _a: Args): Promise<void> {
  const grid = new DataGrid({ rows: [], exportName: "audit-log", columns: [
    { key: "LogDate", label: "Date / time" }, { key: "UserName", label: "User" }, { key: "Action", label: "Action", render: (r) => t(r.Action) },
    { key: "Entity", label: "Entity" }, { key: "EntityID", label: "Record" }, { key: "Details", label: "Details" },
  ] });
  const load = async () => { try { grid.setRows(await api.get("/api/audit")); } catch (e) { fail(e); } };
  clear(root); root.append(page({ title: t("Audit log"), subtitle: t("Accounting"), ribbon: ribbon([[{ label: t("Refresh"), icon: "refresh", onClick: load }]]).el }, grid.el).el);
  await load();
}

// ================================================================ data checks
/** The integrity checks of the books (services/integrity.py): each relation, whether it holds, and where it does not. */
export async function integrityPage(root: HTMLElement, _a: Args): Promise<void> {
  const body = h("div", { class: "ic-list" }, h("div", { class: "loading" }, t("Loading…")));
  const load = async () => {
    try {
      const checks = await api.get<Rec[]>("/api/integrity");
      clear(body);
      const failed = checks.filter((c) => !c.ok).length;
      body.append(h("div", { class: `msgbar ${failed ? "err" : "ok"}` }, failed ? t("{0} data check(s) failed", failed) : t("All data checks pass: the books are consistent.")));
      for (const c of checks) {
        body.append(h("section", { class: `ic-check ${c.ok ? "ok" : "bad"}` },
          h("div", { class: "ic-head" }, h("b", null, t(c.title)), pill(c.ok ? t("Passed") : t("{0} issue(s)", c.issues.length), c.ok ? "ok" : "err")),
          c.ok ? null : h("ul", null, ...c.issues.slice(0, 50).map((i: Rec) => h("li", null, i.asset ? h("a", { href: `#/assets/${i.asset}` }, i.text) : i.text)))));
      }
    } catch (e) { fail(e); }
  };
  const rb = ribbon([[{ label: t("Run checks"), icon: "refresh", primary: true, onClick: load }]]);
  clear(root);
  root.append(page({ title: t("Data checks"), subtitle: t("Accounting"), ribbon: rb.el },
    h("p", { class: "ic-intro" }, t("These checks recalculate the books from the tables: depreciation lines, journals, disposals, VAT, periods and reports must all agree.")), body).el);
  await load();
}
