import { api } from "../api.js";
import { t } from "../i18n.js";
import type { Rec } from "../types.js";
import { DataGrid, clear, fail, guard, h, icon, page, ribbon, toast } from "../ui.js";

const fmtSize = (n: number) => (n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

/** Creates a backup (database + attachments) and reports the result; used by the top-bar button and the Settings page. */
export async function runBackup(): Promise<Rec | null> {
  try {
    const r = await api.post<Rec>("/api/backups");
    toast(t("Backup created: {0} ({1})", r.name, fmtSize(r.size)), "ok");
    return r;
  } catch (e) { fail(e); return null; }
}

export async function backupPage(root: HTMLElement): Promise<void> {
  const info = h("div", { class: "msgbar" });
  const grid = new DataGrid({ rows: [], search: false, limit: 500, empty: "No backups yet.", columns: [
    { key: "name", label: "File", render: (r) => h("a", { href: `/api/backups/${encodeURIComponent(r.name)}/download`, class: "lnk" }, r.name) },
    { key: "created", label: "Created" }, { key: "size", label: "Size", render: (r) => fmtSize(r.size) },
  ] });
  const load = async () => {
    try {
      const d = await api.get<Rec>("/api/backups");
      clear(info); info.append(t("Backups are saved in:"), " ", h("b", null, d.folder));
      grid.setRows(d.items);
    } catch (e) { fail(e); }
  };
  const rb = ribbon([[
    { label: t("Create backup now"), icon: "db", primary: true, onClick: guard(async () => { if (await runBackup()) await load(); }) },
    { label: t("Refresh"), icon: "refresh", onClick: load }]]);
  const how = h("div", { class: "msgbar" }, t("A backup contains the database and all attachment files. To restore, stop the app and run the restore tool with the backup file:"), " ",
    h("code", null, "python tools/restore_backup.py backups/<file>.zip"));
  clear(root);
  root.append(page({ title: t("Backup"), subtitle: t("Settings"), ribbon: rb.el }, info, how, grid.el).el);
  await load();
  void icon;
}
