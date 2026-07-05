# Copyright (c) 2026, Ravindu Gajanayaka
# Licensed under GPLv3. See license.txt

"""Staff Payroll — advances and monthly payslips.

Model (deliberately simple, cash-based, no GL posting):
  * A Staff Advance is money handed to an employee; `balance` is what's still to recover.
  * A Staff Payslip nets a fixed monthly salary against advance deductions and a manual
    adjustment: net_pay = base_salary - advances_deducted + adjustment.
  * A Draft payslip never touches advance balances; only mark_payslip_paid recovers them,
    and cancel_payslip reverses a paid one. This keeps regeneration side-effect free.

All endpoints are owner/manager only (validate_pos_access).
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, nowdate

from pos_prime.api._utils import validate_pos_access


def _loads(value, default):
    if value is None or value == "":
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return default
    return value


# ---------------------------------------------------------------------------
# Advances
# ---------------------------------------------------------------------------

@frappe.whitelist()
def list_advances(employee=None, status=None, limit=100, offset=0):
    validate_pos_access()
    filters = {}
    if employee:
        filters["employee"] = employee
    if status:
        filters["status"] = status
    try:
        limit = max(1, min(int(limit), 500))
        offset = max(0, int(offset))
    except (ValueError, TypeError):
        limit, offset = 100, 0
    return frappe.get_all(
        "Staff Advance",
        filters=filters,
        fields=["name", "employee", "employee_name", "date", "amount", "balance", "status", "notes"],
        order_by="date desc, creation desc",
        limit_page_length=limit,
        limit_start=offset,
    )


@frappe.whitelist()
def get_outstanding_advances(employee):
    """Advances for an employee that still have a recoverable balance."""
    validate_pos_access()
    return frappe.get_all(
        "Staff Advance",
        filters={"employee": employee, "status": ["!=", "Cancelled"], "balance": [">", 0]},
        fields=["name", "date", "amount", "balance"],
        order_by="date asc, creation asc",
    )


@frappe.whitelist()
def create_advance(employee, amount, date=None, notes=None):
    validate_pos_access()
    if not frappe.db.exists("Employee", employee):
        frappe.throw(_("Employee {0} not found").format(employee), frappe.DoesNotExistError)
    if flt(amount) <= 0:
        frappe.throw(_("Advance amount must be greater than zero"))

    doc = frappe.get_doc(
        {
            "doctype": "Staff Advance",
            "employee": employee,
            "date": date or nowdate(),
            "amount": flt(amount),
            "notes": notes,
        }
    )
    doc.insert()
    return doc.as_dict()


@frappe.whitelist()
def cancel_advance(name):
    """Cancel an advance entered by mistake. Not allowed once partly recovered."""
    validate_pos_access()
    doc = frappe.get_doc("Staff Advance", name)
    if flt(doc.balance) < flt(doc.amount):
        frappe.throw(_("This advance has already been partly recovered and cannot be cancelled."))
    doc.status = "Cancelled"
    doc.balance = 0
    doc.save()
    return doc.as_dict()


# ---------------------------------------------------------------------------
# Payslips
# ---------------------------------------------------------------------------

def _active_salaried_employees():
    has_salary = frappe.db.has_column("Employee", "custom_monthly_salary")
    fields = ["name", "employee_name"]
    if has_salary:
        fields.append("custom_monthly_salary")
    rows = frappe.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=fields,
        order_by="employee_name asc",
        limit_page_length=0,
    )
    for r in rows:
        r["base_salary"] = flt(r.get("custom_monthly_salary"))
    return rows


@frappe.whitelist()
def preview_payroll(start_date, end_date):
    """Build a payroll preview for every active employee for the given period.

    Returns base salary, current outstanding advances (with a suggested full deduction),
    and any payslip that already exists for the period so the UI won't double-generate.
    """
    validate_pos_access()

    employees = _active_salaried_employees()
    names = [e.name for e in employees]

    advances_by_emp = {}
    if names:
        for a in frappe.get_all(
            "Staff Advance",
            filters={"employee": ["in", names], "status": ["!=", "Cancelled"], "balance": [">", 0]},
            fields=["name", "employee", "date", "amount", "balance"],
            order_by="date asc, creation asc",
        ):
            advances_by_emp.setdefault(a.employee, []).append(a)

    existing = {}
    if names:
        for p in frappe.get_all(
            "Staff Payslip",
            filters={"employee": ["in", names], "start_date": start_date},
            fields=["name", "employee", "status", "net_pay"],
        ):
            existing[p.employee] = p

    rows = []
    for e in employees:
        advs = advances_by_emp.get(e.name, [])
        suggested = sum(flt(a.balance) for a in advs)
        rows.append(
            {
                "employee": e.name,
                "employee_name": e.employee_name,
                "base_salary": e.base_salary,
                "advances": advs,
                "suggested_deduction": suggested,
                "net_preview": flt(e.base_salary) - suggested,
                "existing_payslip": existing.get(e.name),
            }
        )
    return rows


@frappe.whitelist()
def create_payslip(
    employee,
    start_date,
    end_date,
    base_salary,
    period_label=None,
    advance_deductions=None,
    adjustment=0,
    adjustment_note=None,
):
    """Create or update the Draft payslip for an employee + period.

    `advance_deductions` is a JSON list of {advance, amount}. Draft only — advance
    balances are untouched until mark_payslip_paid.
    """
    validate_pos_access()
    if not frappe.db.exists("Employee", employee):
        frappe.throw(_("Employee {0} not found").format(employee), frappe.DoesNotExistError)

    deductions = _loads(advance_deductions, [])

    existing = frappe.db.exists("Staff Payslip", {"employee": employee, "start_date": start_date})
    if existing:
        doc = frappe.get_doc("Staff Payslip", existing)
        if doc.status == "Paid":
            frappe.throw(_("A paid payslip already exists for this employee and period."))
    else:
        doc = frappe.new_doc("Staff Payslip")
        doc.employee = employee
        doc.start_date = start_date

    doc.end_date = end_date
    doc.period_label = period_label
    doc.base_salary = flt(base_salary)
    doc.adjustment = flt(adjustment)
    doc.adjustment_note = adjustment_note
    doc.status = "Draft"

    doc.set("advances", [])
    for d in deductions:
        advance = (d or {}).get("advance")
        amount = flt((d or {}).get("amount"))
        if not advance or amount <= 0:
            continue
        adv = frappe.db.get_value("Staff Advance", advance, ["employee", "balance"], as_dict=True)
        if not adv or adv.employee != employee:
            frappe.throw(_("Advance {0} does not belong to this employee").format(advance))
        if amount > flt(adv.balance):
            frappe.throw(
                _("Deduction {0} exceeds the remaining balance of advance {1}").format(amount, advance)
            )
        doc.append("advances", {"advance": advance, "amount_deducted": amount})

    doc.save()
    return get_payslip(doc.name)


@frappe.whitelist()
def mark_payslip_paid(name, paid_on=None, payment_mode="Cash"):
    """Mark a payslip Paid and recover its advance deductions from the linked advances."""
    validate_pos_access()
    doc = frappe.get_doc("Staff Payslip", name)
    if doc.status == "Paid":
        return get_payslip(name)
    if doc.status == "Cancelled":
        frappe.throw(_("A cancelled payslip cannot be paid."))

    for row in doc.advances:
        adv = frappe.get_doc("Staff Advance", row.advance)
        # Clamp to the advance's current balance in case it changed since Draft.
        applied = min(flt(row.amount_deducted), flt(adv.balance))
        row.amount_deducted = applied
        adv.balance = flt(adv.balance) - applied
        adv.save()

    doc.status = "Paid"
    doc.paid_on = paid_on or nowdate()
    doc.payment_mode = payment_mode or "Cash"
    doc.save()  # validate() re-totals advances_deducted + net_pay from the (clamped) rows
    return get_payslip(name)


@frappe.whitelist()
def cancel_payslip(name):
    """Cancel a payslip. A paid one restores the advance balances it had recovered."""
    validate_pos_access()
    doc = frappe.get_doc("Staff Payslip", name)
    if doc.status == "Cancelled":
        return get_payslip(name)

    if doc.status == "Paid":
        for row in doc.advances:
            if not frappe.db.exists("Staff Advance", row.advance):
                continue
            adv = frappe.get_doc("Staff Advance", row.advance)
            adv.balance = min(flt(adv.balance) + flt(row.amount_deducted), flt(adv.amount))
            adv.save()

    doc.status = "Cancelled"
    doc.save()
    return get_payslip(name)


@frappe.whitelist()
def list_payslips(employee=None, status=None, limit=100, offset=0):
    validate_pos_access()
    filters = {}
    if employee:
        filters["employee"] = employee
    if status:
        filters["status"] = status
    try:
        limit = max(1, min(int(limit), 500))
        offset = max(0, int(offset))
    except (ValueError, TypeError):
        limit, offset = 100, 0
    return frappe.get_all(
        "Staff Payslip",
        filters=filters,
        fields=[
            "name",
            "employee",
            "employee_name",
            "period_label",
            "start_date",
            "end_date",
            "base_salary",
            "total_advance_deducted",
            "adjustment",
            "net_pay",
            "status",
            "paid_on",
            "payment_mode",
        ],
        order_by="start_date desc, creation desc",
        limit_page_length=limit,
        limit_start=offset,
    )


@frappe.whitelist()
def get_payslip(name):
    validate_pos_access()
    doc = frappe.get_doc("Staff Payslip", name)
    data = doc.as_dict()
    data["advances"] = [
        {
            "advance": r.advance,
            "advance_date": str(r.advance_date) if r.advance_date else None,
            "advance_amount": flt(r.advance_amount),
            "amount_deducted": flt(r.amount_deducted),
        }
        for r in doc.advances
    ]
    return data
