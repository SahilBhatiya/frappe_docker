import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


def execute():
    """Make Employee.date_of_birth and Employee.gender optional.

    Lets the simple "Add Employee" flow in POS Prime Staff create an employee from just
    a name + salary (+ optional mobile/designation). Reversible — delete the Property
    Setters to restore the core mandatory behaviour.
    """
    if not frappe.db.exists("DocType", "Employee"):
        return

    meta = frappe.get_meta("Employee")
    for fieldname in ("date_of_birth", "gender"):
        if meta.has_field(fieldname):
            make_property_setter(
                "Employee",
                fieldname,
                "reqd",
                "0",
                "Check",
                validate_fields_for_doctype=False,
            )
