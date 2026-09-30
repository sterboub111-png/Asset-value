/** Keyboard shortcuts: the catalog, the user's own overrides (kept in this browser) and key-combination helpers. */

export interface ShortcutDef {
  id: string;
  section: string;                 // English key, translated with t()
  label: string;                   // English key, translated with t()
  keys: string;                    // default combination, for example "Ctrl+S"
  act?: string;                    // what it does on the current page or shell: save, new, edit, delete, refresh, nav, theme, lang, backup, search, help
  href?: string;                   // or the page it opens
}

export const SECTIONS = ["General", "Fixed assets", "Contacts", "Maintenance", "Periodic tasks", "Inquiries", "Reports", "Settings"];

export const DEFAULTS: ShortcutDef[] = [
  { id: "save", section: "General", label: "Save the current form", keys: "Ctrl+S", act: "save" },
  { id: "new", section: "General", label: "New record on this page", keys: "Alt+N", act: "new" },
  { id: "edit", section: "General", label: "Edit the selected record", keys: "F2", act: "edit" },
  { id: "delete", section: "General", label: "Delete the selected or open record", keys: "Alt+Delete", act: "delete" },
  { id: "refresh", section: "General", label: "Refresh the list", keys: "Alt+R", act: "refresh" },
  { id: "search", section: "General", label: "Search assets", keys: "/", act: "search" },
  { id: "nav", section: "General", label: "Fold or unfold the navigation pane", keys: "Ctrl+B", act: "nav" },
  { id: "theme", section: "General", label: "Switch dark mode", keys: "Alt+M", act: "theme" },
  { id: "lang", section: "General", label: "Switch language", keys: "Alt+L", act: "lang" },
  { id: "backup", section: "General", label: "Backup now", keys: "Alt+Shift+B", act: "backup" },
  { id: "help", section: "General", label: "Show keyboard shortcuts", keys: "Shift+/", act: "help" },
  { id: "go-home", section: "General", label: "Go to the workspace", keys: "Alt+1", href: "#/" },
  { id: "go-assets", section: "Fixed assets", label: "All fixed assets", keys: "Alt+2", href: "#/assets" },
  { id: "go-asset-new", section: "Fixed assets", label: "New fixed asset", keys: "Alt+Shift+A", href: "#/assets/new" },
  { id: "go-suppliers", section: "Contacts", label: "Suppliers", keys: "Alt+3", href: "#/suppliers" },
  { id: "go-supplier-new", section: "Contacts", label: "New supplier", keys: "Alt+Shift+S", href: "#/suppliers/new" },
  { id: "go-employees", section: "Contacts", label: "Employees", keys: "Alt+4", href: "#/employees" },
  { id: "go-employee-new", section: "Contacts", label: "New employee", keys: "Alt+Shift+E", href: "#/employees/new" },
  { id: "go-custody", section: "Contacts", label: "Asset custody", keys: "Alt+5", href: "#/custody" },
  { id: "go-maint", section: "Maintenance", label: "Maintenance orders", keys: "Alt+6", href: "#/maintenance" },
  { id: "go-maint-new", section: "Maintenance", label: "New maintenance order", keys: "Alt+Shift+M", href: "#/maintenance/new" },
  { id: "go-depr", section: "Periodic tasks", label: "Depreciation run", keys: "Alt+7", href: "#/depreciation" },
  { id: "go-periods", section: "Periodic tasks", label: "Depreciation periods", keys: "Alt+8", href: "#/periods" },
  { id: "go-journal", section: "Inquiries", label: "Fixed asset journal", keys: "Alt+9", href: "#/journal" },
  { id: "go-trans", section: "Inquiries", label: "Fixed asset transactions", keys: "Alt+Shift+T", href: "#/transactions" },
  { id: "go-audit", section: "Inquiries", label: "Audit log", keys: "Alt+Shift+L", href: "#/audit" },
  { id: "go-reports", section: "Reports", label: "Reports", keys: "Alt+0", href: "#/reports" },
  { id: "go-settings", section: "Settings", label: "Settings", keys: "Alt+Shift+G", href: "#/settings" },
  { id: "go-shortcuts", section: "Settings", label: "Keyboard shortcuts", keys: "Alt+Shift+K", href: "#/settings/shortcuts" },
];

