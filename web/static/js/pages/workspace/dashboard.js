/** Workspace: the hub of the system - what needs doing now, where the month-end stands, and one click to every module.
 *  Numbers and lists only (charts live on the Dashboard). Every figure opens the list behind it. */
import { api, lookups } from "../../core/api.js";
import { getLang, t } from "../../core/i18n.js";
import { can, getMe, userTitle } from "../../core/session.js";
import { groupSlug } from "../reports/reports.js";
import { issueDialog } from "../contacts/custody.js";
import { reportGroups } from "../../shell/nav.js";
import { NAV, permFor } from "../../shell/routes.js";
import { clear, fail, fmtDate, fmtInt, fmtMoney, h, icon, nm, page, pill } from "../../ui/index.js";
const greeting = () => { const hr = new Date().getHours(); return hr < 12 ? t("Good morning, {0}") : hr < 17 ? t("Good afternoon, {0}") : t("Good evening, {0}"); };
const longDate = () => new Intl.DateTimeFormat(getLang() === "ar" ? "ar-SA-u-ca-gregory-nu-latn" : "en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(new Date());
export async function dashboardPage(root) {
    root.append(h("div", { class: "loading" }, t("Loading…")));
    const me = getMe();
    const head = (extra) => h("div", { class: "ws-hello" }, h("div", null, h("h2", null, greeting().replace("{0}", userTitle(me) || "")), h("div", { class: "ws-date" }, longDate(), extra || null)));
    let d;
    try {
        d = await api.get("/api/dashboard");
    }
    catch (e) {
        // a role without asset access still gets a home page: the greeting and the way to its own pages
        clear(root);
        root.append(page({ title: t("Workspace"), subtitle: t("Fixed assets") }, head(), h("div", { class: "ws-grid" }, h("div", null, h("div", { class: "msgbar" }, t("Welcome. Use the menu on the side to open the pages you have access to."))), linksPanel())).el);
        if (!(e instanceof Error && /permission/i.test(e.message)))
            fail(e);
        return;
    }
    const cur = d.currency;
    const cyc = d.cycle;
    // ---- quick actions: the things people start from here
    const L = can("custody.manage") ? await lookups().catch(() => null) : null;
    const act = (label, ic, perm, go, primary = false) => can(perm)
        ? h(typeof go === "string" ? "a" : "button", { class: `btn ws-act ${primary ? "primary" : ""}`, ...(typeof go === "string" ? { href: go } : { type: "button", onclick: go }) }, icon(ic), h("span", null, label))
        : null;
    const actions = h("div", { class: "ws-actions" }, act(t("New fixed asset"), "plus", "assets.edit", "#/assets/new", true), act(cyc.period ? t("Run depreciation for {0}", cyc.period.PeriodName) : t("Depreciation run"), "calc", "depreciation.run", cyc.period ? `#/depreciation?period=${cyc.period.PeriodID}` : "#/depreciation"), act(t("New maintenance order"), "wrench", "maintenance.edit", "#/maintenance/new"), L ? act(t("Issue to employee"), "user", "custody.manage", () => void issueDialog(L, {}, (c) => (location.hash = `#/custody/${c.CustodyID}`))) : null, act(t("Reports"), "report", "reports.view", "#/reports"));
    // ---- tiles: one number, one place to go
    const tile = (o) => can(o.perm) ? h("a", { class: `tile2 ws-tile tone-${o.tone} ${o.alert ? "alert" : ""}`, href: o.href }, h("div", { class: "t-body" }, h("div", { class: "t-lbl" }, o.label), h("div", { class: "t-val" }, o.value, o.unit ? h("small", null, ` ${o.unit}`) : null), h("div", { class: "t-cap" }, o.caption ?? " ")), h("span", { class: "t-go", "aria-hidden": "true" }, icon("chevron"))) : null;
    const tiles = h("div", { class: "tiles2 ws-tiles" }, tile({ label: t("Active fixed assets"), value: fmtInt(d.asset_count), tone: "blue", href: "#/assets", caption: t("{0} groups", d.by_category.length) }), tile({ label: t("Net book value"), value: fmtMoney(d.nbv), unit: cur, tone: "green", href: "#/reports/asset-register",
        caption: `${t("Cost")} ${fmtMoney(d.cost)} · ${t("Accum. dep.")} ${fmtMoney(d.accum_dep)}` }), tile({ label: t("Unposted depreciation lines"), value: fmtInt(d.draft_lines), tone: d.draft_lines ? "amber" : "gray", href: "#/depreciation", perm: "depreciation.view",
        caption: d.draft_lines ? t("Review and post") : t("Nothing waiting"), alert: !!d.draft_lines }), d.maint_open !== null ? tile({ label: t("Open maintenance orders"), value: fmtInt(d.maint_open), tone: d.maint_overdue ? "amber" : "gray", href: "#/maintenance?status=Open",
        caption: d.maint_overdue ? t("{0} overdue", d.maint_overdue) : t("None overdue"), alert: !!d.maint_overdue }) : null, d.custody_held !== null ? tile({ label: t("Assets in employee custody"), value: fmtInt(d.custody_held), tone: "purple", href: "#/custody?status=Issued",
        caption: d.custody_unsigned ? t("{0} without a signed form", d.custody_unsigned) : t("All forms signed") }) : null, tile({ label: t("Under repair"), value: fmtInt(d.under_repair), tone: d.under_repair ? "amber" : "gray", href: "#/assets?status=Under%20Repair", caption: t("Out of service") }));
    // ---- needs attention: everything that has a next step, most urgent first
    const items = [];
    if (cyc.behind > 1)
        items.push({ tone: "err", text: t("Depreciation is {0} months behind", cyc.behind), detail: t("Next: {0}", cyc.period.PeriodName), href: `#/depreciation?period=${cyc.period.PeriodID}`, action: t("Run"), perm: "depreciation.run" });
    if (d.draft_lines)
        items.push({ tone: "warn", text: t("{0} depreciation line(s) waiting to be posted", d.draft_lines), href: "#/depreciation", action: t("Review"), perm: "depreciation.post" });
    if (d.maint_overdue)
        items.push({ tone: "err", text: t("{0} maintenance order(s) overdue", d.maint_overdue), href: "#/maintenance?status=Open", action: t("Open"), perm: "maintenance.view" });
    for (const a of d.missing_opening)
        items.push({ tone: "warn", text: t("{0}: enter the opening accumulated depreciation", `${a.AssetCode} · ${nm(a, "AssetName")}`), detail: t("Started before the first period"), href: `#/assets/${a.AssetID}`, action: t("Fix"), perm: "assets.edit" });
    if (cyc.closable.length)
        items.push({ tone: "info", text: t("{0} period(s) fully posted and ready to close", cyc.closable.length), detail: cyc.closable.map((p) => p.PeriodName).join(", "), href: "#/periods", action: t("Close"), perm: "periods.manage" });
    if (d.custody_unsigned)
        items.push({ tone: "info", text: t("{0} custody record(s) without a signed form", d.custody_unsigned), href: "#/custody?status=Issued", action: t("Attach"), perm: "custody.manage" });
    const soon = d.warranty.filter((w) => w.WarrantyExpiryDate <= new Date(Date.now() + 30 * 864e5).toISOString().slice(0, 10));
    if (soon.length)
        items.push({ tone: "info", text: t("{0} warranty(ies) expire within 30 days", soon.length), detail: soon.map((w) => w.AssetCode).join(", "), href: "#/reports/warranty-expiry", action: t("View"), perm: "reports.view" });
    if (d.no_location)
        items.push({ tone: "info", text: t("{0} asset(s) without a location", d.no_location), href: "#/assets", action: t("Open"), perm: "assets.view" });
    const mine = items.filter((i) => can(i.perm));
    const toneIcon = { err: "warn", warn: "warn", info: "list", ok: "check" };
    const attention = mine.length
        ? h("div", { class: "ws-list" }, ...mine.map((i) => h("a", { class: `ws-row tone-${i.tone}`, href: i.href }, h("span", { class: "ws-dot" }, icon(toneIcon[i.tone])), h("span", { class: "ws-main" }, h("b", null, i.text), i.detail ? h("small", null, i.detail) : null), h("span", { class: "ws-go" }, i.action, icon("chevron")))))
        : h("div", { class: "ws-clear" }, icon("check"), h("div", null, h("b", null, t("All clear")), h("div", null, t("Nothing needs your attention right now."))));
    // ---- the other lists, as tabs (Dynamics workspace style)
    const row = (href, main, sub, right, cls = "") => h("a", { class: `ws-row ${cls}`, href }, h("span", { class: "ws-main" }, h("b", null, main), sub ? h("small", null, sub) : null), h("span", { class: "ws-meta" }, right));
    const empty = (text) => h("div", { class: "empty" }, text);
    const tabs = [
        { id: "attention", label: t("Needs attention"), count: mine.length, body: () => attention },
        { id: "maint", label: t("Maintenance due"), count: d.maint_due.length, perm: "maintenance.view", body: () => d.maint_due.length
                ? h("div", { class: "ws-list" }, ...d.maint_due.map((m) => row(`#/maintenance/${m.MaintenanceID}`, `${m.MaintenanceNo} · ${m.Title}`, `${m.AssetCode} · ${nm(m, "AssetName")}`, h("span", null, pill(m.Status), " ", h("span", { class: m.IsOverdue ? "neg" : "" }, fmtDate(m.ScheduledDate))))))
                : empty(t("No open maintenance orders.")) },
        { id: "warranty", label: t("Warranties"), count: d.warranty.length, body: () => d.warranty.length
                ? h("div", { class: "ws-list" }, ...d.warranty.map((w) => row(`#/assets/${w.AssetID}`, `${w.AssetCode} · ${nm(w, "AssetName")}`, "", fmtDate(w.WarrantyExpiryDate))))
                : empty(t("No warranties expiring in the next 90 days.")) },
        { id: "custody", label: t("In custody"), count: d.custody_list.length, perm: "custody.view", body: () => d.custody_list.length
                ? h("div", { class: "ws-list" }, ...d.custody_list.map((c) => row(`#/custody/${c.CustodyID}`, `${c.AssetCode} · ${nm(c, "AssetName")}`, `${c.CustodyNo} · ${nm(c, "EmployeeName")}`, h("span", null, c.AttachmentCount ? pill("Attached", "ok") : pill("Missing", "warn"), " ", fmtDate(c.IssueDate)))))
                : empty(t("No assets are in custody.")) },
        { id: "recent", label: t("Recent activity"), body: () => d.recent.length
                ? h("div", { class: "ws-list" }, ...d.recent.map((r) => row(`#/assets/${r.AssetID}`, `${r.AssetCode} · ${nm(r, "AssetName")}`, r.CreatedBy ? t("by {0}", r.CreatedBy) : "", h("span", null, pill(r.TransactionType), " ", fmtDate(r.TransactionDate)))))
                : empty(t("No transactions yet.")) },
    ].filter((x) => can(x.perm));
    const tabKey = "usool.ws.tab";
    let active = (() => { try {
        return localStorage.getItem(tabKey) || "attention";
    }
    catch {
        return "attention";
    } })();
    if (!tabs.some((x) => x.id === active))
        active = "attention";
    const strip = h("div", { class: "ws-tabs", role: "tablist" });
    const panel = h("div", { class: "ws-panel", role: "tabpanel" });
    const show = (id) => {
        active = id;
        try {
            localStorage.setItem(tabKey, id);
        }
        catch { /* ignore */ }
        clear(strip);
        for (const x of tabs)
            strip.append(h("button", { class: `ws-tab ${x.id === id ? "active" : ""}`, type: "button", role: "tab", "aria-selected": String(x.id === id), onclick: () => show(x.id) }, x.label, x.count ? h("span", { class: `ws-badge ${x.id === "attention" ? "hot" : ""}` }, fmtInt(x.count)) : null));
        clear(panel);
        panel.append(tabs.find((x) => x.id === id).body());
    };
    show(active);
    // ---- month-end: the depreciation cycle as three steps
    const step = (state, title, sub, href, perm) => h("li", { class: `ws-step ${state}` }, h("span", { class: "ws-sn" }, state === "done" ? icon("check") : ""), h("div", null, href && state === "now" && can(perm) ? h("a", { href }, title) : h("b", null, title), h("small", null, sub)));
    const p = cyc.period;
    const cycle = h("ol", { class: "ws-steps" }, p ? step(cyc.drafts ? "done" : "now", t("Create the proposal for {0}", p.PeriodName), cyc.drafts ? t("{0} line(s) proposed", cyc.drafts) : t("Calculates the month's depreciation"), `#/depreciation?period=${p.PeriodID}`, "depreciation.run")
        : step("done", t("Depreciation is up to date"), t("Every open period is posted")), p ? step(cyc.drafts ? "now" : "todo", t("Review and post"), t("Writes the journal: expense / accumulated depreciation"), `#/depreciation?period=${p.PeriodID}`, "depreciation.post") : null, step(cyc.closable.length ? "now" : "done", t("Close posted periods"), cyc.closable.length ? cyc.closable.map((x) => x.PeriodName).join(", ") : t("Nothing to close"), "#/periods", "periods.manage"));
    const curP = d.current_period;
    const card = (title, body, more) => h("section", { class: "card ws-card" }, h("h3", null, h("span", null, title), more ? h("a", { href: more[1], class: "ws-more" }, more[0]) : null), h("div", { class: "card-body" }, body));
    const pg = page({ title: t("Workspace"), subtitle: t("Fixed assets") }, h("div", { class: "ws-top" }, head(curP ? h("span", { class: "ws-period" }, ` · ${t("Current period")} ${curP.PeriodName} `, pill(curP.PeriodStatus)) : null), actions), tiles, h("div", { class: "ws-grid" }, h("section", { class: "card ws-card ws-center" }, strip, panel), h("div", { class: "ws-side" }, can("depreciation.view") ? card(t("Month-end"), cycle, [t("Periods"), "#/periods"]) : null, linksPanel())));
    clear(root);
    root.append(pg.el);
}
/** Every module in one place, as the menu has it, for the pages this user may open. */
function linksPanel() {
    const groups = NAV.filter((s) => s.id !== "assets").map((s) => {
        const items = s.items.filter((i) => can(permFor(i.href))).map((i) => h("a", { href: i.href, class: "ws-link" }, icon(i.icon), t(i.label)));
        if (s.reports && can("reports.view"))
            items.push(...reportGroups.map((g) => h("a", { href: `#/reports/g/${groupSlug(g.group)}`, class: "ws-link" }, icon("report"), t(g.group))));
        return items.length ? h("div", { class: "ws-lgroup" }, h("div", { class: "ws-lhead" }, t(s.section)), ...items) : null;
    }).filter(Boolean);
    return h("section", { class: "card ws-card" }, h("h3", null, h("span", null, t("Links"))), h("div", { class: "card-body ws-links" }, ...groups));
}
