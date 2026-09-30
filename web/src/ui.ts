import { ApiError } from "./api.js";
import { getLang, t } from "./i18n.js";
import type { Col, Rec } from "./types.js";

// ---------------------------------------------------------------- DOM helper
type Attrs = Record<string, any> | null;
export function h<K extends keyof HTMLElementTagNameMap>(tag: K, attrs?: Attrs, ...kids: any[]): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "value") (el as any).value = v;
    else if (v === true) el.setAttribute(k, "");
    else el.setAttribute(k, String(v));
  }
  append(el, kids);
  return el;
}
export function append(el: Node, kids: any[]): void {
  for (const k of kids.flat(Infinity)) {
    if (k === null || k === undefined || k === false) continue;
    el.appendChild(k instanceof Node ? k : document.createTextNode(String(k)));
  }
}
export const clear = (el: Element) => { while (el.firstChild) el.removeChild(el.firstChild); };

// ---------------------------------------------------------------- icons
const ICONS: Record<string, string> = {
  menu: '<path d="M2 4h12M2 8h12M2 12h12"/>', search: '<circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5 14 14"/>',
  home: '<path d="M2 8 8 2.5 14 8M3.5 7v6.5h9V7"/>', asset: '<rect x="2.5" y="4" width="11" height="9" rx="1"/><path d="M5.5 4V2.5h5V4M2.5 8h11"/>',
  calc: '<rect x="3" y="1.8" width="10" height="12.4" rx="1"/><path d="M5.5 5h5M5.5 8h1M9.5 8h1M5.5 11h1M9.5 11h1"/>',
  calendar: '<rect x="2" y="3" width="12" height="11" rx="1"/><path d="M2 6.5h12M5 1.8v2.5M11 1.8v2.5"/>',
  journal: '<path d="M3.5 2h8.5a1 1 0 0 1 1 1v11H4.5a1 1 0 0 1-1-1zM3.5 13a1 1 0 0 1 1-1H13M6 5.5h4.5M6 8h4.5"/>',
  list: '<path d="M5.5 4h8M5.5 8h8M5.5 12h8M2.5 4h.5M2.5 8h.5M2.5 12h.5"/>', report: '<path d="M3 2h7l3 3v9H3zM10 2v3h3M5.5 8h5M5.5 10.5h5"/>',
  setup: '<circle cx="8" cy="8" r="2.2"/><path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M3.4 12.6l1.4-1.4M11.2 4.8l1.4-1.4"/>',
  plus: '<path d="M8 3v10M3 8h10"/>', save: '<path d="M3 2.5h8l2.5 2.5v8.5h-10.5zM5.5 2.5v3.5h4.5V2.5M5.5 13.5V9.5h5v4"/>',
  trash: '<path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.5 9h6l.5-9"/>', edit: '<path d="M2.5 13.5l.6-3L11 2.6l2.4 2.4-7.9 7.9zM9.8 3.8l2.4 2.4"/>',
  refresh: '<path d="M13 8a5 5 0 1 1-1.6-3.7M13 2.5v3h-3"/>', transfer: '<path d="M2 5.5h11M10.5 3l2.5 2.5-2.5 2.5M14 10.5H3M5.5 8 3 10.5 5.5 13"/>',
  dispose: '<path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.5 9h6l.5-9M6.5 7.5l3 3M9.5 7.5l-3 3"/>', check: '<path d="M3 8.5 6.5 12 13 4.5"/>',
  x: '<path d="M3.5 3.5l9 9M12.5 3.5l-9 9"/>', chevron: '<path d="M6 3.5 10.5 8 6 12.5"/>', download: '<path d="M8 2v8M4.5 7 8 10.5 11.5 7M2.5 13.5h11"/>',
  print: '<path d="M4.5 6V2h7v4M4.5 11.5h-2v-5h11v5h-2M4.5 9.5h7v4h-7z"/>', attach: '<path d="M11.5 6.5 7 11a2 2 0 0 1-2.8-2.8l5-5a3 3 0 0 1 4.3 4.2l-5.2 5.2"/>',
  moon: '<path d="M13 9.5A5.5 5.5 0 0 1 6.5 3a5.5 5.5 0 1 0 6.5 6.5z"/>', sun: '<circle cx="8" cy="8" r="3"/><path d="M8 1.5v1.8M8 12.7v1.8M1.5 8h1.8M12.7 8h1.8M3.4 3.4l1.3 1.3M11.3 11.3l1.3 1.3M3.4 12.6l1.3-1.3M11.3 4.7l1.3-1.3"/>',
  wrench: '<path d="M10.5 2.5a3.3 3.3 0 0 0-3.1 4.4L2.5 11.8a1.4 1.4 0 0 0 2 2l4.9-4.9a3.3 3.3 0 0 0 4.4-3.1l-2 1.6-1.8-.4-.4-1.8z"/>',
  truck: '<path d="M1.5 4h8v7h-8zM9.5 6.5h3l2 2V11h-5zM4.5 13a1.3 1.3 0 1 0 0-.01zM11.5 13a1.3 1.3 0 1 0 0-.01z"/>',
  db: '<ellipse cx="8" cy="4" rx="5" ry="2"/><path d="M3 4v8c0 1.1 2.2 2 5 2s5-.9 5-2V4M3 8c0 1.1 2.2 2 5 2s5-.9 5-2"/>',
  globe: '<circle cx="8" cy="8" r="6"/><path d="M2 8h12M8 2c2 2 2 10 0 12M8 2c-2 2-2 10 0 12"/>', back: '<path d="M9.5 3 4.5 8l5 5M4.5 8h9"/>',
  lock: '<rect x="3.5" y="7" width="9" height="6.5" rx="1"/><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2"/>', unlock: '<rect x="3.5" y="7" width="9" height="6.5" rx="1"/><path d="M5.5 7V5a2.5 2.5 0 0 1 4.8-1"/>',
  play: '<path d="M4.5 2.5v11l9-5.5z"/>', filter: '<path d="M2 3h12l-4.5 5.5V13l-3-1.5V8.5z"/>', audit: '<circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5 14 14M5 7l1.5 1.5L9 5.5"/>',
  warn: '<path d="M8 2 14.5 13.5h-13zM8 6.5v3.2M8 11.6v.4"/>', copy: '<rect x="5.5" y="5.5" width="8" height="8" rx="1"/><path d="M10.5 5.5v-2a1 1 0 0 0-1-1h-6a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2"/>',
};
export function icon(name: string): HTMLElement {
  const s = document.createElement("span");
  s.style.display = "inline-flex";
  s.innerHTML = `<svg class="ic" viewBox="0 0 16 16" aria-hidden="true">${ICONS[name] || ""}</svg>`;
  return s;
}

