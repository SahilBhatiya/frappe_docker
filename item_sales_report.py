"""
Install "Item Sales & Stock" Script Report in ERPNext.

Shows per item: current stock, qty sold in a date range, average daily sales,
days of stock remaining, and reorder status (To Order / Low Stock / OK).

Summary row shows total items to order (red), low stock (orange), and in-stock (green).
Bar chart shows top 15 items by qty sold.

Usage: python item_sales_report.py
"""

import requests

ERPNEXT_URL = "http://localhost:8080"
API_KEY     = "12d80506c40944c"
API_SECRET  = "903ef51e33f8869"

HEADERS = {
    "Authorization": f"token {API_KEY}:{API_SECRET}",
    "Content-Type":  "application/json",
}

REPORT_NAME = "Item Sales & Stock"

# ── Python script stored in ERPNext (runs server-side when report is opened) ──
# Uses r''' so the inner f"""SQL""" triple-quotes are stored verbatim.
REPORT_SCRIPT = r'''
import frappe
from frappe.utils import date_diff, nowdate


def execute(filters=None):
    filters = frappe._dict(filters or {})
    if not filters.from_date:
        filters.from_date = frappe.utils.get_first_day(nowdate())
    if not filters.to_date:
        filters.to_date = nowdate()

    columns = get_columns()
    data    = get_data(filters)
    summary = get_summary(data)
    chart   = get_chart(data)
    return columns, data, None, chart, summary


def get_columns():
    return [
        {"fieldname": "item_code",      "label": "Item Code",     "fieldtype": "Link",  "options": "Item",       "width": 140},
        {"fieldname": "item_name",      "label": "Item Name",     "fieldtype": "Data",                           "width": 200},
        {"fieldname": "item_group",     "label": "Group",         "fieldtype": "Link",  "options": "Item Group", "width": 120},
        {"fieldname": "current_stock",  "label": "Stock (Qty)",   "fieldtype": "Float",                          "width": 100},
        {"fieldname": "reorder_level",  "label": "Reorder Level", "fieldtype": "Float",                          "width": 110},
        {"fieldname": "qty_sold",       "label": "Qty Sold",      "fieldtype": "Float",                          "width": 100},
        {"fieldname": "avg_daily_sales","label": "Avg / Day",     "fieldtype": "Float",                          "width": 100},
        {"fieldname": "days_of_stock",  "label": "Days Left",     "fieldtype": "Float",                          "width": 100},
        {"fieldname": "status",         "label": "Status",        "fieldtype": "Data",                           "width": 120},
    ]


def get_data(filters):
    days = (date_diff(filters.to_date, filters.from_date) or 0) + 1

    bin_cond  = "AND b.warehouse   = %(warehouse)s"  if filters.get("warehouse")  else ""
    ir_cond   = "AND ir.warehouse  = %(warehouse)s"  if filters.get("warehouse")  else ""
    sii_cond  = "AND sii.warehouse = %(warehouse)s"  if filters.get("warehouse")  else ""
    item_cond = "AND i.item_group  = %(item_group)s" if filters.get("item_group") else ""

    rows = frappe.db.sql(f"""
        SELECT
            i.item_code,
            i.item_name,
            i.item_group,
            COALESCE(SUM(b.actual_qty), 0)               AS current_stock,
            COALESCE(MAX(ir.warehouse_reorder_level), 0) AS reorder_level,
            COALESCE(sold.qty_sold, 0)                   AS qty_sold
        FROM `tabItem` i
        LEFT JOIN `tabBin` b
            ON  b.item_code = i.item_code {bin_cond}
        LEFT JOIN `tabItem Reorder` ir
            ON  ir.parent = i.item_code {ir_cond}
        LEFT JOIN (
            SELECT   sii.item_code, SUM(sii.qty) AS qty_sold
            FROM     `tabSales Invoice Item` sii
            JOIN     `tabSales Invoice` si ON si.name = sii.parent
            WHERE    si.docstatus    = 1
              AND    si.posting_date BETWEEN %(from_date)s AND %(to_date)s
              {sii_cond}
            GROUP BY sii.item_code
        ) sold ON sold.item_code = i.item_code
        WHERE i.disabled      = 0
          AND i.is_stock_item = 1
          {item_cond}
        GROUP BY i.item_code, i.item_name, i.item_group
    """, filters, as_dict=True)

    data = []
    for r in rows:
        avg = round(r.qty_sold / days, 3) if (days and r.qty_sold) else 0
        if avg > 0:
            days_left = round(r.current_stock / avg, 1)
        else:
            days_left = None if r.current_stock > 0 else 0

        if r.current_stock <= r.reorder_level:
            status = "To Order"
        elif days_left is not None and days_left < 14:
            status = "Low Stock"
        else:
            status = "OK"

        data.append({
            "item_code":       r.item_code,
            "item_name":       r.item_name,
            "item_group":      r.item_group,
            "current_stock":   r.current_stock,
            "reorder_level":   r.reorder_level,
            "qty_sold":        r.qty_sold,
            "avg_daily_sales": avg,
            "days_of_stock":   days_left,
            "status":          status,
        })

    priority = {"To Order": 0, "Low Stock": 1, "OK": 2}
    data.sort(key=lambda r: (priority.get(r["status"], 3), r["days_of_stock"] or 9999))
    return data


def get_summary(data):
    to_order   = sum(1 for r in data if r["status"] == "To Order")
    low_stock  = sum(1 for r in data if r["status"] == "Low Stock")
    ok         = sum(1 for r in data if r["status"] == "OK")
    total_sold = sum(r["qty_sold"] for r in data)
    return [
        {"value": to_order,   "label": "Items to Order", "datatype": "Int",   "indicator": "Red"},
        {"value": low_stock,  "label": "Low Stock",       "datatype": "Int",   "indicator": "Orange"},
        {"value": ok,         "label": "OK",              "datatype": "Int",   "indicator": "Green"},
        {"value": total_sold, "label": "Total Qty Sold",  "datatype": "Float", "indicator": "Blue"},
    ]


def get_chart(data):
    top = [r for r in sorted(data, key=lambda r: r["qty_sold"], reverse=True) if r["qty_sold"]][:15]
    if not top:
        return None
    return {
        "data": {
            "labels":   [r["item_name"] or r["item_code"] for r in top],
            "datasets": [{"name": "Qty Sold", "values": [r["qty_sold"] for r in top]}],
        },
        "type":      "bar",
        "fieldtype": "Float",
        "title":     "Top 15 Items by Qty Sold",
    }
'''

