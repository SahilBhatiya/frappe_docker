import frappe
from frappe.utils import flt

# ---------------------------------------------------------------------------
# HSN prefix -> GST rate (%) override. Matched longest-prefix-first against each
# Item's gst_hsn_code. Adarsh Motor Stores' active catalogue is uniformly 18%
# GST (the older 28% tyre records were discontinued / disabled), so the map is
# empty and every item falls to DEFAULT_RATE. Add prefixes here if a future
# catalogue needs differentiated rates.
# ---------------------------------------------------------------------------
HSN_RATE_MAP = {}
DEFAULT_RATE = 18            # Every item (incl. "0000" placeholders)
GST_RATES = (5, 12, 18, 28)  # Item Tax Templates to create (standard GST slabs)


def rate_for_hsn(hsn):
    if not hsn:
        return DEFAULT_RATE
    hsn = str(hsn).strip()
    for prefix in sorted(HSN_RATE_MAP, key=len, reverse=True):
        if hsn.startswith(prefix):
            return HSN_RATE_MAP[prefix]
    return DEFAULT_RATE


def execute():
    """Create GST Item Tax Templates and assign one to every Item by HSN code.

    Idempotent and non-destructive:
      - Item Tax Templates are created only when missing.
      - An Item gets a tax row only if it has none yet (never overwrites manual
        rates). Rows are inserted directly into `tabItem Tax` to bypass Item
        validation (some items carry placeholder HSNs like "0000" that the
        india_compliance Item validator would reject on a full save).

    No-op on non-India sites or before india_compliance GST accounts exist.
    """
    if "india_compliance" not in frappe.get_installed_apps():
        return
    if not frappe.db.exists("DocType", "Item Tax Template"):
        return

    companies = frappe.get_all(
        "Company", filters={"country": "India"}, pluck="name"
    )
    if not companies:
        return

    for company in companies:
        gstin = frappe.db.get_value("Company", company, "gstin")
        if not gstin:
            continue

        templates = _ensure_item_tax_templates(company)
        if not templates:
            continue

        _assign_templates_to_items(company, templates)


def _ensure_item_tax_templates(company):
    """Return {rate: template_name}, creating any missing GST templates."""
    from india_compliance.gst_india.utils import get_gst_accounts_by_type

    accounts = get_gst_accounts_by_type(company, "Output", throw=False)
    if not accounts or not accounts.get("cgst_account"):
        # GST accounts not configured for this company — skip.
        return {}

    cgst = accounts.get("cgst_account")
    sgst = accounts.get("sgst_account")
    igst = accounts.get("igst_account")

    abbr = frappe.get_cached_value("Company", company, "abbr")
    templates = {}

    for rate in GST_RATES:
        title = f"GST {rate}%"
        name = f"{title} - {abbr}"
        if frappe.db.exists("Item Tax Template", name):
            templates[rate] = name
            continue

        doc = frappe.new_doc("Item Tax Template")
        doc.title = title
        doc.company = company
        if doc.meta.has_field("gst_treatment"):
            doc.gst_treatment = "Taxable"
        if doc.meta.has_field("gst_rate"):
            doc.gst_rate = rate

        # Output accounts: CGST + SGST at half rate (intra-state), IGST at full
        # rate (inter-state). ERPNext picks the matching pair at transaction
        # time based on the Sales Taxes template applied.
        for tax_type, tax_rate in (
            (cgst, flt(rate) / 2),
            (sgst, flt(rate) / 2),
            (igst, flt(rate)),
        ):
            if tax_type:
                doc.append("taxes", {"tax_type": tax_type, "tax_rate": tax_rate})

        doc.insert(ignore_permissions=True)
        templates[rate] = doc.name

    return templates


def _assign_templates_to_items(company, templates):
    """Assign each Item without a tax row the template matching its HSN."""
    # Items that already have at least one tax row — leave them alone.
    items_with_tax = set(
        frappe.get_all(
            "Item Tax", filters={"parenttype": "Item"}, pluck="parent"
        )
    )

    items = frappe.get_all(
        "Item",
        fields=["name", "gst_hsn_code"],
        filters={"disabled": 0},
    )

    inserted = 0
    for item in items:
        if item.name in items_with_tax:
            continue

        rate = rate_for_hsn(item.gst_hsn_code)
        template = templates.get(rate) or templates.get(DEFAULT_RATE)
        if not template:
            continue

        _insert_item_tax_row(item.name, template)
        inserted += 1
        if inserted % 200 == 0:
            frappe.db.commit()

    frappe.db.commit()
    frappe.clear_cache(doctype="Item")
    frappe.logger().info(
        f"POS Prime GST: assigned Item Tax Templates to {inserted} items "
        f"for {company}"
    )


def _insert_item_tax_row(item_name, template):
    row_name = frappe.generate_hash(length=10)
    frappe.db.sql(
        """
        INSERT INTO `tabItem Tax`
            (name, creation, modified, modified_by, owner, docstatus, idx,
             parent, parentfield, parenttype, item_tax_template)
        VALUES
            (%(name)s, NOW(), NOW(), %(user)s, %(user)s, 0, 1,
             %(parent)s, 'taxes', 'Item', %(template)s)
        """,
        {
            "name": row_name,
            "user": frappe.session.user or "Administrator",
            "parent": item_name,
            "template": template,
        },
    )
