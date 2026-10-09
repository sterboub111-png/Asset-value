import { api, lookups } from "../../core/api.js";
import { getLang, t } from "../../core/i18n.js";
import type { Col, Rec } from "../../core/types.js";
import { DataGrid, FieldDef, Form, clear, confirmDialog, fail, fold, guard, h, icon, nm, page, pill, ribbon, toast } from "../../ui/index.js";
import { roleTitle } from "../../core/session.js";

type Args = { args: string[]; query: URLSearchParams };

const userState = (u: Rec): Node => (u.IsLocked ? pill("Locked", "err") : pill(u.IsActive ? "Active" : "Inactive"));

/** Which branches a user works in: ticked branches, grouped by country; none ticked = every branch. */
function branchChecklist(L: Rec, chosen: number[]): { el: HTMLElement; get: () => number[] } {
  const on = new Set(chosen);
  const q = h("input", { class: "gt-input", type: "search", placeholder: t("Find a branch…"), "aria-label": t("Find a branch"), style: "max-width:none;width:100%" }) as HTMLInputElement;
  const list = h("div", { class: "br-list" });
  const note = h("p", { class: "br-note" });
  const cn = (code: string) => { const c = (L.countries as Rec[]).find((x) => x.code === code); return c ? (getLang() === "ar" ? c.nameAr : c.name) : code; };
  const sync = () => { note.textContent = on.size ? t("Works in {0} branch(es) only.", on.size) : t("No branch ticked: the user works in every branch."); };
  const draw = () => {
    clear(list);
    const k = fold(q.value);
    const byCountry = new Map<string, Rec[]>();
    for (const b of L.branches as Rec[]) if (!k || fold(`${b.BranchCode} ${b.BranchName} ${b.BranchNameAr || ""} ${cn(b.CountryCode)}`).includes(k)) byCountry.set(b.CountryCode, [...(byCountry.get(b.CountryCode) || []), b]);
    for (const [code, bs] of byCountry) {
      const all = h("input", { type: "checkbox" }) as HTMLInputElement;
      const refresh = () => { const n = bs.filter((b) => on.has(b.BranchID)).length; all.checked = n === bs.length; all.indeterminate = n > 0 && n < bs.length; };
      all.addEventListener("change", () => { bs.forEach((b) => (all.checked ? on.add(b.BranchID) : on.delete(b.BranchID))); draw(); sync(); });
      list.append(h("label", { class: "perm-head" }, all, h("b", null, cn(code))));
      for (const b of bs) {
        const box = h("input", { type: "checkbox" }) as HTMLInputElement;
        box.checked = on.has(b.BranchID);
        box.addEventListener("change", () => { box.checked ? on.add(b.BranchID) : on.delete(b.BranchID); refresh(); sync(); });
        list.append(h("label", { class: "perm" }, box, h("span", null, `${b.BranchCode} — ${nm(b, "BranchName")}`)));
      }
      refresh();
    }
  };
  q.addEventListener("input", draw);
  draw(); sync();
  return { el: h("div", { class: "br-pick" }, h("h2", { class: "sec" }, t("Branches")), note, q, list), get: () => [...on] };
}

