import { api } from "../api.js";
import { t } from "../i18n.js";
import type { Rec } from "../types.js";
import { clear, fmtMoney, fmtInt, fail, h, icon, page, pill } from "../ui.js";

export async function dashboardPage(root: HTMLElement): Promise<void> {
  const view = h("div", { class: "loading" }, t("Loading…"));
  root.append(view);
  let d: Rec;
  try { d = await api.get("/api/dashboard"); } catch (e) { fail(e); return; }
  const cur = d.currency;
  const tile = (label: string, value: string, cls = "", href?: string, sub?: string) =>
    h("div", { class: `tile ${cls} ${href ? "link" : ""}`, onclick: href ? () => (location.hash = href) : undefined },
      h("div", { class: "lbl" }, label), h("div", { class: "val" }, value, " ", sub ? h("small", null, sub) : null));

  const tiles = h("div", { class: "tiles" },
    tile(t("Active fixed assets"), fmtInt(d.asset_count), "", "#/assets"),
    tile(t("Acquisition cost"), fmtMoney(d.cost), "", "#/reports/asset-summary", cur),
    tile(t("Accumulated depreciation"), fmtMoney(d.accum_dep), "gray", "#/reports/depreciation-schedule", cur),
    tile(t("Net book value"), fmtMoney(d.nbv), "ok", "#/reports/asset-register", cur),
    tile(t("Open maintenance orders"), fmtInt(d.maint_open), d.maint_overdue ? "warn" : "gray", "#/maintenance", d.maint_overdue ? t("{0} overdue", d.maint_overdue) : undefined));

  // by group bars
  const max = Math.max(1, ...d.by_category.map((c: Rec) => c.cost));
  const groups = d.by_category.length
    ? h("div", null,
        h("div", { class: "legend" }, h("span", null, h("i", { style: "background:#9cc8ec" }), t("Acquisition cost")), h("span", null, h("i", { style: "background:var(--blue)" }), t("Net book value"))),
        ...d.by_category.map((c: Rec) => h("div", { class: "bar-row" }, h("span", { class: "name", title: c.name }, c.name),
          h("div", { class: "track" }, h("div", { class: "fill2", style: `width:${(c.cost / max) * 100}%` }), h("div", { class: "fill", style: `width:${(c.nbv / max) * 100}%;position:relative` })),
          h("span", { class: "amt" }, fmtMoney(c.nbv)))))
    : h("div", { class: "empty" }, t("No fixed assets yet."));

  // depreciation trend (SVG columns)
  const trend = d.dep_trend as Rec[];
  let trendEl: HTMLElement;
  if (!trend.length) trendEl = h("div", { class: "empty" }, t("No depreciation has been posted yet."));
  else {
    const tm = Math.max(1, ...trend.map((x) => x.amt));
    const W = 460, H = 150, bw = Math.min(36, (W - 20) / trend.length - 6);
    const bars = trend.map((x, i) => {
      const bh = Math.max(2, (x.amt / tm) * (H - 34)); const bx = 10 + i * ((W - 20) / trend.length) + 3;
      return `<g><rect x="${bx}" y="${H - 18 - bh}" width="${bw}" height="${bh}" fill="var(--blue)"><title>${x.name}: ${fmtMoney(x.amt)}</title></rect>
        <text x="${bx + bw / 2}" y="${H - 4}" font-size="10" text-anchor="middle" fill="var(--ink-2)">${String(x.name).slice(0, 3)}</text></g>`;
    }).join("");
    trendEl = h("div", null);
    trendEl.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${t("Posted depreciation by period")}">${bars}</svg>`;
  }

  // periods to process
  const todo = h("div", { class: "mini-list" });
  if (d.next_period) todo.append(h("a", { href: `#/depreciation?period=${d.next_period.PeriodID}` }, h("span", null, t("Next period to depreciate")), h("b", null, d.next_period.PeriodName)));
  else todo.append(h("div", { class: "row" }, h("span", null, t("Next period to depreciate")), h("b", null, "—")));
  todo.append(h("a", { href: "#/depreciation" }, h("span", null, t("Unposted depreciation lines")), h("b", null, fmtInt(d.draft_lines))));
  if (d.current_period) todo.append(h("div", { class: "row" }, h("span", null, t("Current period")), h("span", null, d.current_period.PeriodName, " ", pill(d.current_period.PeriodStatus))));

  const warr = d.warranty.length
    ? h("div", { class: "mini-list" }, ...d.warranty.map((w: Rec) => h("a", { href: `#/assets/${w.AssetID}` }, h("span", null, `${w.AssetCode} · ${w.AssetName}`), h("span", null, w.WarrantyExpiryDate))))
    : h("div", { class: "empty" }, t("No warranties expiring in the next 90 days."));

  const maint = d.maint_due.length
    ? h("div", { class: "mini-list" }, ...d.maint_due.map((m: Rec) => h("a", { href: `#/maintenance/${m.MaintenanceID}` },
        h("span", null, pill(m.Status), " ", `${m.AssetCode} · ${m.Title}`), h("span", { class: m.IsOverdue ? "neg" : "" }, m.ScheduledDate))))
    : h("div", { class: "empty" }, t("No open maintenance orders."));

  const recent = d.recent.length
    ? h("div", { class: "mini-list" }, ...d.recent.map((r: Rec) => h("a", { href: `#/assets/${r.AssetID}` },
        h("span", null, pill(r.TransactionType), " ", `${r.AssetCode} · ${r.AssetName}`), h("span", null, r.TransactionDate))))
    : h("div", { class: "empty" }, t("No transactions yet."));

  const card = (title: string, body: Node, more?: [string, string], span = 4) =>
    h("div", { class: `card span-${span}` }, h("h3", null, h("span", null, title), more ? h("a", { href: more[1], style: "font-size:12px;font-weight:400" }, more[0]) : null), h("div", { class: "card-body" }, body));

  const pg = page({ title: t("Fixed assets"), subtitle: t("Workspace") },
    tiles,
    h("div", { class: "dash" },
      card(t("Net book value by group"), groups, [t("Open register"), "#/reports/asset-register"], 7),
      card(t("Depreciation posted by period"), trendEl, [t("Schedule"), "#/reports/depreciation-schedule"], 5),
      card(t("To do"), todo, undefined, 4),
      card(t("Maintenance due"), maint, [t("All"), "#/maintenance"], 4),
      card(t("Warranties expiring soon"), warr, undefined, 4),
      card(t("Recent transactions"), recent, [t("All"), "#/transactions"], 12)));
  clear(root); root.append(pg.el);
  void icon;
}
