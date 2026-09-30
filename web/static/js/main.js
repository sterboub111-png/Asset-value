/** Entry point: boots the app, shows sign-in or the shell, and renders the page for the current hash. */
import { api, hooks, lookups } from "./core/api.js";
import { applyLang, setLang, t } from "./core/i18n.js";
import { can, getMe, getTheme, setMe, setTheme } from "./core/session.js";
import { showLogin } from "./pages/auth/login.js";
import { groupSlug } from "./pages/reports/reports.js";
import { initKeyboard } from "./shell/keyboard.js";
import { forcePasswordChange, signOut, signingOut } from "./shell/account.js";
import { buildNav, loadReportGroups, markActive, narrow, railKey, reportGroups } from "./shell/nav.js";
import { ROUTES, permFor } from "./shell/routes.js";
import { buildTopbar } from "./shell/topbar.js";
import { clear, closeAllDialogs, fail, h, icon } from "./ui/index.js";
document.documentElement.dataset.theme = getTheme();
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
    if (!getMe() || getMe().MustChangePassword)
        return;
    const { path, query } = parseHash();
    const my = ++seq;
    closeAllDialogs();
    document.querySelectorAll(".side-panel").forEach((n) => n.remove());
    for (const r of ROUTES) {
        const m = path.match(r.re);
        if (!m)
            continue;
        const repId = path.startsWith("reports/") && !path.startsWith("reports/g/") ? path.slice(8) : "";
        const repGroup = repId ? reportGroups.find((g) => g.ids.includes(repId)) : undefined;
        const navHref = path.startsWith("reports/g/") ? `#/${path}` : repGroup ? `#/reports/g/${groupSlug(repGroup.group)}` : r.nav;
        markActive(navHref);
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
    if (me.Theme === "light" || me.Theme === "dark")
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
window.addEventListener("hashchange", render);
void boot();
