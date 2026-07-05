import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    """Add a simple fixed monthly salary field on Employee (owned by pos_prime).

    The Staff Payroll module reads this as the base salary when generating a payslip.
    Idempotent — create_custom_fields skips existing fields.
    """
    if not frappe.db.exists("DocType", "Employee"):
        return

    create_custom_fields(
        {
            "Employee": [
                {
                    "fieldname": "custom_monthly_salary",
                    "label": "Monthly Salary",
                    "fieldtype": "Currency",
                    "insert_after": "salary_currency"
                    if frappe.get_meta("Employee").has_field("salary_currency")
                    else "employment_details",
                    "description": "Fixed monthly salary used by POS Prime Staff Payroll.",
                }
            ]
        },
        ignore_validate=True,
    )
