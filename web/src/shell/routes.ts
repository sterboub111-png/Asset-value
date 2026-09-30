/** Page routes, the navigation tree and the permission each page needs. */
import { assetFormPage, assetsListPage } from "../pages/assets/assets.js";
import { dashboardPage } from "../pages/workspace/dashboard.js";
import { auditPage, depreciationPage, journalPage, periodsPage, transactionsPage } from "../pages/depreciation/depreciation.js";
import { maintenanceFormPage, maintenanceListPage } from "../pages/maintenance/maintenance.js";
import { reportPage, reportsGroupPage, reportsIndexPage } from "../pages/reports/reports.js";
import { custodyFormPage, custodyListPage, handoverFormPage } from "../pages/contacts/custody.js";
import { employeeFormPage, employeesListPage } from "../pages/contacts/employees.js";
import { supplierFormPage, suppliersListPage } from "../pages/contacts/suppliers.js";
import { settingsPage } from "../pages/settings/settings.js";

export type PageFn = (root: HTMLElement, a: { args: string[]; query: URLSearchParams }) => Promise<void>;
export interface Route { re: RegExp; fn: PageFn; nav: string; crumb: string; }

export const ROUTES: Route[] = [
  { re: /^$/, fn: dashboardPage, nav: "#/", crumb: "Workspace" },
  { re: /^assets$/, fn: assetsListPage, nav: "#/assets", crumb: "All fixed assets" },
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
  { re: /^reports$/, fn: reportsIndexPage, nav: "#/reports", crumb: "Reports" },
  { re: /^reports\/g\/([\w-]+)$/, fn: reportsGroupPage, nav: "#/reports", crumb: "Reports" },
  { re: /^reports\/([\w-]+)$/, fn: reportPage, nav: "#/reports", crumb: "Reports" },
  { re: /^settings(?:\/(\w+))?$/, fn: settingsPage, nav: "#/settings", crumb: "Settings" },
];

export interface NavItem { label: string; icon: string; href: string; }
export interface NavSection { id: string; section: string; items: NavItem[]; reports?: boolean; }

export const NAV: NavSection[] = [
  { id: "assets", section: "Fixed assets", items: [{ label: "Workspace", icon: "home", href: "#/" }, { label: "All fixed assets", icon: "asset", href: "#/assets" }] },
  { id: "contacts", section: "Contacts", items: [
    { label: "Suppliers", icon: "truck", href: "#/suppliers" },
    { label: "Employees", icon: "user", href: "#/employees" },
    { label: "Asset custody", icon: "transfer", href: "#/custody" }] },
  { id: "maint", section: "Maintenance", items: [{ label: "Maintenance orders", icon: "wrench", href: "#/maintenance" }] },
  { id: "periodic", section: "Periodic tasks", items: [{ label: "Depreciation run", icon: "calc", href: "#/depreciation" }, { label: "Depreciation periods", icon: "calendar", href: "#/periods" }] },
  { id: "inq", section: "Inquiries", items: [{ label: "Fixed asset journal", icon: "journal", href: "#/journal" }, { label: "Fixed asset transactions", icon: "list", href: "#/transactions" }, { label: "Audit log", icon: "audit", href: "#/audit" }] },
  { id: "reports", section: "Reports", reports: true, items: [] },
  { id: "setup", section: "Setup", items: [{ label: "Settings", icon: "setup", href: "#/settings" }] },
];

/** Permission needed to open a page (also decides which navigation entries a user sees). */
export function permFor(href: string): string | null {
  if (/^#\/assets\/new/.test(href)) return "assets.edit";
  if (/^#\/maintenance\/new/.test(href)) return "maintenance.edit";
  if (/^#\/(suppliers|employees)\/new/.test(href)) return "contacts.edit";
  if (/^#\/assets/.test(href)) return "assets.view";
  if (/^#\/maintenance/.test(href)) return "maintenance.view";
  if (/^#\/(suppliers|employees)/.test(href)) return "contacts.view";
  if (/^#\/custody/.test(href)) return "custody.view";
  if (/^#\/(depreciation|periods)/.test(href)) return "depreciation.view";
  if (/^#\/(journal|transactions)/.test(href)) return "inquiries.view";
  if (/^#\/audit/.test(href)) return "audit.view";
  if (/^#\/reports/.test(href)) return "reports.view";
  return null;
}