# ── JavaScript stored in ERPNext (runs in the browser for this report) ────────
REPORT_JS = r"""
frappe.query_reports["Item Sales & Stock"] = {

    filters: [
        {
            fieldname: "from_date",
            label:     __("From Date"),
            fieldtype: "Date",
            default:   frappe.datetime.month_start(),
            reqd:      1,
        },
        {
            fieldname: "to_date",
            label:     __("To Date"),
            fieldtype: "Date",
            default:   frappe.datetime.get_today(),
            reqd:      1,
        },
        {
            fieldname: "warehouse",
            label:     __("Warehouse"),
            fieldtype: "Link",
            options:   "Warehouse",
        },
        {
            fieldname: "item_group",
            label:     __("Item Group"),
            fieldtype: "Link",
            options:   "Item Group",
        },
    ],

    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (!data) return value;

        if (column.fieldname === "status") {
            const colors = { "To Order": "red", "Low Stock": "orange", "OK": "green" };
            const color  = colors[data.status] || "gray";
            return `<span class="indicator-pill ${color}">${data.status || ""}</span>`;
        }

        if (column.fieldname === "days_of_stock") {
            if (data.days_of_stock === null || data.days_of_stock === undefined) {
                return `<span style="color:var(--text-muted)">—</span>`;
            }
            if (data.days_of_stock < 7) {
                return `<span style="color:var(--red-500);font-weight:600">${data.days_of_stock}</span>`;
            }
            if (data.days_of_stock < 14) {
                return `<span style="color:var(--yellow-500)">${data.days_of_stock}</span>`;
            }
        }

        if (column.fieldname === "current_stock") {
            if (data.reorder_level > 0 && data.current_stock <= data.reorder_level) {
                return `<span style="color:var(--red-500);font-weight:600">${data.current_stock}</span>`;
            }
        }

        return value;
    },
};
"""


# ── Helpers (same pattern as gstin_setup.py) ─────────────────────────────────

def api_exists(doctype, name):
    r = requests.get(
        f"{ERPNEXT_URL}/api/resource/{doctype}/{requests.utils.quote(str(name))}",
        headers=HEADERS,
        timeout=10,
    )
    return r.status_code == 200


def api_post(doctype, data):
    r = requests.post(
        f"{ERPNEXT_URL}/api/resource/{doctype}",
        headers=HEADERS,
        json={"data": data},
        timeout=30,
    )
    if r.status_code in (200, 201):
        return r.json().get("data", {})
    if r.status_code == 409:
        return {"name": data.get("name", "")}
    print(f"  WARN [{r.status_code}] {doctype}: {r.text[:300]}")
    return None


def upsert_report():
    print(f"Installing Report: {REPORT_NAME}...")
    data = {
        "report_name": REPORT_NAME,
        "report_type": "Script Report",
        "ref_doctype": "Item",
        "is_standard": "No",
        "disabled":    0,
        "script":      REPORT_SCRIPT,
        "javascript":  REPORT_JS,
    }
    if api_exists("Report", REPORT_NAME):
        r = requests.put(
            f"{ERPNEXT_URL}/api/resource/Report/{requests.utils.quote(REPORT_NAME)}",
            headers=HEADERS,
            json={"data": data},
            timeout=30,
        )
        print("  Updated." if r.status_code in (200, 201) else f"  WARN {r.text[:300]}")
    else:
        result = api_post("Report", data)
        print(f"  Created: {result.get('name', '')}" if result else "  Failed.")


def main():
    upsert_report()
    print("\nDone.")
    print(f"Open the report at: {ERPNEXT_URL}/app/query-report/Item%20Sales%20%26%20Stock")
    print("Or search for 'Item Sales & Stock' in the ERPNext search bar.")


if __name__ == "__main__":
    main()
