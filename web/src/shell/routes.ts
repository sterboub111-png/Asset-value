/** Page routes, the navigation tree and the permission each page needs. */
import { assetFormPage, assetsListPage } from "../pages/assets/assets.js";
import { dashboardPage } from "../pages/workspace/dashboard.js";
import { auditPage, depreciationPage, integrityPage, journalPage, periodsPage, transactionsPage } from "../pages/depreciation/depreciation.js";
import { maintenanceFormPage, maintenanceListPage } from "../pages/maintenance/maintenance.js";
import { reportPage, reportsGroupPage, reportsIndexPage } from "../pages/reports/reports.js";
import { chartsDashboardPage } from "../pages/reports/dashboard.js";
import { assetImportPage } from "../pages/assets/import.js";
import { assetLabelsPage } from "../pages/assets/labels.js";
import { countPage, countsListPage } from "../pages/assets/counts.js";
import { custodyFormPage, custodyListPage, handoverFormPage } from "../pages/contacts/custody.js";
import { employeeFormPage, employeesListPage } from "../pages/contacts/employees.js";
import { supplierFormPage, suppliersListPage } from "../pages/contacts/suppliers.js";
import { settingsPage } from "../pages/settings/settings.js";

export type PageFn = (root: HTMLElement, a: { args: string[]; query: URLSearchParams }) => Promise<void>;
export interface Route { re: RegExp; fn: PageFn; nav: string; crumb: string; }

export const ROUTES: Route[] = [
  { re: /^$/, fn: dashboardPage, nav: "#/", crumb: "Home" },
  { re: /^charts$/, fn: chartsDashboardPage, nav: "#/charts", crumb: "Dashboard" },
  { re: /^assets$/, fn: assetsListPage, nav: "#/assets", crumb: "All fixed assets" },
  { re: /^assets\/import$/, fn: assetImportPage, nav: "#/assets/import", crumb: "Import fixed assets" },
  { re: /^assets\/labels$/, fn: assetLabelsPage, nav: "#/assets/labels", crumb: "Asset labels" },
  { re: /^counts$/, fn: countsListPage, nav: "#/counts", crumb: "Physical counts" },
  { re: /^counts\/(\d+)$/, fn: countPage, nav: "#/counts", crumb: "Physical count" },
  { re: /^assets\/(new|\d+)$/, fn: assetFormPage, nav: "#/assets", crumb: "Fixed asset" },
  { re: /^maintenance$/, fn: maintenanceListPage, nav: "#/maintenance", crumb: "Maintenance orders" },
  { re: /^maintenance\/(new|\d+)$/, fn: maintenanceFormPage, nav: "#/maintenance", crumb: "Maintenance order" },
  { re: /^employees$/, fn: employeesListPage, nav: "#/employees", crumb: "Employees" },
  { re: /^employees\/(new|\d+)$/, fn: employeeFormPage, nav: "#/employees", crumb: "Employee" },
  { re: /^custody$/, fn: custodyListPage, nav: "#/custody", crumb: "Asset custody" },
  { re: /^custody\/(\d+)$/, fn: custodyFormPage, nav: "#/custody", crumb: "Custody record" },
  { re: /^custody\/(\d+)\/form$/, fn: handoverFormPage, nav: "#/custody", crumb: "Handover form" },
  { re: /^suppliers$/, fn: suppliersListPage, nav: "#/suppliers", crumb: "Suppliers" },
  { re: /^suppliers\/(new|\d+)$/, fn: supplierFormPage, nav: "#/suppliers", crumb: "Supplier" },
  { re: /^depreciation$/, fn: depreciationPage, nav: "#/depreciation", crumb: "Depreciation run" },
  { re: /^periods$/, fn: periodsPage, nav: "#/periods", crumb: "Depreciation periods" },
  { re: /^journal$/, fn: journalPage, nav: "#/journal", crumb: "Fixed asset journal" },
  { re: /^transactions$/, fn: transactionsPage, nav: "#/transactions", crumb: "Fixed asset transactions" },
  { re: /^audit$/, fn: auditPage, nav: "#/audit", crumb: "Audit log" },
  { re: /^integrity$/, fn: integrityPage, nav: "#/integrity", crumb: "Data checks" },
  { re: /^reports$/, fn: reportsIndexPage, nav: "#/reports", crumb: "Reports" },
  { re: /^reports\/g\/([\w-]+)$/, fn: reportsGroupPage, nav: "#/reports", crumb: "Reports" },
  { re: /^reports\/([\w-]+)$/, fn: reportPage, nav: "#/reports", crumb: "Reports" },
  { re: /^settings(?:\/(\w+))?$/, fn: settingsPage, nav: "#/settings", crumb: "Settings" },
];

/** The navigation pane: a few accounting tasks (QuickBooks-style); a task with pages opens to show them. */
export interface NavLink { label: string; href: string; }
export interface NavItem { label: string; icon: string; href: string; children?: NavLink[]; }

export const NAV: NavItem[] = [
  { label: "Home", icon: "home", href: "#/" },
  { label: "Fixed assets", icon: "asset", href: "#/assets", children: [
    { label: "All fixed assets", href: "#/assets" }, { label: "Physical counts", href: "#/counts" },
    { label: "Asset labels", href: "#/assets/labels" }, { label: "Import from Excel", href: "#/assets/import" }] },
  { label: "Depreciation", icon: "calc", href: "#/depreciation", children: [
    { label: "Depreciation run", href: "#/depreciation" }, { label: "Depreciation periods", href: "#/periods" }] },
  { label: "Maintenance", icon: "wrench", href: "#/maintenance" },
  { label: "Custody", icon: "user", href: "#/custody", children: [
    { label: "Asset custody", href: "#/custody" }, { label: "Employees", href: "#/employees" }] },
  { label: "Suppliers", icon: "truck", href: "#/suppliers" },
  { label: "Accounting", icon: "journal", href: "#/journal", children: [
    { label: "Fixed asset journal", href: "#/journal" }, { label: "Fixed asset transactions", href: "#/transactions" },
    { label: "Data checks", href: "#/integrity" }, { label: "Audit log", href: "#/audit" }] },
  { label: "Reports", icon: "report", href: "#/reports", children: [
    { label: "All reports", href: "#/reports" }, { label: "Dashboard", href: "#/charts" }] },
];
export const NAV_BOTTOM: NavItem[] = [{ label: "Settings", icon: "setup", href: "#/settings" }];

/** Permission needed to open a page (also decides which navigation entries a user sees). */
export function permFor(href: string): string | null {
  if (/^#\/assets\/(new|import)/.test(href)) return "assets.edit";
  if (/^#\/maintenance\/new/.test(href)) return "maintenance.edit";
  if (/^#\/(suppliers|employees)\/new/.test(href)) return "contacts.edit";
  if (/^#\/(assets|counts)/.test(href)) return "assets.view";
  if (/^#\/maintenance/.test(href)) return "maintenance.view";
  if (/^#\/(suppliers|employees)/.test(href)) return "contacts.view";
  if (/^#\/custody/.test(href)) return "custody.view";
  if (/^#\/(depreciation|periods)/.test(href)) return "depreciation.view";
  if (/^#\/(journal|transactions)/.test(href)) return "inquiries.view";
  if (/^#\/audit/.test(href)) return "audit.view";
  if (/^#\/(reports|charts|integrity)/.test(href)) return "reports.view";
  return null;
}
