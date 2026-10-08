/** Searchable lookup (combobox): type part of a name or code instead of scrolling a dropdown.
 *  Behaves like a <select> for the code around it: `value` (get / set) and a "change" event. */
import { t } from "../core/i18n.js";
import { clear, h } from "./dom.js";

export interface ComboOption { value: string | number; label: string; }

/** Lower case, no Arabic diacritics, one form of alef / yaa / taa marbuta: "أصول" and "اصول" match. */
export function fold(s: string): string {
  // NFKD splits أ / إ / آ into alef + a combining hamza or madda (U+0653-U+0655): those marks go with the diacritics
  return s.toLowerCase().normalize("NFKD").replace(/[\u0300-\u036f\u0610-\u061a\u064b-\u065f\u0670\u0640]/g, "")
    .replace(/[أإآٱ]/g, "ا").replace(/ى/g, "ي").replace(/ة/g, "ه").replace(/ؤ/g, "و").replace(/ئ/g, "ي").trim();
}

let seq = 0;
export class ComboBox extends HTMLElement {
  private input!: HTMLInputElement;
  private list!: HTMLElement;
  private clearBtn!: HTMLButtonElement;
  private opts: { value: string; label: string }[] = [];
  private current = "";
  private shown: { value: string; label: string }[] = [];
  private hi = -1;
  private open = false;
  /** An empty value is allowed ("All …" in filters, optional fields); the placeholder names it. */
  allowEmpty = true;

  init(options: ComboOption[], o: { placeholder?: string; label?: string; allowEmpty?: boolean; id?: string } = {}): this {
    const lid = `cb${++seq}`;
    this.allowEmpty = o.allowEmpty !== false;
    this.input = h("input", { type: "text", id: o.id, class: "cb-input", role: "combobox", "aria-expanded": "false", "aria-controls": lid, "aria-autocomplete": "list",
      autocomplete: "off", spellcheck: "false", placeholder: o.placeholder || t("Search…"), "aria-label": o.label }) as HTMLInputElement;
    this.list = h("div", { class: "cb-list", id: lid, role: "listbox" });
    this.clearBtn = h("button", { type: "button", class: "cb-clear", tabindex: -1, "aria-label": t("Clear"), title: t("Clear") }, "×") as HTMLButtonElement;
    this.append(this.input, this.clearBtn, this.list);
    this.classList.add("cb");
    this.setOptions(options);
    this.input.addEventListener("focus", () => { this.input.select(); this.show(""); });
    this.input.addEventListener("click", () => { if (!this.open) this.show(""); });
    this.input.addEventListener("input", () => this.show(this.input.value));
    this.input.addEventListener("keydown", (e) => this.onKey(e));
    this.input.addEventListener("blur", () => setTimeout(() => { if (document.activeElement !== this.input && this.open) this.commitTyped(); }, 120));
    this.clearBtn.addEventListener("mousedown", (e) => e.preventDefault());
    this.clearBtn.addEventListener("click", () => { this.pick(""); this.input.focus(); });
    return this;
  }

  get value(): string { return this.current; }
  set value(v: string) { this.current = v === null || v === undefined ? "" : String(v); this.syncText(); }
  get disabled(): boolean { return this.input.readOnly; }
  set disabled(on: boolean) { this.input.readOnly = on; this.classList.toggle("ro", on); if (on) this.hide(); }
  focus(): void { this.input.focus(); }
  get inputEl(): HTMLInputElement { return this.input; }

  setOptions(options: ComboOption[]): void {
    this.opts = options.map((o) => ({ value: String(o.value), label: o.label }));
    if (this.current && !this.opts.some((o) => o.value === this.current)) this.current = this.allowEmpty ? "" : this.current;
    this.syncText();
  }

  private label(v: string): string { return this.opts.find((o) => o.value === v)?.label ?? ""; }
  private syncText(): void {
    this.input.value = this.label(this.current);
    this.classList.toggle("has-value", !!this.current);
    this.clearBtn.style.display = this.current && this.allowEmpty && !this.disabled ? "" : "none";
  }

