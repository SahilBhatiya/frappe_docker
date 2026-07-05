# Copyright (c) 2026, Ravindu Gajanayaka
# Licensed under GPLv3. See license.txt

"""Staff Attendance — owner-side daily attendance for the POS Prime Staff module.

One record per employee per day (enforced by the {employee}-{attendance_date} name).
Salary is fixed monthly, so attendance is informational and does not affect pay in v1.

QR / mobile self check-in is intentionally deferred: `checkin` is a reserved hook that
writes check_in/check_out on the same records once that flow is built.
"""

import json

import frappe
from frappe import _
from frappe.utils import nowdate

from pos_prime.api._utils import validate_pos_access

VALID_STATUSES = ("Present", "Absent", "Half Day", "Leave", "Holiday")


def _loads(value, default):
    if value is None or value == "":
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return default
    return value


def _upsert(employee, attendance_date, status, check_in=None, check_out=None, notes=None):
    if status not in VALID_STATUSES:
        frappe.throw(_("Invalid attendance status {0}").format(status))
    if not frappe.db.exists("Employee", employee):
        frappe.throw(_("Employee {0} not found").format(employee), frappe.DoesNotExistError)

    name = frappe.db.exists("Staff Attendance", {"employee": employee, "attendance_date": attendance_date})
    doc = frappe.get_doc("Staff Attendance", name) if name else frappe.new_doc("Staff Attendance")
    if not name:
        doc.employee = employee
        doc.attendance_date = attendance_date
    doc.status = status
    if check_in is not None:
        doc.check_in = check_in or None
    if check_out is not None:
        doc.check_out = check_out or None
    if notes is not None:
        doc.notes = notes
    doc.save()
    return doc


@frappe.whitelist()
def list_attendance(from_date, to_date, employee=None):
    """Attendance records in a date range, optionally for one employee."""
    validate_pos_access()
    filters = {"attendance_date": ["between", [from_date, to_date]]}
    if employee:
        filters["employee"] = employee
    return frappe.get_all(
        "Staff Attendance",
        filters=filters,
        fields=[
            "name",
            "employee",
            "employee_name",
            "attendance_date",
            "status",
            "check_in",
            "check_out",
            "working_hours",
            "notes",
        ],
        order_by="attendance_date desc, employee_name asc",
        limit_page_length=0,
    )


@frappe.whitelist()
def mark_attendance(employee, attendance_date, status, check_in=None, check_out=None, notes=None):
    """Create or update one employee's attendance for a day."""
    validate_pos_access()
    doc = _upsert(employee, attendance_date or nowdate(), status, check_in, check_out, notes)
    return doc.as_dict()


@frappe.whitelist()
def bulk_mark(attendance_date, rows):
    """Mark attendance for many employees on one date.

    `rows` is a JSON list of {employee, status, check_in?, check_out?, notes?}.
    Returns per-row results so one bad row doesn't abort the rest.
    """
    validate_pos_access()
    rows = _loads(rows, [])
    attendance_date = attendance_date or nowdate()
    results = []
    for r in rows:
        employee = (r or {}).get("employee")
        try:
            _upsert(
                employee,
                attendance_date,
                (r or {}).get("status"),
                (r or {}).get("check_in"),
                (r or {}).get("check_out"),
                (r or {}).get("notes"),
            )
            results.append({"employee": employee, "ok": True})
        except Exception as e:  # noqa: BLE001 - report per-row, never 500 the batch
            results.append({"employee": employee, "ok": False, "error": str(e)})
    return {"results": results}


@frappe.whitelist()
def day_sheet(attendance_date):
    """Every active employee with their status for a given day (blank = unmarked).

    Powers the Attendance page's single-day marking grid.
    """
    validate_pos_access()
    attendance_date = attendance_date or nowdate()
    employees = frappe.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=["name", "employee_name"],
        order_by="employee_name asc",
        limit_page_length=0,
    )
    marked = {
        a.employee: a
        for a in frappe.get_all(
            "Staff Attendance",
            filters={"attendance_date": attendance_date},
            fields=["employee", "status", "check_in", "check_out", "working_hours", "notes"],
        )
    }
    for e in employees:
        rec = marked.get(e.name)
        e["status"] = rec.status if rec else None
        e["check_in"] = rec.check_in if rec else None
        e["check_out"] = rec.check_out if rec else None
        e["working_hours"] = rec.working_hours if rec else None
        e["notes"] = rec.notes if rec else None
    return employees
