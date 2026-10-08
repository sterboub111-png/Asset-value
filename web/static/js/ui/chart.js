/** SVG charts for the analysis mode and the dashboard: column, bar, line, stacked column and donut.
 *  Thin marks with 4px rounded data ends, 2px surface gaps, hairline grid, one tooltip per category,
 *  a legend from two series up, and a click on a category to drill into it. Colours are the validated
 *  --viz-1..8 tokens (analysis.css), assigned in fixed order and never cycled. */
import { t } from "../core/i18n.js";
import { clear, h } from "./dom.js";
const NS = "http://www.w3.org/2000/svg";
const COMPACT = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
const color = (slot) => (slot > 0 ? `var(--viz-${slot})` : "var(--viz-other)");
function el(tag, attrs = {}, text) {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs))
        n.setAttribute(k, String(v));
    if (text !== undefined)
        n.textContent = text; // labels are data: always text, never markup
    return n;
}
/** Clean tick values from 0 (or the minimum, when negative) to the maximum. */
function ticks(min, max, count = 5) {
    const lo = Math.min(0, min), hi = Math.max(0, max);
    if (hi === lo)
        return [0, 1];
    const raw = (hi - lo) / count;
    const mag = 10 ** Math.floor(Math.log10(raw));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) || raw;
    const out = [];
    for (let v = Math.floor(lo / step) * step; v <= hi + step * 0.001; v += step)
        out.push(Math.round(v * 1e6) / 1e6);
    if (out[out.length - 1] < hi)
        out.push(out[out.length - 1] + step);
    return out;
}
/** A bar whose data end is rounded (4px) and whose baseline end is square. */
function barPath(x, y0, w, y1, horizontal = false) {
    // vertical: from baseline y0 to data end y1; horizontal: x is the bar's y, y0/y1 are x positions
    const len = Math.abs(y1 - y0);
    const r = Math.min(4, w / 2, len);
    if (!horizontal) {
        const up = y1 < y0;
        const a = up ? 1 : -1; // direction toward the data end
        return `M${x},${y0} V${y1 + a * r} Q${x},${y1} ${x + r},${y1} H${x + w - r} Q${x + w},${y1} ${x + w},${y1 + a * r} V${y0} Z`;
    }
    const right = y1 > y0;
    const a = right ? -1 : 1;
    return `M${y0},${x} H${y1 + a * r} Q${y1},${x} ${y1},${x + r} V${x + w - r} Q${y1},${x + w} ${y1 + a * r},${x + w} H${y0} Z`;
}
const textWidth = (s, px = 11) => s.length * px * 0.58;
const clip = (s, n) => (s.length > n ? `${s.slice(0, Math.max(1, n - 1))}…` : s);
export function drawChart(host, spec) {
    clear(host);
    host.classList.add("viz");
    const W = Math.max(280, host.clientWidth || 600);
    const multi = spec.series.length > 1;
    const legendEl = multi ? h("div", { class: "viz-legend" }, ...spec.series.map((s) => h("span", { class: "viz-key" }, h("i", { class: spec.type === "line" ? "line" : "", style: `--c:${color(s.slot)}` }), s.name))) : null;
    const tip = h("div", { class: "viz-tip", role: "status" });
    const frame = h("div", { class: "viz-frame" });
    host.append(...(legendEl ? [legendEl] : []), frame, tip);
    if (!spec.categories.length) {
        frame.append(h("div", { class: "viz-empty" }, t("No data for these parameters.")));
        return;
    }
    const showTip = (i, px, py) => {
        clear(tip);
        tip.append(h("div", { class: "viz-tip-cat" }, spec.categories[i]));
        for (const s of spec.series) {
            const v = s.values[i];
            tip.append(h("div", { class: "viz-tip-row" }, h("b", null, v === null ? "—" : spec.fmt(v)), multi ? h("span", null, h("i", { style: `--c:${color(s.slot)}` }), s.name) : null));
        }
        tip.style.display = "block";
        const fw = frame.clientWidth, tw = tip.offsetWidth;
        tip.style.left = `${Math.min(Math.max(4, px + 14), fw - tw - 4)}px`;
        tip.style.top = `${Math.max(4, py - 10) + (legendEl ? legendEl.offsetHeight + 6 : 0)}px`;
    };
    const hideTip = () => { tip.style.display = "none"; };
    /** A transparent hit area per category: bigger than the marks, focusable, clickable. */
    const hit = (svg, i, x, y, w, hh, mark) => {
        const r = el("rect", { x, y, width: Math.max(1, w), height: Math.max(1, hh), class: "viz-hit", tabindex: 0, role: "img",
            "aria-label": `${spec.categories[i]}: ${spec.series.map((s) => (s.values[i] === null ? "—" : spec.fmt(s.values[i]))).join(", ")}` });
        const on = (e) => {
            const b = r.getBoundingClientRect(), f = frame.getBoundingClientRect();
            showTip(i, e ? e.clientX - f.left : b.left - f.left + b.width / 2, e ? e.clientY - f.top : b.top - f.top);
            mark?.().forEach((m) => m.classList.add("lift"));
        };
        const off = () => { hideTip(); mark?.().forEach((m) => m.classList.remove("lift")); };
        r.addEventListener("pointermove", on);
        r.addEventListener("pointerleave", off);
        r.addEventListener("focus", () => on());
        r.addEventListener("blur", off);
        if (spec.onPick) {
            r.classList.add("pick");
            r.addEventListener("click", () => spec.onPick(i));
            r.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                spec.onPick(i);
            } });
        }
        svg.append(r);
    };
    if (spec.type === "donut")
        return donut(frame, spec, W, showTip, hideTip);
    const vals = spec.series.flatMap((s) => s.values.filter((v) => v !== null));
    const stacked = spec.type === "stacked";
    const totals = spec.categories.map((_, i) => spec.series.reduce((a, s) => a + Math.max(0, s.values[i] || 0), 0));
    const negs = spec.categories.map((_, i) => spec.series.reduce((a, s) => a + Math.min(0, s.values[i] || 0), 0));
    const tk = ticks(stacked ? Math.min(0, ...negs) : Math.min(0, ...vals), stacked ? Math.max(0, ...totals) : Math.max(0, ...vals));
    const lo = tk[0], hi = tk[tk.length - 1];
    const tickW = Math.max(...tk.map((v) => textWidth(COMPACT.format(v)))) + 10;
    const n = spec.categories.length;
    if (spec.type === "bar") { // horizontal bars: categories down the side, long names fit
        const labW = Math.min(200, Math.max(...spec.categories.map((c) => textWidth(clip(c, 30)))) + 12);
        const band = Math.max(22, Math.min(40, 260 / n + 14));
        const H = n * band + 28;
        const m = { l: labW, r: 64, t: 6, b: 22 };
        const pw = W - m.l - m.r;
        const sx = (v) => m.l + ((v - lo) / (hi - lo)) * pw;
        const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, class: "viz-svg" });
        for (const v of tk) {
            svg.append(el("line", { x1: sx(v), x2: sx(v), y1: m.t, y2: H - m.b, class: v === 0 ? "viz-base" : "viz-grid" }));
            svg.append(el("text", { x: sx(v), y: H - 6, class: "viz-tick", "text-anchor": "middle" }, COMPACT.format(v)));
        }
        spec.categories.forEach((c, i) => {
            const y = m.t + i * band;
            const k = spec.series.length;
            const thick = Math.min(24, (band - 8) / k - (k > 1 ? 2 : 0));
            const marks = [];
            spec.series.forEach((s, j) => {
                const v = s.values[i];
                if (v === null)
                    return;
                const by = y + (band - (thick * k + 2 * (k - 1))) / 2 + j * (thick + 2);
                const p = el("path", { d: barPath(by, sx(0), thick, sx(v), true), fill: color(s.slot), class: "viz-mark" });
                marks.push(p);
                svg.append(p);
            });
            svg.append(el("text", { x: m.l - 8, y: y + band / 2 + 4, class: "viz-cat", "text-anchor": "end" }, clip(c, 30)));
            if (k === 1 && spec.series[0].values[i] !== null) { // value at the tip, outside the bar
                const v = spec.series[0].values[i];
                svg.append(el("text", { x: sx(v) + (v >= 0 ? 6 : -6), y: y + band / 2 + 4, class: "viz-val", "text-anchor": v >= 0 ? "start" : "end" }, COMPACT.format(v)));
            }
            hit(svg, i, 0, y, W, band, () => marks);
        });
        frame.append(svg);
        return;
    }
    // column / stacked / line: categories along the bottom
    const H = spec.height || 260;
    const m = { l: tickW, r: 12, t: 18, b: 34 };
    const pw = W - m.l - m.r, ph = H - m.t - m.b;
    const band = pw / n;
    const sy = (v) => m.t + (1 - (v - lo) / (hi - lo)) * ph;
    const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, class: "viz-svg" });
    for (const v of tk) {
        svg.append(el("line", { x1: m.l, x2: W - m.r, y1: sy(v), y2: sy(v), class: v === 0 ? "viz-base" : "viz-grid" }));
        svg.append(el("text", { x: m.l - 6, y: sy(v) + 4, class: "viz-tick", "text-anchor": "end" }, COMPACT.format(v)));
    }
    // category labels: thinned so they never collide
    const maxLab = Math.max(4, Math.floor(band / 6.4));
    const every = Math.max(1, Math.ceil(Math.max(...spec.categories.map((c) => textWidth(clip(c, 18)))) / Math.max(1, band - 4)));
    spec.categories.forEach((c, i) => {
        if (i % every)
            return;
        const label = clip(c, Math.max(maxLab * every, 6)), x = m.l + band * (i + 0.5), half = textWidth(label, 11.5) / 2;
        // labels at the edges are anchored inside the frame instead of spilling past it
        const anchor = x + half > W ? "end" : x - half < 0 ? "start" : "middle";
        svg.append(el("text", { x: anchor === "end" ? W - 2 : anchor === "start" ? 2 : x, y: H - m.b + 16, class: "viz-cat", "text-anchor": anchor }, label));
    });
    if (spec.type === "line") {
        const cx = (i) => m.l + band * (i + 0.5);
        const cross = el("line", { x1: 0, x2: 0, y1: m.t, y2: H - m.b, class: "viz-cross" });
        svg.append(cross);
        for (const s of spec.series) {
            const pts = s.values.map((v, i) => (v === null ? null : [cx(i), sy(v)]));
            let d = "", pen = false;
            pts.forEach((p) => { if (!p) {
                pen = false;
                return;
            } d += `${pen ? "L" : "M"}${p[0]},${p[1]} `; pen = true; });
            if (spec.series.length === 1) { // a single series gets its area wash
                const valid = pts.filter((p) => !!p);
                if (valid.length > 1)
                    svg.append(el("path", { d: `M${valid[0][0]},${sy(Math.max(lo, 0))} ${valid.map((p) => `L${p[0]},${p[1]}`).join(" ")} L${valid[valid.length - 1][0]},${sy(Math.max(lo, 0))} Z`, fill: color(s.slot), class: "viz-area" }));
            }
            svg.append(el("path", { d, stroke: color(s.slot), class: "viz-line" }));
            if (n <= 40)
                pts.forEach((p) => { if (p)
                    svg.append(el("circle", { cx: p[0], cy: p[1], r: 4, fill: color(s.slot), class: "viz-dot" })); });
            // value at the end of the line
            const last = [...s.values].reverse().findIndex((v) => v !== null);
            if (last >= 0 && spec.series.length <= 4) {
                const i = n - 1 - last;
                svg.append(el("text", { x: Math.min(cx(i), W - m.r - 2), y: sy(s.values[i]) - 10, class: "viz-val", "text-anchor": i === n - 1 ? "end" : "middle" }, COMPACT.format(s.values[i])));
            }
        }
        spec.categories.forEach((_, i) => hit(svg, i, m.l + band * i, m.t, band, ph, () => { cross.setAttribute("x1", String(cx(i))); cross.setAttribute("x2", String(cx(i))); cross.classList.add("on"); return []; }));
        svg.addEventListener("pointerleave", () => cross.classList.remove("on"));
        frame.append(svg);
        return;
    }
    const k = stacked ? 1 : spec.series.length;
    const w = Math.max(3, Math.min(24, (band * 0.72 - 2 * (k - 1)) / k));
    const single = spec.series.length === 1;
    spec.categories.forEach((_, i) => {
        const x0 = m.l + band * i + (band - (w * k + 2 * (k - 1))) / 2;
        const marks = [];
        if (stacked) {
            let up = 0, down = 0;
            const segs = spec.series.map((s) => ({ s, v: s.values[i] || 0 })).filter((x) => x.v !== 0);
            const topPos = [...segs].reverse().find((x) => x.v > 0), topNeg = [...segs].reverse().find((x) => x.v < 0);
            for (const { s, v } of segs) {
                const from = v > 0 ? up : down, to = from + v;
                if (v > 0)
                    up = to;
                else
                    down = to;
                const end = (v > 0 && topPos?.s === s) || (v < 0 && topNeg?.s === s);
                // 2px surface gap between stacked segments
                const y0 = sy(from) + (from === 0 ? 0 : v > 0 ? -1 : 1), y1 = sy(to) + (end ? 0 : v > 0 ? 1 : -1);
                const p = el("path", { d: end ? barPath(x0, y0, w, y1) : `M${x0},${y0} V${y1} H${x0 + w} V${y0} Z`, fill: color(s.slot), class: "viz-mark" });
                marks.push(p);
                svg.append(p);
            }
        }
        else {
            spec.series.forEach((s, j) => {
                const v = s.values[i];
                if (v === null)
                    return;
                const x = x0 + j * (w + 2);
                const p = el("path", { d: barPath(x, sy(0), w, sy(v)), fill: color(s.slot), class: "viz-mark" });
                marks.push(p);
                svg.append(p);
                if (single && n <= 14 && w >= 10)
                    svg.append(el("text", { x: x + w / 2, y: v >= 0 ? sy(v) - 5 : sy(v) + 13, class: "viz-val", "text-anchor": "middle" }, COMPACT.format(v)));
            });
        }
        hit(svg, i, m.l + band * i, m.t, band, ph, () => marks);
    });
    frame.append(svg);
}
function donut(frame, spec, W, showTip, hideTip) {
    const s = spec.series[0];
    const vals = s.values.map((v) => Math.max(0, v || 0));
    const total = vals.reduce((a, b) => a + b, 0);
    const size = 210, R = 96, r = 62, cx = size / 2, cy = size / 2;
    const svg = el("svg", { width: size, height: size, viewBox: `0 0 ${size} ${size}`, class: "viz-svg viz-donut" });
    let a0 = -Math.PI / 2;
    const legend = h("div", { class: "viz-dlegend" });
    vals.forEach((v, i) => {
        const slot = spec.categories[i] === t("Other") ? 0 : i + 1;
        const frac = total ? v / total : 0;
        const a1 = a0 + frac * Math.PI * 2;
        if (frac > 0) {
            const big = a1 - a0 > Math.PI ? 1 : 0;
            const p = (rad, a) => `${cx + rad * Math.cos(a)},${cy + rad * Math.sin(a)}`;
            const d = frac >= 0.9999 ? `M${cx - R},${cy} A${R},${R} 0 1 1 ${cx + R},${cy} A${R},${R} 0 1 1 ${cx - R},${cy} M${cx - r},${cy} A${r},${r} 0 1 0 ${cx + r},${cy} A${r},${r} 0 1 0 ${cx - r},${cy} Z`
                : `M${p(R, a0)} A${R},${R} 0 ${big} 1 ${p(R, a1)} L${p(r, a1)} A${r},${r} 0 ${big} 0 ${p(r, a0)} Z`;
            const seg = el("path", { d, fill: color(slot), class: "viz-mark viz-seg", tabindex: 0, role: "img", "aria-label": `${spec.categories[i]}: ${spec.fmt(v)}` });
            const on = (e) => { const f = frame.getBoundingClientRect(); showTip(i, e ? e.clientX - f.left : cx, e ? e.clientY - f.top : cy); seg.classList.add("lift"); };
            const off = () => { hideTip(); seg.classList.remove("lift"); };
            seg.addEventListener("pointermove", on);
            seg.addEventListener("pointerleave", off);
            seg.addEventListener("focus", () => on());
            seg.addEventListener("blur", off);
            if (spec.onPick) {
                seg.classList.add("pick");
                seg.addEventListener("click", () => spec.onPick(i));
                seg.addEventListener("keydown", (e) => { if (e.key === "Enter")
                    spec.onPick(i); });
            }
            svg.append(seg);
        }
        a0 = a1;
        legend.append(h("div", { class: "viz-drow" }, h("i", { style: `--c:${color(slot)}` }), h("span", { class: "n" }, spec.categories[i]), h("b", null, spec.fmt(v)), h("span", { class: "p" }, `${Math.round(frac * 1000) / 10}%`)));
    });
    svg.append(el("text", { x: cx, y: cy - 2, class: "viz-total", "text-anchor": "middle" }, COMPACT.format(total)), el("text", { x: cx, y: cy + 16, class: "viz-tick", "text-anchor": "middle" }, t("Total")));
    frame.append(h("div", { class: "viz-donut-wrap", style: W < 520 ? "flex-direction:column" : "" }, svg, legend));
}
