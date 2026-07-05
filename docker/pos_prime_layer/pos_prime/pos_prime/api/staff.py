# Copyright (c) 2026, Ravindu Gajanayaka
# Licensed under GPLv3. See license.txt

"""Staff (Employee) master for the POS Prime Staff Payroll module.

Reuses ERPNext's core Employee doctype and stores a simple fixed monthly salary in the
pos_prime-owned custom field `custom_monthly_salary`. All endpoints are owner/manager
only — gated by validate_pos_access (POS Invoice read permission).
"""

import frappe
from frappe import _
from frappe.utils import flt, nowdate

from pos_prime.api._utils import validate_pos_access

# Employee fields the frontend needs. `custom_monthly_salary` is guarded at read time
# in case the field hasn't been created yet on a given site.
_EMP_FIELDS = [
    "name",
    "employee_name",
    "designation",
    "cell_number",
    "status",
    "date_of_joining",
    "company",
    "image",
]


def _default_company():
    return (
        frappe.defaults.get_global_default("company")
        or frappe.db.get_single_value("Global Defaults", "default_company")
        or frappe.db.get_value("Company", {}, "name")
    )


def _has_salary_field():
    return frappe.db.has_column("Employee", "custom_monthly_salary")


def _emp_fields():
    fields = list(_EMP_FIELDS)
    if _has_salary_field():
        fields.append("custom_monthly_salary")
    return fields


def _outstanding_map(employees=None):
    """Total outstanding (unrecovered) advance per employee, as a {employee: amount} map.

    Uses raw SQL for the aggregate — Frappe v16 rejects "sum(...) as x" string fields
    in frappe.get_all.
    """
    if employees is not None and not employees:
        return {}
    conditions = "status != 'Cancelled' AND balance > 0"
    params = {}
    if employees:
        conditions += " AND employee IN %(emps)s"
        params["emps"] = tuple(employees)
    rows = frappe.db.sql(
        f"""
        SELECT employee, SUM(balance) AS outstanding
        FROM `tabStaff Advance`
        WHERE {conditions}
        GROUP BY employee
        """,
        params,
        as_dict=True,
    )
    return {r.employee: flt(r.outstanding) for r in rows}


def _ensure_designation(designation):
    designation = (designation or "").strip()
    if designation and not frappe.db.exists("Designation", designation):
        frappe.get_doc(
            {"doctype": "Designation", "designation_name": designation}
        ).insert(ignore_permissions=True)
    return designation or None


@frappe.whitelist()
def list_staff(search="", include_inactive=0):
    """Return employees with their monthly salary + outstanding advance total."""
    validate_pos_access()

    filters = {}
    if not int(include_inactive or 0):
        filters["status"] = "Active"
    or_filters = None
    search = (search or "").strip()
    if search:
        or_filters = {
            "employee_name": ["like", f"%{search}%"],
            "name": ["like", f"%{search}%"],
            "cell_number": ["like", f"%{search}%"],
        }

    employees = frappe.get_all(
        "Employee",
        filters=filters,
        or_filters=or_filters,
        fields=_emp_fields(),
        order_by="employee_name asc",
        limit_page_length=0,
    )

    outstanding = _outstanding_map([e.name for e in employees]) if employees else {}
    for e in employees:
        e["monthly_salary"] = flt(e.get("custom_monthly_salary"))
        e["outstanding_advance"] = outstanding.get(e.name, 0)
    return employees


@frappe.whitelist()
def get_staff(employee):
    """Return a single employee's details for the member view."""
    validate_pos_access()
    if not frappe.db.exists("Employee", employee):
        frappe.throw(_("Employee {0} not found").format(employee), frappe.DoesNotExistError)

    row = frappe.db.get_value("Employee", employee, _emp_fields(), as_dict=True)
    row["monthly_salary"] = flt(row.get("custom_monthly_salary"))
    row["outstanding_advance"] = _outstanding_map([employee]).get(employee, 0)
    return row


@frappe.whitelist()
def create_staff(
    employee_name,
    monthly_salary=0,
    mobile=None,
    designation=None,
    date_of_joining=None,
    company=None,
    gender=None,
    date_of_birth=None,
):
    """Create a minimal Employee. Only name + salary are really required.

    Missing core fields are defaulted (company, joining date, status); date_of_birth /
    gender are optional because the relax_employee_mandatory_fields patch drops their
    mandatory flag.
    """
    validate_pos_access()

    employee_name = (employee_name or "").strip()
    if not employee_name:
        frappe.throw(_("Employee name is required"))

    doc = frappe.new_doc("Employee")
    doc.first_name = employee_name
    doc.company = company or _default_company()
    doc.date_of_joining = date_of_joining or nowdate()
    doc.status = "Active"
    if gender:
        doc.gender = gender
    if date_of_birth:
        doc.date_of_birth = date_of_birth
    if mobile:
        doc.cell_number = mobile
    designation = _ensure_designation(designation)
    if designation:
        doc.designation = designation
    if _has_salary_field():
        doc.custom_monthly_salary = flt(monthly_salary)

    # Employee autoname is "naming_series:" — make sure a series is set.
    ns_field = doc.meta.get_field("naming_series")
    if ns_field and not doc.get("naming_series"):
        doc.naming_series = (
            ns_field.default
            or (ns_field.options or "").split("\n")[0]
            or "HR-EMP-.#####"
        )

    doc.insert()
    return get_staff(doc.name)


@frappe.whitelist()
def update_staff(employee, employee_name=None, monthly_salary=None, mobile=None, designation=None, status=None):
    """Update a subset of employee fields the Staff UI can edit."""
    validate_pos_access()
    if not frappe.db.exists("Employee", employee):
        frappe.throw(_("Employee {0} not found").format(employee), frappe.DoesNotExistError)

    doc = frappe.get_doc("Employee", employee)
    if employee_name is not None and employee_name.strip():
        doc.first_name = employee_name.strip()
        # Clear split-name parts so employee_name recomputes cleanly.
        doc.middle_name = None
        doc.last_name = None
    if mobile is not None:
        doc.cell_number = mobile
    if designation is not None:
        doc.designation = _ensure_designation(designation)
    if status is not None:
        doc.status = status
    if monthly_salary is not None and _has_salary_field():
        doc.custom_monthly_salary = flt(monthly_salary)

    doc.save()
    return get_staff(employee)


@frappe.whitelist()
def set_status(employee, status):
    """Activate / deactivate an employee."""
    validate_pos_access()
    if status not in ("Active", "Inactive", "Left", "Suspended"):
        frappe.throw(_("Invalid status {0}").format(status))
    if not frappe.db.exists("Employee", employee):
        frappe.throw(_("Employee {0} not found").format(employee), frappe.DoesNotExistError)
    doc = frappe.get_doc("Employee", employee)
    doc.status = status
    doc.save()
    return get_staff(employee)
