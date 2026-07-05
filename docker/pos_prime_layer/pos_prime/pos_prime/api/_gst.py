# Copyright (c) 2026, Ravindu Gajanayaka
# Licensed under GPLv3. See license.txt

"""GST (India) support for POS Prime.

POS Prime delegates ALL tax math to ERPNext / india_compliance — it never
computes GST itself. This module bridges the gap that the stock POS Profile
leaves open: it determines the correct GST tax template, place of supply, and
GSTINs for an in-memory invoice (using india_compliance's own
``get_gst_details``) and applies them before the tax engine runs.

Everything degrades gracefully on non-India sites (no india_compliance app, or
a company without a GSTIN) so the same code path works everywhere.
"""

import frappe


def is_gst_enabled(company):
    """True when india_compliance is installed and the company has a GSTIN."""
    if "india_compliance" not in frappe.get_installed_apps():
        return False
    return bool(frappe.db.get_value("Company", company, "gstin"))


def apply_gst(invoice, profile, customer_address=None):
    """Set GST template, place of supply, GSTINs and category on an invoice.

    Mirrors what india_compliance's desk client script does when a customer is
    selected: calls ``get_gst_details`` to resolve the correct
    ``taxes_and_charges`` template (CGST+SGST for intra-state, IGST for
    inter-state) plus ``place_of_supply``, then writes the GST fields and tax
    rows onto the (unsaved) invoice doc.

    Safe to call on any POS Invoice doc before ``set_missing_values()``. Returns
    True when GST was applied, False when it is not applicable (so callers can
    fall back to their static taxes_and_charges behaviour).
    """
    if not is_gst_enabled(invoice.company):
        return False

    company_gstin = frappe.db.get_value("Company", invoice.company, "gstin")

    party_details = frappe._dict(
        {
            "customer": invoice.customer,
            "company": invoice.company,
            "company_gstin": company_gstin,
            "customer_address": customer_address or invoice.get("customer_address"),
            "gst_category": invoice.get("gst_category"),
            "billing_address_gstin": invoice.get("billing_address_gstin"),
            "place_of_supply": invoice.get("place_of_supply"),
        }
    )

    try:
        from india_compliance.gst_india.overrides.transaction import get_gst_details

        gst_details = get_gst_details(
            party_details,
            invoice.doctype,
            invoice.company,
            update_place_of_supply=True,
        )
    except Exception:
        # Never let GST resolution break a sale — log and let the caller fall
        # back to its static taxes_and_charges path.
        frappe.log_error(frappe.get_traceback(), "POS Prime: apply_gst failed")
        return False

    if not gst_details:
        return False

    meta = invoice.meta

    # Header GST fields (all verified present on POS Invoice via india_compliance
    # custom fields, but guard anyway for forward/backward compatibility).
    def _set(fieldname, value):
        if value is not None and meta.has_field(fieldname):
            invoice.set(fieldname, value)

    if meta.has_field("company_gstin"):
        invoice.company_gstin = company_gstin
    _set("gst_category", gst_details.get("gst_category"))
    _set("place_of_supply", gst_details.get("place_of_supply"))
    _set("billing_address_gstin", gst_details.get("billing_address_gstin"))

    # Tax template + rows. An empty template (e.g. internal transfer / export
    # without GST) is a valid "no GST" answer — clear taxes in that case.
    taxes_and_charges = gst_details.get("taxes_and_charges")
    taxes = gst_details.get("taxes")

    if "taxes_and_charges" not in gst_details:
        # get_gst_details returned only place-of-supply data (no template
        # decision) — leave existing taxes untouched.
        return True

    invoice.taxes_and_charges = taxes_and_charges or ""
    invoice.set("taxes", [])

    inclusive = _is_gst_inclusive(profile)
    for tax in taxes or []:
        row = invoice.append("taxes", dict(tax))
        if inclusive:
            row.included_in_print_rate = 1

    return True


def _is_gst_inclusive(profile):
    """Whether item prices are GST-inclusive (MRP). Defaults to True.

    Controlled by the POS Profile ``custom_gst_inclusive`` check field. When the
    field is missing (older installs) default to inclusive, matching the
    retail-MRP behaviour this deployment uses.
    """
    if profile is None:
        return True
    value = profile.get("custom_gst_inclusive")
    if value is None:
        return True
    return bool(value)
