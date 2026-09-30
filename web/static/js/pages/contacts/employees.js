import { api, invalidateLookups, lookups } from "../../core/api.js";
import { t } from "../../core/i18n.js";
import { DataGrid, Form, onSave, redirectIf, clear, confirmDialog, dialog, fail, fastTab, guard, h, nm, opts, page, pill, ribbon, toast } from "../../ui/index.js";
import { custodyGrid, issueDialog } from "./custody.js";
const general = [
    { name: "EmployeeCode", label: "Employee code", required: true, maxlength: 20 },
    { name: "EmployeeName", label: "Employee name", required: true, maxlength: 160, wide: true },
    { name: "EmployeeNameAr", label: "Name (Arabic)", maxlength: 160, wide: true },
    { name: "JobTitle", label: "Job title" }, { name: "Department", label: "Department" },
    { name: "NationalID", label: "ID number" }, { name: "HireDate", label: "Hire date", type: "date" },
    { name: "IsActive", label: "Active", type: "checkbox" },
];
const contact = [{ name: "Phone", label: "Phone" }, { name: "Mobile", label: "Mobile" }, { name: "Email", label: "Email" }];
const notes = [{ name: "Notes", label: "Notes", type: "textarea", wide: true }];
export const employeeOptions = (L, keep) => opts(L.employees.filter((e) => e.IsActive || e.EmployeeID === keep), "EmployeeID", (e) => `${e.EmployeeCode} — ${nm(e, "EmployeeName")}`);
/** Quick-add dialog used from the custody dialog. */
export async function quickEmployee(onSaved) {
    const code = (await api.get("/api/employees/next-code")).code;
    const form = new Form([...general, ...contact, ...notes], { EmployeeCode: code, IsActive: true });
    dialog(t("New employee"), form.el, [
        { label: t("Save"), primary: true, onClick: async () => {
                if (!form.validate())
                    return false;
                const e = await api.post("/api/employees", form.get());
                invalidateLookups();
                toast(t("Employee {0} created", e.EmployeeCode), "ok");
                onSaved(e);
            } },
        { label: t("Cancel") },
    ], { wide: true });
}
// ================================================================ list
export async function employeesListPage(root, _a) {
    const cols = [
        { key: "EmployeeCode", label: "Code", link: (r) => `#/employees/${r.EmployeeID}` }, { key: "EmployeeName", label: "Name", width: 180 },
        { key: "JobTitle", label: "Job title" }, { key: "Department", label: "Department" }, { key: "Mobile", label: "Mobile" }, { key: "Email", label: "Email" },
        { key: "HeldCount", label: "Assets held", type: "int" }, { key: "TotalCustody", label: "Total custody", type: "int" },
        { key: "IsActive", label: "Status", render: (r) => pill(r.IsActive ? "Active" : "Inactive") },
    ];
    const actSel = h("select", { class: "gt-input", style: "width:150px", "aria-label": t("Status") }, h("option", { value: "" }, t("All statuses")), h("option", { value: "1" }, t("Active")), h("option", { value: "0" }, t("Inactive")));
    const grid = new DataGrid({ columns: cols, rows: [], exportName: "employees", tools: [actSel], onOpen: (r) => (location.hash = `#/employees/${r.EmployeeID}`), empty: "No employees yet." });
    const load = async () => { try {
        grid.setRows(await api.get(`/api/employees?active=${actSel.value}`));
    }
    catch (e) {
        fail(e);
    } };
    actSel.onchange = load;
    const rb = ribbon([
        [{ perm: "contacts.edit", label: t("New"), icon: "plus", primary: true, onClick: () => (location.hash = "#/employees/new") },
            { label: t("Edit"), icon: "edit", onClick: () => { const r = grid.selected(); if (r)
                    location.hash = `#/employees/${r.EmployeeID}`;
                else
                    toast(t("Select an employee first.")); } }],
        [{ label: t("Refresh"), icon: "refresh", onClick: load }, { label: t("Reports"), icon: "report", onClick: () => (location.hash = "#/reports/custody-by-employee") }],
    ], [t("Employees"), t("View")]);
    clear(root);
    root.append(page({ title: t("Employees"), subtitle: t("Contacts"), ribbon: rb.el }, grid.el).el);
    await load();
}
// ================================================================ form
export async function employeeFormPage(root, a) {
    const at = location.hash;
    const isNew = a.args[0] === "new";
    const L = await lookups(true);
    let emp = null;
    if (!isNew) {
        try {
            emp = await api.get(`/api/employees/${a.args[0]}`);
        }
        catch (e) {
            fail(e);
            redirectIf(at, "#/employees");
            return;
        }
    }
    const v = emp ? { ...emp } : { EmployeeCode: (await api.get("/api/employees/next-code")).code, IsActive: true };
    const forms = [general, contact, notes].map((d) => new Form(d, v));
    const collect = () => Object.assign({}, ...forms.map((f) => f.get()));
    const save = async () => {
        if (!forms.every((f) => f.validate()))
            return;
        const res = isNew ? await api.post("/api/employees", collect()) : await api.put(`/api/employees/${emp.EmployeeID}`, collect());
        invalidateLookups();
        toast(t("Saved {0}", res.EmployeeCode), "ok");
        if (isNew)
            location.hash = `#/employees/${res.EmployeeID}`;
        else
            await employeeFormPage(root, a);
    };
    const saveG = guard(save);
    onSave(root, () => { void saveG(); });
    const rb = ribbon([
        [{ perm: "contacts.edit", label: t("Save"), icon: "save", primary: true, onClick: saveG }, { perm: "contacts.edit", label: t("New"), icon: "plus", onClick: () => (location.hash = "#/employees/new") },
            { perm: "contacts.edit", label: t("Delete"), icon: "trash", danger: true, disabled: isNew, onClick: guard(async () => {
                    if (await confirmDialog(t("Delete employee {0}?", emp.EmployeeCode), { danger: true, ok: t("Delete") })) {
                        await api.del(`/api/employees/${emp.EmployeeID}`);
                        invalidateLookups();
                        toast(t("Employee deleted"), "ok");
                        location.hash = "#/employees";
                    }
                }) }],
        [{ perm: "custody.manage", label: t("Issue asset"), icon: "transfer", disabled: isNew || !emp?.IsActive, onClick: () => issueDialog(L, { EmployeeID: emp.EmployeeID }, (c) => (location.hash = `#/custody/${c.CustodyID}`)) }],
        [{ label: t("Back to list"), icon: "back", onClick: () => (location.hash = "#/employees") }],
    ], [t("Employee"), t("Custody"), t("View")]);
    const kv = (k, val) => h("div", null, h("span", { class: "k" }, t(k)), h("span", { class: "v" }, val));
    const fb = h("div", { class: "fb" }, h("h4", null, t("Activity")), h("div", { class: "kv" }, kv("Status", emp ? pill(emp.IsActive ? "Active" : "Inactive") : pill("Draft")), kv("Assets held", emp?.HeldCount ?? 0), kv("Total custody", emp?.TotalCustody ?? 0)));
    const tabs = [
        fastTab(t("General"), forms[0].el, { open: true, summary: emp ? [emp.JobTitle, emp.Department].filter(Boolean).join(" · ") : "" }),
        fastTab(t("Contact"), forms[1].el, { open: true, summary: emp ? [emp.Mobile || emp.Phone, emp.Email].filter(Boolean).join(" · ") : "" }),
        fastTab(t("Notes"), forms[2].el),
    ];
    if (emp)
        tabs.push(fastTab(t("Custody"), custodyGrid(emp.custody, { showEmployee: false }), { open: true, summary: t("{0} lines", emp.custody.length) }));
    clear(root);
    root.append(page({ title: isNew ? t("New employee") : `${emp.EmployeeCode} : ${nm(emp, "EmployeeName")}`, subtitle: t("Contacts"), pills: emp ? [pill(emp.IsActive ? "Active" : "Inactive")] : [], ribbon: rb.el, factbox: fb }, ...tabs).el);
}
