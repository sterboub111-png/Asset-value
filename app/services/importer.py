"""Import fixed assets from Excel (.xlsx) or CSV.

The file is read with the standard library only (an .xlsx is a zip of XML parts). Every row goes through the same
validation as the asset form (`_clean_asset`), so the import can never create an asset the form would refuse.
`preview` reports, row by row, what would happen; `run_import` creates the assets that are ready.
"""
from __future__ import annotations

import csv
import io
import re
import zipfile
from datetime import date, datetime, timedelta
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

from .assets import _clean_asset, save_asset
from .common import ApiError, audit, one, rows

MAX_FILE = 5 * 1024 * 1024        # bytes uploaded
MAX_PART = 30 * 1024 * 1024       # bytes of any one part once unzipped (zip bombs stop here)
MAX_ROWS = 5000

# key, English header, Arabic header, required, hint (template second row)
COLUMNS: list[tuple[str, str, str, bool, str]] = [
    ("AssetName", "Asset name", "اسم الأصل", True, "Text"),
    ("AssetNameAr", "Asset name (Arabic)", "اسم الأصل بالعربية", False, "Text"),
    ("Group", "Fixed asset group", "مجموعة الأصل", True, "Group code or name (see the Lists sheet)"),
    ("AcquisitionDate", "Acquisition date", "تاريخ الاقتناء", True, "dd/mm/yyyy"),
    ("PurchaseAmount", "Invoice amount", "مبلغ الفاتورة", True, "Number"),
    ("VatApplicable", "Purchased with VAT", "خاضع للضريبة", False, "Yes / No"),
    ("VatInclusive", "Amount includes VAT", "المبلغ شامل الضريبة", False, "Yes / No"),
    ("VatRate", "VAT rate (%)", "نسبة الضريبة (%)", False, "Number, e.g. 15"),
    ("ResidualValue", "Residual value", "القيمة التخريدية", False, "Number"),
    ("InServiceDate", "In-service date", "تاريخ بدء الاستخدام", False, "dd/mm/yyyy"),
    ("DepreciationStartDate", "Depreciation start date", "تاريخ بدء الإهلاك", False, "dd/mm/yyyy"),
    ("OpeningAccumDep", "Opening accumulated depreciation", "مجمع الإهلاك الافتتاحي", False, "For assets already depreciated before the first period"),
    ("UsefulLifeYears", "Useful life (years)", "العمر الإنتاجي (سنوات)", False, "Blank = the group's life"),
    ("Location", "Location", "الموقع", False, "Code or name"),
    ("CostCenter", "Cost center", "مركز التكلفة", False, "Code or name"),
    ("Supplier", "Supplier", "المورد", False, "Code or name"),
    ("InvoiceNumber", "Invoice number", "رقم الفاتورة", False, "Text"),
    ("PurchaseOrderNumber", "Purchase order", "أمر الشراء", False, "Text"),
    ("SerialNumber", "Serial number", "الرقم التسلسلي", False, "Text"),
    ("Manufacturer", "Manufacturer", "الشركة المصنعة", False, "Text"),
    ("ModelNumber", "Model", "الموديل", False, "Text"),
    ("WarrantyExpiryDate", "Warranty expiry", "انتهاء الضمان", False, "dd/mm/yyyy"),
    ("ResponsiblePerson", "Responsible person", "المسؤول عن الأصل", False, "Text"),
    ("AssetDescription", "Description", "الوصف", False, "Text"),
    ("Notes", "Notes", "ملاحظات", False, "Text"),
]
DATE_KEYS = {"AcquisitionDate", "InServiceDate", "DepreciationStartDate", "WarrantyExpiryDate"}
NUM_KEYS = {"PurchaseAmount", "VatRate", "ResidualValue", "OpeningAccumDep", "UsefulLifeYears"}
BOOL_KEYS = {"VatApplicable", "VatInclusive"}

AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")


def fold(s) -> str:
    """Compare headers and names loosely: case, spaces, '*' and Arabic letter forms do not matter."""
    s = str(s or "").strip().lower().translate(AR_DIGITS)
    s = re.sub(r"[ً-ٰٟـ*]", "", s)
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه"), ("ؤ", "و"), ("ئ", "ي")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()   # trimmed last: "Asset name *" loses its star and the space before it


