# User guide

## 1. Start and sign in
1. Double-click `Usool.bat` (or run `python run.py`). The browser opens `http://127.0.0.1:8742/`.
2. **First time:** create the administrator (full name, user name, password twice). This page appears only when no user exists.
3. **Afterwards:** enter the user name → **Next** → the password → **Sign in**. The app remembers who signed in last on this browser
   and shows their name and a greeting; click the name to use another account.
4. Language (العربية / English) and dark mode are in the top bar and are saved per user.

## 2. Getting around
- **Navigation pane** (left; right in Arabic): Workspaces, Common, Contacts, Maintenance, Periodic tasks, Inquiries, Reports, Setup.
  The menu button in the top bar folds it to an **icon rail** (hover for the name) and back. The pane's search box filters pages.
- **Top bar:** asset quick search (“Go to asset…”), language, backup now, dark mode, your account menu (My account, change password, sign out).
- **Ribbon:** commands of the current page (New, Edit, Delete, Refresh, Export…). Buttons you have no permission for are hidden.
- **Lists:** click a header to sort, type in the filter boxes, double-click a row to open it, Export to CSV (opens in Excel).
- **Forms:** Ctrl+S saves. Required fields are marked; messages appear at the top or as a toast.

## 3. Fixed assets
- **All fixed assets** lists the register with net book value. **New fixed asset** opens the form: group (defaults for life, rate and
  accounts), dates, invoice amount, VAT, residual value, location, cost center, supplier, invoice/PO, serial/model, warranty.
- **Attachments** tab: upload PDF, images, Excel, CSV or any file with a title and type; files are stored under the attachment folder
  by group, month and asset number.
- **Transfer** changes location or cost center (kept in the transaction history). **Status** sets Active / Inactive / Under Repair.
- **Dispose** removes an asset from the books (needs depreciation posted up to the disposal month). **Delete** is possible only for an
  asset with no history.
- After depreciation is posted, cost, life, method and dates are locked.

## 4. Depreciation (Periodic tasks)
1. **Depreciation periods:** *Generate periods* for a fiscal year; close a period when finished; reopen if needed.
2. **Depreciation run:** choose the period → *Propose* to preview every asset with amount or the reason it is skipped → *Create lines*
   (draft) → review → **Post**. Post month by month in order.
3. Results appear in **Fixed asset journal** (Dr expense / Cr accumulated depreciation) and **Fixed asset transactions**.

## 5. Contacts and custody
- **Suppliers** (supplier, manufacturer, maintenance or service provider) and **Employees**: create, edit, deactivate.
- **Asset custody:** *Issue* an asset to an employee (condition, accessories), *Return* it later. Print the **handover form**
  (Arabic/English) for signature, scan it and attach the signed copy to the custody record. An asset can be with only one employee at a time.

## 6. Maintenance
- **Maintenance orders:** type (preventive, corrective, inspection), priority, planned date, vendor/supplier, cost. Workflow: Start →
  Complete (with completion date, cost, next due date) or Cancel. “Out of service” marks the asset Under Repair until the order finishes.

## 7. Reports
Reports → choose a group (Fixed assets, Depreciation, Transactions, Exceptions, Contacts, Suppliers, Maintenance) → set the filters →
run. Every report can be printed, exported to CSV (opens in Excel). Examples: asset register, asset summary, roll-forward (opening, additions,
depreciation, disposals, closing), depreciation schedule and journal, ledger balances, VAT on purchases, fully depreciated assets,
warranty expiry, custody by employee, supplier purchases, maintenance history/cost/schedule.

## 8. Settings
Settings has a list on the side grouped by purpose (Personal, Company, Fixed asset setup, Accounting, Administration) and the chosen setting on the right. The bar above shows the path (Settings / Area / Setting) and **Back** to return to the previous step. You only see the settings you have permission for.
- **Fixed asset parameters** (company, asset code prefix, fiscal year start, depreciation rules, disposal clearing account, VAT),
  **Currencies**, **Tax (VAT)**, **Fixed asset groups**, **Depreciation methods**, **Locations**, **Cost centers**, **Ledger accounts**.
- **Users** and **Roles and permissions:** create users, assign a role, unlock, reset passwords (“must change at next sign-in”).
  Standard roles: Administrator, Asset Accountant, Asset Officer, Viewer; you can define your own.
- **Backup:** choose the backup folder, *Backup now*, or schedule daily/weekly/monthly at a time with the number of copies to keep;
  *Open folder* shows the archives. Set the attachment folder here too.
- **My account:** profile, language, appearance, password.

## 8b. Keyboard shortcuts
Settings > **Keyboard shortcuts** lists every shortcut by section (General, Fixed assets, Contacts, Maintenance, Periodic tasks, Inquiries, Reports,
Settings). Filter by text or section, **Change** a shortcut by pressing the new keys (conflicts are refused), **Reset** one or all,
**Print** the list or **Export** it. Hover a button (Save, Delete, New…) to see its key. Shortcuts are stored in the browser.

## 9. Backup and restore
- A backup is a ZIP of the database and every attachment. Keep copies on another disk.
- To restore: close the app, run `python tools/restore_backup.py <backup.zip>`, start the app again. The previous database is kept as
  `data/gooya_asset.before-restore.db`.

## 10. Tips
- Post depreciation every month before closing the period; posted lines cannot be edited (fix by disposal or adjustment entries in your ledger).
- Use groups to set life and accounts once; assets inherit them.
- Give people the smallest role that lets them work; only administrators need `users.manage` and `backup.manage`.
