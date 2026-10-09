/** Physical inventory: count sessions, scanning (a barcode scanner types the code and Enter), the reconciliation of
 *  found / missing / moved / extra / unknown, and closing with the found locations applied. Rules: services/counts.py. */
import { api, lookups } from "../../core/api.js";
import { t } from "../../core/i18n.js";
import { can } from "../../core/session.js";
import type { Col, Rec } from "../../core/types.js";
import { DataGrid, Form, clear, combo, confirmDialog, dialog, fail, fmtDate, fmtInt, fmtMoney, guard, h, nm, page, pill, ribbon, toast, today } from "../../ui/index.js";

type Args = { args: string[]; query: URLSearchParams };

const RESULT: Record<string, [string, string]> = {   // result -> label, pill tone
  found: ["Found", "ok"], missing: ["Missing", "err"], moved: ["Found elsewhere", "warn"], extra: ["Not expected here", "warn"],
  unknown: ["Unknown code", "err"], disposed: ["Disposed asset", "err"],
};

export async function countsListPage(root: HTMLElement): Promise<void> {
  const L = await lookups();
  const cols: Col[] = [
    { key: "CountNo", label: "Count", link: (r) => `#/counts/${r.CountID}` }, { key: "Title", label: "Title" },
    { key: "CountDate", label: "Date", type: "date" }, { key: "LocationName", label: "Location", render: (r) => r.LocationName || t("All locations") },
    { key: "Status", label: "Status", render: (r) => pill(r.Status === "Open" ? "OPEN" : "CLOSED") }, { key: "ExpectedCount", label: "Expected", type: "int" },
    { key: "FoundCount", label: "Found", type: "int" }, { key: "ExtraCount", label: "Not expected", type: "int" },
  ];
  const grid = new DataGrid({ columns: cols, rows: [], exportName: "counts", onOpen: (r) => (location.hash = `#/counts/${r.CountID}`), empty: "No counts yet." });
  const load = async () => { try { grid.setRows(await api.get("/api/counts")); } catch (e) { fail(e); } };
  const newCount = () => {
    const f = new Form([
      { name: "Title", label: "Title", required: true, maxlength: 120 },
      { name: "CountDate", label: "Count date", type: "date", required: true },
      { name: "LocationID", label: "Location", type: "select", search: true, options: (L.locations as Rec[]).filter((l) => l.IsActive).map((l) => ({ value: l.LocationID, label: `${l.LocationCode} — ${nm(l, "LocationName")}` })),
        hint: "Leave empty to count every location." },
      { name: "Notes", label: "Notes", type: "textarea", wide: true },
    ], { Title: `${t("Physical count")} ${fmtDate(today())}`, CountDate: today() });
    dialog(t("New physical count"), h("div", null, h("p", { class: "dlg-intro" }, t("The assets in the books at that location become the expected list. Then scan or type each asset you see.")), f.el), [
      { label: t("Start the count"), primary: true, onClick: async () => { if (!f.validate()) return false; const c = await api.post<Rec>("/api/counts", f.get()); location.hash = `#/counts/${c.CountID}`; } },
      { label: t("Cancel") }]);
  };
  const rb = ribbon([[{ perm: "assets.edit", label: t("New count"), icon: "plus", primary: true, onClick: newCount }, { label: t("Refresh"), icon: "refresh", onClick: load }]]);
  clear(root);
  root.append(page({ title: t("Physical counts"), subtitle: t("Fixed assets"), ribbon: rb.el },
    h("p", { class: "page-intro" }, t("Compare what is on the floor with the books: print labels, scan each asset, then review what is missing or misplaced.")), grid.el).el);
  await load();
}

/** A short tone for the person scanning: high when found, low when something needs a look. */
function beep(ok: boolean): void {
  try {
    const ctx = new AudioContext(), o = ctx.createOscillator(), g = ctx.createGain();
    o.frequency.value = ok ? 880 : 220; g.gain.value = 0.06;
    o.connect(g); g.connect(ctx.destination); o.start(); o.stop(ctx.currentTime + (ok ? 0.08 : 0.25));
    o.onended = () => void ctx.close();
  } catch { /* no audio: the message on screen is enough */ }
}

