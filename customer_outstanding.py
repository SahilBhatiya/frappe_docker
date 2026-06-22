"""
Install a "Closing Balance" column on the Customer list view.

Creates:
  1. Custom Field - Customer.custom_closing_balance
     Stores the ledger balance for native list sorting.
  2. Server Script (type: API) - get_customer_balances
     Queries GL Entry and returns {customer: closing_balance} for visible rows.
  3. Server Script (type: API) - rebuild_customer_closing_balances
     Backfills the stored values after installation.
  4. Server Script (GL Entry, After Insert) - Sync Customer Closing Balance
     Keeps the stored value current when ledger entries are posted.
  5. Client Script (Customer, List view) - Customer Ledger Balance - List
     Adds a Closing Balance column and populates it with one batched API call
     after each list refresh; clicking its header sorts all Customer rows.

Usage:
  python customer_outstanding.py
"""

import requests

ERPNEXT_URL = "http://localhost:8080"
API_KEY = "12d80506c40944c"
API_SECRET = "903ef51e33f8869"

HEADERS = {
    "Authorization": f"token {API_KEY}:{API_SECRET}",
    "Content-Type": "application/json",
}

SERVER_SCRIPT_NAME = "get_customer_balances"
REBUILD_SCRIPT_NAME = "rebuild_customer_closing_balances"
SYNC_SCRIPT_NAME = "Sync Customer Closing Balance - GL Entry"
CUSTOM_FIELD_NAME = "Customer-custom_closing_balance"
CUSTOM_FIELD_FIELDNAME = "custom_closing_balance"
# Keep the existing identifier so rerunning this installer updates any older copy.
CLIENT_SCRIPT_NAME = "Customer Ledger Balance - List"

SERVER_SCRIPT_CODE = r'''
names = json.loads(frappe.form_dict.customer_names or "[]")
names = [name for name in names if name][:250]
balances = {}

if names:
    rows = frappe.db.sql(
        """
        SELECT party, SUM(debit - credit) AS closing_balance
        FROM `tabGL Entry`
        WHERE party_type = 'Customer'
          AND party IN %(names)s
          AND is_cancelled = 0
        GROUP BY party
        """,
        {"names": names},
        as_dict=True,
    )
    balances = {row.party: float(row.closing_balance or 0) for row in rows}

frappe.response["message"] = balances
'''

REBUILD_SCRIPT_CODE = r'''
rows = frappe.db.sql(
    """
    SELECT party, SUM(debit - credit) AS closing_balance
    FROM `tabGL Entry`
    WHERE party_type = 'Customer'
      AND is_cancelled = 0
    GROUP BY party
    """,
    as_dict=True,
)
balances = {row.party: float(row.closing_balance or 0) for row in rows}
customers = frappe.get_all("Customer", fields=["name"], limit_page_length=0)

for customer in customers:
    frappe.db.set_value(
        "Customer",
        customer.name,
        "custom_closing_balance",
        balances.get(customer.name, 0),
        update_modified=False,
    )

frappe.response["message"] = {"updated": len(customers)}
'''

SYNC_SCRIPT_CODE = r'''
if doc.party_type == "Customer" and doc.party:
    rows = frappe.db.sql(
        """
        SELECT SUM(debit - credit) AS closing_balance
        FROM `tabGL Entry`
        WHERE party_type = 'Customer'
          AND party = %(party)s
          AND is_cancelled = 0
        """,
        {"party": doc.party},
        as_dict=True,
    )
    balance = float(rows[0].closing_balance or 0) if rows else 0
    frappe.db.set_value(
        "Customer",
        doc.party,
        "custom_closing_balance",
        balance,
        update_modified=False,
    )
'''

