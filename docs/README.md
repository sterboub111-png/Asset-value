# Usool (أصول) — documentation

Usool is a local fixed-asset management system: asset register, depreciation, disposal, transfers, maintenance, suppliers,
employees and asset custody, VAT, backups and reports. It runs on one PC (`http://127.0.0.1:8742/`), stores data in SQLite,
and is bilingual (Arabic / English, RTL / LTR) with a Microsoft Dynamics 365 style interface.

| Document | Read it to… |
|---|---|
| [architecture.md](architecture.md) | see the whole system, folder layout and request flow |
| [backend.md](backend.md) | work on the Python code: packages, services, conventions |
| [api.md](api.md) | look up an HTTP endpoint and the permission it needs (generated) |
| [database.md](database.md) | understand tables, keys and the accounting entries |
| [frontend.md](frontend.md) | work on the TypeScript / CSS code and the UI kit |
| [business-rules.md](business-rules.md) | know exactly how depreciation, disposal, VAT, custody and periods behave |
| [security.md](security.md) | understand sign-in, roles, sessions and hardening |
| [user-guide.md](user-guide.md) | use the system day to day (English) |
| [user-guide.ar.md](user-guide.ar.md) | دليل الاستخدام بالعربية |
| [development.md](development.md) | set up, build, test, add a feature or a translation, run the tools |

Quick start: double-click `Usool.bat` (or `python run.py`), open http://127.0.0.1:8742/, create the administrator on the first visit.
