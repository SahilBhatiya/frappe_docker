"""
Install the Stock & Sales Dashboard in ERPNext.

Creates:
  1. Script Report  — "Item Daily Sales Trend"
     Multi-line chart showing day-by-day qty sold for the top N items.
     Use this to see which items are trending on any given day.

  2. Script Report  — "Items to Reorder"
     Grouped bar chart (current stock vs reorder level) for items
     that are at or below their reorder level OR will run out within
     the threshold period. Includes a suggested order qty column.

  3. Dashboard Charts (native ERPNext)
     - "Daily Sales Revenue"   — line  chart (sum of grand_total by day)
     - "Monthly Sales Revenue" — bar   chart (sum of grand_total by month)
     - "Daily Invoice Count"   — line  chart (count of invoices by day)

  4. Number Cards (native ERPNext)
     - "Sales Today"           — sum of grand_total, today
     - "Invoices This Month"   — count of invoices, this month

  5. Dashboard — "Stock Dashboard"
     Combines all four charts and both cards in one page.

Usage: python stock_dashboard.py
"""

import requests
import json

ERPNEXT_URL = "http://localhost:8080"
API_KEY     = "12d80506c40944c"
API_SECRET  = "903ef51e33f8869"

HEADERS = {
    "Authorization": f"token {API_KEY}:{API_SECRET}",
    "Content-Type":  "application/json",
}


