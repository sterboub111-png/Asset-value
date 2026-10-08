/** Analysis mode for report data, after Business Central's "Analyze": choose columns, group rows, pivot, filter,
 *  aggregate, sum the selected cells in the status bar, and keep several named analysis tabs per report. */
import { t } from "../core/i18n.js";
import type { ColType, Rec } from "../core/types.js";
import { clear, h } from "./dom.js";
import { cellValue, fmtInt, parseDate } from "./format.js";
import { downloadCsv } from "./grid.js";
import { csvText } from "./helpers.js";
import { icon } from "./icons.js";
import { fold } from "./combo.js";
import { ChartSeries, ChartSpec, ChartType, drawChart } from "./chart.js";

export interface ACol { key: string; label: string; type: ColType; }
export type Agg = "none" | "sum" | "count" | "avg" | "min" | "max";
interface Filter { text?: string; values?: string[]; min?: string; max?: string; }
export interface AState {
  cols: string[];                    // visible columns, in order
  groups: string[];                  // row groups, outermost first
  aggs: Record<string, Agg>;         // how each number column is totalled
  pivotOn: boolean; pivot: string;   // pivot mode and its column labels field
  filters: Record<string, Filter>;
  sort: { key: string; dir: number } | null;
  collapsed: string[];               // collapsed group paths
  chart?: ChartConf;                 // the chart over the analysis
}
export interface ChartConf { on: boolean; type: "auto" | ChartType; measure: string; }   // measure "" = first value, "*" = all values
export interface ChartData { spec?: Omit<ChartSpec, "onPick">; field?: string; empty?: string; measures: { key: string; label: string }[]; allowAll: boolean; title: string; }
interface Saved { tabs: { name: string; state: AState }[]; active: number; }
export interface AnalysisOpts {
  id: string;                                  // remembered per report
  columns: ACol[];
  rows: Rec[];
  text: (key: string, row: Rec) => string;     // what a cell shows (translated, formatted)
  defaults: () => AState;
  order?: Record<string, string>;              // column -> field holding its natural order
  onPin?: (st: AState, title: string) => void; // "Pin to dashboard"
}
interface GNode { label: string; path: string; depth: number; rows: Rec[]; kids: GNode[]; }

const NUM = new Set<ColType>(["money", "int", "pct"]);
const AGGS: Agg[] = ["sum", "count", "avg", "min", "max"];
const AGG_LABEL: Record<Agg, string> = { none: "None", sum: "Sum", count: "Count", avg: "Average", min: "Min", max: "Max" };
const DETAIL_LIMIT = 3000;   // detail rows drawn at most (groups and totals always cover everything)
const PIVOT_LIMIT = 60;      // distinct column labels in pivot mode
const SEP = "\u0001";

const store = {
  get<T>(k: string): T | null { try { return JSON.parse(localStorage.getItem(k) || "null"); } catch { return null; } },
  set(k: string, v: unknown) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* storage unavailable */ } },
};

function aggregate(agg: Agg, rows: Rec[], key: string): number | null {
  if (agg === "count") return rows.length;
  const vals = rows.map((r) => r[key]).filter((v) => v !== null && v !== undefined && v !== "").map(Number).filter((v) => !Number.isNaN(v));
  if (!vals.length) return agg === "sum" ? 0 : null;
  if (agg === "sum") return vals.reduce((a, b) => a + b, 0);
  if (agg === "avg") return vals.reduce((a, b) => a + b, 0) / vals.length;
  if (agg === "min") return vals.reduce((a, b) => (b < a ? b : a));
  if (agg === "max") return vals.reduce((a, b) => (b > a ? b : a));
  return null;
}

/** Add an analysis tab to a report and make it the active one ("Open in analysis" from the dashboard). */
export function openAnalysisTab(reportId: string, name: string, state: AState): void {
  const k = `usool.analysis.${reportId}`;
  const saved = store.get<Saved>(k);
  const tabs = saved && Array.isArray(saved.tabs) ? saved.tabs : [];
  const at = tabs.findIndex((x) => x.name === name);
  if (at >= 0) tabs[at].state = state; else tabs.push({ name, state });
  store.set(k, { tabs, active: at >= 0 ? at : tabs.length - 1 });
}

