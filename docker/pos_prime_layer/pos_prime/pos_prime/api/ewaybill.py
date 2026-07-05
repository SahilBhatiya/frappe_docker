# Copyright (c) 2026, Ravindu Gajanayaka
# Licensed under GPLv3. See license.txt

"""E-Way Bill generation for POS Prime.

A POS Invoice is NOT an e-Way-Bill-eligible document in india_compliance
(PERMITTED_DOCTYPES = Sales Invoice, Delivery Note, ...). So a qualifying
high-value B2B sale is booked here as a regular **Sales Invoice** (is_pos=0) —
the correct tax-invoice / goods-movement document — carrying transporter
details, and the e-Way Bill is generated on it via india_compliance's API.

These sales are intentionally kept out of the POS cash-drawer closing (they are
wholesale / credit sales, not counter cash). Normal counter sales continue to
use the POS Invoice flow in pos_prime.api.invoices.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt

from pos_prime.api._utils import (
    build_item_dict,
    set_invoice_optional_fields,
    format_invoice_response,
    validate_pos_access,
    safe_float,
)
from pos_prime.api._gst import apply_gst, is_gst_enabled

# Transporter detail keys accepted from the frontend and passed to
# india_compliance's generate_e_waybill `values`.
_TRANSPORTER_FIELDS = (
    "transporter",
    "gst_transporter_id",
    "vehicle_no",
    "mode_of_transport",
    "gst_vehicle_type",
    "distance",
    "lr_no",
    "lr_date",
)


def _ewaybill_threshold():
    return flt(frappe.db.get_single_value("GST Settings", "e_waybill_threshold")) or 50000.0


@frappe.whitelist()
def is_ewaybill_applicable(customer=None, amount=0, company=None):
    """Whether the e-Way Bill option should be offered for this sale.

    True when GST + e-Way Bill are enabled, the customer is GST-registered
    (B2B), and the sale value meets the threshold. Cheap, frontend-facing.
    """
    validate_pos_access()
    company = company or frappe.defaults.get_user_default("company")

    if not company or not is_gst_enabled(company):
        return {"applicable": False, "reason": "gst_disabled"}

    if not frappe.db.get_single_value("GST Settings", "enable_e_waybill"):
        return {"applicable": False, "reason": "ewaybill_disabled"}

    threshold = _ewaybill_threshold()
    gstin = frappe.db.get_value("Customer", customer, "gstin") if customer else None

    return {
        "applicable": bool(gstin) and flt(amount) >= threshold,
        "threshold": threshold,
        "customer_gstin": gstin,
        "has_credentials": bool(
            frappe.db.exists("GST Credential", {"service": "e-Waybill"})
        ),
    }


def _build_transporter_values(transporter_details):
    if isinstance(transporter_details, str):
        transporter_details = json.loads(transporter_details or "{}")
    transporter_details = transporter_details or {}
    values = {}
    for key in _TRANSPORTER_FIELDS:
        val = transporter_details.get(key)
        if val not in (None, ""):
            values[key] = val
    if "distance" in values:
        values["distance"] = safe_float(values["distance"])
    return values


@frappe.whitelist()
def create_invoice_with_ewaybill(
    customer,
    pos_profile,
    items,
    transporter_details=None,
    customer_address=None,
    shipping_address_name=None,
    contact_person=None,
    additional_discount_percentage=0,
    discount_amount=0,
    apply_discount_on="Grand Total",
    update_stock=None,
    remarks=None,
    po_no=None,
    po_date=None,
):
    """Book a B2B Sales Invoice for the cart and generate its e-Way Bill.

    The Sales Invoice is submitted first; e-Way Bill generation is then attempted
    and any failure (e.g. missing API credentials, invalid HSN) is returned as
    `ewaybill_error` WITHOUT rolling back the invoice, so the cashier can retry
    via generate_ewaybill_for_existing.
    """
    validate_pos_access(pos_profile)

    if isinstance(items, str):
        items = json.loads(items)
    if not items:
        frappe.throw(_("Items cannot be empty"))

    profile = frappe.get_doc("POS Profile", pos_profile)

    invoice = frappe.get_doc(
        {
            "doctype": "Sales Invoice",
            "customer": customer,
            "company": profile.company,
            "is_pos": 0,
            "selling_price_list": profile.selling_price_list or "Standard Selling",
            "currency": profile.currency
            or frappe.defaults.get_defaults().get("currency", "INR"),
            "set_warehouse": profile.warehouse,
            "update_stock": int(update_stock) if update_stock is not None
            else getattr(profile, "update_stock", 0),
            "apply_discount_on": apply_discount_on or "Grand Total",
            "ignore_pricing_rule": 1 if profile.ignore_pricing_rule else 0,
        }
    )

    if profile.company_address:
        invoice.company_address = profile.company_address

    for item_data in items:
        invoice.append("items", build_item_dict(item_data, profile))

    if additional_discount_percentage:
        invoice.additional_discount_percentage = safe_float(additional_discount_percentage)
    if discount_amount:
        invoice.discount_amount = safe_float(discount_amount)

    # Address / contact — required for e-Way Bill (ship-from / ship-to pincodes)
    set_invoice_optional_fields(
        invoice,
        profile,
        customer_address=customer_address,
        shipping_address_name=shipping_address_name or customer_address,
        contact_person=contact_person,
        remarks=remarks,
        po_no=po_no,
        po_date=po_date,
    )

    # Transporter details onto the invoice so the e-Way Bill data builder sees them
    tvalues = _build_transporter_values(transporter_details)
    for key, val in tvalues.items():
        if invoice.meta.has_field(key):
            invoice.set(key, val)

    # GST: same engine as the POS path (CGST/SGST/IGST + place of supply)
    apply_gst(invoice, profile, customer_address)

    invoice.flags.ignore_permissions = True
    invoice.insert()
    invoice.submit()

    # Commit the sale BEFORE attempting e-Way Bill generation. _try_generate
    # rolls back on failure (to undo partial e-Way Bill Log writes); without an
    # intervening commit that rollback would also void this submitted invoice.
    frappe.db.commit()

    response = format_invoice_response(invoice)
    response["sales_invoice"] = invoice.name

    # Generate the e-Way Bill (kept separate so a failure doesn't void the sale)
    ewb = _try_generate(invoice.doctype, invoice.name, tvalues)
    response.update(ewb)
    return response


@frappe.whitelist()
def generate_ewaybill_for_existing(doctype, docname, transporter_details=None):
    """Generate (or retry) an e-Way Bill for an already-submitted document."""
    validate_pos_access()
    if doctype not in ("Sales Invoice", "Delivery Note"):
        frappe.throw(_("e-Way Bill is not supported for {0}").format(doctype))
    if not frappe.db.exists(doctype, docname):
        frappe.throw(_("{0} {1} does not exist").format(doctype, docname))

    tvalues = _build_transporter_values(transporter_details)
    return _try_generate(doctype, docname, tvalues)


def _try_generate(doctype, docname, tvalues):
    """Call india_compliance's e-Way Bill API, returning a result/error dict."""
    try:
        from india_compliance.gst_india.utils.e_waybill import generate_e_waybill

        # Passing values makes india_compliance raise on failure (throw=True),
        # which we catch and surface rather than silently logging.
        generate_e_waybill(doctype=doctype, docname=docname, values=tvalues or None)
    except Exception as e:
        frappe.db.rollback()  # undo any partial e-Way log writes; keep the invoice
        return {
            "ewaybill": None,
            "ewaybill_error": str(e) or _("e-Way Bill generation failed"),
        }

    ewaybill = frappe.db.get_value(doctype, docname, "ewaybill")
    return {
        "ewaybill": ewaybill,
        "ewaybill_pdf_url": _get_ewaybill_pdf_url(doctype, docname),
        "ewaybill_error": None,
    }