# ─────────────────────────────────────────────────────────────────────────────
# REPORT 1 — Item Daily Sales Trend
# ─────────────────────────────────────────────────────────────────────────────
DAILY_SCRIPT = r'''
import frappe
from frappe.utils import date_diff, nowdate, getdate, add_days


def execute(filters=None):
    filters = frappe._dict(filters or {})
    if not filters.from_date:
        filters.from_date = frappe.utils.get_first_day(nowdate())
    if not filters.to_date:
        filters.to_date = nowdate()

    top_n   = int(filters.get("top_n") or 10)
    columns = get_columns()
    data, chart = get_data_and_chart(filters, top_n)
    summary     = get_summary(data)
    return columns, data, None, chart, summary


def get_columns():
    return [
        {"fieldname": "posting_date", "label": "Date",       "fieldtype": "Date",  "width": 100},
        {"fieldname": "item_code",    "label": "Item Code",  "fieldtype": "Link",  "options": "Item", "width": 140},
        {"fieldname": "item_name",    "label": "Item Name",  "fieldtype": "Data",  "width": 220},
        {"fieldname": "item_group",   "label": "Group",      "fieldtype": "Link",  "options": "Item Group", "width": 110},
        {"fieldname": "qty_sold",     "label": "Qty Sold",   "fieldtype": "Float", "width": 90},
    ]


def get_data_and_chart(filters, top_n):
    bin_cond  = "AND sii.warehouse = %(warehouse)s"  if filters.get("warehouse")  else ""
    item_cond = "AND i.item_group  = %(item_group)s" if filters.get("item_group") else ""

    # Top N items for the whole period
    top_rows = frappe.db.sql(f"""
        SELECT sii.item_code,
               MAX(i.item_name)  AS item_name,
               MAX(i.item_group) AS item_group,
               SUM(sii.qty)      AS total_qty
        FROM   `tabSales Invoice Item` sii
        JOIN   `tabSales Invoice` si ON si.name    = sii.parent
        JOIN   `tabItem`          i  ON i.name     = sii.item_code
        WHERE  si.docstatus    = 1
          AND  si.posting_date BETWEEN %(from_date)s AND %(to_date)s
          AND  i.disabled      = 0
          {bin_cond}
          {item_cond}
        GROUP  BY sii.item_code
        ORDER  BY total_qty DESC
        LIMIT  %(top_n)s
    """, {**dict(filters), "top_n": top_n}, as_dict=True)

    if not top_rows:
        return [], None

    item_codes    = [r.item_code for r in top_rows]
    item_name_map = {r.item_code: r.item_name  for r in top_rows}
    item_grp_map  = {r.item_code: r.item_group for r in top_rows}

    # Daily breakdown for those items
    daily = frappe.db.sql(f"""
        SELECT si.posting_date, sii.item_code, SUM(sii.qty) AS qty_sold
        FROM   `tabSales Invoice Item` sii
        JOIN   `tabSales Invoice` si ON si.name = sii.parent
        WHERE  si.docstatus    = 1
          AND  si.posting_date BETWEEN %(from_date)s AND %(to_date)s
          AND  sii.item_code   IN %(item_codes)s
          {bin_cond}
        GROUP  BY si.posting_date, sii.item_code
        ORDER  BY si.posting_date, sii.item_code
    """, {**dict(filters), "item_codes": tuple(item_codes)}, as_dict=True)

    data = [{
        "posting_date": str(r.posting_date),
        "item_code":    r.item_code,
        "item_name":    item_name_map.get(r.item_code, r.item_code),
        "item_group":   item_grp_map.get(r.item_code, ""),
        "qty_sold":     r.qty_sold,
    } for r in daily]

    # ── Build multi-line chart ─────────────────────────────────────────
    from_dt   = getdate(filters.from_date)
    to_dt     = getdate(filters.to_date)
    total_days = date_diff(to_dt, from_dt) + 1

    all_dates = []
    d = from_dt
    while d <= to_dt:
        all_dates.append(str(d))
        d = add_days(d, 1)

    daily_map = {ic: {dt: 0 for dt in all_dates} for ic in item_codes}
    for r in daily:
        key = str(r.posting_date)
        if key in daily_map.get(r.item_code, {}):
            daily_map[r.item_code][key] += r.qty_sold

    # Thin out x-axis labels when the period is long
    step   = max(1, total_days // 20)
    labels = [d if i % step == 0 else "" for i, d in enumerate(all_dates)]

    datasets = [{
        "name":   item_name_map.get(ic, ic),
        "values": [daily_map[ic].get(dt, 0) for dt in all_dates],
    } for ic in item_codes]

    chart = {
        "data":        {"labels": labels, "datasets": datasets},
        "type":        "line",
        "title":       f"Daily Sales — Top {len(item_codes)} Items",
        "axisOptions": {"xIsSeries": True},
        "lineOptions": {"hideDots": 1 if total_days > 20 else 0, "spline": 0},
    }

    return data, chart


def get_summary(data):
    items = set(r["item_code"] for r in data)
    total = sum(r["qty_sold"] for r in data)
    peak  = max((r for r in data), key=lambda r: r["qty_sold"], default={})
    return [
        {"value": len(items),          "label": "Items Tracked",    "datatype": "Int",   "indicator": "Blue"},
        {"value": total,               "label": "Total Qty Sold",   "datatype": "Float", "indicator": "Green"},
        {"value": peak.get("qty_sold", 0), "label": "Best Single Day", "datatype": "Float", "indicator": "Purple"},
    ]
'''

DAILY_JS = r"""
frappe.query_reports["Item Daily Sales Trend"] = {
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
            fieldname: "top_n",
            label:     __("Top N Items"),
            fieldtype: "Int",
            default:   10,
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
        if (column.fieldname === "qty_sold" && data && data.qty_sold > 0) {
            value = `<strong>${value}</strong>`;
        }
        return value;
    },
};
"""