const KEY = "usool.shortcuts";
let overrides: Record<string, string> = {};
try { overrides = JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch { overrides = {}; }
const persist = () => { try { localStorage.setItem(KEY, JSON.stringify(overrides)); } catch { /* storage unavailable: the change lasts until reload */ } };

/** The combination now assigned to a shortcut ("" = switched off). */
export const keysOf = (id: string): string => {
  const own = overrides[id];
  return own !== undefined ? own : DEFAULTS.find((d) => d.id === id)?.keys ?? "";
};
export const isCustom = (id: string): boolean => id in overrides;
export function setKeys(id: string, combo: string): void { overrides[id] = combo; persist(); }
export function resetKeys(id?: string): void { if (id) delete overrides[id]; else overrides = {}; persist(); }

/** Which shortcut owns this combination (optionally ignoring one). */
export const ownerOf = (combo: string, except?: string): ShortcutDef | undefined =>
  combo ? DEFAULTS.find((d) => d.id !== except && keysOf(d.id).toLowerCase() === combo.toLowerCase()) : undefined;

// ---------------------------------------------------------------- key combinations
const MODIFIER_CODES = /^(Control|Shift|Alt|Meta)(Left|Right)$/;
const RESERVED = new Set(["Ctrl+C", "Ctrl+V", "Ctrl+X", "Ctrl+A", "Ctrl+Z", "Ctrl+Y", "Ctrl+P", "Ctrl+F", "Ctrl+W", "Ctrl+T", "Ctrl+N", "Ctrl+Q", "Ctrl+R",
  "Ctrl+L", "Ctrl+D", "Ctrl+H", "Ctrl+J", "Ctrl+U", "Ctrl+O", "Ctrl+Tab", "Alt+F4", "Alt+Tab", "F5", "F11", "F12", "Ctrl+Shift+Delete"]);

/** Layout-independent name of the pressed key (works on the Arabic keyboard too), or null for a lone modifier. */
function keyName(e: KeyboardEvent): string | null {
  if (MODIFIER_CODES.test(e.code)) return null;
  const c = e.code;
  if (/^Key[A-Z]$/.test(c)) return c.slice(3);
  if (/^Digit\d$/.test(c)) return c.slice(5);
  if (/^Numpad\d$/.test(c)) return c.slice(6);
  const named: Record<string, string> = { Slash: "/", Comma: ",", Period: ".", Semicolon: ";", Quote: "'", Minus: "-", Equal: "=", Backslash: "\\", BracketLeft: "[", BracketRight: "]", Backquote: "`" };
  if (named[c]) return named[c];
  return e.key.length === 1 ? e.key.toUpperCase() : e.key === " " ? "Space" : e.key;
}

/** "Ctrl+Alt+Shift+Key" for a keyboard event (null while only modifiers are down). */
export function comboOf(e: KeyboardEvent): string | null {
  const k = keyName(e);
  if (!k) return null;
  return [e.ctrlKey || e.metaKey ? "Ctrl" : "", e.altKey ? "Alt" : "", e.shiftKey ? "Shift" : "", k].filter(Boolean).join("+");
}

/** Why a combination cannot be used, or "" when it is fine. */
export function problemWith(combo: string): string {
  if (!combo) return "Press the new key combination.";
  const parts = combo.split("+");
  const key = parts[parts.length - 1];
  const hasMod = parts.length > 1;
  const fn = /^F([1-9]|1[0-2])$/.test(key);
  if (!hasMod && !fn && key !== "/") return "Use Ctrl or Alt with the key (or a function key).";
  if (RESERVED.has(combo)) return "This combination is used by the browser.";
  return "";
}

/** A combination typed in a text field must not fire a shortcut, unless it uses Ctrl or Alt. */
export const firesWhileTyping = (combo: string): boolean => /^(Ctrl|Alt)\+|^F\d+$/.test(combo);

/** Set while the shortcuts page listens for a new combination, so nothing else reacts to the keys. */
export const capture = { on: false };