/** The data side of an analysis (filter, sort, group, total, chart data) - shared by the analysis view and the dashboard. */
export class AnalysisModel {
  term = "";
  constructor(public o: AnalysisOpts, public st: AState) {}
  col(k: string) { return this.o.columns.find((c) => c.key === k); }
  label(k: string) { const c = this.col(k); return c ? t(c.label) : k; }
  isNum(k: string) { const c = this.col(k); return !!c && NUM.has(c.type); }
  valueCols(): string[] { return this.st.cols.filter((k) => this.isNum(k) && (this.st.aggs[k] || "none") !== "none"); }
  // ---------------------------------------------------------------- data
  match(r: Rec): boolean {
    for (const [k, f] of Object.entries(this.st.filters)) {
      const c = this.col(k); if (!c) continue;
      const shown = this.o.text(k, r);
      if (f.values && f.values.length && !f.values.includes(shown)) return false;
      if (f.text && !fold(shown).includes(fold(f.text))) return false;
      if (f.min || f.max) {
        const v = r[k];
        if (v === null || v === undefined || v === "") return false;
        if (c.type === "date") {
          const d = String(v).slice(0, 10), lo = f.min ? parseDate(f.min) : "", hi = f.max ? parseDate(f.max) : "";
          if ((lo && d < lo) || (hi && d > hi)) return false;
        } else {
          if (f.min && Number(v) < Number(f.min)) return false;
          if (f.max && Number(v) > Number(f.max)) return false;
        }
      }
    }
    return !this.term || this.st.cols.some((k) => fold(this.o.text(k, r)).includes(fold(this.term)));
  }
  view(): Rec[] {
    let v = this.o.rows.filter((r) => this.match(r));
    const s = this.st.sort;
    if (s && this.col(s.key)) {
      const num = this.isNum(s.key);
      v = [...v].sort((a, b) => {
        const x = a[s.key], y = b[s.key];
        if (x === y) return 0;
        if (x === null || x === undefined || x === "") return 1;
        if (y === null || y === undefined || y === "") return -1;
        return (num ? Number(x) - Number(y) : String(x).localeCompare(String(y), undefined, { numeric: true })) * s.dir;
      });
    }
    return v;
  }
  tree(rows: Rec[], groups: string[], depth = 0, prefix = ""): GNode[] {
    const key = groups[depth];
    if (!key) return [];
    const map = new Map<string, Rec[]>();
    for (const r of rows) { const v = this.o.text(key, r) || "—"; const list = map.get(v); if (list) list.push(r); else map.set(v, [r]); }
    return this.ordered(key, [...map]).map(([label, rs]) => { const path = `${prefix}${SEP}${label}`; return { label, path, depth, rows: rs, kids: this.tree(rs, groups, depth + 1, path) }; });
  }
  /** Labels of a field in their natural order: by the report's order field, dates and numbers by value, anything else as it comes. */
  ordered(key: string, entries: [string, Rec[]][]): [string, Rec[]][] {
    if (this.st.sort?.key === key) return entries;   // the user sorted by this column: keep that order
    const by = this.o.order?.[key] || (this.col(key)?.type === "date" || this.isNum(key) ? key : "");
    if (!by) return entries;
    const rank = (rs: Rec[]) => rs.reduce<any>((m, r) => { const v = r[by]; return m === null || (v !== null && v !== undefined && v < m) ? v : m; }, null);
    return [...entries].sort((a, b) => {
      const x = rank(a[1]), y = rank(b[1]);
      if (x === y) return 0;
      if (x === null || x === undefined) return 1;
      if (y === null || y === undefined) return -1;
      return typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), undefined, { numeric: true });
    });
  }
  rowGroups() { return this.st.pivotOn ? this.st.groups.filter((g) => g !== this.st.pivot) : this.st.groups; }
  /** What the chart shows: categories = the first row group (or the column labels), series = the values, or the column labels
   *  when the rows are grouped too. Colours follow the entity (its place in the whole data), never its rank after a filter. */
  chartData(conf: ChartConf, rows: Rec[]): ChartData {
    const groups = this.rowGroups();
    const pivot = this.st.pivotOn && this.st.pivot ? this.st.pivot : "";
    const field = groups[0] || pivot;
    const measures = this.valueCols().map((k) => ({ key: k, label: this.label(k) }));
    const mkeys = measures.map((m) => m.key);
    const allowAll = mkeys.length > 1 && new Set(mkeys.map((k) => this.col(k)!.type)).size === 1 && new Set(mkeys.map((k) => this.st.aggs[k])).size === 1;
    if (!field) return { empty: t("Group the rows, or choose column labels, to chart them."), measures, allowAll, title: "" };
    const bySeries = !!(pivot && groups.length && pivot !== field);
    const chosen = conf.measure === "*" && allowAll && !bySeries ? mkeys : [mkeys.includes(conf.measure) ? conf.measure : mkeys[0]].filter((k): k is string => !!k);
    const key = chosen[0];
    const agg = key ? this.st.aggs[key] : "count";
    const value = (k: string | undefined, rs: Rec[]) => (k ? aggregate(this.st.aggs[k], rs, k) : rs.length);
    const groupOf = (k: string, rs: Rec[]) => {
      const map = new Map<string, Rec[]>();
      for (const r of rs) { const v = this.o.text(k, r) || "—"; const l = map.get(v); if (l) l.push(r); else map.set(v, [r]); }
      return this.ordered(k, [...map]);
    };
    let cats = groupOf(field, rows);
    const additive = agg === "sum" || agg === "count";
    let note = "";
    if (cats.length > 40) {   // the tail folds into "Other" where adding up is meaningful, else it is left out
      const tail = cats.slice(39);
      cats = additive ? [...cats.slice(0, 39), [t("Other"), tail.flatMap(([, rs]) => rs)]] : cats.slice(0, 40);
      note = additive ? "" : t("First {0} shown", 40);
    }
    let series: ChartSeries[];
    if (bySeries) {
      const order = groupOf(pivot, this.o.rows).map(([l]) => l);   // the slot of a label comes from all the data
      const present = groupOf(pivot, rows).map(([l]) => l);
      const keep = present.slice(0, additive ? 7 : 8), rest = additive ? present.slice(7) : [];
      series = keep.map((l) => ({ name: l, slot: Math.min(8, order.indexOf(l) + 1) || 8,
        values: cats.map(([, rs]) => value(key, rs.filter((r) => (this.o.text(pivot, r) || "—") === l))) }));
      if (rest.length) series.push({ name: t("Other"), slot: 0, values: cats.map(([, rs]) => value(key, rs.filter((r) => rest.includes(this.o.text(pivot, r) || "—")))) });
    } else if (chosen.length) {
      series = chosen.map((k) => ({ name: this.label(k), slot: Math.min(8, this.st.cols.filter((c) => this.isNum(c)).indexOf(k) + 1) || 1, values: cats.map(([, rs]) => value(k, rs)) }));
      if (series.length === 1) series[0].slot = 1;
    } else series = [{ name: t("Count"), slot: 1, values: cats.map(([, rs]) => rs.length) }];
    // the chart type: asked for, or chosen from the data
    const time = !!this.o.order?.[field] || this.col(field)?.type === "date";
    const longest = Math.max(0, ...cats.map(([l]) => l.length));
    let type: ChartType = conf.type === "auto" ? (time && cats.length >= 3 ? "line" : cats.length > 10 || longest > 16 ? "bar" : "column") : conf.type;
    if (type === "stacked" && (series.length < 2 || !additive)) type = "column";
    const negative = series.some((s) => s.values.some((v) => (v || 0) < 0));
    if (type === "donut" && (series.length > 1 || !additive || negative)) type = "column";
    let categories = cats.map(([l]) => l);
    if (type === "donut" && categories.length > 6) {   // part-to-whole reads at six slices at most
      const s = series[0];
      categories = [...categories.slice(0, 5), t("Other")];
      s.values = [...s.values.slice(0, 5), s.values.slice(5).reduce<number>((a, b) => a + (b || 0), 0)];
    }
    const c = key ? this.col(key) : undefined;
    const fmt = (v: number) => (agg === "count" || !c ? fmtInt(v) : this.fmtAgg(key!, agg, v));
    const what = chosen.length > 1 ? chosen.map((k) => this.label(k)).join(", ") : key ? this.label(key) : t("Count");
    return { spec: { type, categories, series, fmt }, field, measures, allowAll, empty: note || undefined,
      title: `${what} ${t("by")} ${this.label(field)}${bySeries ? ` ${t("and")} ${this.label(pivot)}` : ""}` };
  }
  fmtAgg(k: string, agg: Agg, v: number | null): string {
    if (v === null) return "";
    if (agg === "count") return fmtInt(v);
    const c = this.col(k)!;
    if (agg === "avg" && c.type === "int") return cellValue({ type: "money" }, v);
    return cellValue(c, c.type === "pct" ? Math.round(v * 100) / 100 : v);
  }

}