HEADER_KEYS = {fold(h): key for key, en, ar, _, _ in COLUMNS for h in (en, ar, key)}
HINTS = {fold(c[4]) for c in COLUMNS}


# ---------------------------------------------------------------- reading files
def _safe_xml(data: bytes):
    if b"<!DOCTYPE" in data[:2048].upper() or b"<!ENTITY" in data.upper():
        raise ApiError("The Excel file contains content that is not allowed")
    return ET.fromstring(data)


def _read_part(z: zipfile.ZipFile, name: str) -> bytes:
    info = z.getinfo(name)
    if info.file_size > MAX_PART:
        raise ApiError("The Excel file is too large")
    return z.read(name)


def _col_index(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_xlsx(content: bytes) -> list[list]:
    """The cells of the first worksheet, as rows of values (strings, numbers or None)."""
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
          "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    try:
        z = zipfile.ZipFile(io.BytesIO(content))
        names = set(z.namelist())
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            for si in _safe_xml(_read_part(z, "xl/sharedStrings.xml")).findall("m:si", ns):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{ns['m']}}}t")))
        wb = _safe_xml(_read_part(z, "xl/workbook.xml"))
        first = wb.find("m:sheets/m:sheet", ns)
        rid = first.get(f"{{{ns['r']}}}id")
        rels = _safe_xml(_read_part(z, "xl/_rels/workbook.xml.rels"))
        target = next(r.get("Target") for r in rels if r.get("Id") == rid)
        path = target.lstrip("/") if target.startswith("/") else "xl/" + target
        sheet = _safe_xml(_read_part(z, path))
    except ApiError:
        raise
    except Exception:  # noqa: BLE001 - anything unreadable is the same answer for the user
        raise ApiError("This is not a readable Excel (.xlsx) file")
    out: list[list] = []
    for r in sheet.iter(f"{{{ns['m']}}}row"):
        vals: dict[int, object] = {}
        for c in r.findall("m:c", ns):
            kind, v = c.get("t"), c.find("m:v", ns)
            if kind == "inlineStr":
                val = "".join(t.text or "" for t in c.iter(f"{{{ns['m']}}}t"))
            elif v is None:
                continue
            elif kind == "s":
                val = shared[int(v.text)]
            elif kind in ("str", "e"):
                val = v.text or ""
            elif kind == "b":
                val = "yes" if v.text == "1" else "no"
            else:
                try:
                    val = float(v.text)
                except (TypeError, ValueError):
                    val = v.text
            vals[_col_index(c.get("r"))] = val
        if vals:
            out.append([vals.get(i) for i in range(max(vals) + 1)])
        if len(out) > MAX_ROWS + 2:
            raise ApiError(f"The file has more than {MAX_ROWS} rows")
    return out


def read_csv(content: bytes) -> list[list]:
    text = content.decode("utf-8-sig", errors="replace")
    dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t") if text.strip() else csv.excel
    out = [r for r in csv.reader(io.StringIO(text), dialect)]
    if len(out) > MAX_ROWS + 2:
        raise ApiError(f"The file has more than {MAX_ROWS} rows")
    return out


def read_table(filename: str, content: bytes) -> list[list]:
    if not content:
        raise ApiError("The file is empty")
    if len(content) > MAX_FILE:
        raise ApiError("The file is larger than 5 MB")
    if filename.lower().endswith(".csv"):
        return read_csv(content)
    if content[:2] == b"PK":
        return read_xlsx(content)
    raise ApiError("Choose an Excel (.xlsx) or CSV file")


# ---------------------------------------------------------------- values
def _date(v) -> str | None:
    if v in (None, ""):
        return None
    if isinstance(v, float):   # Excel stores dates as days since 30/12/1899
        if not 1 <= v < 2958466:
            raise ValueError
        return (date(1899, 12, 30) + timedelta(days=int(v))).isoformat()
    s = str(v).strip().translate(AR_DIGITS)
    if re.fullmatch(r"\d{5}(\.0+)?", s):   # an Excel date serial that reached a CSV as text
        return _date(float(s))
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d", "%d/%m/%y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError


