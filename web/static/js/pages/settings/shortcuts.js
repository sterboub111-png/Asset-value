import { t } from "../../core/i18n.js";
import { DEFAULTS, SECTIONS, capture, comboOf, isCustom, keysOf, ownerOf, problemWith, resetKeys, setKeys } from "../../core/shortcuts.js";
import { clear, confirmDialog, csvText, dialog, downloadCsv, h, page, ribbon, toast } from "../../ui/index.js";
const kbd = (combo) => combo ? h("span", { class: "kbds" }, ...combo.split("+").map((k, i) => [i ? h("span", { class: "plus" }, "+") : null, h("kbd", null, k)]).flat())
    : h("span", { class: "sc-off" }, t("Not assigned"));
/** Settings > Keyboard shortcuts: every shortcut by system section, with filter, change, reset and print. */
export async function shortcutsPage(root) {
    let text = "";
    let section = "";
    const body = h("div", { class: "sc-list" });
    const matches = (d) => {
        if (section && d.section !== section)
            return false;
        const q = text.trim().toLowerCase();
        if (!q)
            return true;
        return [d.label, t(d.label), d.section, t(d.section), keysOf(d.id), d.keys].some((v) => v.toLowerCase().includes(q));
    };
    function draw() {
        clear(body);
        let shown = 0;
        for (const sec of SECTIONS) {
            const items = DEFAULTS.filter((d) => d.section === sec && matches(d));
            if (!items.length)
                continue;
            shown += items.length;
            const rows = items.map((d) => h("tr", null, h("td", { class: "sc-action" }, t(d.label)), h("td", { class: "sc-keys" }, kbd(keysOf(d.id)), isCustom(d.id) ? h("span", { class: "pill" }, t("Changed")) : null), h("td", { class: "sc-default" }, kbd(d.keys)), h("td", { class: "sc-noprint sc-btns" }, h("button", { class: "btn", type: "button", onclick: () => change(d) }, t("Change")), isCustom(d.id) ? h("button", { class: "btn", type: "button", onclick: () => { resetKeys(d.id); draw(); } }, t("Reset")) : null)));
            body.append(h("section", { class: "sc-section" }, h("h2", { class: "sec" }, t(sec), h("span", { class: "sc-count" }, String(items.length))), h("table", { class: "sc-table" }, h("thead", null, h("tr", null, h("th", null, t("Action")), h("th", null, t("Shortcut")), h("th", null, t("Default")), h("th", { class: "sc-noprint" }, ""))), h("tbody", null, ...rows))));
        }
        if (!shown)
            body.append(h("div", { class: "empty" }, t("No shortcuts match the filter.")));
    }
    /** Ask for the new key combination, refuse browser-reserved or already used ones. */
    function change(d) {
        let combo = keysOf(d.id);
        const view = h("div", { class: "sc-capture", tabindex: 0 }, kbd(combo));
        const msg = h("div", { class: "msgbar err", style: "display:none" });
        const onKey = (e) => {
            if (e.key === "Escape" || (e.key === "Tab" && !e.ctrlKey && !e.altKey))
                return; // keep Esc / Tab for closing and moving focus
            e.preventDefault();
            e.stopPropagation();
            const c = comboOf(e);
            if (!c)
                return;
            combo = c;
            clear(view);
            view.append(kbd(combo));
            const bad = problemWith(combo);
            const owner = ownerOf(combo, d.id);
            msg.textContent = bad ? t(bad) : owner ? t("Already used by: {0}", t(owner.label)) : "";
            msg.style.display = msg.textContent ? "" : "none";
        };
        document.addEventListener("keydown", onKey, true);
        capture.on = true;
        const stop = () => { document.removeEventListener("keydown", onKey, true); capture.on = false; };
        dialog(t("Change shortcut"), h("div", { class: "sc-dialog" }, h("p", null, h("b", null, t(d.label))), h("p", { class: "sc-hint" }, t("Press the new key combination.")), view, msg, h("p", { class: "sc-hint" }, t("Use Ctrl or Alt with a key. Esc closes without changing."))), [
            { label: t("Save"), primary: true, onClick: () => {
                    const bad = problemWith(combo);
                    if (bad && combo) {
                        msg.textContent = t(bad);
                        msg.style.display = "";
                        return false;
                    }
                    const owner = ownerOf(combo, d.id);
                    if (owner) {
                        msg.textContent = t("Already used by: {0}", t(owner.label));
                        msg.style.display = "";
                        return false;
                    }
                    setKeys(d.id, combo);
                    draw();
                } },
            { label: t("Switch off"), onClick: () => { setKeys(d.id, ""); draw(); } },
            { label: t("Cancel") },
        ], { onClose: stop });
        view.focus();
    }
    const exportCsv = () => downloadCsv("shortcuts", [["Section", "Action", "Shortcut", "Default"].map(csvText).join(","),
        ...DEFAULTS.filter(matches).map((d) => [t(d.section), t(d.label), keysOf(d.id), d.keys].map(csvText).join(","))].join("\n"));
    const reset = async () => {
        if (await confirmDialog(t("Restore every shortcut to its default?"), { ok: t("Reset all") })) {
            resetKeys();
            draw();
            toast(t("Shortcuts restored"), "ok");
        }
    };
    const rb = ribbon([[{ label: t("Print"), icon: "print", primary: true, onClick: () => window.print() }, { label: t("Export"), icon: "download", onClick: exportCsv }],
        [{ label: t("Reset all"), icon: "refresh", onClick: () => void reset() }]], [t("Shortcuts"), t("Manage")]);
    const filter = h("input", { type: "search", placeholder: t("Filter shortcuts…"), "aria-label": t("Filter shortcuts…"), autocomplete: "off" });
    filter.addEventListener("input", () => { text = filter.value; draw(); });
    const pick = h("select", { "aria-label": t("Section") }, h("option", { value: "" }, t("All sections")), ...SECTIONS.map((s) => h("option", { value: s }, t(s))));
    pick.addEventListener("change", () => { section = pick.value; draw(); });
    clear(root);
    root.append(page({ title: t("Keyboard shortcuts"), subtitle: t("Settings"), ribbon: rb.el }, h("div", { class: "sc-print-title" }, h("h1", null, `${t("Usool")} — ${t("Keyboard shortcuts")}`), h("p", null, new Date().toLocaleDateString())), h("div", { class: "msgbar sc-noprint" }, t("Shortcuts are saved in this browser. Letters follow the physical key, so they also work with the Arabic keyboard.")), h("div", { class: "sc-toolbar sc-noprint" }, filter, pick), body).el);
    draw();
}