def _get_ewaybill_pdf_url(doctype, docname):
    """URL of the e-Way Bill PDF india_compliance attaches to the document."""
    files = frappe.get_all(
        "File",
        filters={
            "attached_to_doctype": doctype,
            "attached_to_name": docname,
            "file_name": ["like", "%e-Waybill%"],
        },
        fields=["file_url"],
        order_by="creation desc",
        limit=1,
    )
    return files[0].file_url if files else None


@frappe.whitelist()
def get_ewaybill_options():
    """Dropdown options for the e-Way Bill dialog: transport modes, vehicle
    types, and saved transporters."""
    validate_pos_access()

    meta = frappe.get_meta("Sales Invoice")

    def _opts(fieldname):
        f = meta.get_field(fieldname)
        return [o for o in (f.options or "").split("\n") if o.strip()] if f else []

    transporters = frappe.get_all(
        "Supplier",
        filters={"is_transporter": 1, "disabled": 0},
        fields=["name", "supplier_name", "gst_transporter_id"],
        order_by="supplier_name asc",
        limit_page_length=50,
    )

    return {
        "modes_of_transport": _opts("mode_of_transport") or ["Road", "Air", "Rail", "Ship"],
        "gst_vehicle_types": _opts("gst_vehicle_type") or ["Regular", "Over Dimensional Cargo"],
        "transporters": transporters,
        "threshold": _ewaybill_threshold(),
    }