CLIENT_SCRIPT_CODE = r"""
(function () {
    "use strict";

    var COLUMN_CLASS = "customer-closing-balance";
    var SORT_FIELD = "custom_closing_balance";
    var COLUMN_STYLE = "width:150px;flex:0 0 150px;text-align:right;padding-right:12px;";
    var timer = null;

    function formatBalance(value) {
        var amount = flt(value || 0);
        var formatted = frappe.format(Math.abs(amount), {fieldtype: "Currency"});

        if (amount < 0) {
            return '<span title="' + __("Credit balance") +
                '" style="color:var(--green-600)">' + formatted + " Cr</span>";
        }

        return formatted;
    }

    function getVisibleRows(listview) {
        var rows = [];

        $(listview.page.main).find(".list-row-container .list-row").each(function () {
            var $row = $(this);
            var $checkbox = $row.find(".list-row-checkbox[data-name]").first();
            if (!$checkbox.length) {
                return;
            }

            rows.push({
                name: $checkbox.attr("data-name"),
                cell: $row.find(".level-left").first(),
            });
        });

        return rows;
    }

    function ensureColumn(listview) {
        var $header = $(listview.page.main)
            .find(".list-row-head .list-header-subject")
            .first();

        if ($header.length && !$header.find("." + COLUMN_CLASS).length) {
            var $headerTarget = $header
                .find(".customer_group, .default_currency, .billing_currency")
                .first();
            var headerHtml =
                '<div class="list-row-col hidden-xs text-right ' + COLUMN_CLASS +
                '" style="' + COLUMN_STYLE + '"><span data-sort-by="' + SORT_FIELD +
                '" title="' + __("Click to sort by Closing Balance") + '">' +
                __("Closing Balance") +
                "</span></div>";

            if ($headerTarget.length) {
                $headerTarget.before(headerHtml);
            } else {
                $header.append(headerHtml);
            }
        }

        var rows = getVisibleRows(listview);
        rows.forEach(function (row) {
            if (!row.cell.find("." + COLUMN_CLASS).length) {
                var $cellTarget = row.cell
                    .find(".customer_group, .default_currency, .billing_currency")
                    .first();
                var cellHtml = '<div class="list-row-col hidden-xs text-right ' + COLUMN_CLASS +
                    '" style="' + COLUMN_STYLE + 'color:var(--text-muted)">...</div>';

                if ($cellTarget.length) {
                    $cellTarget.before(cellHtml);
                } else {
                    row.cell.append(cellHtml);
                }
            }
        });

        return rows;
    }

    function loadBalances(listview) {
        var rows = ensureColumn(listview);
        var names = rows.map(function (row) {
            return row.name;
        });

        if (!names.length) {
            return;
        }

        frappe.call({
            method: "get_customer_balances",
            args: {customer_names: JSON.stringify(names)},
            callback: function (response) {
                var balances = (response && response.message) || {};
                rows.forEach(function (row) {
                    var amount = Object.prototype.hasOwnProperty.call(balances, row.name)
                        ? balances[row.name]
                        : 0;
                    row.cell.find("." + COLUMN_CLASS).html(formatBalance(amount));
                });
            },
        });
    }

    var settings = frappe.listview_settings.Customer || {};
    var originalRefresh = settings.refresh;

    settings.refresh = function (listview) {
        if (originalRefresh) {
            originalRefresh.call(this, listview);
        }

        ensureColumn(listview);
        clearTimeout(timer);
        timer = setTimeout(function () {
            loadBalances(listview);
        }, 150);
    };

    frappe.listview_settings.Customer = settings;
})();
"""


def api_exists(doctype, name):
    response = requests.get(
        f"{ERPNEXT_URL}/api/resource/{doctype}/{requests.utils.quote(str(name))}",
        headers=HEADERS,
        timeout=10,
    )
    return response.status_code == 200


def api_post(doctype, data):
    response = requests.post(
        f"{ERPNEXT_URL}/api/resource/{doctype}",
        headers=HEADERS,
        json={"data": data},
        timeout=30,
    )
    if response.status_code in (200, 201):
        return response.json().get("data", {})
    if response.status_code == 409:
        return {"name": data.get("name", "")}
    print(f"  WARN [{response.status_code}] {doctype}: {response.text[:300]}")
    return None