# ─────────────────────────────────────────────────────────────────────────────
# REPORT 2 — Items to Reorder
# ─────────────────────────────────────────────────────────────────────────────
REORDER_SCRIPT = r'''
import math
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
    chart   = get_chart(data)
    summary = get_summary(data)
    return columns, data, None, chart, summary


def get_columns():
    return [
        {"fieldname": "item_code",           "label": "Item",              "fieldtype": "Link",  "options": "Item",       "width": 140},
        {"fieldname": "item_name",            "label": "Item Name",         "fieldtype": "Data",                           "width": 200},
        {"fieldname": "item_group",           "label": "Group",             "fieldtype": "Link",  "options": "Item Group", "width": 110},
        {"fieldname": "current_stock",        "label": "In Stock",          "fieldtype": "Float",                          "width": 90},
        {"fieldname": "reorder_level",        "label": "Reorder Level",     "fieldtype": "Float",                          "width": 110},
        {"fieldname": "stock_gap",            "label": "Stock Gap",         "fieldtype": "Float",                          "width": 90},
        {"fieldname": "avg_daily_sales",      "label": "Avg / Day",         "fieldtype": "Float",                          "width": 90},
        {"fieldname": "days_of_stock",        "label": "Days Left",         "fieldtype": "Float",                          "width": 90},
        {"fieldname": "suggested_order_qty",  "label": "Suggest Order",     "fieldtype": "Float",                          "width": 120},
        {"fieldname": "status",               "label": "Status",            "fieldtype": "Data",                           "width": 110},
    ]


def get_data(filters):
    days      = (date_diff(filters.to_date, filters.from_date) or 0) + 1
    threshold = int(filters.get("days_threshold") or 14)

    bin_cond  = "AND b.warehouse   = %(warehouse)s"  if filters.get("warehouse")  else ""
    ir_cond   = "AND ir.warehouse  = %(warehouse)s"  if filters.get("warehouse")  else ""
    sii_cond  = "AND sii.warehouse = %(warehouse)s"  if filters.get("warehouse")  else ""
    item_cond = "AND i.item_group  = %(item_group)s" if filters.get("item_group") else ""

    rows = frappe.db.sql(f"""
        SELECT
            i.item_code, i.item_name, i.item_group,
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
        HAVING
            current_stock <= reorder_level
            OR (
                qty_sold > 0
                AND (current_stock / (qty_sold / %(days)s)) < %(threshold)s
            )
        ORDER BY
            CASE WHEN current_stock <= reorder_level THEN 0 ELSE 1 END,
            current_stock ASC
    """, {**dict(filters), "days": days, "threshold": threshold}, as_dict=True)

    data = []
    for r in rows:
        avg = round(r.qty_sold / days, 3) if (days and r.qty_sold) else 0
        if avg > 0:
            days_left = round(r.current_stock / avg, 1)
        else:
            days_left = None if r.current_stock > 0 else 0

        stock_gap = max(0, r.reorder_level - r.current_stock)
        # Suggest enough stock to last 30 days, covering the gap first
        suggest = math.ceil(avg * 30 + stock_gap) if avg > 0 else stock_gap or 0

        data.append({
            "item_code":          r.item_code,
            "item_name":          r.item_name,
            "item_group":         r.item_group,
            "current_stock":      r.current_stock,
            "reorder_level":      r.reorder_level,
            "stock_gap":          stock_gap,
            "avg_daily_sales":    avg,
            "days_of_stock":      days_left,
            "suggested_order_qty": suggest,
            "status":             "To Order" if r.current_stock <= r.reorder_level else "Low Stock",
        })

    return data


def get_chart(data):
    if not data:
        return None
    top = data[:20]  # show top 20 most urgent
    return {
        "data": {
            "labels":   [r["item_name"] or r["item_code"] for r in top],
            "datasets": [
                {"name": "Current Stock", "values": [r["current_stock"]  for r in top]},
                {"name": "Reorder Level", "values": [r["reorder_level"] for r in top]},
            ],
        },
        "type":   "bar",
        "title":  "Current Stock vs Reorder Level (most urgent first)",
        "colors": ["#36a2eb", "#ff6384"],
    }


def get_summary(data):
    to_order  = sum(1 for r in data if r["status"] == "To Order")
    low_stock = sum(1 for r in data if r["status"] == "Low Stock")
    total_sug = sum(r["suggested_order_qty"] for r in data)
    return [
        {"value": to_order,   "label": "Must Order Now",     "datatype": "Int",   "indicator": "Red"},
        {"value": low_stock,  "label": "Low Stock",           "datatype": "Int",   "indicator": "Orange"},
        {"value": total_sug,  "label": "Total Units to Buy",  "datatype": "Float", "indicator": "Blue"},
    ]
'''