// ---------------------------------------------------------------- formatting
const moneyFmt = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const fmtMoney = (v: any) => (v === null || v === undefined || v === "" ? "" : moneyFmt.format(Number(v)));
export const fmtInt = (v: any) => (v === null || v === undefined || v === "" ? "" : new Intl.NumberFormat("en-US").format(Number(v)));
export const fmtDate = (v: any) => (v ? String(v).slice(0, 10) : "");
export const fmtPct = (v: any) => (v === null || v === undefined || v === "" ? "" : `${Number(v)}%`);
export const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };

const STATUS_CLASS: Record<string, string> = {
  Active: "ok", POSTED: "ok", OPEN: "ok", Posted: "ok", Draft: "info", DRAFT: "info", Planned: "info", "In Progress": "warn", Completed: "ok", Cancelled: "", High: "err", Medium: "warn", Low: "", Overdue: "err", NEW: "info", Inactive: "", "Under Repair": "warn",
  Disposed: "err", CLOSED: "warn", ACQUISITION: "ok", DISPOSAL: "err", TRANSFER: "info", STATUS: "warn",
};
export const pill = (text: string, cls?: string) => h("span", { class: `pill ${cls ?? STATUS_CLASS[text] ?? ""}` }, t(text));

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

// ---------------------------------------------------------------- toast / dialogs
export function toast(message: string, kind: "ok" | "err" | "" = ""): void {
  let box = document.querySelector(".toasts") as HTMLElement | null;
  if (!box) { box = h("div", { class: "toasts" }); document.body.appendChild(box); }
  const el = h("div", { class: `toast ${kind}`, role: "status" }, message);
  box.appendChild(el);
  setTimeout(() => el.remove(), kind === "err" ? 7000 : 3500);
}
export const fail = (e: unknown) => toast(e instanceof Error ? t(e.message) : String(e), "err");

