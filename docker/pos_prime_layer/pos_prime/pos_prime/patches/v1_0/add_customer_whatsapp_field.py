import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    """Add a dedicated WhatsApp number field on Customer (separate from mobile_no).

    Used by the POS Prime customer panel to show/edit a WhatsApp contact and
    build a wa.me link. Idempotent — create_custom_fields skips existing fields.
    """
    if not frappe.db.exists("DocType", "Customer"):
        return

    create_custom_fields(
        {
            "Customer": [
                {
                    "fieldname": "custom_whatsapp",
                    "label": "WhatsApp",
                    "fieldtype": "Data",
                    "options": "Phone",
                    "insert_after": "mobile_no",
                }
            ]
        },
        ignore_validate=True,
    )
