"""
Run inside bench: bench --site erpnext.localhost execute link_item_tax.execute
Links Item Tax Templates to all items based on GST rate.
Priority: HSN code → rate in item name → 18% default.
Also fixes duplicate UOM entries that block item saves.
"""
import re
import frappe

GST_PATTERN = re.compile(r'\b(28|18|12|5)\s*%|\((\d+)%\)', re.IGNORECASE)
NIL_PATTERN  = re.compile(r'\bnil\b|\bexempt\b', re.IGNORECASE)
ABBR = "AMS"

# Rates from CBIC official schedule & IndiaFilings Ch.40/87 tables (2026).
# Longer prefixes (6-digit) override shorter (4-digit) matches.
HSN_GST_MAP = {
    # Chapter 40 – Rubber
    "4001": 5,  "4002": 18, "4003": 18, "4004": 5,
    "4005": 18, "4006": 18, "4007": 18, "4008": 18,
    "4009": 18, "4010": 18,
    "4011": 18,           # All pneumatic tyres – 18% (current CBIC schedule)
    "4012": 18,           # Retreaded tyres
    "4013": 18,           # Inner tubes
    "4014": 12,           # Hygienic/pharmaceutical rubber
    "4015": 18, "401511": 12,   # Rubber gloves; surgical gloves 12%
    "4016": 18, "4017": 18,
    # Chapter 85 – Electrical
    "8507": 28, "850760": 18,   # Batteries; lithium-ion 18%
    "8511": 18, "8512": 18, "8536": 18,
    # Chapter 87 – Vehicles & parts
    "8701": 12,
    "8708": 28, "870810": 18,   # Motor vehicle parts 28%; tractor bumpers 18%
    "8711": 28, "8712": 12,
    "8714": 28, "871420": 18,   # Motorcycle parts 28%; baby carriage parts 18%
    "8715": 18, "8716": 18,
    # Lubricants / tools / misc
    "2710": 18, "3403": 18, "3819": 18,
    "8205": 18, "8207": 18,
    "3401": 18, "3926": 18, "7320": 18,
}

def _rate_from_hsn(hsn):
    h = re.sub(r'\s', '', str(hsn or ""))
    for length in (8, 6, 4):
        prefix = h[:length]
        if prefix and prefix in HSN_GST_MAP:
            return HSN_GST_MAP[prefix]
    return None

def infer_template(name, hsn=""):
    rate = _rate_from_hsn(hsn)
    if rate is None:
        m = GST_PATTERN.search(name)
        if m:
            r = int(m.group(1) or m.group(2))
            if r in (5, 12, 18, 28):
                rate = r
    if rate is None:
        if NIL_PATTERN.search(name):
            return f"Nil-Rated - {ABBR}"
        rate = 18   # default for unclassified items
    return f"GST {rate}% - {ABBR}"


def execute():
    items = frappe.get_all("Item", fields=["name", "gst_hsn_code"], limit_page_length=0)
    linked = skipped = no_rate = errors = 0

    for item in items:
        code = item["name"]
        tmpl = infer_template(code, hsn=item.get("gst_hsn_code") or "")

        # Skip if already has a tax template
        existing = frappe.db.get_all("Item Tax", filters={"parent": code}, fields=["name"])
        if existing:
            skipped += 1
            continue

        if tmpl is None:   # shouldn't happen now, but keep as safety net
            no_rate += 1
            continue

        try:
            # Remove duplicate UOM rows that block saves
            uoms = frappe.db.sql(
                "SELECT name, uom FROM `tabItem UOM` WHERE parent=%s ORDER BY idx",
                code, as_dict=True
            )
            seen_uoms = set()
            for row in uoms:
                if row.uom in seen_uoms:
                    frappe.db.sql("DELETE FROM `tabItem UOM` WHERE name=%s", row.name)
                else:
                    seen_uoms.add(row.uom)

            # Insert Item Tax row directly (avoids full-doc validation)
            frappe.db.sql(
                """INSERT INTO `tabItem Tax`
                   (name, parent, parenttype, parentfield, item_tax_template, idx,
                    creation, modified, owner, modified_by)
                   VALUES (%s, %s, 'Item', 'taxes', %s, 1, NOW(), NOW(), 'Administrator', 'Administrator')""",
                (frappe.generate_hash("", 10), code, tmpl)
            )
            frappe.db.commit()
            linked += 1

        except Exception as e:
            errors += 1
            if errors <= 10:
                frappe.logger().warning(f"link_item_tax ERR {code}: {e}")

    print(f"Linked: {linked}, Already set: {skipped}, No rate marker (skipped): {no_rate}, Errors: {errors}")