export interface DlgButton { label: string; primary?: boolean; danger?: boolean; onClick?: () => Promise<boolean | void> | boolean | void; }
export function dialog(title: string, content: Node, buttons: DlgButton[], opts: { wide?: boolean } = {}) {
  const err = h("div", { class: "msgbar err", style: "display:none" });
  const box = h("div", { class: `dlg ${opts.wide ? "wide" : ""}`, role: "dialog", "aria-modal": "true", "aria-label": title });
  const overlay = h("div", { class: "overlay" }, box);
  const close = () => { overlay.remove(); document.removeEventListener("keydown", onKey); };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "Escape") close();
    else if (e.key === "Enter" && (e.target as HTMLElement).tagName === "INPUT" && (e.target as HTMLInputElement).type !== "file" && box.contains(e.target as Node)) { e.preventDefault(); (foot.querySelector(".btn.primary, .btn.danger") as HTMLButtonElement | null)?.click(); }
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
  box.append(h("header", null, h("span", null, title), h("button", { class: "tb-btn", style: "color:var(--ink);height:32px", "aria-label": t("Close"), onclick: close }, icon("x"))),
    h("div", { class: "dbody" }, err, content), foot);
  overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) close(); });
  document.addEventListener("keydown", onKey);
  document.body.appendChild(overlay);
  (box.querySelector("input:not([readonly]):not([type=hidden]), select, textarea") as HTMLElement | null)?.focus();
  return { close, el: box };
}
export function confirmDialog(message: string, opts: { danger?: boolean; ok?: string; title?: string } = {}): Promise<boolean> {
  return new Promise((resolve) => {
    let done = false;
    const finish = (v: boolean) => { if (!done) { done = true; resolve(v); } };
    const d = dialog(opts.title || t("Confirm"), h("p", { style: "margin:0" }, message), [
      { label: opts.ok || t("Yes"), primary: !opts.danger, danger: opts.danger, onClick: () => { finish(true); } },
      { label: t("Cancel"), onClick: () => { finish(false); } },
    ]);
    d.el.parentElement!.addEventListener("mousedown", () => setTimeout(() => finish(false), 0));
  });
}

