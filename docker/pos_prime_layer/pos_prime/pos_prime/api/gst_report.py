# Copyright (c) 2026, Ravindu Gajanayaka
# Licensed under GPLv3. See license.txt

"""GST liability reporting for POS Prime ("the GST to be given").

Aggregates the OUTPUT GST collected on sales (Sales Invoice + POS Invoice) over
a period so the shop owner can see how much GST they owe — without opening the
ERPNext Desk GSTR reports.

Source of truth: india_compliance's per-item GST detail columns
(`cgst_amount` / `sgst_amount` / `igst_amount` / `cgst_rate` ...) on the invoice
item tables. These are the same figures india_compliance rolls up into GSTR-1 /
GSTR-3B, and they net correctly across credit notes (return invoices carry
negative amounts).

NOTE (follow-up): this reports OUTPUT GST collected. Net cash payable
(GSTR-3B style) = output GST  -  input tax credit on purchases. The input-credit
side (Purchase Invoice input GST accounts) is intentionally NOT implemented yet.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from pos_prime.api._utils import validate_pos_access

# Sales documents whose output GST counts toward liability.
_SALES_DOCTYPES = ("Sales Invoice", "POS Invoice")


def _resolve_company(company):
    if company:
        return company
    return frappe.defaults.get_user_default("company") or frappe.db.get_single_value(
        "Global Defaults", "default_company"
    )


@frappe.whitelist()
def get_gst_summary(company=None, from_date=None, to_date=None):
    """Output GST collected over a period, with a per-rate breakdown.

    Returns totals (taxable / cgst / sgst / igst / total_gst / invoice_count) and
    a `by_rate` list, aggregated across Sales Invoice + POS Invoice and netted for
    returns.
    """
    validate_pos_access()
    company = _resolve_company(company)
    if not company:
        frappe.throw(_("Company is required"))
    if not from_date or not to_date:
        frappe.throw(_("From and To dates are required"))

    from_date, to_date = getdate(from_date), getdate(to_date)

    totals = {
        "taxable_amount": 0.0,
        "cgst": 0.0,
        "sgst": 0.0,
        "igst": 0.0,
        "total_gst": 0.0,
        "invoice_count": 0,
    }
    # rate (effective GST %) -> aggregated bucket
    rate_buckets = {}

    for doctype in _SALES_DOCTYPES:
        item_table = f"tab{doctype} Item"
        rows = frappe.db.sql(
            f"""
            SELECT
                ROUND(it.cgst_rate + it.sgst_rate + it.igst_rate, 2) AS gst_rate,
                SUM(it.base_net_amount) AS taxable,
                SUM(it.cgst_amount)     AS cgst,
                SUM(it.sgst_amount)     AS sgst,
                SUM(it.igst_amount)     AS igst
            FROM `{item_table}` it
            INNER JOIN `tab{doctype}` inv ON inv.name = it.parent
            WHERE inv.docstatus = 1
              AND inv.company = %(company)s
              AND inv.posting_date BETWEEN %(from_date)s AND %(to_date)s
            GROUP BY gst_rate
            """,
            {"company": company, "from_date": from_date, "to_date": to_date},
            as_dict=True,
        )

        for r in rows:
            cgst, sgst, igst = flt(r.cgst), flt(r.sgst), flt(r.igst)
            taxable = flt(r.taxable)
            totals["taxable_amount"] += taxable
            totals["cgst"] += cgst
            totals["sgst"] += sgst
            totals["igst"] += igst

            rate = flt(r.gst_rate)
            b = rate_buckets.setdefault(
                rate, {"gst_rate": rate, "taxable_amount": 0.0, "cgst": 0.0, "sgst": 0.0, "igst": 0.0}
            )
            b["taxable_amount"] += taxable
            b["cgst"] += cgst
            b["sgst"] += sgst
            b["igst"] += igst

        # Distinct invoices that actually carried GST in the period
        totals["invoice_count"] += (
            frappe.db.sql(
                f"""
                SELECT COUNT(DISTINCT inv.name)
                FROM `tab{doctype}` inv
                INNER JOIN `{item_table}` it ON it.parent = inv.name
                WHERE inv.docstatus = 1
                  AND inv.company = %(company)s
                  AND inv.posting_date BETWEEN %(from_date)s AND %(to_date)s
                  AND (it.cgst_amount <> 0 OR it.sgst_amount <> 0 OR it.igst_amount <> 0)
                """,
                {"company": company, "from_date": from_date, "to_date": to_date},
            )[0][0]
            or 0
        )

    totals["total_gst"] = totals["cgst"] + totals["sgst"] + totals["igst"]
    for key in totals:
        if key != "invoice_count":
            totals[key] = flt(totals[key], 2)

    by_rate = []
    for b in sorted(rate_buckets.values(), key=lambda x: x["gst_rate"]):
        b["total_gst"] = flt(b["cgst"] + b["sgst"] + b["igst"], 2)
        for key in ("taxable_amount", "cgst", "sgst", "igst"):
            b[key] = flt(b[key], 2)
        # Skip empty/no-GST buckets unless they carry a rate
        if b["total_gst"] or b["gst_rate"]:
            by_rate.append(b)

    return {
        "company": company,
        "from_date": str(from_date),
        "to_date": str(to_date),
        **totals,
        "by_rate": by_rate,
    }


@frappe.whitelist()
def get_gst_invoices(company=None, from_date=None, to_date=None, limit=50, offset=0):
    """Paginated list of GST-bearing invoices for drill-down / CSV export."""
    validate_pos_access()
    company = _resolve_company(company)
    if not company:
        frappe.throw(_("Company is required"))
    if not from_date or not to_date:
        frappe.throw(_("From and To dates are required"))

    from_date, to_date = getdate(from_date), getdate(to_date)
    limit, offset = int(limit), int(offset)

    results = []
    for doctype in _SALES_DOCTYPES:
        item_table = f"tab{doctype} Item"
        rows = frappe.db.sql(
            f"""
            SELECT
                inv.name, inv.posting_date, inv.customer, inv.customer_name,
                inv.is_return, inv.place_of_supply, inv.billing_address_gstin AS gstin,
                ROUND(SUM(it.base_net_amount), 2) AS taxable,
                ROUND(SUM(it.cgst_amount), 2) AS cgst,
                ROUND(SUM(it.sgst_amount), 2) AS sgst,
                ROUND(SUM(it.igst_amount), 2) AS igst
            FROM `{item_table}` it
            INNER JOIN `tab{doctype}` inv ON inv.name = it.parent
            WHERE inv.docstatus = 1
              AND inv.company = %(company)s
              AND inv.posting_date BETWEEN %(from_date)s AND %(to_date)s
            GROUP BY inv.name
            HAVING (cgst <> 0 OR sgst <> 0 OR igst <> 0)
            """,
            {"company": company, "from_date": from_date, "to_date": to_date},
            as_dict=True,
        )
        for r in rows:
            r["doctype"] = doctype
            r["total_gst"] = flt(flt(r.cgst) + flt(r.sgst) + flt(r.igst), 2)
            r["posting_date"] = str(r.posting_date)
            results.append(r)

    # Newest first, then paginate the combined set
    results.sort(key=lambda x: x["posting_date"], reverse=True)
    total = len(results)
    page = results[offset : offset + limit]

    return {"invoices": page, "total": total, "has_more": offset + limit < total}