def _num(v) -> float | None:
    if v in (None, ""):
        return None
    if isinstance(v, float):
        return v
    s = re.sub(r"[^\d.\-]", "", str(v).translate(AR_DIGITS).replace(",", ""))
    if not s or s in ("-", "."):
        raise ValueError
    return float(s)


def _bool(v):
    if v in (None, ""):
        return None
    s = fold(v)
    if s in ("yes", "y", "true", "1", "1.0", "نعم", "x"):
        return 1
    if s in ("no", "n", "false", "0", "0.0", "لا"):
        return 0
    raise ValueError


class _Lookup:
    """Finds a master record by its code or by its English or Arabic name."""
    def __init__(self, con, table: str, pk: str, code: str, name: str):
        self.items = rows(con, f"SELECT {pk} id, {code} code, {name} name, {name}Ar name_ar, IsActive active FROM {table}", raw=True)

    def find(self, v) -> dict | None:
        k = fold(str(int(v)) if isinstance(v, float) and v.is_integer() else v)   # a numeric code typed in Excel arrives as 12.0
        return next((i for i in self.items if fold(i["code"]) == k), None) or \
            next((i for i in self.items if k and k in (fold(i["name"]), fold(i["name_ar"]))), None)


# ---------------------------------------------------------------- preview and import
def _rows_with_keys(table: list[list]) -> tuple[list[tuple[int, dict]], list[str]]:
    """Find the header row (the first one that names a required column) and map every following row to column keys."""
    for hi, header in enumerate(table[:10]):
        keys = [HEADER_KEYS.get(fold(h)) for h in header]
        if "AssetName" in keys and "Group" in keys:
            break
    else:
        raise ApiError("The header row was not found. Use the template: it needs at least the columns Asset name and Fixed asset group.")
    missing = [en for key, en, _, req, _ in COLUMNS if req and key not in keys]
    out = []
    for i, r in enumerate(table[hi + 1:], start=hi + 2):
        rec = {k: r[j] for j, k in enumerate(keys) if k and j < len(r) and r[j] not in (None, "")}
        if not rec or all(fold(v) in HINTS for v in rec.values()):
            continue   # blank rows, and the template's hint row
        out.append((i, rec))
    return out, missing


def msg(text: str, *args) -> dict:
    """A message the screen translates: an English template ({0}, {1} ...) and its values (column names are translated too)."""
    return {"t": text, "a": [str(a) for a in args]}


def _prepare(con, rec: dict, look: dict) -> tuple[dict, list[dict]]:
    """The asset as the form would send it, and the problems found on the way."""
    data: dict = {}
    errors: list[dict] = []
    for key, en, _, req, _ in COLUMNS:
        v = rec.get(key)
        if v in (None, ""):
            if req:
                errors.append(msg("{0} is required", en))
            continue
        try:
            if key in DATE_KEYS:
                data[key] = _date(v)
            elif key in NUM_KEYS:
                data[key] = _num(v)
            elif key in BOOL_KEYS:
                data[key] = _bool(v)
            elif key in ("Group", "Location", "CostCenter", "Supplier"):
                hit = look[key].find(v)
                if not hit:
                    errors.append(msg("{0} '{1}' was not found", en, v))
                else:
                    data[{"Group": "CategoryID", "Location": "LocationID", "CostCenter": "CostCenterID", "Supplier": "SupplierID"}[key]] = hit["id"]
            else:
                data[key] = str(v).strip() if not isinstance(v, float) else (str(int(v)) if v.is_integer() else str(v))
        except ValueError:
            errors.append(msg("{0} '{1}' is not valid", en, v))
    return data, errors


