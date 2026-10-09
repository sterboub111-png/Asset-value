/** Number, date and status formatting. */
import { t } from "../core/i18n.js";
import type { Col } from "../core/types.js";
import { h } from "./dom.js";

const moneyFmt = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const fmtMoney = (v: any) => (v === null || v === undefined || v === "" ? "" : moneyFmt.format(Number(v)));
export const fmtInt = (v: any) => (v === null || v === undefined || v === "" ? "" : new Intl.NumberFormat("en-US").format(Number(v)));
/** Dates are shown day first (dd/mm/yyyy); the server always works with ISO yyyy-mm-dd. */
export const fmtDate = (v: any) => {
  const s = v ? String(v).slice(0, 10) : "";
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : s;
};
const AR_DIGITS = "٠١٢٣٤٥٦٧٨٩";
/** A typed date -> ISO; "" when empty, null when it is not a real date. Takes d/m/yyyy (also - or .), ddmmyyyy, yyyy-mm-dd and Arabic digits. */
export function parseDate(text: string): string | null {
  const s = text.trim().replace(/[٠-٩]/g, (d) => String(AR_DIGITS.indexOf(d)));
  if (!s) return "";
  let y: number, mo: number, d: number, m: RegExpMatchArray | null;
  if ((m = s.match(/^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$/))) [y, mo, d] = [+m[1], +m[2], +m[3]];
  else if ((m = s.match(/^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2}|\d{4})$/))) [d, mo, y] = [+m[1], +m[2], +m[3]];
  else if ((m = s.match(/^(\d{2})(\d{2})(\d{4})$/))) [d, mo, y] = [+m[1], +m[2], +m[3]];
  else return null;
  if (y < 100) y += 2000;
  const dt = new Date(Date.UTC(y, mo - 1, d));
  if (dt.getUTCFullYear() !== y || dt.getUTCMonth() !== mo - 1 || dt.getUTCDate() !== d) return null;
  return `${y}-${String(mo).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}
export const fmtPct = (v: any) => (v === null || v === undefined || v === "" ? "" : `${Number(v)}%`);
export const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };

const STATUS_CLASS: Record<string, string> = {
  Active: "ok", POSTED: "ok", OPEN: "ok", Posted: "ok", Draft: "info", DRAFT: "info", Issued: "warn", Locked: "err", Returned: "", Attached: "ok", Missing: "warn", Planned: "info", "In Progress": "warn", Completed: "ok", Cancelled: "", High: "err", Medium: "warn", Low: "", Overdue: "err", NEW: "info", Inactive: "", "Under Repair": "warn",
  Disposed: "err", CLOSED: "warn", ACQUISITION: "ok", DISPOSAL: "err", TRANSFER: "info", STATUS: "warn",
};
/** A status or type code as people read it: its translation, else "DEPRECIATION" -> "Depreciation" (codes are stored upper case). */
export function codeLabel(code: string): string {
  const tr = t(code);
  if (tr !== code || !/^[A-Z][A-Z_ ]+$/.test(code)) return tr;
  return code.charAt(0) + code.slice(1).toLowerCase().replace(/_/g, " ");
}
export const pill = (text: string, cls?: string) => h("span", { class: `pill ${cls ?? STATUS_CLASS[text] ?? ""}` }, codeLabel(text));

export function cellValue(col: Col | { type?: string }, v: any): string {
  switch (col.type) {
    case "money": return fmtMoney(v);
    case "int": return fmtInt(v);
    case "date": return fmtDate(v);
    case "pct": return fmtPct(v);
    case "bool": return v ? "✓" : "";
    default: return v === null || v === undefined ? "" : String(v);
  }
}
