/** Dashboard: charts pinned from the analysis of any report, each live on today's data. A click opens the analysis behind it. */
import { api } from "../../core/api.js";
import { t } from "../../core/i18n.js";
import type { Rec, ReportResult } from "../../core/types.js";
import { AState, AnalysisModel, clear, drawChart, h, icon, openAnalysisTab, page, ribbon } from "../../ui/index.js";
import { REPORT_INFO, analysisOpts } from "./reports.js";

export interface Pin { uid: string; title: string; report: string; params: Record<string, string>; state: Partial<AState>; }
const KEY = "usool.dashboard.pins";

const chart = (type: string, measure: string) => ({ on: true, type, measure }) as AState["chart"];
/** What a new dashboard starts with: the questions an asset accountant asks first. */
function defaultPins(): Pin[] {
  return [
    { uid: "d1", title: t("Net book value by group"), report: "asset-register", params: {}, state: { groups: ["CategoryName"], chart: chart("auto", "NBV") } },
    { uid: "d2", title: t("Depreciation by period"), report: "depreciation-schedule", params: {}, state: { groups: ["PeriodName"], chart: chart("auto", "PeriodDepreciation") } },
    { uid: "d3", title: t("Depreciation by period and group"), report: "depreciation-schedule", params: {},
      state: { groups: ["PeriodName"], pivotOn: true, pivot: "CategoryName", chart: chart("stacked", "PeriodDepreciation") } },
    { uid: "d4", title: t("Cost by location"), report: "asset-register", params: {}, state: { groups: ["LocationName"], chart: chart("bar", "Cost") } },
    { uid: "d5", title: t("Assets with and without VAT"), report: "asset-register", params: {}, state: { groups: ["VatStatus"], chart: chart("donut", "Cost") } },
    { uid: "d6", title: t("Maintenance cost by type"), report: "maintenance-history", params: {}, state: { groups: ["MaintenanceType"], chart: chart("column", "Cost") } },
  ];
}
function loadPins(): Pin[] {
  try { const v = JSON.parse(localStorage.getItem(KEY) || "null"); if (Array.isArray(v)) return v; } catch { /* ignore */ }
  return defaultPins();
}
function savePins(p: Pin[]): void { try { localStorage.setItem(KEY, JSON.stringify(p)); } catch { /* ignore */ } }
export function addPin(p: Omit<Pin, "uid">): void { savePins([...loadPins(), { ...p, uid: `p${Date.now().toString(36)}` }]); }

export async function chartsDashboardPage(root: HTMLElement): Promise<void> {
  const allowed: Rec[] = await api.get("/api/reports");
  let pins = loadPins();
  const rerender = () => void chartsDashboardPage(root);
  const rb = ribbon([[{ label: t("Refresh"), icon: "refresh", onClick: rerender },
    { label: t("Restore default charts"), icon: "back", onClick: () => { savePins(defaultPins()); rerender(); } }]]);
  const grid = h("div", { class: "dash-charts" });
  const visible = pins.filter((p) => allowed.some((r) => r.id === p.report));   // charts of reports this user may not run are skipped
  const body = visible.length ? grid : h("div", { class: "msgbar" }, t("No charts yet. Open a report, choose Analyze, then Chart, and pin it to the dashboard."));
  clear(root);
  root.append(page({ title: t("Dashboard"), subtitle: t("Reports"), ribbon: rb.el },
    h("div", { class: "dash-hint" }, t("Charts follow today's data. Click a chart to open its analysis; pin more from any report.")), body).el);

  const cache = new Map<string, Promise<ReportResult>>();   // one request per report and parameters
  const fetchReport = (p: Pin) => {
    const qs = new URLSearchParams(p.params).toString();
    const k = `${p.report}?${qs}`;
    if (!cache.has(k)) cache.set(k, api.get<ReportResult>(`/api/reports/${p.report}${qs ? `?${qs}` : ""}`));
    return cache.get(k)!;
  };
  for (const p of visible) {
    const host = h("div", { class: "dash-host" }, h("div", { class: "loading" }, t("Loading…")));
    const open = h("button", { class: "an-chip-x dash-act", type: "button", title: t("Open in analysis"), "aria-label": t("Open in analysis") }, icon("columns"));
    const remove = h("button", { class: "an-chip-x dash-act", type: "button", title: t("Remove from dashboard"), "aria-label": t("Remove from dashboard"),
      onclick: () => { pins = pins.filter((x) => x.uid !== p.uid); savePins(pins); rerender(); } }, icon("x"));
    grid.append(h("section", { class: "card dash-card" },
      h("h3", null, h("span", null, p.title, h("small", null, t(REPORT_INFO[p.report]?.title || p.report))), h("span", { class: "dash-acts" }, open, remove)), host));
    fetchReport(p).then((res) => {
      const opts = analysisOpts(res);
      const st: AState = { ...opts.defaults(), ...p.state, filters: { ...(p.state.filters || {}) } } as AState;
      st.chart = { on: true, type: st.chart?.type || "auto", measure: st.chart?.measure || "" };
      const model = new AnalysisModel(opts, st);
      const data = model.chartData(st.chart, model.view());
      const go = () => {
        openAnalysisTab(p.report, p.title, st);
        location.hash = `#/reports/${p.report}?${new URLSearchParams(p.params)}`;   // parameters not pinned take their defaults (today ...)
      };
      open.addEventListener("click", go);
      clear(host);
      if (!data.spec) { host.append(h("div", { class: "viz-empty" }, data.empty || t("No data for these parameters."))); return; }
      const draw = () => drawChart(host, { ...data.spec!, height: 230, onPick: go });
      draw();
      let w = host.clientWidth;
      new ResizeObserver(() => { if (Math.abs(host.clientWidth - w) > 4) { w = host.clientWidth; draw(); } }).observe(host);
    }).catch((e) => { clear(host); host.append(h("div", { class: "msgbar err" }, e instanceof Error ? t(e.message) : String(e))); });
  }
}
