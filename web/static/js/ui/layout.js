/** Page chrome: ribbon and page header. */
import { t } from "../core/i18n.js";
import { can } from "../core/session.js";
import { keysOf } from "../core/shortcuts.js";
import { append, h } from "./dom.js";
/** Dynamics-style action pane. With `titles` the button groups become tabs (Asset | Manage | View ...). */
export function ribbon(allGroups, allTitles) {
    // hide the commands the signed-in user has no permission for, and any group (tab) left empty
    const keep = allGroups.map((g) => g.filter((b) => can(b.perm)));
    const groups = keep.filter((g) => g.length);
    const titles = allTitles && allTitles.length === allGroups.length ? allTitles.filter((_, i) => keep[i].length) : undefined;
    const tabbed = !!titles && titles.length === groups.length && groups.length > 1;
    const el = h("div", { class: `ribbon ${tabbed ? "tabbed" : ""}`, role: "toolbar" });
    const btns = {};
    // the standard commands carry their action name so the keyboard shortcuts (shell/keyboard.ts) can press them
    const acts = { [t("New")]: "new", [t("Edit")]: "edit", [t("Delete")]: "delete", [t("Refresh")]: "refresh", [t("Save")]: "save" };
    const strip = tabbed ? h("div", { class: "ribbon-tabs", role: "tablist" }) : null;
    const panes = [];
    groups.forEach((g) => {
        const ge = h("div", { class: "grp" });
        for (const b of g) {
            const act = acts[b.label];
            const keys = act ? keysOf(act) : "";
            const be = h("button", { class: `rb ${b.primary ? "primary" : ""} ${b.danger ? "danger" : ""} ${b.active ? "active" : ""}`, type: "button", disabled: b.disabled,
                "data-act": act, title: keys ? `${b.label} (${keys})` : undefined }, h("span", null, b.label));
            be.addEventListener("click", b.onClick);
            if (b.id)
                btns[b.id] = be;
            ge.appendChild(be);
        }
        panes.push(ge);
    });
    if (tabbed && strip) {
        const show = (i) => {
            panes.forEach((p, k) => { p.style.display = k === i ? "flex" : "none"; });
            [...strip.children].forEach((c, k) => { c.classList.toggle("active", k === i); c.setAttribute("aria-selected", String(k === i)); });
        };
        titles.forEach((title, i) => strip.appendChild(h("button", { class: "ribbon-tab", type: "button", role: "tab", onclick: () => show(i) }, title)));
        const wrap = h("div", { class: "ribbon-wrap" }, strip, h("div", { class: "ribbon-row" }, ...panes));
        show(0);
        el.appendChild(wrap);
    }
    else
        panes.forEach((p) => el.appendChild(p));
    return { el, btns };
}
export function page(o, ...body) {
    const titleEl = h("h1", null, o.title);
    const head = h("div", { class: "page-head" }, h("div", { class: "title-row" }, titleEl, o.subtitle ? h("span", { class: "sub" }, o.subtitle) : null, ...(o.pills || [])), o.ribbon);
    const content = h("div", { class: `page-body ${o.factbox ? "with-factbox" : ""}` });
    if (o.factbox)
        content.append(h("div", { class: "main-col" }, ...body), h("aside", { class: "factbox" }, o.factbox));
    else
        append(content, body);
    return { el: h("div", { class: "page" }, head, content), titleEl };
}