def preview(con, filename: str, content: bytes) -> dict:
    """Row by row: what will be created, or why not. Nothing is written."""
    table = read_table(filename, content)
    recs, missing = _rows_with_keys(table)
    if missing:
        raise ApiError("Columns missing from the file: " + ", ".join(missing))
    look = {"Group": _Lookup(con, "tbl_AssetCategories", "CategoryID", "CategoryCode", "CategoryName"),
            "Location": _Lookup(con, "tbl_Locations", "LocationID", "LocationCode", "LocationName"),
            "CostCenter": _Lookup(con, "tbl_CostCenters", "CostCenterID", "CostCenterCode", "CostCenterName"),
            "Supplier": _Lookup(con, "tbl_Suppliers", "SupplierID", "SupplierCode", "SupplierName")}
    st_vat = one(con, "SELECT SettingValue v FROM tbl_Settings WHERE SettingKey='VATDefaultApplicable'", raw=True)
    first = one(con, "SELECT MIN(StartDate) s FROM tbl_DepreciationPeriods", raw=True)["s"]
    serials = {fold(r["SerialNumber"]) for r in rows(con, "SELECT SerialNumber FROM tbl_Assets WHERE SerialNumber IS NOT NULL", raw=True)}
    seen: dict[str, int] = {}
    out = []
    for line, rec in recs:
        data, errors = _prepare(con, rec, look)
        warnings: list[dict] = []
        if "VatApplicable" not in data:
            data["VatApplicable"] = 1 if (st_vat and st_vat["v"] == "1") else 0
        clean = None
        if not errors:
            try:
                clean = _clean_asset(con, data, None)   # exactly the form's rules
            except ApiError as e:
                errors.append(msg(str(e)))
        if clean:
            start = clean["DepreciationStartDate"]
            if first and start[:7] < first[:7] and not clean["OpeningAccumDep"]:
                warnings.append(msg("Depreciation started before the first period: enter the opening accumulated depreciation, or it will not be depreciated"))
        sn = fold(data.get("SerialNumber"))
        if sn:
            if sn in serials:
                warnings.append(msg("An asset with this serial number already exists"))
            if sn in seen:
                warnings.append(msg("Same serial number as row {0}", seen[sn]))
            seen.setdefault(sn, line)
        out.append({"row": line, "status": "error" if errors else "warning" if warnings else "ok", "errors": errors, "warnings": warnings,
                    "AssetName": data.get("AssetName") or rec.get("AssetName"), "Group": rec.get("Group"),
                    "AcquisitionDate": data.get("AcquisitionDate"), "PurchaseAmount": data.get("PurchaseAmount"),
                    "AcquisitionCost": clean["AcquisitionCost"] if clean else None, "VatAmount": clean["VatAmount"] if clean else None, "data": data})
    if not out:
        raise ApiError("The file has no asset rows under the header")
    ready = [r for r in out if r["status"] != "error"]
    return {"rows": out, "total": len(out), "ready": len(ready), "errors": len(out) - len(ready),
            "cost": round(sum(r["AcquisitionCost"] or 0 for r in ready), 2)}


def run_import(con, filename: str, content: bytes, skip_errors: bool) -> dict:
    """Create the ready rows. With errors in the file nothing is created unless skip_errors is set."""
    p = preview(con, filename, content)
    if p["errors"] and not skip_errors:
        raise ApiError(f"{p['errors']} row(s) have errors. Fix them, or choose to import only the rows that are ready.")
    created = []
    for r in p["rows"]:
        if r["status"] == "error":
            continue
        a = save_asset(con, r["data"])
        created.append({"row": r["row"], "AssetID": a["AssetID"], "AssetCode": a["AssetCode"], "AssetName": a["AssetName"]})
    audit(con, "IMPORT", "tbl_Assets", "-", f"{filename}: {len(created)} asset(s) created, {p['errors']} row(s) skipped")
    con.commit()
    return {"created": created, "skipped": p["errors"]}


# ---------------------------------------------------------------- the template
def _cell(ref: str, v, style: int = 0) -> str:
    s = f' s="{style}"' if style else ""
    if isinstance(v, (int, float)):
        return f'<c r="{ref}"{s}><v>{v}</v></c>'
    return f'<c r="{ref}" t="inlineStr"{s}><is><t xml:space="preserve">{escape(str(v))}</t></is></c>'


def _ref(col: int, row: int) -> str:
    name = ""
    col += 1
    while col:
        col, rem = divmod(col - 1, 26)
        name = chr(65 + rem) + name
    return f"{name}{row}"


