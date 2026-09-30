import { api } from "../../core/api.js";
import { getLang, setLang, t } from "../../core/i18n.js";
import { getMe, getTheme, roleTitle, setMe, setTheme } from "../../core/session.js";
import { Form, clear, fastTab, guard, h, page, ribbon, toast } from "../../ui/index.js";
/** "My account": profile, personal preferences and password (available to every signed-in user). */
export async function accountPage(root, _a, onChanged) {
    const me = getMe();
    const profile = new Form([
        { name: "UserName", label: "User name", readonly: true }, { name: "RoleName", label: "Role", readonly: true },
        { name: "FullName", label: "Full name", required: true, maxlength: 120 }, { name: "FullNameAr", label: "Name (Arabic)", maxlength: 120 },
        { name: "Email", label: "Email" }, { name: "Phone", label: "Phone" },
    ], { ...me, RoleName: roleTitle(me) });
    const prefs = new Form([
        { name: "Language", label: "Language", type: "select", options: [{ value: "en", label: "English" }, { value: "ar", label: "العربية" }] },
        { name: "Theme", label: "Appearance", type: "select", options: [{ value: "light", label: t("Light") }, { value: "dark", label: t("Dark") }] },
    ], { Language: me.Language || getLang(), Theme: me.Theme || getTheme() });
    const pw = new Form([
        { name: "Current", label: "Current password", type: "password", required: true },
        { name: "New", label: "New password", type: "password", required: true },
        { name: "Confirm", label: "Confirm new password", type: "password", required: true },
    ], {});
    const saveProfile = guard(async () => {
        if (!profile.validate())
            return;
        const upd = await api.put("/api/auth/profile", { ...profile.get(), ...prefs.get() });
        setMe(upd);
        if (prefs.value("Language") !== getLang())
            setLang(prefs.value("Language"));
        setTheme(prefs.value("Theme"));
        toast(t("Saved"), "ok");
        onChanged();
    });
    const changePw = guard(async () => {
        if (!pw.validate())
            return;
        if (pw.value("New") !== pw.value("Confirm")) {
            toast(t("The passwords do not match"), "err");
            return;
        }
        await api.post("/api/auth/password", { Current: pw.value("Current"), New: pw.value("New") });
        ["Current", "New", "Confirm"].forEach((n) => pw.set(n, ""));
        toast(t("Password changed"), "ok");
    });
    const rb = ribbon([[{ label: t("Save"), icon: "save", primary: true, onClick: saveProfile }],
        [{ label: t("Change password"), icon: "lock", onClick: changePw }]], [t("Account"), t("Security")]);
    clear(root);
    root.append(page({ title: t("My account"), subtitle: t("Settings"), ribbon: rb.el }, fastTab(t("Profile"), profile.el, { open: true, summary: me.UserName }), fastTab(t("Preferences"), prefs.el, { open: true }), fastTab(t("Password"), h("div", null, pw.el, h("div", { style: "margin-top:10px" }, h("button", { class: "btn primary", type: "button", onclick: changePw }, t("Change password")))), { open: true,
        summary: t("Use at least 8 characters with letters and digits.") })).el);
}
