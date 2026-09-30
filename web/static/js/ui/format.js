/** Number, date and status formatting. */
import { t } from "../core/i18n.js";
import { h } from "./dom.js";
const moneyFmt = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const fmtMoney = (v) => (v === null || v === undefined || v === "" ? "" : moneyFmt.format(Number(v)));
export const fmtInt = (v) => (v === null || v === undefined || v === "" ? "" : new Intl.NumberFormat("en-US").format(Number(v)));
export const fmtDate = (v) => (v ? String(v).slice(0, 10) : "");
export const fmtPct = (v) => (v === null || v === undefined || v === "" ? "" : `${Number(v)}%`);
export const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const STATUS_CLASS = {
    Active: "ok", POSTED: "ok", OPEN: "ok", Posted: "ok", Draft: "info", DRAFT: "info", Issued: "warn", Locked: "err", Returned: "", Attached: "ok", Missing: "warn", Planned: "info", "In Progress": "warn", Completed: "ok", Cancelled: "", High: "err", Medium: "warn", Low: "", Overdue: "err", NEW: "info", Inactive: "", "Under Repair": "warn",
    Disposed: "err", CLOSED: "warn", ACQUISITION: "ok", DISPOSAL: "err", TRANSFER: "info", STATUS: "warn",
};
export const pill = (text, cls) => h("span", { class: `pill ${cls ?? STATUS_CLASS[text] ?? ""}` }, t(text));
export function cellValue(col, v) {
    switch (col.type) {
        case "money": return fmtMoney(v);
        case "int": return fmtInt(v);
        case "date": return fmtDate(v);
        case "pct": return fmtPct(v);
        case "bool": return v ? "✓" : "";
        default: return v === null || v === undefined ? "" : String(v);
    }
}