// ---------------------------------------------------------------- forms
export interface FieldDef {
  name: string; label: string; type?: "text" | "number" | "date" | "select" | "textarea" | "checkbox";
  options?: { value: any; label: string }[]; required?: boolean; readonly?: boolean; wide?: boolean; hint?: string;
  step?: string; onChange?: (v: string, form: Form) => void; maxlength?: number;
}
export class Form {
  el: HTMLElement;
  private inputs = new Map<string, HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>();
  private wraps = new Map<string, HTMLElement>();
  constructor(public defs: FieldDef[], values: Rec = {}, cls = "fields") {
    this.el = h("div", { class: cls });
    for (const d of defs) this.el.appendChild(this.build(d, values[d.name]));
  }
  private build(d: FieldDef, val: any): HTMLElement {
    const id = `f_${d.name}_${Math.random().toString(36).slice(2, 7)}`;
    let input: HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement;
    if (d.type === "select") {
      input = h("select", { id });
      this.fillOptions(input, d.options || [], !d.required);
    } else if (d.type === "textarea") {
      input = h("textarea", { id, rows: 3 });
    } else {
      input = h("input", { id, type: d.type === "number" ? "number" : d.type === "date" ? "date" : d.type === "checkbox" ? "checkbox" : "text",
        step: d.type === "number" ? d.step || "any" : undefined, maxlength: d.maxlength });
    }
    if (d.readonly) { input.setAttribute(d.type === "select" || d.type === "checkbox" ? "disabled" : "readonly", ""); }
    this.inputs.set(d.name, input);
    this.set(d.name, val);
    input.addEventListener("input", () => { wrap.classList.remove("invalid"); d.onChange?.(this.value(d.name), this); });
    input.addEventListener("change", () => d.onChange?.(this.value(d.name), this));
    const label = h("label", { for: id }, t(d.label), d.required ? h("span", { class: "req" }, "*") : null);
    const wrap = h("div", { class: `field ${d.wide ? "wide" : ""} ${d.type === "checkbox" ? "check" : ""}` },
      d.type === "checkbox" ? [input, label] : [label, input], d.hint ? h("span", { class: "hint" }, t(d.hint)) : null);
    this.wraps.set(d.name, wrap);
    return wrap;
  }
  private fillOptions(sel: HTMLSelectElement, opts: { value: any; label: string }[], blank: boolean) {
    clear(sel);
    if (blank) sel.appendChild(h("option", { value: "" }, ""));
    for (const o of opts) sel.appendChild(h("option", { value: String(o.value) }, o.label));
  }
  setOptions(name: string, opts: { value: any; label: string }[], blank = true) {
    const sel = this.inputs.get(name) as HTMLSelectElement; const cur = sel.value;
    this.fillOptions(sel, opts, blank); sel.value = cur;
  }
  set(name: string, v: any) {
    const i = this.inputs.get(name); if (!i) return;
    if (i instanceof HTMLInputElement && i.type === "checkbox") i.checked = !!v;
    else i.value = v === null || v === undefined ? "" : String(v);
  }
  value(name: string): string {
    const i = this.inputs.get(name)!;
    return i instanceof HTMLInputElement && i.type === "checkbox" ? String(i.checked) : i.value;
  }
  input(name: string) { return this.inputs.get(name)!; }
  wrapOf(name: string) { return this.wraps.get(name)!; }
  setReadonly(name: string, ro: boolean) {
    const i = this.inputs.get(name)!;
    const attr = i instanceof HTMLSelectElement || (i instanceof HTMLInputElement && i.type === "checkbox") ? "disabled" : "readonly";
    if (ro) i.setAttribute(attr, ""); else i.removeAttribute(attr);
  }
  get(): Rec {
    const out: Rec = {};
    for (const d of this.defs) {
      const i = this.inputs.get(d.name)!;
      out[d.name] = i instanceof HTMLInputElement && i.type === "checkbox" ? i.checked : i.value;
    }
    return out;
  }
  validate(): boolean {
    let ok = true, first: HTMLElement | null = null;
    for (const d of this.defs) {
      const bad = d.required && !this.value(d.name).trim();
      this.wraps.get(d.name)!.classList.toggle("invalid", !!bad);
      if (bad) { ok = false; first ??= this.inputs.get(d.name)!; }
    }
    if (!ok) { toast(t("Fill in the required fields."), "err"); first?.focus(); }
    return ok;
  }
}

export function fastTab(title: string, content: Node, opts: { open?: boolean; summary?: string } = {}): HTMLElement {
  const tab = h("section", { class: `fasttab ${opts.open ? "open" : ""}` });
  const head = h("header", { tabindex: 0, role: "button" }, icon("chevron"), h("h3", null, title), opts.summary ? h("span", { class: "summary" }, opts.summary) : null);
  const toggle = () => tab.classList.toggle("open");
  head.addEventListener("click", toggle);
  head.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } });
  tab.append(head, h("div", { class: "content" }, content));
  return tab;
}

// ---------------------------------------------------------------- page chrome
export interface RibbonBtn { id?: string; label: string; icon: string; onClick: () => void; primary?: boolean; danger?: boolean; disabled?: boolean; }
export function ribbon(groups: RibbonBtn[][]) {
  const el = h("div", { class: "ribbon", role: "toolbar" });
  const btns: Record<string, HTMLButtonElement> = {};
  for (const g of groups) {
    const ge = h("div", { class: "grp" });
    for (const b of g) {
      const be = h("button", { class: `rb ${b.primary ? "primary" : ""} ${b.danger ? "danger" : ""}`, type: "button", disabled: b.disabled },
        icon(b.icon), h("span", null, b.label));
      be.addEventListener("click", b.onClick);
      if (b.id) btns[b.id] = be;
      ge.appendChild(be);
    }
    el.appendChild(ge);
  }
  return { el, btns };
}