def api_put(doctype, name, data):
    response = requests.put(
        f"{ERPNEXT_URL}/api/resource/{doctype}/{requests.utils.quote(name)}",
        headers=HEADERS,
        json={"data": data},
        timeout=30,
    )
    return response


def upsert_custom_field():
    print("Installing Custom Field: Customer.closing_balance...")
    data = {
        "dt": "Customer",
        "fieldname": CUSTOM_FIELD_FIELDNAME,
        "label": "Closing Balance",
        "fieldtype": "Currency",
        "insert_after": "default_currency",
        "read_only": 1,
        "hidden": 1,
        "in_list_view": 0,
        "in_standard_filter": 0,
        "search_index": 1,
        "precision": "2",
    }
    if api_exists("Custom Field", CUSTOM_FIELD_NAME):
        response = api_put("Custom Field", CUSTOM_FIELD_NAME, data)
        print("  Updated." if response.status_code in (200, 201) else f"  WARN {response.text[:200]}")
    else:
        result = api_post("Custom Field", data)
        print(f"  Created: {result.get('name', '')}" if result else "  Failed.")


def upsert_server_script(name, data):
    print(f"Installing Server Script: {name}...")
    data = {"name": name, "disabled": 0, **data}
    if api_exists("Server Script", name):
        response = api_put("Server Script", name, data)
        print("  Updated." if response.status_code in (200, 201) else f"  WARN {response.text[:200]}")
    else:
        result = api_post("Server Script", data)
        print(f"  Created: {result.get('name', '')}" if result else "  Failed.")


def install_server_scripts():
    upsert_server_script(SERVER_SCRIPT_NAME, {
        "script_type": "API",
        "api_method": SERVER_SCRIPT_NAME,
        "script": SERVER_SCRIPT_CODE,
        "allow_guest": 0,
    })
    upsert_server_script(REBUILD_SCRIPT_NAME, {
        "script_type": "API",
        "api_method": REBUILD_SCRIPT_NAME,
        "script": REBUILD_SCRIPT_CODE,
        "allow_guest": 0,
    })
    upsert_server_script(SYNC_SCRIPT_NAME, {
        "script_type": "DocType Event",
        "reference_doctype": "GL Entry",
        "doctype_event": "After Insert",
        "script": SYNC_SCRIPT_CODE,
    })


def rebuild_closing_balances():
    print("Backfilling Customer closing balances...")
    response = requests.post(
        f"{ERPNEXT_URL}/api/method/{REBUILD_SCRIPT_NAME}",
        headers=HEADERS,
        timeout=60,
    )
    if response.status_code == 200:
        updated = response.json().get("message", {}).get("updated", 0)
        print(f"  Updated: {updated} customers.")
    else:
        print(f"  WARN [{response.status_code}]: {response.text[:300]}")


def upsert_client_script():
    print(f"Installing Client Script: {CLIENT_SCRIPT_NAME}...")
    data = {
        "name": CLIENT_SCRIPT_NAME,
        "dt": "Customer",
        "script": CLIENT_SCRIPT_CODE,
        "enabled": 1,
        "view": "List",
    }
    if api_exists("Client Script", CLIENT_SCRIPT_NAME):
        response = requests.put(
            f"{ERPNEXT_URL}/api/resource/Client Script/{requests.utils.quote(CLIENT_SCRIPT_NAME)}",
            headers=HEADERS,
            json={"data": data},
            timeout=30,
        )
        print("  Updated." if response.status_code in (200, 201) else f"  WARN {response.text[:200]}")
    else:
        result = api_post("Client Script", data)
        print(f"  Created: {result.get('name', '')}" if result else "  Failed.")


def main():
    upsert_custom_field()
    install_server_scripts()
    upsert_client_script()
    rebuild_closing_balances()
    print("\nDone.")
    print("Reload the Customer list; click Closing Balance to sort it.")


if __name__ == "__main__":
    main()
