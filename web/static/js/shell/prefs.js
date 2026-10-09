/** Personal preferences and the backup, as commands: they live in Settings, and the keyboard shortcuts run them from anywhere. */
import { api } from "../core/api.js";
import { getLang, setLang, t } from "../core/i18n.js";
import { can, getMe, getTheme, nextTheme, setMe, setTheme, themeLabel } from "../core/session.js";
import { runBackup } from "../pages/settings/backup.js";
import { toast } from "../ui/index.js";
/** Arabic <-> English, kept on the profile; the page is redrawn in the new language. */
export async function switchLanguage() {
    const next = getLang() === "ar" ? "en" : "ar";
    setLang(next);
    try {
        await api.put("/api/auth/profile", { Language: next });
    }
    catch { /* keep the local choice */ }
    const me = getMe();
    if (me)
        setMe({ ...me, Language: next });
    location.reload();
}
/** Light -> dark -> automatic, kept on the profile. */
export function cycleAppearance() {
    setTheme(nextTheme());
    void api.put("/api/auth/profile", { Theme: getTheme() }).catch(() => undefined);
    toast(`${t("Appearance")}: ${t(themeLabel())}`);
}
export async function backupNow() {
    if (!can("backup.manage")) {
        toast(t("You do not have permission to do this"), "err");
        return;
    }
    await runBackup();
}
