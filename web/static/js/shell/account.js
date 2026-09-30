/** Signed-in user: account menu, sign-out and the forced password change. */
import { ApiError, api } from "../core/api.js";
import { t } from "../core/i18n.js";
import { getMe, initials, roleTitle, setMe, userTitle } from "../core/session.js";
import { Form, dialog, h, toast } from "../ui/index.js";
/** Avatar button with the account menu (account settings, password, sign out). */
export function userMenu(sig, onSignOut) {
    const me = getMe();
    const wrap = h("div", { class: "user-wrap" });
    const btn = h("button", { class: "tb-btn user-btn", type: "button", "aria-haspopup": "true", "aria-expanded": "false", title: userTitle(me) }, h("span", { class: "avatar" }, initials(me.FullName)));
    const menu = h("div", { class: "user-menu", role: "menu", style: "display:none" }, h("div", { class: "um-head" }, h("span", { class: "avatar big" }, initials(me.FullName)), h("div", null, h("b", null, userTitle(me)), h("div", { class: "um-sub" }, me.UserName), h("div", { class: "um-sub" }, roleTitle(me)))), h("a", { href: "#/settings/account", role: "menuitem", class: "um-item" }, t("My account")), h("a", { href: "#/settings/account", role: "menuitem", class: "um-item" }, t("Change password")), h("button", { type: "button", role: "menuitem", class: "um-item", onclick: () => onSignOut() }, t("Sign out")));
    const close = () => { menu.style.display = "none"; btn.setAttribute("aria-expanded", "false"); };
    btn.addEventListener("click", (e) => { e.stopPropagation(); const open = menu.style.display === "none"; menu.style.display = open ? "" : "none"; btn.setAttribute("aria-expanded", String(open)); });
    menu.addEventListener("click", (e) => { if (e.target.closest("a"))
        close(); });
    document.addEventListener("click", (e) => { if (!wrap.contains(e.target))
        close(); }, sig);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape")
        close(); }, sig);
    wrap.append(btn, menu);
    return wrap;
}
export let signingOut = false;
/** Ends the session on the server, then `restart` shows the sign-in page. */
export async function signOut(restart) {
    signingOut = true;
    try {
        try {
            await api.post("/api/auth/logout");
        }
        catch { /* the session may already be gone */ }
        setMe(null);
        location.hash = "#/";
        await restart();
    }
    finally {
        signingOut = false;
    }
}
export function forcePasswordChange(restart) {
    if (document.querySelector(".force-pw"))
        return;
    const form = new Form([
        { name: "Current", label: "Current password", type: "password", required: true },
        { name: "New", label: "New password", type: "password", required: true },
        { name: "Confirm", label: "Confirm new password", type: "password", required: true },
    ], {});
    const d = dialog(t("Change your password"), h("div", null, h("div", { class: "msgbar warn" }, t("You must set a new password before you continue.")), form.el), [
        { label: t("Change password"), primary: true, onClick: async () => {
                if (!form.validate())
                    return false;
                if (form.value("New") !== form.value("Confirm"))
                    throw new ApiError("The passwords do not match");
                await api.post("/api/auth/password", { Current: form.value("Current"), New: form.value("New") });
                setMe({ ...getMe(), MustChangePassword: 0 });
                toast(t("Password changed"), "ok");
                void restart();
            } },
        { label: t("Sign out"), onClick: () => void signOut(restart) },
    ], { dismissable: false });
    d.el.classList.add("force-pw");
}
