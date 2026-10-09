/** Toasts and modal dialogs. */
import { t } from "../core/i18n.js";
import { h } from "./dom.js";
import { icon } from "./icons.js";

export function toast(message: string, kind: "ok" | "err" | "" = ""): void {
  let box = document.querySelector(".toasts") as HTMLElement | null;
  if (!box) { box = h("div", { class: "toasts" }); document.body.appendChild(box); }
  if (kind === "ok") box.querySelectorAll(".toast.err").forEach((n) => n.remove());   // a success makes earlier errors stale
  const el = h("div", { class: `toast ${kind}`, role: kind === "err" ? "alert" : "status" }, message);
  box.appendChild(el);
  setTimeout(() => el.remove(), kind === "err" ? 7000 : 3500);
}
export const fail = (e: unknown) => toast(e instanceof Error ? t(e.message) : String(e), "err");

const dialogStack: { close: () => void }[] = [];
/** Close every open dialog (used when the page changes). */
export function closeAllDialogs(): void { [...dialogStack].reverse().forEach((d) => d.close()); }

export interface DlgButton { label: string; primary?: boolean; danger?: boolean; onClick?: () => Promise<boolean | void> | boolean | void; }
export function dialog(title: string, content: Node, buttons: DlgButton[], opts: { wide?: boolean; onClose?: () => void; dismissable?: boolean } = {}) {
  const err = h("div", { class: "msgbar err", style: "display:none" });
  const box = h("div", { class: `dlg ${opts.wide ? "wide" : ""}`, role: "dialog", "aria-modal": "true", "aria-label": title });
  const overlay = h("div", { class: "overlay" }, box);
  const previousFocus = document.activeElement as HTMLElement | null;
  const entry = { close: () => close() };
  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    overlay.remove(); document.removeEventListener("keydown", onKey);
    const at = dialogStack.indexOf(entry); if (at >= 0) dialogStack.splice(at, 1);
    if (previousFocus && previousFocus.isConnected) previousFocus.focus();
    opts.onClose?.();
  };
  const dismissable = opts.dismissable !== false;
  const onKey = (e: KeyboardEvent) => {
    if (dialogStack[dialogStack.length - 1] !== entry) return;   // only the top dialog reacts
    if (e.key === "Escape" && dismissable) close();
    else if (e.key === "Tab") {   // keep the focus inside the dialog
      const items = [...box.querySelectorAll<HTMLElement>("button:not(:disabled), input:not([type=hidden]):not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href]")].filter((n) => n.offsetParent !== null);
      if (!items.length) return;
      const first = items[0], last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    } else if (e.key === "Enter" && (e.target as HTMLElement).tagName === "INPUT" && (e.target as HTMLInputElement).type !== "file" && box.contains(e.target as Node)) { e.preventDefault(); (foot.querySelector(".btn.primary, .btn.danger") as HTMLButtonElement | null)?.click(); }
  };
  const foot = h("footer", null);
  for (const b of buttons) {
    const btn = h("button", { class: `btn ${b.primary ? "primary" : ""} ${b.danger ? "danger" : ""}`, type: "button" }, b.label);
    btn.addEventListener("click", async () => {
      err.style.display = "none";
      if (!b.onClick) return close();
      btn.disabled = true;
      try {
        if ((await b.onClick()) !== false) close();
      } catch (e) {
        err.textContent = e instanceof Error ? t(e.message) : String(e);
        err.style.display = "block";
      } finally { btn.disabled = false; }
    });
    foot.appendChild(btn);
  }
  box.append(h("header", null, h("span", null, title), dismissable ? h("button", { class: "tb-btn", style: "color:var(--ink);height:32px", "aria-label": t("Close"), onclick: close }, icon("x")) : null),
    h("div", { class: "dbody" }, err, content), foot);
  overlay.addEventListener("mousedown", (e) => { if (e.target === overlay && dismissable) close(); });
  dialogStack.push(entry);
  document.addEventListener("keydown", onKey);
  document.body.appendChild(overlay);
  (box.querySelector("input:not([readonly]):not([type=hidden]), select, textarea") as HTMLElement | null)?.focus();
  return { close, el: box };
}
export function confirmDialog(message: string, opts: { danger?: boolean; ok?: string; title?: string } = {}): Promise<boolean> {
  return new Promise((resolve) => {
    let done = false;
    const finish = (v: boolean) => { if (!done) { done = true; resolve(v); } };
    // finish(true) runs before the dialog closes; any other way of closing (Cancel, X, Esc, click outside) answers "no"
    dialog(opts.title || t("Confirm"), h("p", { style: "margin:0" }, message), [
      { label: opts.ok || t("Yes"), primary: !opts.danger, danger: opts.danger, onClick: () => { finish(true); } },
      { label: t("Cancel") },
    ], { onClose: () => finish(false) });
  });
}