// ================================================================ users
export async function usersPage(root: HTMLElement, _a: Args): Promise<void> {
  let roles: Rec[] = await api.get("/api/roles");
  const L = await lookups(true);
  const cols: Col[] = [
    { key: "UserName", label: "User name", width: 130 }, { key: "FullName", label: "Full name", render: (r) => (r.FullNameAr && document.documentElement.lang === "ar" ? r.FullNameAr : r.FullName) },
    { key: "RoleName", label: "Role", render: (r) => roleTitle(r as any) }, { key: "Status", label: "Status", render: userState },
    { key: "Branches", label: "Branches", render: (r) => (r.BranchCount ? t("{0} branch(es)", r.BranchCount) : t("All branches")) },
    { key: "Email", label: "Email" }, { key: "LastLogin", label: "Last sign-in", render: (r) => (r.LastLogin ? String(r.LastLogin).slice(0, 16) : "—") },
  ];
  const grid = new DataGrid({ columns: cols, rows: [], exportName: "users", limit: 1000, onOpen: (r) => edit(r) });
  const holder = h("div", { class: "split-side" });
  let panel: HTMLElement | null = null;
  const closePanel = () => { panel?.remove(); panel = null; };
  const load = async () => { try { roles = await api.get("/api/roles"); grid.setRows(await api.get("/api/users")); } catch (e) { fail(e); } };

  function edit(rec: Rec | null) {
    closePanel();
    const defs: FieldDef[] = [
      { name: "UserName", label: "User name", required: true, maxlength: 40 }, { name: "FullName", label: "Full name", required: true, maxlength: 120 },
      { name: "FullNameAr", label: "Name (Arabic)", maxlength: 120 }, { name: "Email", label: "Email" }, { name: "Phone", label: "Phone" },
      { name: "RoleID", label: "Role", type: "select", required: true, options: roles.map((r) => ({ value: r.RoleID, label: roleTitle(r as any) })) },
      { name: "Password", label: rec ? "New password (leave blank to keep)" : "Password", type: "password", required: !rec },
      { name: "ConfirmPassword", label: "Confirm password", type: "password", required: !rec },
      { name: "MustChangePassword", label: "Must change password at next sign-in", type: "checkbox" }, { name: "IsActive", label: "Active", type: "checkbox" },
    ];
    const form = new Form(defs, rec ? { ...rec, Password: "", ConfirmPassword: "" } : { IsActive: true, MustChangePassword: true, RoleID: roles.find((r) => r.RoleName === "Viewer")?.RoleID });
    const branches = L.branches.length ? branchChecklist(L, rec?.Branches || []) : null;
    const save = guard(async () => {
      if (!form.validate()) return;
      if (form.value("Password") !== form.value("ConfirmPassword")) { toast(t("The passwords do not match"), "err"); return; }
      const body: Rec = form.get(); if (!body.Password) delete body.Password; delete body.ConfirmPassword;
      if (branches) body.Branches = branches.get();
      if (rec) await api.put(`/api/users/${rec.UserID}`, body); else await api.post("/api/users", body);
      toast(t("Saved"), "ok"); closePanel(); await load();
    });
    panel = h("aside", { class: "side-panel inline", role: "dialog" },
      h("header", null, h("span", null, rec ? `${t("Edit")} · ${rec.UserName}` : t("New user")), h("button", { class: "tb-btn", style: "color:var(--ink);height:28px", onclick: closePanel, "aria-label": t("Close") }, icon("x"))),
      h("div", { class: "dbody" }, form.el, branches?.el ?? ""), h("footer", null, h("button", { class: "btn primary", onclick: save }, t("Save")), h("button", { class: "btn", onclick: closePanel }, t("Cancel"))));
    holder.append(panel);
    (form.el.querySelector("input,select") as HTMLElement | null)?.focus();
  }
  const sel = (fn: (r: Rec) => void) => () => { const r = grid.selected(); if (r) fn(r); else toast(t("Select a user first.")); };
  const rb = ribbon([
    [{ label: t("New"), icon: "plus", primary: true, onClick: () => edit(null) }, { label: t("Edit"), icon: "edit", onClick: sel(edit) },
     { label: t("Delete"), icon: "trash", danger: true, onClick: sel((r) => void guard(async () => {
         if (await confirmDialog(t("Delete user {0}?", r.UserName), { danger: true, ok: t("Delete") })) { await api.del(`/api/users/${r.UserID}`); toast(t("User deleted"), "ok"); await load(); }
       })()) }],
    [{ label: t("Unlock"), icon: "unlock", onClick: sel((r) => void guard(async () => { await api.post(`/api/users/${r.UserID}/unlock`); toast(t("User unlocked"), "ok"); await load(); })()) },
     { label: t("Roles and permissions"), icon: "lock", onClick: () => (location.hash = "#/settings/roles") }],
    [{ label: t("Refresh"), icon: "refresh", onClick: load }],
  ], [t("Users"), t("Access"), t("View")]);
  clear(root); root.append(page({ title: t("Users"), subtitle: t("Settings"), ribbon: rb.el }, h("div", { class: "split" }, h("div", { class: "split-main" }, grid.el), holder)).el);
  window.addEventListener("hashchange", closePanel, { once: true });
  await load();
}

