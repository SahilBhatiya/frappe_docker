import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    """Add a POS Profile flag controlling GST-inclusive (MRP) pricing.

    When checked (the default), POS Prime treats item selling prices as
    GST-inclusive: the GST tax rows are marked included_in_print_rate so the
    tax is extracted from the price rather than added on top. Read by
    pos_prime.api._gst.apply_gst. Idempotent — create_custom_fields skips
    existing fields.
    """
    if not frappe.db.exists("DocType", "POS Profile"):
        return

    create_custom_fields(
        {
            "POS Profile": [
                {
                    "fieldname": "custom_gst_inclusive",
                    "label": "Prices are GST Inclusive (MRP)",
                    "fieldtype": "Check",
                    "default": "1",
                    "insert_after": "taxes_and_charges",
                    "description": (
                        "When checked, item prices already include GST and the"
                        " tax portion is shown extracted on the receipt."
                    ),
                }
            ]
        },
        ignore_validate=True,
    )
