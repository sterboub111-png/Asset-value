/** Import fixed assets from Excel: download the template, choose the file, review every row, import the ready ones.
 *  The server checks each row with the asset form's own rules (services/importer.py); nothing is saved before "Import". */
import { api, invalidateLookups } from "../../core/api.js";
import { getLang, t } from "../../core/i18n.js";
import type { Col, Rec } from "../../core/types.js";
import { DataGrid, clear, combo, fmtMoney, guard, h, page, pill, ribbon, toast } from "../../ui/index.js";

type Msg = { t: string; a: string[] };
const say = (m: Msg) => t(m.t, ...m.a.map((x) => t(x)));   // column names are translated as well

export async function assetImportPage(root: HTMLElement): Promise<void> {
  let file: File | null = null;
  let preview: Rec | null = null;
  const stage = h("div", { class: "imp-stage" });

  // step 1: the template
  const template = h("a", { class: "btn", href: `/api/assets/import-template?lang=${getLang()}`, download: "usool-assets-import.xlsx" }, t("Download the template"));
  // step 2: the file
  const input = h("input", { type: "file", accept: ".xlsx,.csv", style: "display:none" }) as HTMLInputElement;
  const drop = h("div", { class: "drop imp-drop", tabindex: 0, role: "button" }, h("b", null, t("Choose an Excel or CSV file")), h("span", null, t("or drop it here")));
  drop.addEventListener("click", () => input.click());
  drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); const f = e.dataTransfer?.files[0]; if (f) void check(f); });
  input.addEventListener("change", () => { const f = input.files?.[0]; if (f) void check(f); input.value = ""; });

  const step = (n: number, title: string, body: Node, sub?: string) =>
    h("section", { class: "imp-step" }, h("div", { class: "imp-n" }, String(n)), h("div", { class: "imp-b" }, h("h3", null, title), sub ? h("p", null, sub) : null, body));

  async function check(f: File) {
    file = f;
    clear(stage); stage.append(h("div", { class: "loading" }, t("Checking the file…")));
    try { preview = await api.upload<Rec>("/api/assets/import?dry=1", f, {}); }
    catch (e) { clear(stage); stage.append(h("div", { class: "msgbar err" }, e instanceof Error ? t(e.message) : String(e))); return; }
    showPreview();
  }

  function showPreview() {
    const p = preview!;
    const rows: Rec[] = (p.rows as Rec[]).map((r) => ({ ...r, Messages: [...r.errors, ...r.warnings].map(say).join(" · ") }));
    const label = { ok: "Ready", warning: "Ready with warning", error: "Error" } as Record<string, string>;
    const tone = { ok: "ok", warning: "warn", error: "err" } as Record<string, string>;
    const cols: Col[] = [
      { key: "row", label: "Row", type: "int", width: 50 },
      { key: "status", label: "Status", render: (r) => pill(label[r.status], tone[r.status]) },
      { key: "AssetName", label: "Name" }, { key: "Group", label: "Group" },
      { key: "AcquisitionDate", label: "Acquired", type: "date" }, { key: "PurchaseAmount", label: "Invoice amount", type: "money" },
      { key: "AcquisitionCost", label: "Net cost", type: "money" }, { key: "VatAmount", label: "VAT", type: "money" },
      { key: "Messages", label: "Notes", render: (r) => h("span", { class: r.status === "error" ? "neg" : "", title: r.Messages }, r.Messages) },
    ];
    const grid = new DataGrid({ columns: cols, rows, totals: ["AcquisitionCost", "VatAmount"], limit: 1000, exportName: "import-check" });
    const show = combo([{ value: "error", label: t("Errors") }, { value: "warning", label: t("Warnings") }, { value: "ok", label: t("Ready") }],
      { placeholder: t("All rows"), label: t("Show"), width: 170 });
    show.addEventListener("change", () => grid.setRows(show.value ? rows.filter((r) => r.status === show.value) : rows));
    const skip = h("input", { type: "checkbox" }) as HTMLInputElement;
    const go = h("button", { class: "btn primary", type: "button" }, t("Import {0} asset(s)", p.ready)) as HTMLButtonElement;
    const sync = () => { go.disabled = !p.ready || (p.errors > 0 && !skip.checked); };
    skip.addEventListener("change", sync); sync();
    go.addEventListener("click", guard(async () => {
      const res = await api.upload<Rec>(`/api/assets/import${p.errors ? "?skip=1" : ""}`, file!, {});
      invalidateLookups();
      toast(t("{0} asset(s) created", res.created.length), "ok");
      clear(stage);
      stage.append(h("div", { class: "msgbar ok" }, t("{0} asset(s) created", res.created.length), res.skipped ? ` · ${t("{0} row(s) skipped", res.skipped)}` : ""),
        h("div", { class: "imp-done" }, ...res.created.slice(0, 12).map((c: Rec) => h("a", { href: `#/assets/${c.AssetID}` }, `${c.AssetCode} · ${c.AssetName}`)),
          res.created.length > 12 ? h("span", null, t("and {0} more", res.created.length - 12)) : null),
        h("div", { class: "imp-actions" }, h("a", { class: "btn primary", href: "#/assets" }, t("Open fixed assets")),
          h("button", { class: "btn", type: "button", onclick: () => { clear(stage); input.click(); } }, t("Import another file"))));
    }));
    clear(stage);
    stage.append(
      h("div", { class: "imp-sum" },
        h("span", null, h("b", null, file!.name)),
        h("span", null, t("{0} row(s)", p.total)), h("span", { class: "ok" }, t("{0} ready", p.ready)),
        p.errors ? h("span", { class: "err" }, t("{0} with errors", p.errors)) : null,
        h("span", null, t("Net cost"), " ", h("b", null, fmtMoney(p.cost)))),
      p.errors ? h("div", { class: "msgbar warn" }, t("Rows with errors are not imported. Fix them in the file and choose it again, or import the rows that are ready.")) : "",
      h("div", { class: "imp-tools" }, show), grid.el,
      h("div", { class: "imp-actions" }, go, p.errors ? h("label", { class: "imp-skip" }, skip, t("Import only the rows that are ready")) : null,
        h("button", { class: "btn", type: "button", onclick: () => input.click() }, t("Choose another file"))));
  }

  const rb = ribbon([[{ label: t("Back to list"), icon: "back", onClick: () => (location.hash = "#/assets") }]]);
  clear(root);
  root.append(page({ title: t("Import fixed assets"), subtitle: t("Fixed assets"), ribbon: rb.el },
    h("div", { class: "imp" },
      step(1, t("Download the template"), template, t("One row per asset. Required columns are marked *. The second sheet lists the groups, locations, cost centers and suppliers you can use (code or name).")),
      step(2, t("Choose the file"), h("div", null, drop, input), t("Excel (.xlsx) or CSV, up to 5,000 rows. Nothing is saved until you import.")),
      step(3, t("Review and import"), stage, t("Every row is checked with the same rules as the asset form.")))).el);
}
