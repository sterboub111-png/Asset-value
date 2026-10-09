/** Top bar: navigation toggle, brand, breadcrumb, search everything, the branch picker and the account menu (language, appearance and backup live in Settings). */
import { t } from "../core/i18n.js";
import { h, icon } from "../ui/index.js";
import { userMenu } from "./account.js";
import { toggleNav } from "./nav.js";
import { scopePicker } from "./scope.js";
import { globalSearch } from "./search.js";
export function buildTopbar({ sig, signOut }) {
    const crumb = h("span", { class: "crumb" });
    const el = h("header", { class: "topbar" }, h("button", { class: "tb-btn", "data-act": "nav", "aria-label": t("Navigation"), title: t("Navigation"), onclick: toggleNav }, icon("menu")), h("div", { class: "brand" }, h("span", { class: "logo" }, icon("asset")), t("Usool")), h("span", { class: "sep" }), crumb, h("span", { class: "spacer" }), globalSearch(sig), h("span", { class: "spacer" }), scopePicker(sig), userMenu(sig, signOut));
    return { el, crumb };
}
