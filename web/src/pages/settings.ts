import { t } from "../i18n.js";
import { clear, h, icon, page } from "../ui.js";
import { backupPage } from "./backup.js";
import { masterPage, parametersPage } from "./setup.js";

type Args = { args: string[]; query: URLSearchParams };

export const SETTINGS_SECTIONS = [
  { id: "parameters", label: "Fixed asset parameters", icon: "setup" },
  { id: "categories", label: "Fixed asset groups", icon: "asset" },
  { id: "methods", label: "Depreciation methods", icon: "calc" },
  { id: "locations", label: "Locations", icon: "home" },
  { id: "costcenters", label: "Cost centers", icon: "list" },
  { id: "glaccounts", label: "Ledger accounts", icon: "journal" },
  { id: "backup", label: "Backup", icon: "db" },
];

/** One Settings area: a section list on the side and the chosen section on the right. */
export async function settingsPage(root: HTMLElement, a: Args): Promise<void> {
  const id = SETTINGS_SECTIONS.some((s) => s.id === a.args[0]) ? a.args[0] : "parameters";
  const side = h("nav", { class: "settings-nav", "aria-label": t("Settings") }, h("h6", null, t("Settings")),
    ...SETTINGS_SECTIONS.map((s) => h("a", { href: `#/settings/${s.id}`, class: s.id === id ? "active" : "" }, icon(s.icon), h("span", null, t(s.label)))));
  const content = h("div", { class: "settings-content" });
  clear(root);
  root.append(h("div", { class: "settings" }, side, content));
  if (id === "parameters") await parametersPage(content, a);
  else if (id === "backup") await backupPage(content);
  else await masterPage(content, { args: [id], query: a.query });
  void page;
}