export interface PageOpts { title: string; subtitle?: string; pills?: Node[]; ribbon?: HTMLElement; factbox?: Node; }
export function page(o: PageOpts, ...body: any[]) {
  const titleEl = h("h1", null, o.title);
  const head = h("div", { class: "page-head" }, h("div", { class: "title-row" }, titleEl,
    o.subtitle ? h("span", { class: "sub" }, o.subtitle) : null, ...(o.pills || [])), o.ribbon);
  const content = h("div", { class: `page-body ${o.factbox ? "with-factbox" : ""}` });
  if (o.factbox) content.append(h("div", { class: "main-col" }, ...body), h("aside", { class: "factbox" }, o.factbox));
  else append(content, body);
  return { el: h("div", { class: "page" }, head, content), titleEl };
}

// ---------------------------------------------------------------- data grid
export interface GridOpts {
  columns: Col[]; rows: Rec[]; onOpen?: (r: Rec) => void; onSelect?: (r: Rec | null) => void;
  search?: boolean; exportName?: string; totals?: string[]; empty?: string; tools?: Node[]; limit?: number; maxHeight?: string;
}
export class DataGrid {
  el: HTMLElement;
  private rows: Rec[];
  private sortKey: string | null = null;
  private sortDir = 1;
  private term = "";
  private sel: Rec | null = null;
  private shown = 0;
  private tbody = h("tbody");
  private thead = h("thead");
  private tfoot = h("tfoot");
  private foot = h("div", { class: "grid-foot" });
  private scroll: HTMLElement;