  private show(term: string): void {
    if (this.disabled) return;
    const q = fold(term === this.label(this.current) ? "" : term);
    this.shown = q ? this.opts.filter((o) => fold(o.label).includes(q) || fold(o.value).includes(q)) : this.opts;
    clear(this.list);
    if (!this.shown.length) this.list.append(h("div", { class: "cb-none" }, t("No matches")));
    this.shown.slice(0, 200).forEach((o, i) => {
      const item = h("div", { class: `cb-item ${o.value === this.current ? "sel" : ""}`, role: "option", "aria-selected": String(o.value === this.current), "data-i": i }, o.label);
      item.addEventListener("mousedown", (e) => { e.preventDefault(); this.pick(o.value); });
      this.list.append(item);
    });
    this.hi = Math.max(0, this.shown.findIndex((o) => o.value === this.current));
    if (q) this.hi = 0;
    this.mark();
    this.place();
    this.open = true; this.list.style.display = "block"; this.input.setAttribute("aria-expanded", "true");
  }
  /** Fixed position under the box, so dialogs and scrolling panels never clip the list. */
  reposition(): void { if (this.open) this.place(); }
  private place(): void {
    const r = this.input.getBoundingClientRect();
    const below = innerHeight - r.bottom, up = below < 220 && r.top > below;
    Object.assign(this.list.style, { position: "fixed", left: `${r.left}px`, width: `${Math.max(r.width, 200)}px`,
      top: up ? "" : `${r.bottom + 2}px`, bottom: up ? `${innerHeight - r.top + 2}px` : "", maxHeight: `${Math.max(160, Math.min(300, (up ? r.top : below) - 12))}px` });
  }
  private hide(): void { this.open = false; this.list.style.display = "none"; this.input.setAttribute("aria-expanded", "false"); }
  private mark(): void {
    [...this.list.querySelectorAll<HTMLElement>(".cb-item")].forEach((n, i) => {
      n.classList.toggle("hi", i === this.hi);
      if (i === this.hi) { n.scrollIntoView({ block: "nearest" }); this.input.setAttribute("aria-activedescendant", n.id = `${this.list.id}-${i}`); }
    });
  }
  private pick(v: string): void {
    const changed = v !== this.current;
    this.current = v; this.syncText(); this.hide();
    if (changed) this.dispatchEvent(new Event("change"));
  }
  /** Leaving the box: an exact (or single) match is taken, anything else goes back to the last choice. */
  private commitTyped(): void {
    const typed = fold(this.input.value);
    if (!typed) { this.allowEmpty ? this.pick("") : (this.syncText(), this.hide()); return; }
    const exact = this.opts.find((o) => fold(o.label) === typed) || (this.shown.length === 1 ? this.shown[0] : undefined);
    if (exact) this.pick(exact.value); else { this.syncText(); this.hide(); }
  }
  private onKey(e: KeyboardEvent): void {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!this.open) { this.show(""); return; }
      const n = Math.min(this.shown.length, 200);
      if (n) { this.hi = (this.hi + (e.key === "ArrowDown" ? 1 : -1) + n) % n; this.mark(); }
    } else if (e.key === "Enter" && this.open) {
      e.preventDefault(); e.stopPropagation();   // Enter chooses here; it does not submit the dialog
      const o = this.shown[this.hi];
      if (o) this.pick(o.value); else this.hide();
    } else if (e.key === "Escape" && this.open) {
      e.stopPropagation(); this.syncText(); this.hide();
    } else if (e.key === "Tab" && this.open) {
      this.commitTyped();
    }
  }
}
if (!customElements.get("u-combo")) customElements.define("u-combo", ComboBox);
// an open list follows its box when anything scrolls
document.addEventListener("scroll", () => document.querySelectorAll<ComboBox>("u-combo").forEach((c) => c.reposition()), true);

/** A searchable filter / lookup. `options` are the choices; the empty value is "all" (or nothing chosen). */
export function combo(options: ComboOption[], o: { value?: string | number; placeholder?: string; label?: string; allowEmpty?: boolean; width?: number; id?: string } = {}): ComboBox {
  const c = (document.createElement("u-combo") as ComboBox).init(options, o);
  if (o.width) c.style.width = `${o.width}px`;
  if (o.value !== undefined) c.value = String(o.value);
  return c;
}
