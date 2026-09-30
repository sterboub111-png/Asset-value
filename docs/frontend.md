# Frontend

TypeScript (strict, unused code is an error) compiled with `tsc` to ES modules in `web/static/js/`. No framework and no bundler:
the browser loads `js/main.js` and follows the `import` graph. Styles are plain CSS files with variables.

Build: `node node_modules/typescript/bin/tsc -p .` (`Usool.bat` does not build; run the compiler after editing `web/src`).

## Source layout (`web/src`)

| Path | Role |
|---|---|
| `main.ts` | entry: `boot()` asks `/api/auth/status`, shows sign-in or `startSession()`, `render()` runs the page for the hash |
| `core/api.ts` | `api.get/post/put/del`, uploads, `lookups()` cache; sends `X-Lang` and `X-Requested-With`; `hooks.onUnauthorized` / `onMustChange` |
| `core/i18n.ts`, `core/ar.ts` | `t("English key")`, `getLang/setLang/applyLang` (sets `lang`/`dir` on `<html>`); `ar.ts` is generated |
| `core/session.ts` | `getMe/setMe`, `can(permission)`, theme, initials and name helpers |
| `core/types.ts` | `Rec`, `Col`, `Lookups` |
| `shell/routes.ts` | `ROUTES` (regex → page function, breadcrumb), `NAV` tree, `permFor(href)` |
| `shell/nav.ts` | navigation pane: sections, live filter, report groups, **icon rail** |
| `shell/topbar.ts` | top bar: nav toggle, brand, breadcrumb, asset search, language, backup, theme, account menu |
| `shell/account.ts` | account menu, sign-out, forced password change |
| `ui/` | the UI kit (below); `ui/index.ts` re-exports it, pages import from `../../ui/index.js` |
| `pages/settings/settings.ts` | Settings area: a side list of settings grouped as Personal / Company / Fixed asset setup / Accounting / Administration (`SETTINGS_GROUPS`, `SETTINGS_SECTIONS` with permissions) and the chosen setting on the right; a bar above it has **Back** and the path (Settings / Area / Setting) |
| `pages/<feature>/` | one file per screen family: `workspace/dashboard`, `assets/assets`, `depreciation/depreciation`, `maintenance/maintenance`, `contacts/{suppliers,employees,custody}`, `reports/reports`, `settings/{settings,setup,users,backup,account}`, `auth/login` |

### UI kit (`ui/`)

| Module | Provides |
|---|---|
| `dom.ts` | `h(tag, attrs, ...children)`, `append`, `clear` |
| `icons.ts` | `icon(name)` inline SVG set (add new paths to `ICONS`) |
| `format.ts` | `fmtMoney`, `fmtInt`, `fmtDate`, `fmtPct`, `today`, `pill`, `cellValue` |
| `dialogs.ts` | `toast`, `fail`, `dialog` (stacked, focus trap, Esc), `confirmDialog`, `closeAllDialogs` |
| `form.ts` | `Form` + `FieldDef` (typed fields, validation, `get()/value()/set`), `fastTab` (collapsible section) |
| `layout.ts` | `ribbon` (tabs, groups, permission-aware buttons), `page` (header + body) |
| `grid.ts` | `DataGrid` (sort, quick filter, column filters, selection, CSV export, double-click open) |
| `helpers.ts` | `nm` (Arabic/English name), `opts`, `guard` (busy wrapper), `onSave` (Ctrl+S), `redirectIf`, `csvText`, `displayText` |

## Pages

A page is `async (root: HTMLElement, { args, query }) => void`. It builds its DOM with `h()`, loads data with `api`, and registers
Ctrl+S with `onSave(root, fn)`. Register it in `shell/routes.ts` (route + nav entry + `permFor` rule). Wrap every action that calls the server in
`guard(async () => …)` so double clicks are ignored and errors surface as toasts.

Text: always `t("English text")`; the same key is the translation lookup. Names from data: `nm(record, "AssetName")` returns the Arabic
column in Arabic mode.

## Navigation pane (sidebar)

- The menu button in the top bar folds the pane to a **52 px icon rail** and back (persisted in `localStorage["gooya.nav.rail"]`).
  In the rail, section titles become thin dividers, every entry keeps its icon and a tooltip (`title`), and the search box becomes an icon
  that expands the pane and focuses the search when clicked.
- Below 900 px the pane is a drawer: the same button slides it in and out (`body.nav-collapsed`), and choosing a page closes it.
- Expanded state remembers which sections are collapsed (`gooya.nav.state`). The pane also filters pages as you type in its search box.

## Keyboard shortcuts

- `core/shortcuts.ts` holds the catalog (`DEFAULTS`: id, section, label, default keys, and an action or a target page), the user's overrides
  (`localStorage["usool.shortcuts"]`, per browser) and the key helpers. Keys are read from `event.code`, so letters work on the Arabic keyboard.
- `shell/keyboard.ts` is the single `keydown` handler. Page actions (`save`, `new`, `edit`, `delete`, `refresh`) press the matching ribbon button:
  `ribbon()` tags buttons labelled New/Edit/Delete/Refresh/Save with `data-act` and puts the key in their tooltip (the label stays plain). `save` first calls the
  page's `onSave` hook. Shell actions (`nav`, `theme`, `lang`, `backup`) click the top-bar button with the same `data-act`.
- Shortcuts without Ctrl/Alt (`/`, `Shift+/`) never fire while typing in a field. Browser-reserved combinations cannot be assigned, and
  a combination can belong to one shortcut only.
- Settings > Keyboard shortcuts (`pages/settings/shortcuts.ts`): grouped by system section, filter by text and section, change (captures the
  next key press), switch off, reset one or all, export CSV, print.
- To add a shortcut: add an entry to `DEFAULTS` (and translations in `tools/gen_ar.py`); a page shortcut needs only a `href`.

## CSS (`web/static/css`, loaded in this order)

`base` (tokens, reset) → `shell` (top bar, navigation) → `page` (headers, ribbon) → `components` (tiles, grid, forms, dialogs) →
`settings` (split views, settings list and path bar) → `dark` (theme overrides via `:root[data-theme="dark"]`) → `documents` (handover form, report
viewer, print) → `account` (menu, roles editor, no-access) → `login` → `nav-rail`.

- Colours, spacing and shadows are CSS variables in `base.css`; the look follows Microsoft Dynamics 365 (Segoe UI, 2 px radius, blue accent).
- RTL uses logical properties (`inset-inline-*`, `padding-inline-*`, `border-inline-*`); numbers stay left-to-right through a dedicated rule.
- Print styles hide the chrome and lay out reports and forms on paper (A4).
