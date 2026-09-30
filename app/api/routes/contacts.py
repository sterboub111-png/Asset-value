"""Suppliers and employees."""
from __future__ import annotations

from ... import services as s

from ..router import route


@route("GET", "/api/suppliers/next-code")
def _snc(c): return {"code": s.next_supplier_code(c.con)}

@route("GET", "/api/suppliers")
def _sl(c): return s.list_suppliers(c.con, c.q("q"), c.q("active"), c.q("type"))

@route("POST", "/api/suppliers")
def _sc(c): return s.save_supplier(c.con, c.body)

@route("GET", "/api/suppliers/(\\d+)")
def _sg2(c, i): return s.get_supplier(c.con, int(i))

@route("PUT", "/api/suppliers/(\\d+)")
def _su(c, i): return s.save_supplier(c.con, c.body, int(i))

@route("DELETE", "/api/suppliers/(\\d+)")
def _sd(c, i): return s.delete_supplier(c.con, int(i))

@route("GET", "/api/employees/next-code")
def _enc(c): return {"code": s.next_employee_code(c.con)}

@route("GET", "/api/employees")
def _el(c): return s.list_employees(c.con, c.q("q"), c.q("active"))

@route("POST", "/api/employees")
def _ec(c): return s.save_employee(c.con, c.body)

@route("GET", "/api/employees/(\\d+)")
def _eg(c, i): return s.get_employee(c.con, int(i))

@route("PUT", "/api/employees/(\\d+)")
def _eu(c, i): return s.save_employee(c.con, c.body, int(i))

@route("DELETE", "/api/employees/(\\d+)")
def _ed(c, i): return s.delete_employee(c.con, int(i))