export class Analysis extends AnalysisModel {
  el: HTMLElement;
  private saved: Saved;
  private paneTab: "columns" | "filters" = "columns";
  private colSearch = "";
  private tabsEl = h("div", { class: "an-tabs", role: "tablist" });
  private scroll = h("div", { class: "an-scroll", tabindex: 0 });
  private pane = h("aside", { class: "an-pane", "aria-label": t("Analysis") });
  private status = h("div", { class: "an-status", "aria-live": "polite" });
  private grid: HTMLTableCellElement[][] = [];   // drawn cells by row/column, for rectangle selection
  private sel = new Set<HTMLTableCellElement>();
  private anchor: HTMLTableCellElement | null = null;
  private dragging = false;
  private viewRows: Rec[] = [];
  private chartBox = h("div", { class: "an-chart" });
  private chartBtn: HTMLElement | null = null;
  private chartRO: ResizeObserver | null = null;

  constructor(o: AnalysisOpts) {
    super(o, o.defaults());
    const keys = new Set(o.columns.map((c) => c.key));
    const clean = (s: AState): AState => {   // a saved analysis may name columns this report no longer has
      const d = o.defaults();
      const ok = (k: string) => keys.has(k);
      return {
        cols: (s.cols || d.cols).filter(ok), groups: (s.groups || []).filter(ok), aggs: { ...d.aggs, ...(s.aggs || {}) },
        pivotOn: !!s.pivotOn, pivot: ok(s.pivot) ? s.pivot : "", sort: s.sort && ok(s.sort.key) ? s.sort : null,
        filters: Object.fromEntries(Object.entries(s.filters || {}).filter(([k]) => ok(k))), collapsed: s.collapsed || [],
        chart: s.chart ? { on: !!s.chart.on, type: s.chart.type || "auto", measure: s.chart.measure || "" } : undefined,
      };
    };
    const got = store.get<Saved>(this.key());
    this.saved = got && Array.isArray(got.tabs) && got.tabs.length
      ? { tabs: got.tabs.map((x) => ({ name: String(x.name || ""), state: clean(x.state || ({} as AState)) })), active: Math.min(Math.max(0, got.active | 0), got.tabs.length - 1) }
      : { tabs: [{ name: t("Analysis {0}", 1), state: o.defaults() }], active: 0 };
    this.st = this.saved.tabs[this.saved.active].state;
    const paneOpen = store.get<boolean>("usool.analysis.pane") ?? false;   // the data gets the full width until the pane is asked for

    const search = h("input", { class: "gt-input an-search", type: "search", placeholder: t("Search…"), "aria-label": t("Search") }) as HTMLInputElement;
    search.addEventListener("input", () => { this.term = search.value.trim().toLowerCase(); this.renderGrid(); });
    const tool = (label: string, ic: string, fn: () => void, cls = "") => h("button", { class: `rb an-tool ${cls}`, type: "button", title: label, onclick: fn }, icon(ic), h("span", null, label));
    const paneBtn = tool(t("Analysis pane"), "columns", () => {
      const open = !this.el.classList.contains("pane-open");
      this.el.classList.toggle("pane-open", open); paneBtn.classList.toggle("active", open);
      store.set("usool.analysis.pane", open);
    }, paneOpen ? "active" : "");
    this.chartBtn = tool(t("Chart"), "chart", () => { const c = this.chartConf(); c.on = !c.on; this.save(); this.renderChart(); });
    const bar = h("div", { class: "an-bar" }, this.tabsEl, h("span", { class: "spacer" }), search, this.chartBtn,
      tool(t("Expand all"), "plus", () => { this.st.collapsed = []; this.commit(false); }),
      tool(t("Collapse all"), "minus", () => { this.st.collapsed = this.allPaths(); this.commit(false); }), paneBtn);
    this.el = h("div", { class: `an ${paneOpen ? "pane-open" : ""}` }, bar, h("div", { class: "an-body" }, h("div", { class: "an-main" }, this.chartBox, this.scroll, this.status), this.pane));

    // cell selection: drag a rectangle, Shift extends, Ctrl/Cmd adds single cells; Ctrl+C copies
    this.scroll.addEventListener("mousedown", (e) => this.onDown(e));
    this.scroll.addEventListener("mouseover", (e) => {
      if (!this.dragging || !this.anchor) return;
      const td = (e.target as HTMLElement).closest("td");
      if (td && this.scroll.contains(td)) this.selectRect(this.anchor, td as HTMLTableCellElement);
    });
    document.addEventListener("mouseup", () => { this.dragging = false; });
    this.scroll.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "c" && this.sel.size) { e.preventDefault(); void this.copy(); }
      if (e.key === "Escape") { this.clearSel(); this.updateStatus(); }
    });
    this.renderTabs(); this.renderPane(); this.renderGrid();
  }

  // ---------------------------------------------------------------- state
  private key() { return `usool.analysis.${this.o.id}`; }
  private save() { store.set(this.key(), this.saved); }
  /** Save, redraw the grid, and (unless told otherwise) the pane. */
  private commit(pane = true) { this.save(); this.renderGrid(); if (pane) this.renderPane(); }
  private filterCount() { return Object.values(this.st.filters).filter((f) => f.text || f.min || f.max || (f.values && f.values.length)).length; }

  // ---------------------------------------------------------------- tabs
  private renderTabs() {
    clear(this.tabsEl);
    this.saved.tabs.forEach((tab, i) => {
      const active = i === this.saved.active;
      const b = h("button", { class: `an-tab ${active ? "active" : ""}`, type: "button", role: "tab", "aria-selected": String(active), title: t("Double-click to rename") }, tab.name);
      b.addEventListener("click", () => { if (!active) { this.saved.active = i; this.st = tab.state; this.clearSel(); this.save(); this.renderTabs(); this.renderPane(); this.renderGrid(); } });
      b.addEventListener("dblclick", () => {
        const inp = h("input", { class: "an-tab-edit", value: tab.name, "aria-label": t("Rename") }) as HTMLInputElement;
        const done = () => { tab.name = inp.value.trim() || tab.name; this.save(); this.renderTabs(); };
        inp.addEventListener("keydown", (e) => { if (e.key === "Enter") inp.blur(); if (e.key === "Escape") { inp.value = tab.name; inp.blur(); } });
        inp.addEventListener("blur", done);
        b.replaceWith(inp); inp.focus(); inp.select();
      });
      const wrap = h("span", { class: "an-tabw" }, b);
      if (active && this.saved.tabs.length > 1) {
        wrap.append(h("button", { class: "an-tab-x", type: "button", "aria-label": t("Delete analysis"), title: t("Delete analysis"), onclick: () => {
          this.saved.tabs.splice(i, 1); this.saved.active = Math.max(0, i - 1); this.st = this.saved.tabs[this.saved.active].state;
          this.save(); this.renderTabs(); this.renderPane(); this.renderGrid();
        } }, icon("x")));
      }
      this.tabsEl.append(wrap);
    });
    this.tabsEl.append(h("button", { class: "an-tab an-add", type: "button", title: t("New analysis"), "aria-label": t("New analysis"), onclick: () => {
      const n = this.saved.tabs.length + 1;
      this.saved.tabs.push({ name: t("Analysis {0}", n), state: this.o.defaults() });
      this.saved.active = this.saved.tabs.length - 1; this.st = this.saved.tabs[this.saved.active].state;
      this.save(); this.renderTabs(); this.renderPane(); this.renderGrid();
    } }, icon("plus")));
  }

  private allPaths(): string[] {
    const out: string[] = [];
    const walk = (ns: GNode[]) => ns.forEach((n) => { out.push(n.path); walk(n.kids); });
    walk(this.tree(this.view(), this.rowGroups()));
    return out;
  }
  // ---------------------------------------------------------------- grid
  private renderGrid() {
    this.clearSel();
    this.viewRows = this.view();
    this.grid = [];
    const table = this.st.pivotOn && this.st.pivot ? this.pivotTable() : this.listTable();
    clear(this.scroll); this.scroll.append(table);
    this.updateStatus();
    this.renderChart();
  }

  // ---------------------------------------------------------------- chart
  private chartConf(): ChartConf { return (this.st.chart ||= { on: false, type: "auto", measure: "" }); }
  /** The chart above the grid: it follows the grouping, values, pivot and filters; a click on a category filters to it. */
  private renderChart() {
    const conf = this.chartConf();
    this.chartBtn?.classList.toggle("active", conf.on);
    this.chartRO?.disconnect();
    clear(this.chartBox);
    this.chartBox.style.display = conf.on ? "" : "none";
    if (!conf.on) return;
    const data = this.chartData(conf, this.viewRows);
    const seg = (ty: ChartConf["type"], label: string) => h("button", { class: `an-seg ${conf.type === ty ? "on" : ""}`, type: "button", "aria-pressed": String(conf.type === ty),
      onclick: () => { conf.type = ty; this.save(); this.renderChart(); } }, label);
    let measure: HTMLElement | null = null;
    if (data.measures.length > 1) {
      const sel = h("select", { class: "an-agg an-measure", "aria-label": t("Value") },
        ...data.measures.map((m) => h("option", { value: m.key, selected: conf.measure === m.key }, m.label)),
        data.allowAll ? h("option", { value: "*", selected: conf.measure === "*" }, t("All values")) : null) as HTMLSelectElement;
      sel.addEventListener("change", () => { conf.measure = sel.value; this.save(); this.renderChart(); });
      measure = sel;
    }
    const pin = this.o.onPin && data.spec ? h("button", { class: "rb an-tool", type: "button", title: t("Pin to dashboard"),
      onclick: () => this.o.onPin!(JSON.parse(JSON.stringify({ ...this.st, chart: { ...conf, on: true } })), data.title) }, icon("pin"), h("span", null, t("Pin to dashboard"))) : null;
    const host = h("div", { class: "an-chart-host" });
    this.chartBox.append(h("div", { class: "an-chart-bar" },
      h("div", { class: "an-chart-title" }, data.title, data.spec ? h("span", { class: "an-chart-hint" }, t("Click a bar to filter")) : null),
      h("div", { class: "an-segs", role: "group", "aria-label": t("Chart type") }, seg("auto", t("Auto")), seg("column", t("Column")), seg("bar", t("Bar")),
        seg("line", t("Line")), seg("stacked", t("Stacked")), seg("donut", t("Donut"))), measure, pin), host);
    if (!data.spec) { host.append(h("div", { class: "viz-empty" }, data.empty || "")); return; }
    if (data.empty) this.chartBox.append(h("div", { class: "an-chart-note" }, data.empty));
    const field = data.field!;
    const spec: ChartSpec = { ...data.spec, onPick: (i) => {
      const label = data.spec!.categories[i];
      if (label === t("Other")) return;
      this.st.filters[field] = { ...(this.st.filters[field] || {}), values: [label] };   // drill: filter to the clicked category
      this.commit();
    } };
    let lastW = -1;
    const draw = () => { lastW = host.clientWidth; drawChart(host, spec); };
    draw();
    this.chartRO = new ResizeObserver(() => { if (Math.abs(host.clientWidth - lastW) > 4) draw(); });
    this.chartRO.observe(host);
  }
  private numCell(k: string, agg: Agg, rows: Rec[]): HTMLTableCellElement {
    const v = aggregate(agg, rows, k);
    const td = h("td", { class: `num ${v !== null && v < 0 ? "neg" : ""}` }, this.fmtAgg(k, agg, v));
    if (v !== null) td.dataset.n = String(Math.round(v * 1e6) / 1e6);   // no float noise in the export or the status bar
    return td;
  }
  private caret(path: string, open: boolean): HTMLElement {
    return h("button", { class: `an-caret ${open ? "open" : ""}`, type: "button", "aria-expanded": String(open), "aria-label": open ? t("Collapse") : t("Expand"),
      onclick: () => {
        const at = this.st.collapsed.indexOf(path);
        if (at >= 0) this.st.collapsed.splice(at, 1); else this.st.collapsed.push(path);
        this.commit(false);
      } }, icon("chevron"));
  }
  private th(k: string, sortable = true): HTMLTableCellElement {
    const s = this.st.sort;
    const cell = h("th", { class: this.isNum(k) ? "num" : "", scope: "col", draggable: "true", tabindex: sortable ? 0 : undefined,
      "aria-sort": s && s.key === k ? (s.dir > 0 ? "ascending" : "descending") : "none", title: t("Click to sort, drag to group") },
      this.label(k), s && s.key === k ? h("span", { class: "srt" }, s.dir > 0 ? "▲" : "▼") : null);
    cell.addEventListener("dragstart", (e) => e.dataTransfer?.setData("text/plain", `an-col:${k}`));
    if (sortable) {
      const sort = () => { this.st.sort = s && s.key === k ? (s.dir > 0 ? { key: k, dir: -1 } : null) : { key: k, dir: 1 }; this.commit(false); };
      cell.addEventListener("click", sort);
      cell.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sort(); } });
    }
    return cell;
  }
  private addRow(body: HTMLElement, tr: HTMLTableRowElement) {
    const cells = [...tr.children] as HTMLTableCellElement[];
    const ri = this.grid.length;
    cells.forEach((c, ci) => { c.dataset.ri = String(ri); c.dataset.ci = String(ci); });
    this.grid.push(cells);
    body.append(tr);
  }

  /** Rows (optionally grouped, with subtotals) — the normal analysis view. */
  private listTable(): HTMLElement {
    const groups = this.rowGroups();
    const detail = this.st.cols.filter((k) => !groups.includes(k));
    const values = new Set(this.valueCols());
    const thead = h("thead", null, h("tr", null,
      groups.length ? h("th", { class: "an-gcol", scope: "col" }, groups.map((g) => this.label(g)).join(" › ")) : null,
      ...detail.map((k) => this.th(k))));
    const tbody = h("tbody");
    let drawn = 0, cut = false;
    const detailRow = (r: Rec, depth: number) => {
      if (drawn >= DETAIL_LIMIT) { cut = true; return; }
      drawn++;
      const tr = h("tr", { class: "an-row" },
        groups.length ? h("td", { class: "an-gcell", style: `--d:${depth}` }) : null,
        ...detail.map((k) => {
          const c = this.col(k)!, v = r[k], num = NUM.has(c.type);
          const td = h("td", { class: `${num ? "num" : ""} ${num && Number(v) < 0 ? "neg" : ""}` }, this.o.text(k, r));
          if (num && v !== null && v !== undefined && v !== "") td.dataset.n = String(v);
          return td;
        }));
      this.addRow(tbody, tr);
    };
    const walk = (nodes: GNode[]) => {
      for (const n of nodes) {
        const open = !this.st.collapsed.includes(n.path);
        const tr = h("tr", { class: `an-grp lvl${Math.min(n.depth, 3)}` },
          h("td", { class: "an-gcell", style: `--d:${n.depth}` }, this.caret(n.path, open), h("span", { class: "an-glabel" }, n.label), h("span", { class: "an-count" }, fmtInt(n.rows.length))),
          ...detail.map((k) => (values.has(k) ? this.numCell(k, this.st.aggs[k], n.rows) : h("td"))));
        this.addRow(tbody, tr);
        if (open) n.kids.length ? walk(n.kids) : n.rows.forEach((r) => detailRow(r, n.depth + 1));
      }
    };
    if (groups.length) walk(this.tree(this.viewRows, groups)); else this.viewRows.forEach((r) => detailRow(r, 0));
    if (!this.viewRows.length) tbody.append(h("tr", null, h("td", { class: "empty", colspan: detail.length + (groups.length ? 1 : 0) }, t("No data for these parameters."))));
    if (cut) tbody.append(h("tr", null, h("td", { class: "an-more", colspan: detail.length + (groups.length ? 1 : 0) }, t("Showing the first {0} rows. Group or filter to see the rest; totals include every row.", fmtInt(DETAIL_LIMIT)))));
    const tfoot = h("tfoot");
    if (this.viewRows.length && (values.size || groups.length)) {
      const tr = h("tr", null,
        groups.length ? h("td", { class: "an-gcell" }, t("Total"), h("span", { class: "an-count" }, fmtInt(this.viewRows.length))) : null,
        ...detail.map((k, i) => (values.has(k) ? this.numCell(k, this.st.aggs[k], this.viewRows) : h("td", null, !groups.length && i === 0 ? t("Total") : ""))));
      this.addRow(tfoot, tr);
    }
    return h("table", { class: "an-grid" }, thead, tbody, tfoot);
  }

  /** Pivot mode: row groups down the side, the column-label field across the top, aggregated values in the cells. */
  private pivotTable(): HTMLElement {
    const pk = this.st.pivot;
    const groups = this.rowGroups();
    let values = this.valueCols().map((k) => ({ k, agg: this.st.aggs[k] }));
    if (!values.length) values = [{ k: pk, agg: "count" as Agg }];
    const byLabel = new Map<string, Rec[]>();
    for (const r of this.viewRows) { const v = this.o.text(pk, r) || "—"; const l = byLabel.get(v); if (l) l.push(r); else byLabel.set(v, [r]); }
    const labels = this.ordered(pk, [...byLabel]).slice(0, PIVOT_LIMIT).map(([l]) => l);
    const many = values.length > 1;
    const vName = (v: { k: string; agg: Agg }) => (v.agg === "count" && v.k === pk ? t("Count") : `${t(AGG_LABEL[v.agg])}: ${this.label(v.k)}`);
    const corner = h("th", { class: "an-gcol", scope: "col", rowspan: many ? 2 : 1 },
      groups.length ? groups.map((g) => this.label(g)).join(" › ") : "", many ? "" : h("span", { class: "an-vname" }, vName(values[0])));
    const top = h("tr", null, corner, ...[...labels, t("Total")].map((l, i) => h("th", { class: `num ${i === labels.length ? "an-tot" : ""}`, colspan: values.length, scope: "colgroup" }, l)));
    const thead = h("thead", null, top);
    if (many) thead.append(h("tr", null, ...[...labels, ""].flatMap((_, i) => values.map((v) => h("th", { class: `num ${i === labels.length ? "an-tot" : ""}`, scope: "col" }, vName(v))))));
    const cells = (rows: Rec[]) => [
      ...labels.flatMap((l) => { const sub = rows.filter((r) => (this.o.text(pk, r) || "—") === l); return values.map((v) => this.numCell(v.k, v.agg, sub)); }),
      ...values.map((v) => { const td = this.numCell(v.k, v.agg, rows); td.classList.add("an-tot"); return td; }),
    ];
    const tbody = h("tbody");
    const walk = (nodes: GNode[]) => {
      for (const n of nodes) {
        const open = !this.st.collapsed.includes(n.path);
        const tr = h("tr", { class: `an-grp lvl${Math.min(n.depth, 3)} ${n.kids.length ? "" : "leaf"}` },
          h("td", { class: "an-gcell", style: `--d:${n.depth}` }, n.kids.length ? this.caret(n.path, open) : h("span", { class: "an-caret-sp" }), h("span", { class: "an-glabel" }, n.label), h("span", { class: "an-count" }, fmtInt(n.rows.length))),
          ...cells(n.rows));
        this.addRow(tbody, tr);
        if (open) walk(n.kids);
      }
    };
    walk(this.tree(this.viewRows, groups));
    const tfoot = h("tfoot");
    if (this.viewRows.length) this.addRow(tfoot, h("tr", null, h("td", { class: "an-gcell" }, t("Total")), ...cells(this.viewRows)));
    else tbody.append(h("tr", null, h("td", { class: "empty", colspan: 1 + (labels.length + 1) * values.length }, t("No data for these parameters."))));
    return h("table", { class: "an-grid pivot" }, thead, tbody, tfoot);
  }

  // ---------------------------------------------------------------- selection and status bar
  private onDown(e: MouseEvent) {
    const td = (e.target as HTMLElement).closest("td") as HTMLTableCellElement | null;
    if (!td || !td.dataset.ri || (e.target as HTMLElement).closest("button") || e.button !== 0) return;
    this.scroll.focus({ preventScroll: true });
    if (e.shiftKey && this.anchor) { e.preventDefault(); this.selectRect(this.anchor, td); return; }
    if (e.ctrlKey || e.metaKey) { e.preventDefault(); this.toggle(td, !this.sel.has(td)); this.anchor = td; this.updateStatus(); return; }
    this.clearSel(); this.anchor = td; this.toggle(td, true); this.dragging = true; this.updateStatus();
  }
  private toggle(td: HTMLTableCellElement, on: boolean) { td.classList.toggle("an-sel", on); if (on) this.sel.add(td); else this.sel.delete(td); }
  private clearSel() { this.sel.forEach((td) => td.classList.remove("an-sel")); this.sel.clear(); }
  private selectRect(a: HTMLTableCellElement, b: HTMLTableCellElement) {
    const [r0, r1] = [Number(a.dataset.ri), Number(b.dataset.ri)].sort((x, y) => x - y);
    const [c0, c1] = [Number(a.dataset.ci), Number(b.dataset.ci)].sort((x, y) => x - y);
    this.clearSel();
    for (let r = r0; r <= r1; r++) for (let c = c0; c <= c1; c++) { const td = this.grid[r]?.[c]; if (td) this.toggle(td, true); }
    this.updateStatus();
  }
  private updateStatus() {
    clear(this.status);
    const item = (k: string, v: string) => h("span", { class: "an-st" }, h("span", { class: "k" }, k), h("b", null, v));
    const total = this.o.rows.length, shown = this.viewRows.length;
    this.status.append(item(t("Rows"), shown === total ? fmtInt(total) : t("{0} of {1}", fmtInt(shown), fmtInt(total))));
    const nf = this.filterCount();
    if (nf) this.status.append(h("button", { class: "an-st an-clear", type: "button", onclick: () => { this.st.filters = {}; this.commit(); } }, icon("filter"), t("{0} filter(s)", nf), icon("x")));
    if (this.sel.size) {
      const nums = [...this.sel].map((td) => td.dataset.n).filter((n): n is string => n !== undefined).map(Number);
      const money = (v: number) => cellValue({ type: "money" }, v);
      this.status.append(h("span", { class: "an-sep" }), item(t("Count"), fmtInt([...this.sel].filter((td) => (td.textContent || "").trim()).length)));
      if (nums.length) {
        const sum = nums.reduce((a, b) => a + b, 0);
        this.status.append(item(t("Sum"), money(sum)), item(t("Average"), money(sum / nums.length)),
          item(t("Min"), money(Math.min(...nums))), item(t("Max"), money(Math.max(...nums))));
      }
    } else this.status.append(h("span", { class: "an-hint" }, t("Select cells to see their sum. Ctrl+C copies them.")));
  }
  private async copy() {
    const cells = [...this.sel];
    const rows = [...new Set(cells.map((c) => Number(c.dataset.ri)))].sort((a, b) => a - b);
    const cols = [...new Set(cells.map((c) => Number(c.dataset.ci)))].sort((a, b) => a - b);
    const text = rows.map((r) => cols.map((c) => { const td = this.grid[r]?.[c]; return td && this.sel.has(td) ? (td.dataset.n ?? (td.textContent || "").trim()) : ""; }).join("\t")).join("\n");
    try { await navigator.clipboard.writeText(text); } catch { /* clipboard blocked: nothing to do */ }
  }

  // ---------------------------------------------------------------- analysis pane
  private renderPane() {
    clear(this.pane);
    const nf = this.filterCount();
    const tabBtn = (id: "columns" | "filters", label: string) => h("button", { class: `an-ptab ${this.paneTab === id ? "active" : ""}`, type: "button",
      onclick: () => { this.paneTab = id; this.renderPane(); } }, label);
    this.pane.append(h("div", { class: "an-phead" }, tabBtn("columns", t("Columns")), tabBtn("filters", nf ? `${t("Filters")} (${nf})` : t("Filters"))));
    const body = h("div", { class: "an-pbody" });
    this.pane.append(body, h("div", { class: "an-pfoot" }, h("button", { class: "btn sm", type: "button", onclick: () => {
      const tab = this.saved.tabs[this.saved.active];
      tab.state = this.o.defaults(); this.st = tab.state; this.commit();
    } }, t("Reset analysis"))));
    if (this.paneTab === "columns") this.columnsPane(body); else this.filtersPane(body);
  }

  private dropZone(title: string, hint: string, chips: HTMLElement[], onDrop: (k: string) => void): HTMLElement {
    const zone = h("div", { class: "an-zone" }, h("div", { class: "an-ztitle" }, title), chips.length ? h("div", { class: "an-chips" }, ...chips) : h("div", { class: "an-zhint" }, hint));
    zone.addEventListener("dragover", (e) => { if (e.dataTransfer?.types.includes("text/plain")) { e.preventDefault(); zone.classList.add("over"); } });
    zone.addEventListener("dragleave", () => zone.classList.remove("over"));
    zone.addEventListener("drop", (e) => {
      e.preventDefault(); zone.classList.remove("over");
      const data = e.dataTransfer?.getData("text/plain") || "";
      if (data.startsWith("an-col:")) onDrop(data.slice(7));
    });
    return zone;
  }
  private chip(label: string, onRemove: () => void, extra: Node[] = []): HTMLElement {
    return h("span", { class: "an-chip" }, h("span", { class: "an-chip-l" }, label), ...extra,
      h("button", { class: "an-chip-x", type: "button", "aria-label": t("Remove"), title: t("Remove"), onclick: onRemove }, icon("x")));
  }
  private addGroup(k: string) {
    if (this.st.groups.includes(k)) return;
    this.st.groups.push(k); this.st.collapsed = [];
    if (this.st.pivot === k) this.st.pivot = "";
    this.commit();
  }

  private columnsPane(body: HTMLElement) {
    const st = this.st;
    // pivot switch
    const sw = h("input", { type: "checkbox", role: "switch" }) as HTMLInputElement;
    sw.checked = st.pivotOn;
    sw.addEventListener("change", () => { st.pivotOn = sw.checked; st.collapsed = []; this.commit(); });
    body.append(h("label", { class: "an-switch" }, sw, h("span", { class: "an-sw" }), t("Pivot mode")));

    // row groups
    const gChips = st.groups.map((k, i) => this.chip(this.label(k), () => { st.groups.splice(i, 1); st.collapsed = []; this.commit(); },
      i > 0 ? [h("button", { class: "an-chip-x", type: "button", "aria-label": t("Move up"), title: t("Move up"), onclick: () => { [st.groups[i - 1], st.groups[i]] = [st.groups[i], st.groups[i - 1]]; st.collapsed = []; this.commit(); } }, "↑")] : []));
    body.append(this.dropZone(t("Row groups"), t("Drag a column here to group by it"), gChips, (k) => this.addGroup(k)));

    // column labels (pivot)
    if (st.pivotOn) {
      const pChips = st.pivot ? [this.chip(this.label(st.pivot), () => { st.pivot = ""; this.commit(); })] : [];
      body.append(this.dropZone(t("Column labels"), t("Drag a column here to spread its values across the top"), pChips, (k) => {
        st.pivot = k; st.groups = st.groups.filter((g) => g !== k); st.collapsed = []; this.commit();
      }));
    }

    // values
    const vChips = this.valueCols().map((k) => {
      const sel = h("select", { class: "an-agg", "aria-label": t("Total by") }, ...AGGS.map((a) => h("option", { value: a, selected: st.aggs[k] === a }, t(AGG_LABEL[a])))) as HTMLSelectElement;
      sel.addEventListener("change", () => { st.aggs[k] = sel.value as Agg; this.commit(); });
      return this.chip(this.label(k), () => { st.aggs[k] = "none"; this.commit(); }, [sel]);
    });
    body.append(this.dropZone(t("Values"), t("Drag a number column here to total it"), vChips, (k) => {
      if (!this.isNum(k)) return;
      if (!st.cols.includes(k)) st.cols.push(k);
      if ((st.aggs[k] || "none") === "none") st.aggs[k] = "sum";
      this.commit();
    }));

    // the column list: show / hide, group, total
    const q = h("input", { class: "gt-input", type: "search", placeholder: t("Search columns"), "aria-label": t("Search columns"), value: this.colSearch }) as HTMLInputElement;
    const list = h("div", { class: "an-cols" });
    const fill = () => {
      clear(list);
      const term = this.colSearch.toLowerCase();
      const ordered = [...st.cols, ...this.o.columns.map((c) => c.key).filter((k) => !st.cols.includes(k))];
      for (const k of ordered) {
        if (term && !this.label(k).toLowerCase().includes(term)) continue;
        const box = h("input", { type: "checkbox", "aria-label": this.label(k) }) as HTMLInputElement;
        box.checked = st.cols.includes(k);
        box.addEventListener("change", () => {
          if (box.checked) st.cols.push(k); else if (st.cols.length > 1) st.cols = st.cols.filter((x) => x !== k); else { box.checked = true; return; }
          this.commit();
        });
        const grouped = st.groups.includes(k);
        const row = h("div", { class: "an-col", draggable: "true" },
          h("span", { class: "an-grip", "aria-hidden": "true" }, "⋮⋮"), box, h("span", { class: "an-col-l" }, this.label(k)),
          this.isNum(k) ? h("button", { class: `an-mini ${(st.aggs[k] || "none") !== "none" ? "on" : ""}`, type: "button", title: t("Total this column"), "aria-label": t("Total this column"),
            onclick: () => { st.aggs[k] = (st.aggs[k] || "none") === "none" ? "sum" : "none"; if (!st.cols.includes(k)) st.cols.push(k); this.commit(); } }, "Σ") : null,
          h("button", { class: `an-mini ${grouped ? "on" : ""}`, type: "button", title: grouped ? t("Ungroup") : t("Group by this column"), "aria-label": grouped ? t("Ungroup") : t("Group by this column"),
            onclick: () => { if (grouped) { st.groups = st.groups.filter((g) => g !== k); st.collapsed = []; this.commit(); } else this.addGroup(k); } }, icon("group")));
        row.addEventListener("dragstart", (e) => e.dataTransfer?.setData("text/plain", `an-col:${k}`));
        list.append(row);
      }
    };
    q.addEventListener("input", () => { this.colSearch = q.value; fill(); });
    fill();
    body.append(h("div", { class: "an-ztitle" }, t("Columns")), q, list);
  }

  private filtersPane(body: HTMLElement) {
    const st = this.st;
    for (const c of this.o.columns) {
      const f: Filter = st.filters[c.key] || {};
      const setF = (patch: Partial<Filter>) => {
        const nf = { ...(st.filters[c.key] || {}), ...patch };
        if (!nf.text && !nf.min && !nf.max && !(nf.values && nf.values.length)) delete st.filters[c.key]; else st.filters[c.key] = nf;
        this.save(); this.renderGrid();
        const head = this.pane.querySelectorAll(".an-ptab")[1];   // keep the "Filters (n)" count right without rebuilding the inputs
        if (head) head.textContent = this.filterCount() ? `${t("Filters")} (${this.filterCount()})` : t("Filters");
        title.classList.toggle("on", !!st.filters[c.key]);
      };
      const title = h("summary", { class: st.filters[c.key] ? "on" : "" }, t(c.label));
      const block = h("details", { class: "an-filter", open: !!st.filters[c.key] }, title);
      if (NUM.has(c.type) || c.type === "date") {
        const ph = c.type === "date" ? t("dd/mm/yyyy") : "";
        const lo = h("input", { class: "gt-input", type: c.type === "date" ? "text" : "number", step: "any", placeholder: ph || t("From"), value: f.min || "", "aria-label": `${t(c.label)} ${t("From")}` }) as HTMLInputElement;
        const hi = h("input", { class: "gt-input", type: c.type === "date" ? "text" : "number", step: "any", placeholder: ph || t("To"), value: f.max || "", "aria-label": `${t(c.label)} ${t("To")}` }) as HTMLInputElement;
        const apply = () => {
          const bad = c.type === "date" && [lo, hi].some((x) => x.value && parseDate(x.value) === null);
          lo.classList.toggle("bad", c.type === "date" && !!lo.value && parseDate(lo.value) === null);
          hi.classList.toggle("bad", c.type === "date" && !!hi.value && parseDate(hi.value) === null);
          if (!bad) setF({ min: lo.value.trim(), max: hi.value.trim() });
        };
        lo.addEventListener("change", apply); hi.addEventListener("change", apply);
        block.append(h("div", { class: "an-range" }, h("label", null, t("From"), lo), h("label", null, t("To"), hi)));
      } else {
        const distinct = [...new Set(this.o.rows.map((r) => this.o.text(c.key, r)))].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
        if (distinct.length <= 30) {
          const chosen = new Set(f.values || []);
          const list = h("div", { class: "an-vals" }, ...distinct.map((v) => {
            const box = h("input", { type: "checkbox" }) as HTMLInputElement;
            box.checked = chosen.has(v);
            box.addEventListener("change", () => { box.checked ? chosen.add(v) : chosen.delete(v); setF({ values: [...chosen] }); });
            return h("label", null, box, v || t("(blank)"));
          }));
          if (distinct.length > 6) {   // long value lists get their own search box
            const q = h("input", { class: "gt-input an-vsearch", type: "search", placeholder: t("Search…"), "aria-label": `${t(c.label)} ${t("Search")}` }) as HTMLInputElement;
            q.addEventListener("input", () => { const k = fold(q.value); list.querySelectorAll<HTMLElement>("label").forEach((l) => { l.style.display = !k || fold(l.textContent || "").includes(k) ? "" : "none"; }); });
            block.append(q);
          }
          block.append(list);
        } else {
          const inp = h("input", { class: "gt-input", type: "search", placeholder: t("Contains…"), value: f.text || "", "aria-label": t(c.label) }) as HTMLInputElement;
          inp.addEventListener("input", () => setF({ text: inp.value.trim() }));
          block.append(inp);
        }
      }
      body.append(block);
    }
    if (this.filterCount()) body.append(h("button", { class: "btn sm an-clearall", type: "button", onclick: () => { st.filters = {}; this.commit(); } }, t("Clear all filters")));
  }

  // ---------------------------------------------------------------- export
  /** What is on screen (groups, subtotals, pivot) as CSV for Excel. */
  exportCsv(name: string) {
    const table = this.scroll.querySelector("table");
    if (!table) return;
    const lines: string[] = [];
    // header rows, colspans repeated so every column has its full name
    const heads = [...table.tHead!.rows].map((tr) => {
      const out: string[] = [];
      for (const th of [...tr.cells]) for (let i = 0; i < th.colSpan; i++) out.push((th.textContent || "").replace(/[▲▼]/g, "").trim());
      return out;
    });
    if (heads.length === 2) heads[1].unshift("");   // the corner cell spans both rows
    const width = Math.max(...heads.map((r) => r.length));
    lines.push(Array.from({ length: width }, (_, i) => csvText(heads.map((r) => r[i] || "").filter(Boolean).join(" - "))).join(","));
    for (const sec of [table.tBodies[0], table.tFoot]) {
      for (const tr of [...(sec?.rows || [])]) {
        if (tr.querySelector(".empty, .an-more")) continue;
        lines.push([...tr.cells].map((td) => {
          if (td.dataset.n !== undefined) return td.dataset.n;
          const lbl = td.querySelector(".an-glabel");
          return csvText(lbl ? `${"  ".repeat(Number(getComputedStyle(td).getPropertyValue("--d")) || 0)}${lbl.textContent}` : (td.textContent || "").trim());
        }).join(","));
      }
    }
    downloadCsv(name, lines.join("\r\n"));
  }
}
