# Business rules

These are the rules the server enforces (`app/services/*`). The user interface only mirrors them.

## Assets
- Code = prefix (Settings) + group code + running number, for example `IT-0001`. Numbers restart only after the reset tool.
- Required: name, group, acquisition date. In-service date and depreciation start default to the acquisition date and may not precede it.
- Cost is entered as the **invoice amount**; the register stores the **net cost**. With VAT enabled, "price includes VAT" splits
  `amount / (1 + rate)`; otherwise VAT is added on top for information only. Residual value ≤ cost; opening accumulated depreciation ≤ cost − residual.
- Useful life and rate default from the group; rate = 100 ÷ life when not given.
- Once any depreciation is **posted**, cost, residual, life, method, opening accumulated depreciation, group and the dates are locked.
- Location and cost center change only through **Transfer** (a transaction with from/to values). Transfer needs a different, active target.
- Status: `Active`, `Inactive`, `Under Repair` (maintenance can set and release Under Repair). A disposed asset cannot be edited.
- **Delete** is allowed only when the asset has no depreciation, no maintenance, no custody, and only acquisition/status transactions.
  Otherwise dispose or deactivate it.
- Editing anything the depreciation depends on discards that asset's unposted (draft) lines.

## Depreciation
- Method `SL` (straight line), monthly: `(cost − residual) ÷ (life × 12)`; the first month is the depreciation-start month (full month).
- The last month takes the exact remainder so rounding never leaves a stray cent or an extra month. Opening accumulated depreciation counts
  toward the depreciable amount.
- Flow: **Propose** (calculated, not stored) → **Create lines** (stored as DRAFT) → **Post** (writes journal, marks POSTED).
  Posting recomputes the lines and refuses if they are stale (asset changed, amounts differ).
- Periods must be posted **in sequence per asset**: an earlier month that is not posted blocks later months (skipped months of fully
  depreciated or disposed assets do not block).
- A **closed** period cannot receive proposals, lines or posting; closing is refused while unposted lines exist. Generating, closing and reopening periods all need the `periods.manage` permission.
- "No depreciation" method, missing life, not-yet-started, disposed and fully depreciated assets are listed with the reason instead of being proposed.

## Disposal
- Needs: not already disposed, no open maintenance orders, no custody in progress, disposal date not before acquisition, period of the date open.
- Depreciation must be posted up to the month before the disposal month (for `SL` assets that are not fully depreciated), and the date must be
  after the last posted depreciation. Draft lines of the asset are dropped.
- Books: remove accumulated depreciation and cost, take proceeds to the clearing account, book gain or loss (see database.md).
  Group accounts (asset, accumulated depreciation, gain/loss) and the clearing account (when proceeds > 0) must be configured.

## Periods
- `generate_periods(fiscal_year)` creates twelve monthly periods from the fiscal year start month. Existing periods are kept.
- `OPEN` ↔ `CLOSED`. The depreciation run suggests the earliest open period that still has something to do.

## VAT
- Enabled in Settings with a default rate and defaults for "applicable" and "price includes VAT". The asset stores applicable, inclusive,
  rate, invoice amount and VAT amount. Reports: *VAT on purchases* (by period) — the books themselves never contain VAT.

## Maintenance
- Types: Preventive, Corrective, Inspection. Priorities: Low, Medium, High. Statuses: Planned → In Progress → Completed / Cancelled.
- Start needs a planned order; complete needs an open order and a completion date not before the start; the next due date must be after
  completion. "Out of service" sets the asset to Under Repair until the order completes or is cancelled.
- Only a planned or cancelled order can be deleted; an asset that has orders cannot be deleted.

## Suppliers and employees
- Codes `SUP-nnnn` and `EMP-nnnn`; names, phone format and e-mail are validated; national ID is unique.
- A supplier or employee that is referenced (asset, maintenance, custody) cannot be deleted; mark it inactive.
- Inactive suppliers/employees cannot be chosen for new records.

## Custody
- One active custody per asset. Issue needs an active employee, a non-disposed asset and an issue date not before acquisition.
- Only an issued record without signed documents can be deleted.
- Return records date, condition and notes; the asset becomes available again. The **handover form** (printable, bilingual) is produced
  from the record; the signed scan is attached to the custody record (visible only to users with custody permissions).
- Users without `custody.view` never see who holds an asset or the signed forms, even inside the asset page.

## Backups
- Manual (any time) or scheduled (daily / weekly / monthly at a chosen time, keep the newest N). Each archive contains a consistent
  copy of the database and all attachments. The scheduler runs in the background thread inside the server.
