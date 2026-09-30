import { api } from "../api.js";
import { t } from "../i18n.js";
import { DataGrid, Form, clear, fail, fastTab, guard, h, icon, page, ribbon, toast } from "../ui.js";
const fmtSize = (n) => (n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);
/** Creates a backup (database + attachments) and reports the result; used by the top-bar button and the Settings page. */
export async function runBackup() {
    try {
        const r = await api.post("/api/backups");
        toast(t("Backup created: {0} ({1})", r.name, fmtSize(r.size)), "ok");
        return r;
    }
    catch (e) {
        fail(e);
        return null;
    }
}
export async function backupPage(root) {
    const info = h("div", { class: "msgbar" });
    const grid = new DataGrid({ rows: [], search: false, limit: 500, empty: "No backups yet.", columns: [
            { key: "name", label: "File", render: (r) => h("a", { href: `/api/backups/${encodeURIComponent(r.name)}/download`, class: "lnk" }, r.name) },
            { key: "kind", label: "Type", render: (r) => t(r.kind === "auto" ? "Automatic" : "Manual") }, { key: "created", label: "Created" }, { key: "size", label: "Size", render: (r) => fmtSize(r.size) },
        ] });
    const days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].map((d, i) => ({ value: String(i), label: t(d) }));
    const sched = new Form([
        { name: "BackupSchedule", label: "Frequency", type: "select", required: true, options: [{ value: "OFF", label: t("Off") }, { value: "DAILY", label: t("Daily") }, { value: "WEEKLY", label: t("Weekly") },
                { value: "MONTHLY", label: t("Monthly") }, { value: "QUARTERLY", label: t("Quarterly") }], onChange: () => toggle() },
        { name: "BackupTime", label: "Time", type: "time", required: true },
        { name: "BackupWeekday", label: "Day of the week", type: "select", options: days },
        { name: "BackupDayOfMonth", label: "Day of the month", type: "number", step: "1", hint: "1-28. Quarterly backups run in January, April, July and October." },
        { name: "BackupKeep", label: "Automatic backups to keep", type: "number", step: "1", hint: "Older automatic backups are deleted. 0 keeps all." },
    ], {});
    const schedInfo = h("div", { class: "msgbar" });
    const toggle = () => {
        const m = sched.value("BackupSchedule");
        sched.wrapOf("BackupTime").style.display = sched.wrapOf("BackupKeep").style.display = m === "OFF" ? "none" : "";
        sched.wrapOf("BackupWeekday").style.display = m === "WEEKLY" ? "" : "none";
        sched.wrapOf("BackupDayOfMonth").style.display = m === "MONTHLY" || m === "QUARTERLY" ? "" : "none";
    };
    const saveSched = guard(async () => {
        if (!sched.validate())
            return;
        const v = sched.get();
        await api.put("/api/settings", { BackupSchedule: v.BackupSchedule, BackupTime: v.BackupTime || "02:00", BackupWeekday: v.BackupWeekday || "0", BackupDayOfMonth: v.BackupDayOfMonth || "1", BackupKeep: v.BackupKeep || "0" });
        toast(t("Backup schedule saved"), "ok");
        await load();
    });
    const load = async () => {
        try {
            const d = await api.get("/api/backups");
            const sc = d.schedule;
            sched.set("BackupSchedule", sc.mode);
            sched.set("BackupTime", sc.time);
            sched.set("BackupWeekday", String(sc.weekday));
            sched.set("BackupDayOfMonth", sc.dom);
            sched.set("BackupKeep", sc.keep);
            toggle();
            clear(schedInfo);
            schedInfo.append(sc.mode === "OFF" ? t("Automatic backup is off.") : `${t("Next automatic backup")}: ${sc.next_run}`, sc.last_run ? ` · ${t("Last automatic backup")}: ${sc.last_run}` : "", sc.last_result && sc.last_result.startsWith("Error") ? ` · ${sc.last_result}` : "");
            schedInfo.className = `msgbar ${sc.last_result && sc.last_result.startsWith("Error") ? "err" : ""}`;
            clear(info);
            info.append(t("Backups are saved in:"), " ", h("b", null, d.folder));
            grid.setRows(d.items);
        }
        catch (e) {
            fail(e);
        }
    };
    const rb = ribbon([[
            { label: t("Create backup now"), icon: "db", primary: true, onClick: guard(async () => { if (await runBackup())
                    await load(); }) },
            { label: t("Refresh"), icon: "refresh", onClick: load }
        ],
        [{ label: t("Save schedule"), icon: "save", onClick: saveSched }]], [t("Backup"), t("Schedule")]);
    const how = h("div", { class: "msgbar" }, t("A backup contains the database and all attachment files. To restore, stop the app and run the restore tool with the backup file:"), " ", h("code", null, "python tools/restore_backup.py backups/<file>.zip"));
    clear(root);
    root.append(page({ title: t("Backup"), subtitle: t("Settings"), ribbon: rb.el }, info, how, fastTab(t("Automatic backup"), h("div", null, schedInfo, sched.el, h("p", { style: "color:var(--ink-3);font-size:12px" }, t("Automatic backups run while Gooya Asset is open. If the computer was off at the scheduled time, the backup is taken as soon as the app starts."))), { open: true }), h("h2", { class: "sec" }, t("Backups")), grid.el).el);
    await load();
    void icon;
}