// ================================================================ roles and permissions
export async function rolesPage(root: HTMLElement, _a: Args): Promise<void> {
  let roles: Rec[] = [];
  const catalog: Rec[] = await api.get("/api/permissions");
  const groups = [...new Set(catalog.map((p) => p.group))];
  let current: Rec | null = null;
  const listEl = h("div", { class: "role-list", role: "listbox" });
  const editor = h("div", { class: "role-editor" });

  const load = async (selectId?: number | null) => {
    try { roles = await api.get("/api/roles"); } catch (e) { fail(e); return; }
    current = selectId === null ? null : roles.find((r) => r.RoleID === (selectId ?? current?.RoleID)) || roles[0] || null;
    drawList(); drawEditor(current);
  };
  const drawList = () => {
    clear(listEl);
    for (const r of roles) {
      listEl.append(h("button", { class: `role-item ${current?.RoleID === r.RoleID ? "active" : ""}`, type: "button", role: "option", onclick: () => { current = r; drawList(); drawEditor(r); } },
        h("span", { class: "rn" }, roleTitle(r as any)), h("span", { class: "rc" }, t("{0} users", r.UserCount))));
    }
  };
  function drawEditor(role: Rec | null) {
    clear(editor);
    const locked = !!role?.IsSystem;
    const isNew = !role;
    const form = new Form([
      { name: "RoleName", label: "Role name", required: true, readonly: locked, maxlength: 60 }, { name: "RoleNameAr", label: "Name (Arabic)", readonly: locked, maxlength: 60 },
      { name: "Description", label: "Description", wide: true, readonly: locked, maxlength: 200 },
    ], role || {});
    const checked = new Set<string>(role?.permissions || []);
    const boxes = new Map<string, HTMLInputElement>();
    const groupEls = groups.map((g) => {
      const items = catalog.filter((p) => p.group === g);
      const all = h("input", { type: "checkbox", disabled: locked, "aria-label": t(g) }) as HTMLInputElement;
      const refresh = () => { const n = items.filter((p) => boxes.get(p.key)!.checked).length; all.checked = n === items.length; all.indeterminate = n > 0 && n < items.length; };
      all.addEventListener("change", () => { items.forEach((p) => { boxes.get(p.key)!.checked = all.checked; }); refresh(); });
      const rows = items.map((p) => {
        const box = h("input", { type: "checkbox", id: `perm_${p.key}`, disabled: locked }) as HTMLInputElement;
        box.checked = checked.has(p.key); boxes.set(p.key, box); box.addEventListener("change", refresh);
        return h("label", { class: "perm", for: `perm_${p.key}` }, box, h("span", null, t(p.label)));
      });
      const el = h("div", { class: "perm-group" }, h("label", { class: "perm-head" }, all, h("b", null, t(g))), ...rows);
      refresh();
      return el;
    });
    const save = guard(async () => {
      if (!form.validate()) return;
      const body = { ...form.get(), permissions: [...boxes.entries()].filter(([, b]) => b.checked).map(([k]) => k) };
      const saved: Rec = role ? await api.put(`/api/roles/${role.RoleID}`, body) : await api.post("/api/roles", body);
      toast(t("Saved"), "ok"); await load(saved.RoleID);
    });
    const del = guard(async () => {
      if (!role) return;
      if (await confirmDialog(t("Delete role {0}?", role.RoleName), { danger: true, ok: t("Delete") })) { await api.del(`/api/roles/${role.RoleID}`); toast(t("Role deleted"), "ok"); await load(); }
    });
    editor.append(h("div", { class: "fasttab open" }, h("header", null, h("h3", null, isNew ? t("New role") : roleTitle(role as any))),
      h("div", { class: "content", style: "display:block" },
        locked ? h("div", { class: "msgbar" }, t("The Administrator role always has full access and cannot be changed.")) : null, form.el,
        h("h2", { class: "sec" }, t("Permissions")), h("div", { class: "perm-grid" }, ...groupEls),
        locked ? null : h("div", { class: "role-actions" }, h("button", { class: "btn primary", type: "button", onclick: save }, t("Save")),
          role ? h("button", { class: "btn danger", type: "button", onclick: del }, t("Delete")) : null))));
  }
  const rb = ribbon([[{ label: t("New role"), icon: "plus", primary: true, onClick: () => { current = null; drawList(); drawEditor(null); } }],
    [{ label: t("Users"), icon: "user", onClick: () => (location.hash = "#/settings/users") }, { label: t("Refresh"), icon: "refresh", onClick: () => void load() }]], [t("Roles"), t("View")]);
  clear(root);
  root.append(page({ title: t("Roles and permissions"), subtitle: t("Settings"), ribbon: rb.el }, h("div", { class: "roles" }, h("div", { class: "role-side" }, h("h6", null, t("Roles")), listEl), editor)).el);
  await load();
}
