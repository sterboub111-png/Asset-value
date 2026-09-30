"""Files attached to assets."""
from __future__ import annotations

import os
import re
from pathlib import Path

from .assets import get_asset
from .files import _attach_root, _remove_file
from .common import ApiError, actor, audit, now, one

def add_attachment(con, asset_id: int, filename: str, content: bytes, meta: dict) -> dict:
    a = get_asset(con, asset_id)
    if not content:
        raise ApiError("The file is empty")
    if len(content) > 50 * 1024 * 1024:
        raise ApiError("File is larger than 50 MB")
    clean = lambda x: re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(x)).strip(" .") or "x"
    ext = re.sub(r"[^.\w]", "", Path(os.path.basename(filename)).suffix.lower())[:12]
    if ext in (".", ""):
        ext = ""
    cat = one(con, "SELECT CategoryCode, CategoryName FROM tbl_AssetCategories WHERE CategoryID=?", (a["CategoryID"],), raw=True) or {}
    raw_asset = one(con, "SELECT AssetCode, AcquisitionDate FROM tbl_Assets WHERE AssetID=?", (asset_id,), raw=True)
    # <root>/<group>/<purchase year-month>/<asset number>/<asset number>_<purchase date>[_n].<ext>
    folder = (_attach_root(con) / clean(f"{cat.get('CategoryCode', '')} - {cat.get('CategoryName', '')}")
              / raw_asset["AcquisitionDate"][:7] / clean(raw_asset["AssetCode"]))
    folder.mkdir(parents=True, exist_ok=True)
    base = f"{clean(raw_asset['AssetCode'])}_{raw_asset['AcquisitionDate']}"
    custody_id = int(meta["custody_id"]) if meta.get("custody_id") else None
    if custody_id:  # signed handover / return forms: <asset>_<custody no>_<issue date>
        cu = one(con, "SELECT CustodyNo, IssueDate FROM tbl_AssetCustody WHERE CustodyID=? AND AssetID=?", (custody_id, asset_id), raw=True)
        if not cu:
            raise ApiError("Custody record not found", 404)
        base = f"{clean(raw_asset['AssetCode'])}_{clean(cu['CustodyNo'])}_{cu['IssueDate']}"
    target, n = folder / f"{base}{ext}", 1
    while target.exists():
        n += 1
        target = folder / f"{base}_{n}{ext}"
    safe = target.name
    target.write_bytes(content)
    con.execute("INSERT INTO tbl_AssetAttachments(AssetID,CustodyID,DocumentTitle,DocumentType,FileName,FileExtension,FilePath,Notes,"
                "CreatedAt,CreatedBy) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (asset_id, custody_id, meta.get("title") or os.path.basename(filename)[:150] or safe, meta.get("type") or None, target.name,
                 target.suffix.lstrip(".").lower(), str(target), meta.get("notes") or None, now(), actor()))
    audit(con, "ATTACH", "tbl_Assets", asset_id, target.name)
    con.commit()
    return get_asset(con, asset_id)


def get_attachment(con, att_id: int) -> dict:
    att = one(con, "SELECT * FROM tbl_AssetAttachments WHERE AttachmentID=?", (att_id,))
    if not att or not Path(att["FilePath"] or "").is_file():
        raise ApiError("Attachment file not found", 404)
    return att


def delete_attachment(con, att_id: int) -> dict:
    att = one(con, "SELECT * FROM tbl_AssetAttachments WHERE AttachmentID=?", (att_id,))
    if not att:
        raise ApiError("Attachment not found", 404)
    _remove_file(att["FilePath"])
    con.execute("DELETE FROM tbl_AssetAttachments WHERE AttachmentID=?", (att_id,))
    audit(con, "DETACH", "tbl_Assets", att["AssetID"], att["FileName"])
    con.commit()
    return get_asset(con, att["AssetID"])
