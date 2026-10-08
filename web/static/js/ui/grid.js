/** The data grid (sort, filter, export). */
import { t } from "../core/i18n.js";
import { clear, h } from "./dom.js";
import { cellValue, pill, today } from "./format.js";
import { csvText, displayText } from "./helpers.js";
export class DataGrid {
    o;
    el;
    rows;
    sortKey = null;
    sortDir = 1;
    term = "";
    sel = null;
    shown = 0;
    tbody = h("tbody");
    thead = h("thead");
    tfoot = h("tfoot");
    foot = h("div", { class: "grid-foot" });
    scroll;
    hidden; // columns switched off (Col.hidden by default, then the user's choice, remembered per list)
    constructor(o) {
        this.o = o;
        this.rows = o.rows;
        this.hidden = new Set(o.columns.filter((c) => c.hidden).map((c) => c.key));
        const key = o.exportName ? `usool.grid.cols.${o.exportName}` : "";
        try {
            const saved = key && JSON.parse(localStorage.getItem(key) || "null");
            if (saved)
                for (const [k, on] of Object.entries(saved))
                    on ? this.hidden.delete(k) : this.hidden.add(k);
        }
        catch { /* ignore */ }
        const tools = h("div", { class: "grid-tools" });
        if (o.search !== false) {
            const s = h("input", { class: "gt-input", style: "max-width:260px", type: "search", placeholder: t("Search…"), "aria-label": t("Search") });
            s.addEventListener("input", () => { this.term = s.value.toLowerCase(); this.render(); });
            tools.append(s);
        }
        (o.tools || []).forEach((n) => tools.append(n));
        tools.append(h("span", { class: "spacer" }));
        if (o.exportName && o.columns.filter((c) => c.label).length > 4)
            tools.append(this.columnChooser(key));
        if (o.exportName)
            tools.append(h("button", { class: "rb", type: "button", onclick: () => this.exportCsv() }, h("span", null, t("Export to Excel"))));
        const table = h("table", { class: "grid" }, this.thead, this.tbody, this.tfoot);
        this.scroll = h("div", { class: "grid-scroll", style: o.maxHeight ? `max-height:${o.maxHeight}` : undefined }, table);
        this.el = h("div", { class: "grid-wrap" }, tools, this.scroll, this.foot);
        this.render();
    }
    cols() { return this.o.columns.filter((c) => !this.hidden.has(c.key)); }
    /** "Columns" button: a checklist of the columns; the choice is kept in this browser. */
    columnChooser(key) {
        const pop = h("div", { class: "col-pop", role: "dialog", "aria-label": t("Columns") });
        const btn = h("button", { class: "rb", type: "button", "aria-haspopup": "true", "aria-expanded": "false" }, h("span", null, t("Columns")));
        const wrap = h("span", { class: "col-chooser" }, btn, pop);
        const save = () => { try {
            if (key)
                localStorage.setItem(key, JSON.stringify(Object.fromEntries(this.o.columns.map((c) => [c.key, !this.hidden.has(c.key)]))));
        }
        catch { /* ignore */ } };
        const fill = () => {
            clear(pop);
            for (const c of this.o.columns.filter((x) => x.label)) {
                const box = h("input", { type: "checkbox" });
                box.checked = !this.hidden.has(c.key);
                box.addEventListener("change", () => {
                    if (!box.checked && this.cols().length <= 1) {
                        box.checked = true;
                        return;
                    } // keep at least one column
                    box.checked ? this.hidden.delete(c.key) : this.hidden.add(c.key);
                    save();
                    this.render();
                });
                pop.append(h("label", null, box, t(c.label)));
            }
            pop.append(h("button", { class: "btn sm", type: "button", onclick: () => {
                    this.hidden = new Set(this.o.columns.filter((c) => c.hidden).map((c) => c.key));
                    try {
                        if (key)
                            localStorage.removeItem(key);
                    }
                    catch { /* ignore */ }
                    fill();
                    this.render();
                } }, t("Reset")));
        };
        const close = (e) => { if (!wrap.contains(e.target)) {
            wrap.classList.remove("open");
            btn.setAttribute("aria-expanded", "false");
            document.removeEventListener("mousedown", close);
        } };
        btn.addEventListener("click", () => {
            const open = !wrap.classList.contains("open");
            wrap.classList.toggle("open", open);
            btn.setAttribute("aria-expanded", String(open));
            if (open) {
                fill();
                document.addEventListener("mousedown", close);
            }
            else
                document.removeEventListener("mousedown", close);
        });
        return wrap;
    }
    setRows(rows) { this.rows = rows; this.sel = null; this.o.onSelect?.(null); this.render(); }
    selected() { return this.sel; }
    view() {
        let v = this.rows;
        if (this.term) {
            const cols = this.cols();
            v = v.filter((r) => cols.some((c) => displayText(c, r).toLowerCase().includes(this.term)));
        }
        if (this.sortKey) {
            const k = this.sortKey;
            const col = this.cols().find((c) => c.key === k);
            const numeric = col && ["money", "int", "pct"].includes(col.type || "");
            v = [...v].sort((a, b) => {
                const x = a[k], y = b[k];
                if (x === y)
                    return 0;
                if (x === null || x === undefined || x === "")
                    return 1;
                if (y === null || y === undefined || y === "")
                    return -1;
                return (numeric ? Number(x) - Number(y) : String(x).localeCompare(String(y), undefined, { numeric: true })) * this.sortDir;
            });
        }
        return v;
    }
    render() {
        const cols = this.cols();
        clear(this.thead);
        const selectable = !!this.o.onOpen;
        this.thead.append(h("tr", null, selectable ? h("th", { class: "chk", scope: "col" }) : null, ...cols.map((c) => {
            const th = h("th", { class: ["money", "int", "pct"].includes(c.type || "") ? "num" : "", style: c.width ? `min-width:${c.width}px` : undefined, scope: "col", tabindex: c.label ? 0 : undefined,
                "aria-sort": this.sortKey === c.key ? (this.sortDir > 0 ? "ascending" : "descending") : "none" }, t(c.label), this.sortKey === c.key ? h("span", { class: "srt" }, this.sortDir > 0 ? "▲" : "▼") : null);
            const sort = () => { if (this.sortKey === c.key)
                this.sortDir *= -1;
            else {
                this.sortKey = c.key;
                this.sortDir = 1;
            } this.render(); };
            th.addEventListener("click", sort);
            th.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                sort();
            } });
            return th;
        })));
        const view = this.view();
        const limit = this.o.limit ?? 300;
        this.shown = Math.min(view.length, Math.max(this.shown, limit));
        if (this.shown > view.length || this.term || this.sortKey)
            this.shown = Math.min(view.length, Math.max(limit, this.shown));
        clear(this.tbody);
        if (!view.length) {
            this.tbody.append(h("tr", null, h("td", { colspan: cols.length + (this.o.onOpen ? 1 : 0), class: "empty" }, t(this.o.empty || "No records to show."))));
        }
        for (const r of view.slice(0, this.shown))
            this.tbody.append(this.row(r, cols));
        clear(this.tfoot);
        if (this.o.totals && view.length) {
            this.tfoot.append(h("tr", null, this.o.onOpen ? h("td", { class: "chk" }) : null, ...cols.map((c, i) => h("td", { class: ["money", "int", "pct"].includes(c.type || "") ? "num" : "" }, this.o.totals.includes(c.key) ? cellValue(c, view.reduce((s, r) => s + Number(r[c.key] || 0), 0)) : i === 0 ? t("Total") : ""))));
        }
        clear(this.foot);
        this.foot.append(h("span", null, t("{0} records", view.length)));
        if (view.length > this.shown) {
            this.foot.append(h("button", { class: "btn sm", type: "button", onclick: () => { this.shown += limit; this.render(); } }, t("Show more")));
        }
    }
    row(r, cols) {
        const tr = h("tr", { class: `${this.o.onOpen ? "clickable" : ""} ${this.sel === r ? "sel" : ""}`, tabindex: this.o.onOpen ? 0 : undefined });
        if (this.o.onOpen) {
            const box = h("input", { type: "checkbox", "aria-label": t("Select row") });
            box.checked = this.sel === r;
            box.addEventListener("click", (e) => { e.stopPropagation(); if (this.sel === r) {
                this.sel = null;
                this.o.onSelect?.(null);
                tr.classList.remove("sel");
                box.checked = false;
            }
            else {
                tr.click();
            } });
            tr.append(h("td", { class: "chk" }, box));
        }
        tr.append(...cols.map((c) => {
            const v = r[c.key];
            let content;
            if (c.render)
                content = c.render(r);
            else if (c.type === "status")
                content = v ? pill(String(v)) : "";
            else
                content = cellValue(c, v);
            if (c.link && v !== null && v !== "") {
                const href = c.link(r);
                if (href)
                    content = h("a", { href, class: "lnk", onclick: (e) => e.stopPropagation() }, content);
            }
            const num = ["money", "int", "pct"].includes(c.type || "");
            const td = h("td", { class: `${num ? "num" : ""} ${c.type === "bool" ? "ctr" : ""} ${num && Number(v) < 0 ? "neg" : ""}`, title: typeof content === "string" && content.length > 38 ? content : undefined }, content);
            return td;
        }));
        tr.addEventListener("click", () => {
            this.sel = r;
            this.o.onSelect?.(r);
            this.tbody.querySelectorAll("tr.sel").forEach((x) => { x.classList.remove("sel"); x.querySelector("input[type=checkbox]")?.removeAttribute("checked"); (x.querySelector("input[type=checkbox]") || {}).checked = false; });
            tr.classList.add("sel");
            const cb = tr.querySelector("input[type=checkbox]");
            if (cb)
                cb.checked = true;
        });
        if (this.o.onOpen) {
            tr.addEventListener("dblclick", () => this.o.onOpen(r));
            tr.addEventListener("keydown", (e) => {
                if (e.target.closest("a,button,input"))
                    return;
                if (e.key === " ") {
                    e.preventDefault();
                    tr.click();
                }
                else if (e.key === "Enter") {
                    e.preventDefault();
                    this.o.onOpen(r);
                }
            });
        }
        return tr;
    }
    exportCsv() {
        const cols = this.cols();
        const lines = [cols.filter((c) => c.label).map((c) => csvText(t(c.label))).join(",")];
        for (const r of this.view())
            lines.push(cols.filter((c) => c.label).map((c) => (["money", "int", "pct"].includes(c.type || "") && !c.render ? String(r[c.key] ?? "") : csvText(displayText(c, r)))).join(","));
        downloadCsv(this.o.exportName || "export", lines.join("\r\n"));
    }
}
export function downloadCsv(name, text) {
    const blob = new Blob(["﻿" + text], { type: "text/csv;charset=utf-8" });
    const a = h("a", { href: URL.createObjectURL(blob), download: `${name}-${today()}.csv` });
    document.body.appendChild(a);
    a.click();
    a.remove();
}
