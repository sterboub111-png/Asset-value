/** Entry point: boots the app, shows sign-in or the shell, and renders the page for the current hash. */
import { api, hooks, lookups } from "./core/api.js";
import { applyLang, setLang, t } from "./core/i18n.js";
import { applyTheme, can, getMe, setMe, setTheme } from "./core/session.js";
import { showLogin } from "./pages/auth/login.js";
import { initKeyboard } from "./shell/keyboard.js";
import { forcePasswordChange, signOut, signingOut } from "./shell/account.js";
import { buildNav, loadReportGroups, markActive, narrow, railKey } from "./shell/nav.js";
import { ROUTES, permFor } from "./shell/routes.js";
import { buildTopbar } from "./shell/topbar.js";
import { rememberVisit } from "./shell/search.js";
import { clear, closeAllDialogs, confirmDialog, fail, h, icon } from "./ui/index.js";
import { isDirty, markClean } from "./core/dirty.js";
applyTheme();
let mainEl;
let crumbEl;
let seq = 0;
let shellAbort = null;
function parseHash() {
    const raw = location.hash.replace(/^#\/?/, "");
    const [path, qs] = raw.split("?");
    return { path: path.replace(/\/$/, ""), query: new URLSearchParams(qs || "") };
}
async function render() {
    if (!getMe() || getMe().MustChangePassword || !mainEl?.isConnected)
        return; // the shell is still being built
    const { path, query } = parseHash();
    const my = ++seq;
    closeAllDialogs();
    document.querySelectorAll(".side-panel").forEach((n) => n.remove());
    for (const r of ROUTES) {
        const m = path.match(r.re);
        if (!m)
            continue;
        markActive(r.nav);
        crumbEl.textContent = t(r.crumb);
        clear(mainEl);
        mainEl.scrollTop = 0;
        const holder = h("div", null);
        mainEl.append(holder);
        if (!can(permFor(`#/${path}`))) {
            holder.append(h("div", { class: "denied" }, icon("lock"), h("h2", null, t("No access")), h("p", null, t("You do not have permission to open this page.")), h("a", { href: "#/", class: "btn primary" }, t("Back to workspace"))));
            return;
        }
        try {
            await r.fn(holder, { args: m.slice(1), query });
            if (my === seq)
                rememberVisit(location.hash, holder.querySelector(".page-head h1")?.textContent || "", t(r.crumb));
        }
        catch (e) {
            if (my === seq) {
                fail(e);
                holder.append(h("div", { class: "msgbar err", style: "margin:24px" }, e instanceof Error ? t(e.message) : String(e)));
            }
        }
        return;
    }
    location.hash = "#/";
}
function buildShell() {
    shellAbort?.abort();
    shellAbort = new AbortController();
    const top = buildTopbar({ sig: { signal: shellAbort.signal }, restart: () => void boot(), signOut: () => void signOut(boot) });
    crumbEl = top.crumb;
    mainEl = h("main", { class: "main", id: "main" });
    return h("div", { class: "shell" }, top.el, h("div", { class: "body" }, buildNav(), mainEl));
}
let authLost = false;
hooks.onUnauthorized = () => {
    if (authLost || signingOut)
        return;
    authLost = true;
    setMe(null);
    void boot(t("Your session has ended. Please sign in again.")).finally(() => { authLost = false; });
};
hooks.onMustChange = () => forcePasswordChange(boot);
async function startSession(me) {
    setMe(me);
    if (me.Language === "ar" || me.Language === "en")
        setLang(me.Language); // personal preferences
    if (me.Theme === "light" || me.Theme === "dark" || me.Theme === "system")
        setTheme(me.Theme);
    applyLang();
    const app = document.getElementById("app");
    clear(app);
    await loadReportGroups();
    app.append(buildShell());
    document.body.classList.toggle("nav-collapsed", narrow());
    try {
        document.body.classList.toggle("nav-rail", localStorage.getItem(railKey) === "1");
    }
    catch { /* ignore */ }
    if (me.MustChangePassword) {
        forcePasswordChange(boot);
        return;
    } // nothing else may load until the password is changed
    try {
        const L = await lookups(true);
        if (L.settings.CompanyName)
            document.title = `${t("Usool")} — ${L.settings.CompanyName}`;
    }
    catch (e) {
        fail(e);
    }
    await render();
}
async function boot(notice) {
    applyLang();
    const app = document.getElementById("app");
    let st;
    try {
        st = await api.get("/api/auth/status");
    }
    catch (e) {
        clear(app);
        app.append(h("div", { class: "msgbar err", style: "margin:24px" }, e instanceof Error ? e.message : String(e)));
        return;
    }
    if (st.needs_setup || !st.user) {
        setMe(null);
        showLogin(app, st.needs_setup, (me) => { location.hash = "#/"; void startSession(me); }, () => void boot(), notice);
        return;
    }
    await startSession(st.user);
}
initKeyboard();
// leaving a form with unsaved changes asks first; "stay" puts the address back without reloading the page
let lastHash = location.hash;
window.addEventListener("hashchange", async () => {
    if (isDirty()) {
        const leave = await confirmDialog(t("You have unsaved changes. Leave this page and discard them?"), { danger: true, ok: t("Discard changes"), title: t("Unsaved changes") });
        if (!leave) {
            history.replaceState(null, "", lastHash || "#/");
            return;
        }
        markClean();
    }
    lastHash = location.hash;
    void render();
});
addEventListener("beforeunload", (e) => { if (isDirty()) {
    e.preventDefault();
    e.returnValue = "";
} });
void boot();
