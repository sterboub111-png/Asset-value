import { t } from "../../core/i18n.js";
import { can } from "../../core/session.js";
import { clear, h } from "../../ui/index.js";
import { accountPage } from "./account.js";
import { backupPage } from "./backup.js";
import { shortcutsPage } from "./shortcuts.js";
import { rolesPage, usersPage } from "./users.js";
import { masterPage, parametersPage, taxPage } from "./setup.js";

type Args = { args: string[]; query: URLSearchParams };

export interface SettingsSection { id: string; label: string; group: string; perm?: string; }

/** Grouped by who needs them: personal preferences, company set-up, fixed asset set-up, accounting, administration. */
export const SETTINGS_GROUPS = [
  { id: "personal", label: "Personal" }, { id: "company", label: "Company" }, { id: "setup", label: "Fixed asset setup" },
  { id: "accounting", label: "Accounting" }, { id: "admin", label: "Administration" },
];

export const SETTINGS_SECTIONS: SettingsSection[] = [
  { id: "account", label: "My account", group: "personal" },
  { id: "shortcuts", label: "Keyboard shortcuts", group: "personal" },
  { id: "parameters", label: "Fixed asset parameters", group: "company", perm: "settings.view" },
  { id: "tax", label: "Tax (VAT)", group: "company", perm: "settings.view" },
  { id: "currencies", label: "Currencies", group: "company", perm: "settings.view" },
  { id: "branches", label: "Branches", group: "company", perm: "settings.view" },
  { id: "categories", label: "Fixed asset groups", group: "setup", perm: "settings.view" },
  { id: "methods", label: "Depreciation methods", group: "setup", perm: "settings.view" },
  { id: "locations", label: "Locations", group: "setup", perm: "settings.view" },
  { id: "costcenters", label: "Cost centers", group: "setup", perm: "settings.view" },
  { id: "glaccounts", label: "Ledger accounts", group: "accounting", perm: "settings.view" },
  { id: "users", label: "Users", group: "admin", perm: "users.manage" },
  { id: "roles", label: "Roles and permissions", group: "admin", perm: "users.manage" },
  { id: "backup", label: "Backup", group: "admin", perm: "backup.manage" },
];

/** The bar above the settings: Back (one step) and the path Settings / Area / Setting. */
function trail(groupLabel: string, sectionLabel: string): HTMLElement {
  const back = h("button", { class: "btn", type: "button", onclick: () => (history.length > 1 ? history.back() : (location.hash = "#/settings")) }, t("Back"));
  return h("div", { class: "settings-bar" }, back,
    h("nav", { class: "trail", "aria-label": t("Settings") }, h("span", null, t("Settings")), h("span", { class: "sep" }, "/"), h("span", null, groupLabel), h("span", { class: "sep" }, "/"), h("span", { class: "cur" }, sectionLabel)));
}

/** One Settings area: the sections (grouped) on the side and the chosen section on the right. */
export async function settingsPage(root: HTMLElement, a: Args): Promise<void> {
  const sections = SETTINGS_SECTIONS.filter((s) => can(s.perm));
  const section = sections.find((s) => s.id === a.args[0]) || sections[0];
  const links: Node[] = [];
  let last = "";
  for (const s of sections) {
    if (s.group !== last) { links.push(h("h6", null, t(SETTINGS_GROUPS.find((g) => g.id === s.group)!.label))); last = s.group; }
    links.push(h("a", { href: `#/settings/${s.id}`, class: s.id === section.id ? "active" : "" }, t(s.label)));
  }
  const side = h("nav", { class: "settings-nav", "aria-label": t("Settings") }, ...links);
  const body = h("div", { class: "settings-body" });
  const content = h("div", { class: "settings-content" }, trail(t(SETTINGS_GROUPS.find((g) => g.id === section.group)!.label), t(section.label)), body);
  clear(root);
  root.append(h("div", { class: "settings" }, side, content));
  const id = section.id;
  if (id === "account") await accountPage(body, a, () => location.reload());
  else if (id === "shortcuts") await shortcutsPage(body);
  else if (id === "users") await usersPage(body, a);
  else if (id === "roles") await rolesPage(body, a);
  else if (id === "parameters") await parametersPage(body, a);
  else if (id === "backup") await backupPage(body);
  else if (id === "tax") await taxPage(body, a);
  else await masterPage(body, { args: [id], query: a.query });
}
