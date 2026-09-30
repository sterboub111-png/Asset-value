"""Importing this package registers every route (order matters only for overlapping patterns)."""
from . import setup, assets, depreciation, maintenance, contacts, custody, backups, accounts, inquiries

__all__ = ["setup", "assets", "depreciation", "maintenance", "contacts", "custody", "backups", "accounts", "inquiries"]
