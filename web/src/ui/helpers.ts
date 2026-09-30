/** Small helpers shared by the pages (names, guards, save hook, CSV). */
import { getLang, t } from "../core/i18n.js";
import type { Col, Rec } from "../core/types.js";
import { fail } from "./dialogs.js";
import { cellValue } from "./format.js";

/** Display name of a record: the Arabic column (<key>Ar) in Arabic mode when filled, else the English one. */
export const nm = (r: Rec | undefined | null, key: string): string => (r ? (getLang() === "ar" && r[key + "Ar"] ? r[key + "Ar"] : r[key] ?? "") : "");
export const opts = (rows: Rec[], value: string, label: (r: Rec) => string) => rows.map((r) => ({ value: r[value], label: label(r) }));
export const guard = (fn: () => Promise<any>) => {
  let busy = false;
  return async () => {
    if (busy) return;
    busy = true;
    try { await fn(); } catch (e) { fail(e); } finally { busy = false; }
  };
};

// ---- Save shortcut: the page on screen registers its save action; the keyboard handler (shell/keyboard.ts) calls it
let saveSlot: { root: HTMLElement; fn: () => void } | null = null;
/** Register the save action of the current page; it only fires while `root` is still in the document. */
export function onSave(root: HTMLElement, fn: () => void): void { saveSlot = { root, fn }; }
/** Run the current page's save action. False when the page has none. */
export function runSave(): boolean {
  if (!saveSlot || !saveSlot.root.isConnected) return false;
  saveSlot.fn();
  return true;
}

/** Redirect only if the user is still on the page that asked for it (a slow page must not pull the user back). */
export const redirectIf = (at: string, to: string): void => { if (location.hash === at) location.hash = to; };

/** A cell that Excel cannot mistake for a formula. */
export const csvText = (s: string): string => `"${(/^[=+\-@\t\r]/.test(s) ? "'" + s : s).replace(/"/g, '""')}"`;
/** What a cell shows, as plain text (used by search and export). */
export function displayText(c: Col, r: Rec): string {
  if (c.render) { const n = c.render(r); return n instanceof Node ? (n.textContent || "") : String(n ?? ""); }
  if (c.type === "status") return r[c.key] ? t(String(r[c.key])) : "";
  return cellValue(c, r[c.key]);
}