REORDER_JS = r"""
frappe.query_reports["Items to Reorder"] = {
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
            fieldname: "days_threshold",
            label:     __("Low if < N Days Left"),
            fieldtype: "Int",
            default:   14,
            description: "Include items that will run out within this many days",
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
            const color = data.status === "To Order" ? "red" : "orange";
            return `<span class="indicator-pill ${color}">${data.status}</span>`;
        }
        if (column.fieldname === "days_of_stock") {
            if (data.days_of_stock === null || data.days_of_stock === undefined)
                return `<span style="color:var(--text-muted)">—</span>`;
            if (data.days_of_stock < 7)
                return `<span style="color:var(--red-500);font-weight:600">${data.days_of_stock}</span>`;
            if (data.days_of_stock < 14)
                return `<span style="color:var(--yellow-500)">${data.days_of_stock}</span>`;
        }
        if (column.fieldname === "current_stock" && data.current_stock <= data.reorder_level && data.reorder_level > 0) {
            return `<span style="color:var(--red-500);font-weight:600">${data.current_stock}</span>`;
        }
        if (column.fieldname === "suggested_order_qty" && data.suggested_order_qty > 0) {
            return `<strong style="color:var(--blue-500)">${data.suggested_order_qty}</strong>`;
        }
        return value;
    },
};
"""


