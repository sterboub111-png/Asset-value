/** One global keyboard handler: turns key combinations into the shortcut actions defined in core/shortcuts.ts. */
import { can, getMe } from "../core/session.js";
import { DEFAULTS, capture, comboOf, firesWhileTyping, keysOf } from "../core/shortcuts.js";
import { runSave } from "../ui/index.js";
import { permFor } from "./routes.js";

const typing = (el: EventTarget | null): boolean => {
  const n = el as HTMLElement | null;
  return !!n && (n.tagName === "INPUT" || n.tagName === "TEXTAREA" || n.tagName === "SELECT" || n.isContentEditable);
};

/** Click the ribbon button of the page on screen that carries this action (New, Delete, ...), if it is enabled. */
function ribbonAct(act: string): boolean {
  const b = document.querySelector<HTMLButtonElement>(`.main .ribbon button[data-act="${act}"]:not(:disabled)`);
  if (!b) return false;
  b.click();
  return true;
}
const clickShell = (act: string): boolean => {
  const b = document.querySelector<HTMLButtonElement>(`.topbar [data-act="${act}"]:not(:disabled)`);
  b?.click();
  return !!b;
};

function run(act: string): boolean {
  switch (act) {
    case "save": return runSave() || ribbonAct("save");
    case "new": case "edit": case "delete": case "refresh": return ribbonAct(act);
    case "search": { const i = document.querySelector<HTMLInputElement>(".tb-search input"); i?.focus(); return !!i; }
    case "help": location.hash = "#/settings/shortcuts"; return true;
    default: return clickShell(act);   // nav, theme, lang, backup
  }
}

export function initKeyboard(): void {
  document.addEventListener("keydown", (e) => {
    if (capture.on || e.repeat || !getMe() || !document.querySelector(".shell")) return;
    const combo = comboOf(e);
    if (!combo) return;
    if (typing(e.target) && !firesWhileTyping(combo)) return;
    const def = DEFAULTS.find((d) => keysOf(d.id).toLowerCase() === combo.toLowerCase());
    if (!def) return;
    if (def.href) {
      e.preventDefault();
      if (can(permFor(def.href)) && location.hash !== def.href) location.hash = def.href;
      return;
    }
    if (def.act && run(def.act)) e.preventDefault();
    else if (def.act === "save" && combo === "Ctrl+S") e.preventDefault();   // never open the browser's "save page" dialog
  });
}
