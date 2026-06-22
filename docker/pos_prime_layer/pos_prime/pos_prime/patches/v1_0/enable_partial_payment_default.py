import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


def execute():
    """Allow partial / pay-later payments across all POS surfaces.

    POS Prime and ERPNext's standard POS both gate partial payment on the POS
    Profile's `allow_partial_payment` flag. This makes that the default for new
    profiles and turns it on for every existing one. Idempotent.
    """
    if not frappe.db.exists("DocType", "POS Profile"):
        return

    # New POS Profiles default to allowing partial payment.
    make_property_setter(
        "POS Profile",
        "allow_partial_payment",
        "default",
        "1",
        "Check",
        validate_fields_for_doctype=False,
    )

    # Enable on every existing profile that doesn't already have it.
    for name in frappe.get_all("POS Profile", pluck="name"):
        if not frappe.db.get_value("POS Profile", name, "allow_partial_payment"):
            frappe.db.set_value("POS Profile", name, "allow_partial_payment", 1)