# ─────────────────────────────────────────────────────────────────────────────
# NATIVE DASHBOARD CHARTS
# ─────────────────────────────────────────────────────────────────────────────
CHARTS = [
    {
        "chart_name":       "Daily Sales Revenue",
        "chart_type":       "Sum",
        "document_type":    "Sales Invoice",
        "based_on":         "posting_date",
        "value_based_on":   "grand_total",
        "time_interval":    "Daily",
        "timespan":         "Last Month",
        "filters_json":     json.dumps([["Sales Invoice", "docstatus", "=", 1]]),
        "type":             "Line",
        "color":            "#318AD8",
        "is_public":        1,
    },
    {
        "chart_name":       "Monthly Sales Revenue",
        "chart_type":       "Sum",
        "document_type":    "Sales Invoice",
        "based_on":         "posting_date",
        "value_based_on":   "grand_total",
        "time_interval":    "Monthly",
        "timespan":         "Last Year",
        "filters_json":     json.dumps([["Sales Invoice", "docstatus", "=", 1]]),
        "type":             "Bar",
        "color":            "#5E64FF",
        "is_public":        1,
    },
    {
        "chart_name":       "Daily Invoice Count",
        "chart_type":       "Count",
        "document_type":    "Sales Invoice",
        "based_on":         "posting_date",
        "time_interval":    "Daily",
        "timespan":         "Last Month",
        "filters_json":     json.dumps([["Sales Invoice", "docstatus", "=", 1]]),
        "type":             "Bar",
        "color":            "#29CD42",
        "is_public":        1,
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# NUMBER CARDS
# ─────────────────────────────────────────────────────────────────────────────
CARDS = [
    {
        "label":                        "Sales Today",
        "document_type":                "Sales Invoice",
        "function":                     "Sum",
        "aggregate_function_based_on":  "grand_total",
        "filters_json":                 json.dumps([
            ["Sales Invoice", "docstatus",     "=", 1],
            ["Sales Invoice", "posting_date",  "=", "Today"],
        ]),
        "color":    "#4CAF50",
        "is_public": 1,
    },
    {
        "label":         "Invoices This Month",
        "document_type": "Sales Invoice",
        "function":      "Count",
        "filters_json":  json.dumps([
            ["Sales Invoice", "docstatus",    "=", 1],
            ["Sales Invoice", "posting_date", "Timespan", "this month"],
        ]),
        "color":    "#FF9800",
        "is_public": 1,
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────
DASHBOARD_NAME = "Stock Dashboard"


# ─────────────────────────────────────────────────────────────────────────────
# Installer helpers
# ─────────────────────────────────────────────────────────────────────────────

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
        return {"name": data.get("name") or data.get("chart_name") or data.get("label") or data.get("dashboard_name", "")}
    print(f"  WARN [{r.status_code}] {doctype}: {r.text[:300]}")
    return None


def api_put(doctype, name, data):
    r = requests.put(
        f"{ERPNEXT_URL}/api/resource/{doctype}/{requests.utils.quote(str(name))}",
        headers=HEADERS,
        json={"data": data},
        timeout=30,
    )
    return r.status_code in (200, 201)


def upsert_report(name, ref_doctype, script, js):
    print(f"  Report: {name}...")
    data = {
        "report_name": name,
        "report_type": "Script Report",
        "ref_doctype": ref_doctype,
        "is_standard": "No",
        "disabled":    0,
        "script":      script,
        "javascript":  js,
    }
    if api_exists("Report", name):
        ok = api_put("Report", name, data)
        print("    Updated." if ok else "    WARN: update failed.")
    else:
        result = api_post("Report", data)
        print(f"    Created: {result.get('name','')}" if result else "    Failed.")


def upsert_chart(chart):
    name = chart["chart_name"]
    print(f"  Dashboard Chart: {name}...")
    if api_exists("Dashboard Chart", name):
        ok = api_put("Dashboard Chart", name, chart)
        print("    Updated." if ok else "    WARN.")
    else:
        result = api_post("Dashboard Chart", chart)
        print(f"    Created: {result.get('name','')}" if result else "    Failed.")


def upsert_card(card):
    name = card["label"]
    print(f"  Number Card: {name}...")
    if api_exists("Number Card", name):
        ok = api_put("Number Card", name, card)
        print("    Updated." if ok else "    WARN.")
    else:
        result = api_post("Number Card", card)
        print(f"    Created: {result.get('name','')}" if result else "    Failed.")


def upsert_dashboard():
    name = DASHBOARD_NAME
    print(f"  Dashboard: {name}...")
    data = {
        "dashboard_name": name,
        "is_public":      1,
        "charts": [
            {"chart": "Daily Sales Revenue",  "width": "Full"},
            {"chart": "Monthly Sales Revenue","width": "Half"},
            {"chart": "Daily Invoice Count",  "width": "Half"},
        ],
        "cards": [
            {"card": "Sales Today"},
            {"card": "Invoices This Month"},
        ],
    }
    if api_exists("Dashboard", name):
        ok = api_put("Dashboard", name, data)
        print("    Updated." if ok else "    WARN.")
    else:
        result = api_post("Dashboard", data)
        print(f"    Created: {result.get('name','')}" if result else "    Failed.")


def main():
    print("─── Script Reports ───────────────────────────────────")
    upsert_report("Item Daily Sales Trend", "Sales Invoice Item", DAILY_SCRIPT,   DAILY_JS)
    upsert_report("Items to Reorder",       "Item",               REORDER_SCRIPT, REORDER_JS)

    print("─── Dashboard Charts ─────────────────────────────────")
    for chart in CHARTS:
        upsert_chart(chart)

    print("─── Number Cards ─────────────────────────────────────")
    for card in CARDS:
        upsert_card(card)

    print("─── Dashboard ────────────────────────────────────────")
    upsert_dashboard()

    print("\nDone.")
    print(f"\nOpen the dashboard:  {ERPNEXT_URL}/app/dashboard-view/Stock%20Dashboard")
    print(f"Daily trend report:  {ERPNEXT_URL}/app/query-report/Item%20Daily%20Sales%20Trend")
    print(f"Reorder report:      {ERPNEXT_URL}/app/query-report/Items%20to%20Reorder")


if __name__ == "__main__":
    main()