def write_xlsx(sheets: list[tuple[str, list[list], list[int]]]) -> bytes:
    """A minimal .xlsx: [(sheet name, rows, column widths)]; row 1 bold, row 2 grey italic when it is a hint row."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                   + "".join(f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(len(sheets)))
                   + "</Types>")
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   + "".join(f'<sheet name="{escape(n)}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, (n, _, _) in enumerate(sheets)) + "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + "".join(f'<Relationship Id="rId{i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i + 1}.xml"/>' for i in range(len(sheets)))
                   + f'<Relationship Id="rId{len(sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        z.writestr("xl/styles.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   '<fonts count="3"><font><sz val="11"/><name val="Segoe UI"/></font><font><b/><sz val="11"/><name val="Segoe UI"/></font><font><i/><sz val="10"/><color rgb="FF5C6773"/><name val="Segoe UI"/></font></fonts>'
                   '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFEEF4F9"/></patternFill></fill></fills>'
                   '<borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs>'
                   '<cellXfs count="3"><xf/><xf fontId="1" fillId="2" applyFont="1" applyFill="1"/><xf fontId="2" applyFont="1"/></cellXfs></styleSheet>')
        for i, (_, data, widths) in enumerate(sheets):
            cols = "".join(f'<col min="{j + 1}" max="{j + 1}" width="{w}" customWidth="1"/>' for j, w in enumerate(widths))
            body = "".join(f'<row r="{r + 1}">' + "".join(_cell(_ref(c, r + 1), v, 1 if r == 0 else 2 if (r == 1 and i == 0) else 0)
                                                          for c, v in enumerate(row) if v not in (None, "")) + "</row>" for r, row in enumerate(data))
            z.writestr(f"xl/worksheets/sheet{i + 1}.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                       '<sheetViews><sheetView workbookViewId="0"><pane ySplit="2" topLeftCell="A3" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
                       f"<cols>{cols}</cols><sheetData>{body}</sheetData></worksheet>")
    return buf.getvalue()


def template(con, lang: str = "en") -> bytes:
    """The import template: the columns (with a hint row), one example, and the valid groups, locations, cost centers and suppliers."""
    ar = lang == "ar"
    head = [(c[2] if ar else c[1]) + (" *" if c[3] else "") for c in COLUMNS]
    hints = [c[4] for c in COLUMNS]
    cat = one(con, "SELECT CategoryCode FROM tbl_AssetCategories WHERE IsActive=1 ORDER BY CategoryCode LIMIT 1", raw=True)
    example = {"AssetName": "Office desk", "AssetNameAr": "مكتب", "Group": cat["CategoryCode"] if cat else "", "AcquisitionDate": date.today().strftime("%d/%m/%Y"),
               "PurchaseAmount": 1150, "VatApplicable": "Yes", "VatInclusive": "Yes", "VatRate": 15, "SerialNumber": "SN-0001"}
    sheet1 = [head, hints, [example.get(c[0], "") for c in COLUMNS]]
    lists = [["Groups", "", "Locations", "", "Cost centers", "", "Suppliers", ""], ["Code", "Name", "Code", "Name", "Code", "Name", "Code", "Name"]]
    cols = [rows(con, f"SELECT {c}, {n}{'Ar' if ar else ''} n2, {n} FROM {t} WHERE IsActive=1 ORDER BY {c}", raw=True)
            for t, c, n in (("tbl_AssetCategories", "CategoryCode", "CategoryName"), ("tbl_Locations", "LocationCode", "LocationName"),
                            ("tbl_CostCenters", "CostCenterCode", "CostCenterName"), ("tbl_Suppliers", "SupplierCode", "SupplierName"))]
    for i in range(max((len(c) for c in cols), default=0)):
        row = []
        for c in cols:
            r = c[i] if i < len(c) else None
            row += [list(r.values())[0], r["n2"] or list(r.values())[2]] if r else ["", ""]
        lists.append(row)
    return write_xlsx([("Assets" if not ar else "الأصول", sheet1, [24 if c[0] in ("AssetName", "AssetNameAr", "Group") else 18 for c in COLUMNS]),
                       ("Lists" if not ar else "القوائم", lists, [12, 28] * 4)])
