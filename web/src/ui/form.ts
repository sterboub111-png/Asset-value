/** Forms, field definitions and fast tabs. */
import { t } from "../core/i18n.js";
import type { Rec } from "../core/types.js";
import { toast } from "./dialogs.js";
import { fmtDate, parseDate } from "./format.js";
import { clear, h } from "./dom.js";
import { icon } from "./icons.js";
import { ComboBox, combo } from "./combo.js";

export interface FieldDef {
  name: string; label: string; type?: "text" | "number" | "date" | "time" | "password" | "select" | "textarea" | "checkbox";
  options?: { value: any; label: string }[]; required?: boolean; readonly?: boolean; wide?: boolean; hint?: string;
  step?: string; autocomplete?: string; onChange?: (v: string, form: Form) => void; maxlength?: number;
  search?: boolean;   // select: a searchable lookup even with few options (lists of more than five always are)
}
type Control = HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement | ComboBox;
export class Form {
  el: HTMLElement;
  private inputs = new Map<string, Control>();
  private wraps = new Map<string, HTMLElement>();
  private dates = new Set<string>();   // date fields: typed and shown dd/mm/yyyy, read as ISO
  constructor(public defs: FieldDef[], values: Rec = {}, cls = "fields") {
    this.el = h("div", { class: cls });
    for (const d of defs) this.el.appendChild(this.build(d, values[d.name]));
  }
  private build(d: FieldDef, val: any): HTMLElement {
    const id = `f_${d.name}_${Math.random().toString(36).slice(2, 7)}`;
    let input: Control;
    let control: HTMLElement | null = null;
    if (d.type === "date") {
      // a text box (day first, independent of the browser's locale) with the calendar picker behind a button
      const text = h("input", { id, type: "text", inputmode: "numeric", placeholder: t("dd/mm/yyyy"), autocomplete: "off", maxlength: 10 }) as HTMLInputElement;
      const native = h("input", { type: "date", class: "date-native", tabindex: -1, "aria-hidden": "true" }) as HTMLInputElement;
      const pick = h("button", { type: "button", class: "date-pick", tabindex: -1, "aria-label": t("Choose a date"), title: t("Choose a date") }, icon("calendar"));
      pick.addEventListener("click", () => {
        if (text.readOnly) return;
        native.value = parseDate(text.value) || "";
        try { native.showPicker(); } catch { native.focus(); }
      });
      native.addEventListener("change", () => { text.value = fmtDate(native.value); wrap.classList.remove("invalid"); text.dispatchEvent(new Event("change")); });
      text.addEventListener("blur", () => { const iso = parseDate(text.value); if (iso) text.value = fmtDate(iso); });
      this.dates.add(d.name);
      input = text;
      control = h("span", { class: "date-in" }, text, pick, native);
    } else if (d.type === "select" && (d.search || (d.options || []).length > 5)) {
      input = combo(d.options || [], { id, allowEmpty: !d.required, placeholder: t("Type to search…"), label: t(d.label) });
    } else if (d.type === "select") {
      input = h("select", { id });
      this.fillOptions(input, d.options || [], !d.required);
    } else if (d.type === "textarea") {
      input = h("textarea", { id, rows: 3 });
    } else {
      input = h("input", { id, type: d.type === "number" ? "number" : d.type === "time" ? "time" : d.type === "password" ? "password" : d.type === "checkbox" ? "checkbox" : "text",
        step: d.type === "number" ? d.step || "any" : undefined, maxlength: d.maxlength, autocomplete: d.autocomplete ?? (d.type === "password" ? "new-password" : "off") });
    }
    if (d.readonly) this.lock(input, true);
    this.inputs.set(d.name, input);
    this.set(d.name, val);
    input.addEventListener("input", () => { wrap.classList.remove("invalid"); if (!this.dates.has(d.name)) d.onChange?.(this.value(d.name), this); });
    input.addEventListener("change", () => { wrap.classList.remove("invalid"); d.onChange?.(this.value(d.name), this); });
    const label = h("label", { for: id }, t(d.label), d.required ? h("span", { class: "req" }, "*") : null);
    const wrap = h("div", { class: `field ${d.wide ? "wide" : ""} ${d.type === "checkbox" ? "check" : ""}` },
      d.type === "checkbox" ? [input, label] : [label, control || input], d.hint ? h("span", { class: "hint" }, t(d.hint)) : null);
    this.wraps.set(d.name, wrap);
    return wrap;
  }
  private fillOptions(sel: HTMLSelectElement, opts: { value: any; label: string }[], blank: boolean) {
    clear(sel);
    if (blank) sel.appendChild(h("option", { value: "" }, ""));
    for (const o of opts) sel.appendChild(h("option", { value: String(o.value) }, o.label));
  }
  setOptions(name: string, opts: { value: any; label: string }[], blank = true) {
    const sel = this.inputs.get(name)!;
    if (sel instanceof ComboBox) { sel.allowEmpty = blank; sel.setOptions(opts); return; }
    const cur = sel.value;
    this.fillOptions(sel as HTMLSelectElement, opts, blank); sel.value = cur;
  }
  set(name: string, v: any) {
    const i = this.inputs.get(name); if (!i) return;
    if (i instanceof HTMLInputElement && i.type === "checkbox") i.checked = !!v;
    else if (this.dates.has(name)) i.value = fmtDate(v);
    else i.value = v === null || v === undefined ? "" : String(v);
  }
  value(name: string): string {
    const i = this.inputs.get(name)!;
    if (this.dates.has(name)) return parseDate(i.value) ?? i.value;   // a bad date goes through as typed, so the server names the field
    return i instanceof HTMLInputElement && i.type === "checkbox" ? String(i.checked) : i.value;
  }
  input(name: string) { return this.inputs.get(name)!; }
  wrapOf(name: string) { return this.wraps.get(name)!; }
  setReadonly(name: string, ro: boolean) { this.lock(this.inputs.get(name)!, ro); }
  private lock(i: Control, ro: boolean) {
    if (i instanceof ComboBox) { i.disabled = ro; return; }
    const attr = i instanceof HTMLSelectElement || (i instanceof HTMLInputElement && i.type === "checkbox") ? "disabled" : "readonly";
    if (ro) i.setAttribute(attr, ""); else i.removeAttribute(attr);
  }
  get(): Rec {
    const out: Rec = {};
    for (const d of this.defs) {
      const i = this.inputs.get(d.name)!;
      out[d.name] = i instanceof HTMLInputElement && i.type === "checkbox" ? i.checked : this.dates.has(d.name) ? this.value(d.name) : i.value;
    }
    return out;
  }
  validate(): boolean {
    let ok = true, badDate = false, first: HTMLElement | null = null;
    for (const d of this.defs) {
      const dateBad = this.dates.has(d.name) && parseDate(this.inputs.get(d.name)!.value) === null;
      const bad = dateBad || (d.required && !this.value(d.name).trim());
      this.wraps.get(d.name)!.classList.toggle("invalid", !!bad);
      if (bad) { ok = false; badDate ||= dateBad; first ??= this.inputs.get(d.name)!; }
    }
    if (!ok) { toast(t(badDate ? "Enter dates as dd/mm/yyyy." : "Fill in the required fields."), "err"); first?.focus(); }
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