export async function countPage(root: HTMLElement, a: Args): Promise<void> {
  const L = await lookups();
  let c: Rec;
  try { c = await api.get(`/api/counts/${a.args[0]}`); } catch (e) { fail(e); location.hash = "#/counts"; return; }
  const open = c.Status === "Open" && can("assets.edit");
  let filter = a.query.get("show") || "";

  const progress = h("div", { class: "cnt-progress" });
  const feedback = h("div", { class: "cnt-feedback", role: "status", "aria-live": "assertive" });
  const filters = h("div", { class: "cnt-filters", role: "tablist" });
  const cols: Col[] = [
    { key: "Result", label: "Result", render: (r) => pill(t(RESULT[r.Result][0]), RESULT[r.Result][1]) },
    { key: "AssetCode", label: "Asset", link: (r) => (r.AssetID ? `#/assets/${r.AssetID}` : null), render: (r) => r.AssetCode || r.ScannedCode },
    { key: "AssetName", label: "Name" }, { key: "CategoryName", label: "Group" },
    { key: "BookLocation", label: "Location in the books" }, { key: "FoundLocation", label: "Found at" },
    { key: "FoundAt", label: "Counted", hidden: true, render: (r) => (r.FoundAt ? `${fmtDate(r.FoundAt)} ${String(r.FoundAt).slice(11, 16)}` : "") },
    { key: "NBV", label: "Net book value", type: "money" },
    ...(open ? [{ key: "undo", label: "", render: (r: Rec) => (r.Found ? h("button", { class: "btn sm", type: "button", onclick: (e: Event) => { e.stopPropagation(); void undo(r); } }, t("Undo")) : "") }] : []),
  ];
  const grid = new DataGrid({ columns: cols, rows: [], exportName: `count-${c.CountNo}`, limit: 2000, empty: "Nothing here." });

  const draw = () => {
    const s = c.summary as Record<string, number>;
    const counted = s.found + s.moved;
    const pct = c.ExpectedCount ? Math.round((counted / c.ExpectedCount) * 100) : 0;
    clear(progress);
    progress.append(h("div", { class: "cnt-nums" },
      h("span", null, h("b", null, `${fmtInt(counted)} / ${fmtInt(c.ExpectedCount)}`), " ", t("expected assets counted")),
      h("span", { class: s.missing ? "err" : "" }, h("b", null, fmtInt(s.missing)), " ", t("missing"), s.missing ? ` (${fmtMoney(c.MissingNBV)})` : ""),
      s.moved ? h("span", { class: "warn" }, h("b", null, fmtInt(s.moved)), " ", t("found elsewhere")) : null,
      s.extra ? h("span", { class: "warn" }, h("b", null, fmtInt(s.extra)), " ", t("not expected here")) : null,
      s.unknown + s.disposed ? h("span", { class: "err" }, h("b", null, fmtInt(s.unknown + s.disposed)), " ", t("unknown or disposed")) : null),
      h("div", { class: "cnt-bar", role: "progressbar", "aria-valuenow": pct, "aria-valuemin": 0, "aria-valuemax": 100 }, h("i", { style: `width:${pct}%` })));
    clear(filters);
    const tabs: [string, string, number][] = [["", t("All"), c.lines.length], ["missing", t("Missing"), s.missing], ["found", t("Found"), s.found],
      ["moved", t("Found elsewhere"), s.moved], ["extra", t("Not expected here"), s.extra], ["unknown", t("Unknown code"), s.unknown + s.disposed]];
    for (const [k, label, n] of tabs) {
      if (k && !n) continue;
      filters.append(h("button", { class: `ws-tab ${filter === k ? "active" : ""}`, type: "button", onclick: () => { filter = k; draw(); } }, label, h("span", { class: "ws-badge" }, fmtInt(n))));
    }
    grid.setRows((c.lines as Rec[]).filter((l) => !filter || l.Result === filter || (filter === "unknown" && l.Result === "disposed")));
  };
  const refresh = async () => { c = await api.get(`/api/counts/${c.CountID}`); draw(); };
  async function undo(r: Rec) { c = await api.del(`/api/counts/${c.CountID}/lines/${r.LineID}`); draw(); input?.focus(); }

  // the scanner box: a scanner types the code and presses Enter; people can type too
  let input: HTMLInputElement | null = null;
  let scanBox: Node | null = null;
  if (open) {
    input = h("input", { class: "cnt-input", type: "text", autocomplete: "off", spellcheck: "false", placeholder: t("Scan or type an asset code, then Enter"), "aria-label": t("Asset code") }) as HTMLInputElement;
    const at = combo((L.locations as Rec[]).map((l) => ({ value: l.LocationID, label: nm(l, "LocationName") })), { value: c.LocationID ?? "", placeholder: t("Location of the count"), label: t("Found at"), width: 240 });
    input.addEventListener("keydown", async (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      const code = input!.value.trim();
      if (!code) return;
      input!.value = "";
      try {
        const r = await api.post<Rec>(`/api/counts/${c.CountID}/scan`, { code, LocationID: at.value || null });
        const ln = r.line as Rec;
        const good = r.status === "found";
        beep(good);
        const what = r.status === "already" ? t("Already counted") : t(RESULT[r.status]?.[0] || r.status);
        clear(feedback);
        feedback.className = `cnt-feedback ${good ? "ok" : r.status === "already" ? "info" : r.status === "moved" || r.status === "extra" ? "warn" : "err"}`;
        feedback.append(h("b", null, what), " · ", ln.AssetCode ? `${ln.AssetCode} · ${nm(ln, "AssetName")}` : code,
          r.status === "moved" || r.status === "extra" ? ` · ${t("in the books at")} ${nm(ln, "BookLocation") || "—"}` : "");
        await refresh();
      } catch (ex) { beep(false); fail(ex); }
      input!.focus();
    });
    scanBox = h("div", { class: "cnt-scan" }, h("div", { class: "cnt-scan-row" }, input, at), feedback);
  }

  const close = () => {
    const apply = h("input", { type: "checkbox", checked: true }) as HTMLInputElement;
    const s = c.summary as Record<string, number>;
    dialog(t("Close the count"), h("div", null,
      h("p", null, t("{0} missing asset(s) stay listed in this count for follow-up (search, transfer or dispose them).", s.missing)),
      s.moved + s.extra ? h("label", { class: "imp-skip" }, apply, t("Move the {0} asset(s) found elsewhere to the location where they were counted", s.moved + s.extra)) : null), [
      { label: t("Close the count"), primary: true, onClick: async () => {
          const r = await api.post<Rec>(`/api/counts/${c.CountID}/close`, { apply_locations: apply.checked });
          toast(r.transferred ? t("Count closed; {0} asset(s) transferred", r.transferred) : t("Count closed"), "ok"); await countPage(root, a); } },
      { label: t("Cancel") }]);
  };
  const rb = ribbon([[
    { perm: "assets.edit", label: t("Close the count"), icon: "check", primary: true, disabled: !open, onClick: close },
    { label: t("Print the count sheet"), icon: "print", onClick: () => { filter = ""; draw(); setTimeout(() => window.print(), 50); } },
    { label: t("Refresh"), icon: "refresh", onClick: guard(refresh) },
    { perm: "assets.edit", label: t("Delete"), icon: "trash", danger: true, disabled: !open, onClick: guard(async () => {
        if (await confirmDialog(t("Delete count {0}? The scans are lost.", c.CountNo), { danger: true, ok: t("Delete") })) { await api.del(`/api/counts/${c.CountID}`); location.hash = "#/counts"; } }) },
  ]]);
  clear(root);
  root.append(page({ title: `${c.CountNo} : ${c.Title}`, subtitle: t("Physical counts"), ribbon: rb.el, pills: [pill(c.Status === "Open" ? "OPEN" : "CLOSED", c.Status === "Open" ? "info" : "")] },
    h("div", { class: "cnt-meta" }, `${fmtDate(c.CountDate)} · ${c.LocationName ? nm(c, "LocationName") : t("All locations")}`),
    scanBox, progress, filters, grid.el).el);
  draw();
  input?.focus();
}
