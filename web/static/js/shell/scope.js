/** The branch picker in the top bar (like the company switcher of Business Central): everything, one country or one
 *  branch. The choice travels with every API call (core/api.ts X-Scope) and the server narrows lists, reports, the
 *  workspace and depreciation runs to it, within the branches the user may see. */
import { api, getScope, setScope } from "../core/api.js";
import { getLang, t } from "../core/i18n.js";
import { clear, fold, h, icon } from "../ui/index.js";
const cName = (c) => (getLang() === "ar" ? c.nameAr : c.name);
const bName = (b) => (getLang() === "ar" && b.BranchNameAr ? b.BranchNameAr : b.BranchName);
/** The label of the current scope, or null when there are no branches yet (the picker is then left out). */
function current(tree) {
    const v = getScope();
    if (v.startsWith("country:")) {
        const c = tree.countries.find((x) => x.code === v.slice(8));
        if (c)
            return cName(c);
    }
    if (v.startsWith("branch:")) {
        for (const c of tree.countries) {
            const b = c.branches.find((x) => String(x.BranchID) === v.slice(7));
            if (b)
                return `${b.BranchCode} · ${bName(b)}`;
        }
    }
    return tree.limited ? t("My branches") : t("All branches");
}
export function scopePicker(sig) {
    const wrap = h("div", { class: "scope", hidden: true });
    void api.get("/api/branches/tree").then((tree) => {
        const all = tree.countries.reduce((n, c) => n + c.branches.length, 0);
        if (!all) {
            if (getScope())
                setScope("");
            return;
        }
        const label = h("span", { class: "scope-name" }, current(tree));
        const btn = h("button", { class: "scope-btn", type: "button", "aria-haspopup": "listbox", "aria-expanded": "false", title: t("Branches shown") }, icon("branch"), label, icon("chevron"));
        const q = h("input", { class: "gt-input", type: "search", placeholder: t("Find a country or branch…"), "aria-label": t("Find a country or branch") });
        const list = h("div", { class: "scope-list", role: "listbox" });
        const pop = h("div", { class: "scope-pop", hidden: true }, q, list);
        const choose = (v) => { if (v !== getScope()) {
            setScope(v);
            location.reload();
        }
        else
            close(); };
        const opt = (v, text, sub, cls = "") => h("button", { class: `scope-opt ${cls} ${getScope() === v ? "on" : ""}`, type: "button", role: "option", "aria-selected": String(getScope() === v), onclick: () => choose(v) }, h("span", null, text), sub ? h("small", null, sub) : "");
        const draw = () => {
            const k = fold(q.value);
            clear(list);
            if (!k)
                list.append(opt("", tree.limited ? t("My branches") : t("All branches"), t("{0} branches", all), "top"));
            for (const c of tree.countries) {
                const hitC = !k || fold(`${c.name} ${c.nameAr} ${c.code}`).includes(k);
                const bs = c.branches.filter((b) => hitC || fold(`${b.BranchCode} ${b.BranchName} ${b.BranchNameAr || ""} ${b.City || ""}`).includes(k));
                if (!bs.length)
                    continue;
                list.append(opt(`country:${c.code}`, cName(c), t("{0} branches", c.branches.length), "country"));
                for (const b of bs)
                    list.append(opt(`branch:${b.BranchID}`, `${b.BranchCode} · ${bName(b)}`, b.City || "", "branch"));
            }
            if (!list.children.length)
                list.append(h("div", { class: "empty" }, t("No match")));
        };
        const close = () => { pop.hidden = true; btn.setAttribute("aria-expanded", "false"); };
        btn.addEventListener("click", (e) => {
            e.stopPropagation();
            const open = pop.hidden;
            pop.hidden = !open;
            btn.setAttribute("aria-expanded", String(open));
            if (open) {
                q.value = "";
                draw();
                q.focus();
            }
        });
        q.addEventListener("input", draw);
        q.addEventListener("keydown", (e) => {
            if (e.key === "Escape") {
                close();
                btn.focus();
            }
            if (e.key === "Enter")
                list.querySelector(".scope-opt")?.click();
            if (e.key === "ArrowDown") {
                e.preventDefault();
                list.querySelector(".scope-opt")?.focus();
            }
        });
        list.addEventListener("keydown", (e) => {
            const opts = [...list.querySelectorAll(".scope-opt")];
            const i = opts.indexOf(document.activeElement);
            if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                e.preventDefault();
                opts[Math.max(0, Math.min(opts.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)))]?.focus();
            }
            if (e.key === "Escape") {
                close();
                btn.focus();
            }
        });
        document.addEventListener("click", (e) => { if (!wrap.contains(e.target))
            close(); }, sig);
        wrap.append(btn, pop);
        wrap.hidden = false;
        wrap.classList.toggle("narrowed", !!getScope());
    }).catch(() => { });
    return wrap;
}
