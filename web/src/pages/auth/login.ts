import { api } from "../../core/api.js";
import { getLang, setLang, t } from "../../core/i18n.js";
import { Me, getTheme, initials, setTheme } from "../../core/session.js";
import { clear, h, icon } from "../../ui/index.js";

const LAST = "gooya.lastUser";
interface Known { UserName: string; FullName: string; FullNameAr?: string | null; }
const readKnown = (): Known | null => { try { const v = JSON.parse(localStorage.getItem(LAST) || "null"); return v && v.UserName ? v : null; } catch { return null; } };
const writeKnown = (m: Me | null) => { try { if (m) localStorage.setItem(LAST, JSON.stringify({ UserName: m.UserName, FullName: m.FullName, FullNameAr: m.FullNameAr })); else localStorage.removeItem(LAST); } catch { /* ignore */ } };
const shownName = (k: Known) => (getLang() === "ar" && k.FullNameAr ? k.FullNameAr : k.FullName);

function greeting(): string {
  const hr = new Date().getHours();
  return hr < 12 ? t("Good morning") : hr < 18 ? t("Good afternoon") : t("Good evening");
}

/** Sign-in page: a Microsoft-style two-step card (user name, then password) that remembers who signed in last. */
export function showLogin(app: HTMLElement, needsSetup: boolean, onDone: (me: Me) => void, rerender: () => void, notice?: string): void {
  clear(app);
  let known: Known | null = needsSetup ? null : readKnown();
  let step: "user" | "password" = known ? "password" : "user";

  const err = h("div", { class: "msgbar err", role: "alert", style: "display:none" });
  const field = (id: string, label: string, type: string, extra: Record<string, any> = {}) => {
    const input = h("input", { id, type, ...extra }) as HTMLInputElement;
    return { input, wrap: h("div", { class: "field" }, h("label", { for: id }, label), input) };
  };
  const full = field("l_full", t("Full name"), "text", { autocomplete: "name", maxlength: 120 });
  const user = field("l_user", t("User name"), "text", { autocomplete: "username", autocapitalize: "none", spellcheck: "false", maxlength: 40 });
  const pass = field("l_pass", t("Password"), "password", { autocomplete: needsSetup ? "new-password" : "current-password" });
  const conf = field("l_conf", t("Confirm password"), "password", { autocomplete: "new-password" });
  if (known) user.input.value = known.UserName;

  // show / hide password + caps lock hint
  const eye = h("button", { class: "pw-eye", type: "button", "aria-label": t("Show password"), title: t("Show password") }, icon("eye"));
  eye.addEventListener("click", () => {
    const show = pass.input.type === "password";
    pass.input.type = show ? "text" : "password"; eye.replaceChildren(icon(show ? "eyeoff" : "eye"));
    pass.input.focus();
  });
  const caps = h("div", { class: "hint caps", style: "display:none" }, icon("warn"), " ", t("Caps Lock is on"));
  pass.wrap.append(eye, caps); pass.wrap.classList.add("has-eye");
  for (const el of [pass.input, user.input]) el.addEventListener("keyup", (e) => { caps.style.display = (e as KeyboardEvent).getModifierState?.("CapsLock") ? "" : "none"; });

  // identity chip shown on the password step (click to use another account)
  const chip = h("button", { class: "id-chip", type: "button", title: t("Use another account") });
  const drawChip = () => {
    clear(chip);
    const typed = user.input.value.trim();
    const name = known ? shownName(known) : typed;
    chip.append(icon("back"), h("span", { class: "avatar" }, initials(name || "?")),
      h("span", { class: "id-text" }, h("b", null, name), name !== typed ? h("small", null, typed) : null));
  };
  chip.addEventListener("click", () => { known = null; writeKnown(null); user.input.value = ""; pass.input.value = ""; go("user"); });

  const title = h("h1", null);
  const sub = h("p", { class: "login-sub" });
  const bar = h("div", { class: "login-bar", "aria-hidden": "true" }, h("i"));
  const btn = h("button", { class: "btn primary login-btn", type: "submit" });
  const btnLabel = h("span", null);
  btn.append(h("span", { class: "spin", "aria-hidden": "true" }), btnLabel);
  const notes = notice ? h("div", { class: "msgbar warn" }, notice) : null;
  const panes = h("div", { class: "login-panes" }, needsSetup ? full.wrap : null, user.wrap, pass.wrap, needsSetup ? conf.wrap : null);
  const form = h("form", { class: "login-card", novalidate: true },
    bar, h("div", { class: "login-logo" }, h("span", { class: "lg" }, icon("asset")), h("span", { class: "lw" }, t("Usool"))),
    needsSetup ? null : chip, title, sub, notes, err, panes, btn);

  function go(next: "user" | "password", animate = true) {
    step = next;
    err.style.display = "none";
    const second = next === "password" && !needsSetup;
    user.wrap.style.display = second ? "none" : "";       // the name stays in the form (password managers), it is just not shown
    pass.wrap.style.display = next === "user" && !needsSetup ? "none" : "";
    chip.style.display = second ? "" : "none";
    if (needsSetup) { title.textContent = t("Welcome to Usool"); sub.textContent = t("Create the administrator account to get started."); btnLabel.textContent = t("Create administrator"); }
    else if (next === "user") { title.textContent = t("Sign in"); sub.textContent = t("Enter your user name and password."); btnLabel.textContent = t("Next"); }
    else { drawChip(); title.textContent = known ? `${greeting()}, ${shownName(known).split(" ")[0]}` : t("Enter password"); sub.textContent = t("Enter the password for your account."); btnLabel.textContent = t("Sign in"); }
    if (animate) { panes.classList.remove("swap"); void panes.offsetWidth; panes.classList.add("swap"); }
    (needsSetup ? full.input : next === "user" ? user.input : pass.input).focus();
  }

  const fail = (msg: string) => {
    err.textContent = msg; err.style.display = "block";
    form.classList.remove("shake"); void form.offsetWidth; form.classList.add("shake");
  };
  const busy = (on: boolean) => {
    form.classList.toggle("busy", on); btn.disabled = on;
    [user.input, pass.input, full.input, conf.input].forEach((i) => { i.disabled = on; });
    if (!on) (step === "password" || needsSetup ? pass.input : user.input).focus();
  };

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    err.style.display = "none";
    if (!needsSetup && step === "user") {   // step 1 only moves on: the server never reveals whether a name exists
      if (!user.input.value.trim()) { fail(t("Enter your user name.")); user.input.focus(); return; }
      go("password"); return;
    }
    if (!pass.input.value || !user.input.value.trim() || (needsSetup && !full.input.value.trim())) { fail(t("Fill in the required fields.")); return; }
    if (needsSetup && pass.input.value !== conf.input.value) { fail(t("The passwords do not match")); conf.input.focus(); return; }
    busy(true);
    try {
      const me = needsSetup
        ? await api.post<Me>("/api/auth/setup", { UserName: user.input.value.trim(), FullName: full.input.value.trim(), Password: pass.input.value, ConfirmPassword: conf.input.value })
        : await api.post<Me>("/api/auth/login", { UserName: user.input.value.trim(), Password: pass.input.value });
      writeKnown(me); form.classList.add("done");
      onDone(me);
    } catch (ex) {
      pass.input.value = ""; conf.input.value = "";
      busy(false);
      fail(ex instanceof Error ? t(ex.message) : String(ex));
    }
  });

  // page chrome: language and theme, a small clock, footer
  const langBtn = h("button", { class: "login-tool", type: "button", onclick: () => { setLang(getLang() === "ar" ? "en" : "ar"); rerender(); } }, icon("globe"), getLang() === "ar" ? "English" : "العربية");
  const themeBtn = h("button", { class: "login-tool", type: "button", "aria-label": t("Dark mode"), title: t("Dark mode"), onclick: () => { setTheme(getTheme() === "dark" ? "light" : "dark"); themeBtn.replaceChildren(icon(getTheme() === "dark" ? "sun" : "moon")); } }, icon(getTheme() === "dark" ? "sun" : "moon"));
  const clock = h("div", { class: "login-clock" }, h("b", null), h("span", null));
  const tick = () => {
    const d = new Date(); const loc = getLang() === "ar" ? "ar-SA-u-nu-latn" : "en-GB";
    clock.querySelector("b")!.textContent = d.toLocaleTimeString(loc, { hour: "2-digit", minute: "2-digit" });
    clock.querySelector("span")!.textContent = d.toLocaleDateString(loc, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  };
  tick();
  const timer = window.setInterval(() => { if (!clock.isConnected) window.clearInterval(timer); else tick(); }, 20000);

  app.append(h("div", { class: "login-shell" }, h("div", { class: "login-bg", "aria-hidden": "true" }, h("i"), h("i"), h("i")),
    h("main", { class: "login-main" }, h("div", { class: "login-tools" }, langBtn, themeBtn), form),
    clock, h("footer", { class: "login-foot" }, `${t("Usool")} · ${t("Fixed asset register")}`)));
  go(step, false);
}