  constructor(private o: GridOpts) {
    this.rows = o.rows;
    const tools = h("div", { class: "grid-tools" });
    if (o.search !== false) {
      const s = h("input", { class: "gt-input", style: "max-width:260px", type: "search", placeholder: t("Search…"), "aria-label": t("Search") });
      s.addEventListener("input", () => { this.term = s.value.toLowerCase(); this.render(); });
      tools.append(s);
    }
    (o.tools || []).forEach((n) => tools.append(n));
    tools.append(h("span", { class: "spacer" }));
    if (o.exportName) tools.append(h("button", { class: "rb", type: "button", onclick: () => this.exportCsv() }, icon("download"), h("span", null, t("Export to Excel"))));
    const table = h("table", { class: "grid" }, this.thead, this.tbody, this.tfoot);
    this.scroll = h("div", { class: "grid-scroll", style: o.maxHeight ? `max-height:${o.maxHeight}` : undefined }, table);
    this.el = h("div", { class: "grid-wrap" }, tools, this.scroll, this.foot);
    this.render();
  }
  private cols() { return this.o.columns.filter((c) => !c.hidden); }
  setRows(rows: Rec[]) { this.rows = rows; this.sel = null; this.o.onSelect?.(null); this.render(); }
  selected() { return this.sel; }
  private view(): Rec[] {
    let v = this.rows;
    if (this.term) {
      const cols = this.cols();
      v = v.filter((r) => cols.some((c) => cellValue(c, r[c.key]).toLowerCase().includes(this.term)));
    }
    if (this.sortKey) {
      const k = this.sortKey; const col = this.cols().find((c) => c.key === k);
      const numeric = col && ["money", "int", "pct"].includes(col.type || "");
      v = [...v].sort((a, b) => {
        const x = a[k], y = b[k];
        if (x === y) return 0;
        if (x === null || x === undefined || x === "") return 1;
        if (y === null || y === undefined || y === "") return -1;
        return (numeric ? Number(x) - Number(y) : String(x).localeCompare(String(y), undefined, { numeric: true })) * this.sortDir;
      });
    }
    return v;
  }
  private render() {
    const cols = this.cols();
    clear(this.thead);
    this.thead.append(h("tr", null, ...cols.map((c) => {
      const th = h("th", { class: ["money", "int", "pct"].includes(c.type || "") ? "num" : "", style: c.width ? `min-width:${c.width}px` : undefined, scope: "col" },
        t(c.label), this.sortKey === c.key ? h("span", { class: "srt" }, this.sortDir > 0 ? "▲" : "▼") : null);
      th.addEventListener("click", () => { if (this.sortKey === c.key) this.sortDir *= -1; else { this.sortKey = c.key; this.sortDir = 1; } this.render(); });
      return th;
    })));
    const view = this.view();
    const limit = this.o.limit ?? 300;
    this.shown = Math.min(view.length, Math.max(this.shown, limit));
    if (this.shown > view.length || this.term || this.sortKey) this.shown = Math.min(view.length, Math.max(limit, this.shown));
    clear(this.tbody);
    if (!view.length) {
      this.tbody.append(h("tr", null, h("td", { colspan: cols.length, class: "empty" }, t(this.o.empty || "No records to show."))));
    }
    for (const r of view.slice(0, this.shown)) this.tbody.append(this.row(r, cols));
    clear(this.tfoot);
    if (this.o.totals && view.length) {
      this.tfoot.append(h("tr", null, ...cols.map((c, i) => h("td", { class: ["money", "int", "pct"].includes(c.type || "") ? "num" : "" },
        this.o.totals!.includes(c.key) ? cellValue(c, view.reduce((s, r) => s + Number(r[c.key] || 0), 0)) : i === 0 ? t("Total") : ""))));
    }
    clear(this.foot);
    this.foot.append(h("span", null, t("{0} records", view.length)));
    if (view.length > this.shown) {
      this.foot.append(h("button", { class: "btn sm", type: "button", onclick: () => { this.shown += limit; this.render(); } }, t("Show more")));
    }
  }
  private row(r: Rec, cols: Col[]): HTMLElement {
    const tr = h("tr", { class: `${this.o.onOpen ? "clickable" : ""} ${this.sel === r ? "sel" : ""}` });
    tr.append(...cols.map((c, i) => {
      const v = r[c.key];
      let content: any;
      if (c.render) content = c.render(r);
      else if (c.type === "status") content = v ? pill(String(v)) : "";
      else content = cellValue(c, v);
      if (c.link && v !== null && v !== "") {
        const href = c.link(r);
        if (href) content = h("a", { href, class: "lnk", onclick: (e: Event) => e.stopPropagation() }, content);
      }
      const num = ["money", "int", "pct"].includes(c.type || "");
      const td = h("td", { class: `${num ? "num" : ""} ${c.type === "bool" ? "ctr" : ""} ${num && Number(v) < 0 ? "neg" : ""}`, title: typeof content === "string" && content.length > 38 ? content : undefined }, content);
      return td;
    }));
    tr.addEventListener("click", () => {
      this.sel = r; this.o.onSelect?.(r);
      this.tbody.querySelectorAll("tr.sel").forEach((x) => x.classList.remove("sel")); tr.classList.add("sel");
    });
    if (this.o.onOpen) tr.addEventListener("dblclick", () => this.o.onOpen!(r));
    return tr;
  }
  exportCsv() {
    const cols = this.cols();
    const esc = (s: string) => `"${s.replace(/"/g, '""')}"`;
    const lines = [cols.map((c) => esc(t(c.label))).join(",")];
    for (const r of this.view()) lines.push(cols.map((c) => (["money", "int", "pct"].includes(c.type || "") ? String(r[c.key] ?? "") : esc(cellValue(c, r[c.key])))).join(","));
    downloadCsv(this.o.exportName || "export", lines.join("\r\n"));
  }
}
export function downloadCsv(name: string, text: string) {
  const blob = new Blob(["﻿" + text], { type: "text/csv;charset=utf-8" });
  const a = h("a", { href: URL.createObjectURL(blob), download: `${name}-${today()}.csv` });
  document.body.appendChild(a); a.click(); a.remove();
}

/** Display name of a record: the Arabic column (<key>Ar) in Arabic mode when filled, else the English one. */
export const nm = (r: Rec | undefined | null, key: string): string => (r ? (getLang() === "ar" && r[key + "Ar"] ? r[key + "Ar"] : r[key] ?? "") : "");
export const opts = (rows: Rec[], value: string, label: (r: Rec) => string) => rows.map((r) => ({ value: r[value], label: label(r) }));
export const guard = (fn: () => Promise<any>) => async () => { try { await fn(); } catch (e) { fail(e); } };
export { ApiError, getLang };
