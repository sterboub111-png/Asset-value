/** Fixed asset ledger entries (like the FA Ledger Entries of Business Central): every acquisition, addition, month of
 *  depreciation, revaluation, impairment, transfer and disposal, each with its document number. Selecting an entry shows
 *  its journal lines in the side pane. The server pages the list (services/ledger.py), so it stays quick on a large register. */
import { api, lookups } from "../../core/api.js";
import { t } from "../../core/i18n.js";
import { DataGrid, clear, codeLabel, combo, dialog, fail, fmtDate, fmtMoney, h, nm, page, pill, ribbon } from "../../ui/index.js";
const PAGE = 500;
const PERIODS = [["this-month", "This month"], ["last-month", "Last month"], ["this-quarter", "This quarter"],
    ["last-quarter", "Last quarter"], ["this-year", "This fiscal year"], ["last-year", "Last fiscal year"]];
/** [from, to] of a period preset, on the fiscal year of the parameters. */
function range(id, fyStartMonth) {
    const now = new Date(), y = now.getFullYear(), m = now.getMonth(), q = Math.floor(m / 3) * 3, fs = Math.min(12, Math.max(1, fyStartMonth)) - 1;
    const fy = m >= fs ? y : y - 1;
    const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    const span = (a, b) => [iso(a), iso(b)];
    const first = (yy, mm) => new Date(yy, mm, 1), last = (yy, mm) => new Date(yy, mm + 1, 0);
    switch (id) {
        case "this-month": return span(first(y, m), last(y, m));
        case "last-month": return span(first(y, m - 1), last(y, m - 1));
        case "this-quarter": return span(first(y, q), last(y, q + 2));
        case "last-quarter": return span(first(y, q - 3), last(y, q - 1));
        case "this-year": return span(first(fy, fs), last(fy + 1, fs - 1));
        case "last-year": return span(first(fy - 1, fs), last(fy, fs - 1));
        default: return ["", ""];
    }
}
const POSTS = new Set(["DEPRECIATION", "IMPAIRMENT", "REVALUATION", "DISPOSAL"]); // entries with journal lines
const KINDS = ["ACQUISITION", "ADDITION", "DEPRECIATION", "IMPAIRMENT", "REVALUATION", "DISPOSAL", "TRANSFER", "STATUS"];
/** The ledger columns, shared with the Ledger entries tab of the asset card (one asset: with the running balance). */
export function ledgerCols(oneAsset, open) {
    return [
        { key: "EntryDate", label: "Date", type: "date" },
        { key: "Document", label: "Document", render: (r) => (POSTS.has(r.EntryType)
                ? h("button", { class: "lnk-btn nw", type: "button", onclick: (e) => { e.stopPropagation(); open(r); } }, r.Document) : h("span", { class: "nw" }, r.Document)) },
        { key: "EntryType", label: "Type", render: (r) => pill(r.EntryType) },
        ...(oneAsset ? [] : [{ key: "AssetCode", label: "Asset", link: (r) => `#/assets/${r.AssetID}` }, { key: "AssetName", label: "Name" }]),
        { key: "Description", label: "Description", render: (r) => describe(r) },
        { key: "CostChange", label: "Cost", type: "money" },
        { key: "DepChange", label: "Depreciation", type: "money" },
        { key: "ValueChange", label: "Value change", type: "money" },
        { key: "NBVChange", label: "Net change", type: "money" },
        ...(oneAsset ? [{ key: "Balance", label: "Net book value", type: "money" }] : []),
        { key: "UserName", label: "User", hidden: !oneAsset },
    ];
}
/** Amounts that do not move show as blanks, so each entry reads at a glance (the export keeps the numbers). */
export function blankZeros(rows) {
    return rows.map((r) => { const o = { ...r }; for (const k of ["CostChange", "DepChange", "ValueChange", "NBVChange"])
        if (!o[k])
            o[k] = null; return o; });
}
function describe(r) {
    if (r.EntryType === "TRANSFER")
        return `${nm(r, "FromLocation") || "—"} → ${nm(r, "ToLocation") || "—"}`;
    if (r.EntryType === "DISPOSAL" && r.Proceeds)
        return `${t("Proceeds")} ${fmtMoney(r.Proceeds)}${r.Description ? ` · ${r.Description}` : ""}`;
    if (r.EntryType === "STATUS") { // "Active -> Under Repair (MT-0002)"
        const m = String(r.Description || "").match(/^(.+?) -> (.+?)(\s*\(.+\))?$/);
        return m ? `${t(m[1])} → ${t(m[2])}${m[3] || ""}` : r.Description || "";
    }
    return r.EntryType === "DEPRECIATION" ? r.Description : t(r.Description || "");
}
/** The journal lines behind one entry. */
async function journalOf(r) {
    return api.get(`/api/ledger/journal?${r.TransactionID ? `tx=${r.TransactionID}` : `dep=${r.DepreciationID}`}`);
}
function journalTable(lines) {
    const dr = lines.reduce((s, l) => s + (l.DebitAmount || 0), 0), cr = lines.reduce((s, l) => s + (l.CreditAmount || 0), 0);
    return h("table", { class: "grid je" }, h("thead", null, h("tr", null, h("th", null, t("Account")), h("th", null, t("Account name")), h("th", { class: "num" }, t("Debit")), h("th", { class: "num" }, t("Credit")))), h("tbody", null, ...lines.map((l) => h("tr", null, h("td", { class: "nw" }, l.AccountCode), h("td", null, nm(l, "AccountName")), h("td", { class: "num" }, l.DebitAmount ? fmtMoney(l.DebitAmount) : ""), h("td", { class: "num" }, l.CreditAmount ? fmtMoney(l.CreditAmount) : "")))), h("tfoot", null, h("tr", null, h("td", { colspan: 2 }, t("Total")), h("td", { class: "num" }, fmtMoney(dr)), h("td", { class: "num" }, fmtMoney(cr)))));
}
/** A dialog with an entry's journal (opened from a document number). */
export async function entryDialog(r) {
    try {
        const j = await journalOf(r);
        dialog(`${r.Document} · ${codeLabel(r.EntryType)}`, h("div", null, h("p", { class: "dlg-intro" }, `${fmtDate(r.EntryDate)} · ${r.AssetCode} · ${nm(r, "AssetName")}`), j.lines.length ? journalTable(j.lines) : h("div", { class: "msgbar" }, t("This entry posts nothing to the ledger."))), [{ label: t("Close") }], { wide: true });
    }
    catch (e) {
        fail(e);
    }
}
export async function ledgerPage(root, a) {
    const L = await lookups();
    const asset = a.query.get("asset") || "";
    const q = h("input", { class: "gt-input", type: "search", placeholder: t("Asset code or name…"), "aria-label": t("Asset"), style: "max-width:220px", value: a.query.get("q") || "" });
    const kind = combo(KINDS.map((k) => ({ value: k, label: codeLabel(k) })), { placeholder: t("All entry types"), label: t("Type"), width: 190, value: a.query.get("type") || "" });
    const branch = L.branches.length ? combo(L.branches.filter((b) => !L.scope || L.scope.includes(b.BranchID)).map((b) => ({ value: b.BranchID, label: `${b.BranchCode} — ${nm(b, "BranchName")}` })), { placeholder: t("All branches"), label: t("Branch"), width: 210 }) : null;
    const fsm = Number(L.settings.FiscalYearStartMonth || 1);
    const period = combo(PERIODS.map(([v, label]) => ({ value: v, label: t(label) })), { placeholder: t("All dates"), label: t("Period"), width: 190, value: a.query.get("period") || "" });
    const strip = h("div", { class: "lg-sum" });
    const more = h("button", { class: "btn", type: "button", hidden: true }, t("Load more"));
    const side = h("div", null, h("div", { class: "fb" }, h("h4", null, t("Entry")), h("div", { class: "kv lg-empty" }, t("Select an entry to see its journal lines."))));
    let rows = [], total = 0, offset = 0, token = 0;
    const showEntry = async (r) => {
        const my = ++token;
        clear(side);
        if (!r) {
            side.append(h("div", { class: "fb" }, h("h4", null, t("Entry")), h("div", { class: "kv lg-empty" }, t("Select an entry to see its journal lines."))));
            return;
        }
        const kv = (k, v) => h("div", null, h("span", { class: "k" }, t(k)), h("span", { class: "v" }, v));
        side.append(h("div", { class: "fb" }, h("h4", null, `${r.Document} · ${codeLabel(r.EntryType)}`), h("div", { class: "kv" }, kv("Date", fmtDate(r.EntryDate)), kv("Asset", h("a", { href: `#/assets/${r.AssetID}` }, r.AssetCode)), kv("Name", nm(r, "AssetName")), r.CostChange ? kv("Cost", fmtMoney(r.CostChange)) : null, r.DepChange ? kv("Depreciation", fmtMoney(r.DepChange)) : null, r.ValueChange ? kv("Revaluation / (impairment)", fmtMoney(r.ValueChange)) : null, h("hr"), kv("Book value change", fmtMoney(r.NBVChange)), r.UserName ? kv("User", r.UserName) : null)));
        if (!POSTS.has(r.EntryType))
            return;
        const box = h("div", { class: "fb" }, h("h4", null, t("Journal lines")), h("div", { class: "kv lg-empty" }, t("Loading…")));
        side.append(box);
        try {
            const j = await journalOf(r);
            if (my !== token)
                return;
            box.lastElementChild.replaceWith(j.lines.length ? h("div", { class: "lg-je" }, journalTable(j.lines)) : h("div", { class: "kv lg-empty" }, t("This entry posts nothing to the ledger.")));
        }
        catch (e) {
            fail(e);
        }
    };
    const grid = new DataGrid({ columns: ledgerCols(false, (r) => void entryDialog(r)), rows: [], exportName: "fa-ledger", search: false, limit: PAGE,
        tools: [q, kind, ...(branch ? [branch] : []), period], onSelect: (r) => void showEntry(r), empty: "No ledger entries match the filter." });
    const url = (off) => {
        const p = new URLSearchParams({ limit: String(PAGE), offset: String(off) });
        if (asset)
            p.set("asset", asset);
        if (q.value.trim())
            p.set("q", q.value.trim());
        if (kind.value)
            p.set("type", kind.value);
        if (branch?.value)
            p.set("branch", branch.value);
        const [from, to] = range(period.value, fsm);
        if (from)
            p.set("from", from);
        if (to)
            p.set("to", to);
        return `/api/ledger?${p}`;
    };
    const load = async (append = false) => {
        try {
            const res = await api.get(url(append ? offset : 0));
            rows = append ? [...rows, ...res.rows] : res.rows;
            total = res.total;
            offset = rows.length;
            grid.setRows(blankZeros(rows));
            const s = res.sums;
            clear(strip);
            strip.append(h("span", null, h("b", null, t("{0} entries", total))), h("span", null, t("Cost"), " ", h("b", null, fmtMoney(s.CostChange))), h("span", null, t("Depreciation"), " ", h("b", null, fmtMoney(s.DepChange))), s.ValueChange ? h("span", null, t("Revaluation / (impairment)"), " ", h("b", null, fmtMoney(s.ValueChange))) : "", h("span", null, t("Book value change"), " ", h("b", null, fmtMoney(s.NBVChange))), rows.length < total ? h("span", { class: "muted" }, t("Showing the newest {0}", rows.length)) : "");
            more.hidden = rows.length >= total;
        }
        catch (e) {
            fail(e);
        }
    };
    let timer = 0;
    q.addEventListener("input", () => { clearTimeout(timer); timer = window.setTimeout(() => void load(), 300); });
    for (const c of [kind, period, ...(branch ? [branch] : [])])
        c.addEventListener("change", () => void load());
    more.addEventListener("click", () => void load(true));
    const rb = ribbon([[{ label: t("Refresh"), icon: "refresh", onClick: () => void load() },
            { label: t("Fixed asset journal"), icon: "journal", onClick: () => (location.hash = "#/reports/depreciation-journal") }]]);
    clear(root);
    root.append(page({ title: t("Fixed asset ledger"), subtitle: t("Accounting"), ribbon: rb.el, factbox: side }, asset ? h("div", { class: "msgbar" }, t("One asset only."), " ", h("a", { href: "#/ledger" }, t("Show all assets"))) : "", strip, grid.el, h("div", { class: "lg-more" }, more)).el);
    await load();
}
