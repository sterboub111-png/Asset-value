/** Asset labels: a Code 39 barcode of the asset code with the name, group and location, laid out on standard A4
 *  label sheets. Printed labels are what the physical count scans. */
import { api, lookups } from "../../core/api.js";
import { t } from "../../core/i18n.js";
import type { Rec } from "../../core/types.js";
import { clear, code39, combo, fail, fold, h, nm, page, ribbon } from "../../ui/index.js";

type Args = { args: string[]; query: URLSearchParams };
const LAYOUTS: Record<string, { label: string; cls: string; per: number }> = {
  "3x8": { label: "A4, 24 labels (70 × 37 mm)", cls: "l3x8", per: 24 },
  "2x7": { label: "A4, 14 labels (99 × 38 mm)", cls: "l2x7", per: 14 },
};

export async function assetLabelsPage(root: HTMLElement, a: Args): Promise<void> {
  const L = await lookups();
  let assets: Rec[] = [];
  try { assets = await api.get<Rec[]>("/api/assets"); } catch (e) { fail(e); }
  assets = assets.filter((x) => x.AssetStatus !== "Disposed");
  const company = L.settings.CompanyName || t("Usool");

  const group = combo((L.categories as Rec[]).map((c) => ({ value: c.CategoryID, label: `${c.CategoryCode} — ${nm(c, "CategoryName")}` })), { placeholder: t("All groups"), label: t("Group"), width: 220, value: a.query.get("category") ?? "" });
  const loc = combo((L.locations as Rec[]).map((l) => ({ value: l.LocationID, label: nm(l, "LocationName") })), { placeholder: t("All locations"), label: t("Location"), width: 200 });
  const layout = combo(Object.entries(LAYOUTS).map(([k, v]) => ({ value: k, label: t(v.label) })), { value: "3x8", allowEmpty: false, label: t("Label sheet"), width: 240 });
  const q = h("input", { class: "gt-input", type: "search", placeholder: t("Search…"), "aria-label": t("Search"), style: "max-width:220px" }) as HTMLInputElement;
  const count = h("span", { class: "lbl-count" });
  const sheet = h("div", { class: "lbl-sheet" });

  const label = (x: Rec) => h("div", { class: "lbl" },
    h("div", { class: "lbl-co" }, company),
    h("div", { class: "lbl-bc" }, code39(x.AssetCode)),
    h("div", { class: "lbl-code" }, x.AssetCode),
    h("div", { class: "lbl-name" }, nm(x, "AssetName")),
    h("div", { class: "lbl-sub" }, [nm(x, "CategoryName"), nm(x, "LocationName")].filter(Boolean).join(" · ")));
  const draw = () => {
    const k = fold(q.value);
    const list = assets.filter((x) => (!group.value || String(x.CategoryID) === group.value) && (!loc.value || String(x.LocationID) === loc.value)
      && (!k || fold(`${x.AssetCode} ${x.AssetName} ${x.AssetNameAr || ""} ${x.SerialNumber || ""}`).includes(k)));
    const lay = LAYOUTS[layout.value] || LAYOUTS["3x8"];
    sheet.className = `lbl-sheet ${lay.cls}`;
    clear(sheet); sheet.append(...list.map(label));
    count.textContent = t("{0} label(s) on {1} sheet(s)", list.length, Math.max(1, Math.ceil(list.length / lay.per)));
  };
  for (const c of [group, loc, layout]) c.addEventListener("change", draw);
  q.addEventListener("input", draw);

  const rb = ribbon([[{ label: t("Print labels"), icon: "print", primary: true, onClick: () => window.print() },
    { label: t("Physical counts"), icon: "list", onClick: () => (location.hash = "#/counts") }]]);
  clear(root);
  root.append(page({ title: t("Asset labels"), subtitle: t("Fixed assets"), ribbon: rb.el },
    h("div", { class: "lbl-tools" }, q, group, loc, layout, count),
    h("p", { class: "page-intro" }, t("Stick a label on each asset; the physical count reads the barcode with any scanner. In the print dialog choose scale 100% and no margins.")),
    h("div", { class: "lbl-paper" }, sheet)).el);
  draw();
}
