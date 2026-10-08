import { api } from "../../core/api.js";
import { t } from "../../core/i18n.js";
import { clear, fmtDate, fmtMoney, fmtInt, fail, h, icon, page, pill } from "../../ui/index.js";
export async function dashboardPage(root) {
    const view = h("div", { class: "loading" }, t("Loading…"));
    root.append(view);
    let d;
    try {
        d = await api.get("/api/dashboard");
    }
    catch (e) {
        clear(root);
        // a role without asset access still gets a home page instead of a spinner and an error
        root.append(page({ title: t("Fixed assets"), subtitle: t("Workspace") }, h("div", { class: "msgbar" }, t("Welcome. Use the menu on the side to open the pages you have access to."))).el);
        if (!(e instanceof Error && /permission/i.test(e.message)))
            fail(e);
        return;
    }
    const cur = d.currency;
    // Workspace tile: icon, label, big number (+ unit), a caption and an optional progress bar
    const tile = (o) => h("a", { class: `tile2 tone-${o.tone}`, href: o.href }, h("div", { class: "t-body" }, h("div", { class: "t-lbl" }, o.label), h("div", { class: "t-val" }, o.value, o.unit ? h("small", null, ` ${o.unit}`) : null), o.bar !== undefined ? h("div", { class: "t-bar", role: "img", "aria-label": `${Math.round(o.bar)}%` }, h("i", { style: `width:${Math.max(0, Math.min(100, o.bar))}%` })) : null, h("div", { class: "t-cap" }, o.caption ?? "\u00a0")));
    const pctDep = d.cost > 0 ? (d.accum_dep / d.cost) * 100 : 0;
    const tiles = h("div", { class: "tiles2" }, tile({ label: t("Active fixed assets"), value: fmtInt(d.asset_count), icon: "asset", tone: "blue", href: "#/assets", caption: t("{0} groups", d.by_category.length) }), tile({ label: t("Acquisition cost"), value: fmtMoney(d.cost), unit: cur, icon: "list", tone: "teal", href: "#/reports/asset-summary", caption: t("Net of VAT") }), tile({ label: t("Accumulated depreciation"), value: fmtMoney(d.accum_dep), unit: cur, icon: "calc", tone: "gray", href: "#/reports/depreciation-schedule", bar: pctDep, caption: t("{0}% of cost", Math.round(pctDep)) }), tile({ label: t("Net book value"), value: fmtMoney(d.nbv), unit: cur, icon: "journal", tone: "green", href: "#/reports/asset-register", bar: 100 - pctDep, caption: t("{0}% of cost", Math.round(d.cost > 0 ? 100 - pctDep : 0)) }), tile({ label: t("Open maintenance orders"), value: fmtInt(d.maint_open), icon: "wrench", tone: d.maint_overdue ? "amber" : "gray", href: "#/maintenance", caption: d.maint_overdue ? t("{0} overdue", d.maint_overdue) : t("None overdue") }), tile({ label: t("Assets in employee custody"), value: fmtInt(d.custody_held), icon: "user", tone: "purple", href: "#/custody", caption: t("Not part of asset reports") }));
    // by group bars
    const max = Math.max(1, ...d.by_category.map((c) => c.cost));
    const groups = d.by_category.length
        ? h("div", null, h("div", { class: "legend" }, h("span", null, h("i", { style: "background:var(--bar2)" }), t("Acquisition cost")), h("span", null, h("i", { style: "background:var(--blue)" }), t("Net book value"))), ...d.by_category.map((c) => h("div", { class: "bar-row" }, h("span", { class: "name", title: c.name }, c.name), h("div", { class: "track" }, h("div", { class: "fill2", style: `width:${(c.cost / max) * 100}%` }), h("div", { class: "fill", style: `width:${(c.nbv / max) * 100}%;position:relative` })), h("span", { class: "amt" }, fmtMoney(c.nbv)))))
        : h("div", { class: "empty" }, t("No fixed assets yet."));
    // depreciation trend (SVG columns)
    const trend = d.dep_trend;
    let trendEl;
    if (!trend.length)
        trendEl = h("div", { class: "empty" }, t("No depreciation has been posted yet."));
    else {
        const tm = Math.max(1, ...trend.map((x) => x.amt));
        const W = 460, H = 150, bw = Math.min(36, (W - 20) / trend.length - 6);
        const NS = "http://www.w3.org/2000/svg";
        const el = (tag, attrs, text) => {
            const n = document.createElementNS(NS, tag);
            for (const [k, v] of Object.entries(attrs))
                n.setAttribute(k, v);
            if (text !== undefined)
                n.textContent = text;
            return n;
        };
        const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%", role: "img", "aria-label": t("Posted depreciation by period") });
        trend.forEach((x, i) => {
            const bh = Math.max(2, (x.amt / tm) * (H - 34));
            const bx = 10 + i * ((W - 20) / trend.length) + 3;
            const rect = el("rect", { x: String(bx), y: String(H - 18 - bh), width: String(bw), height: String(bh), fill: "var(--blue)" });
            rect.append(el("title", {}, `${x.name}: ${fmtMoney(x.amt)}`));
            svg.append(rect, el("text", { x: String(bx + bw / 2), y: String(H - 4), "font-size": "10", "text-anchor": "middle", fill: "var(--ink-2)" }, String(x.name).slice(0, 3)));
        });
        trendEl = h("div", null, svg);
    }
    // periods to process
    // every line is a way in: the chevron says so, and the button runs the next step
    const go = (href, label, value) => h("a", { href, class: "todo-go" }, h("span", null, label), h("span", { class: "tv" }, value, icon("chevron")));
    const todo = h("div", { class: "mini-list todo" });
    if (d.next_period)
        todo.append(go(`#/depreciation?period=${d.next_period.PeriodID}`, t("Next period to depreciate"), h("b", null, d.next_period.PeriodName)));
    else
        todo.append(h("div", { class: "row" }, h("span", null, t("Next period to depreciate")), h("b", null, "—")));
    todo.append(go("#/depreciation", t("Unposted depreciation lines"), h("b", { class: d.draft_lines ? "neg" : "" }, fmtInt(d.draft_lines))));
    if (d.current_period)
        todo.append(go("#/periods", t("Current period"), h("span", null, d.current_period.PeriodName, " ", pill(d.current_period.PeriodStatus))));
    if (d.next_period || d.draft_lines) {
        const next = d.draft_lines ? t("Review and post depreciation") : t("Run depreciation for {0}", d.next_period.PeriodName);
        todo.append(h("div", { class: "todo-cta" }, h("a", { class: "btn primary", href: d.next_period ? `#/depreciation?period=${d.next_period.PeriodID}` : "#/depreciation" }, next)));
    }
    const warr = d.warranty.length
        ? h("div", { class: "mini-list" }, ...d.warranty.map((w) => h("a", { href: `#/assets/${w.AssetID}` }, h("span", null, `${w.AssetCode} · ${w.AssetName}`), h("span", null, fmtDate(w.WarrantyExpiryDate)))))
        : h("div", { class: "empty" }, t("No warranties expiring in the next 90 days."));
    const maint = d.maint_due.length
        ? h("div", { class: "mini-list" }, ...d.maint_due.map((m) => h("a", { href: `#/maintenance/${m.MaintenanceID}` }, h("span", null, pill(m.Status), " ", `${m.AssetCode} · ${m.Title}`), h("span", { class: m.IsOverdue ? "neg" : "" }, fmtDate(m.ScheduledDate)))))
        : h("div", { class: "empty" }, t("No open maintenance orders."));
    const recent = d.recent.length
        ? h("div", { class: "mini-list" }, ...d.recent.map((r) => h("a", { href: `#/assets/${r.AssetID}` }, h("span", null, pill(r.TransactionType), " ", `${r.AssetCode} · ${r.AssetName}`), h("span", null, fmtDate(r.TransactionDate)))))
        : h("div", { class: "empty" }, t("No transactions yet."));
    const card = (title, body, more, span = 4) => h("div", { class: `card span-${span}` }, h("h3", null, h("span", null, title), more ? h("a", { href: more[1], style: "font-size:12px;font-weight:400" }, more[0]) : null), h("div", { class: "card-body" }, body));
    const pg = page({ title: t("Fixed assets"), subtitle: t("Workspace") }, tiles, h("div", { class: "dash" }, card(t("Net book value by group"), groups, [t("Open register"), "#/reports/asset-register"], 7), card(t("Depreciation posted by period"), trendEl, [t("Schedule"), "#/reports/depreciation-schedule"], 5), card(t("To do"), todo, undefined, 4), card(t("Maintenance due"), maint, [t("All"), "#/maintenance"], 4), card(t("Warranties expiring soon"), warr, undefined, 4), card(t("Recent transactions"), recent, [t("All"), "#/transactions"], 12)));
    clear(root);
    root.append(pg.el);
}
