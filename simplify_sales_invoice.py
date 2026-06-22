"""
Simplify the Sales Invoice form to reduce clutter.

Hides:
  - Company-currency duplicate fields (base_total, base_net_total, etc.) —
    only relevant for multi-currency invoices, almost never needed in India
  - Tax Category, Shipping Rule, Incoterm, Named Place — advanced/unused fields
  - Taxes & Charges table rows when empty (shows again once a template is chosen)
  - Redundant columns in the Items table (description, net_rate/amount, income_account, cost_center)

All hidden fields are still present in the document — the script only hides them from view.
Disable this Client Script in ERPNext to restore the original form.

Run: python simplify_sales_invoice.py
"""

import requests

ERPNEXT_URL = "http://localhost:8080"
API_KEY     = "12d80506c40944c"
API_SECRET  = "903ef51e33f8869"

HEADERS = {
    "Authorization": f"token {API_KEY}:{API_SECRET}",
    "Content-Type":  "application/json",
}

SCRIPT_NAME = "Sales Invoice - Simplified Form"

CLIENT_SCRIPT = r"""
(function () {
    'use strict';

    /* ── Fields to hide regardless of currency ── */
    var ALWAYS_HIDE = [
        'tax_category',          // Tax Category      — rarely used
        'shipping_rule',         // Shipping Rule      — rarely used
        'incoterm',              // Incoterm           — export only
        'named_place',           // Named Place        — paired with Incoterm
        'column_break_payment_terms', // spacer that becomes orphaned
    ];

    /* ── Company-currency mirror fields — hide when billing in local currency ── */
    var BASE_FIELDS = [
        'base_total',
        'base_net_total',
        'base_total_taxes_and_charges',
        'base_grand_total',
        'base_rounded_total',
        'base_in_account_currency',
        'total_advance',         // company-currency version duplicate
    ];

    /* ── Items grid columns to hide ── */
    var HIDE_ITEM_COLS = [
        'item_name',        // already shown as tooltip / bold under item_code
        'description',      // verbose, not needed at invoice entry time
        'net_rate',         // same as rate when no discount
        'net_amount',       // same as amount when no discount
        'base_rate',        // company-currency duplicate
        'base_amount',      // company-currency duplicate
        'income_account',   // accounting detail — set by item master
        'cost_center',      // accounting detail — set by default
        'project',          // project billing — hide if not used
        'page_break',       // print layout option
    ];

    function applySimplification(frm) {
        /* 1 ── Always-hidden fields */
        ALWAYS_HIDE.forEach(function (f) {
            frm.toggle_display(f, false);
        });

        /* 2 ── Company-currency duplicates: hide when customer currency = company currency */
        var isMultiCurrency = frm.doc.currency &&
            frm.doc.currency !== frappe.defaults.get_default('currency');
        BASE_FIELDS.forEach(function (f) {
            frm.toggle_display(f, !!isMultiCurrency);
        });

        /* 3 ── Taxes table: hide when empty (no template chosen yet / no rows) */
        var hasTaxRows = !!(frm.doc.taxes && frm.doc.taxes.length);
        frm.toggle_display('taxes', hasTaxRows);

        /* 4 ── Simplify Items child table columns */
        var grid = frm.fields_dict.items && frm.fields_dict.items.grid;
        if (grid) {
            HIDE_ITEM_COLS.forEach(function (col) {
                try { grid.set_column_disp(col, false); } catch (e) { /* column may not exist */ }
            });
        }
    }

    frappe.ui.form.on('Sales Invoice', {

        onload: applySimplification,
        refresh: applySimplification,

        /* Re-evaluate multi-currency display if currency changes */
        currency: applySimplification,

        /* Show taxes table as soon as a template fills it */
        taxes_and_charges: function (frm) {
            /* ERPNext populates frm.doc.taxes after a short async fetch */
            setTimeout(function () {
                var hasTaxRows = !!(frm.doc.taxes && frm.doc.taxes.length);
                frm.toggle_display('taxes', hasTaxRows);
            }, 800);
        },

        /* Show taxes table when user manually adds a tax row */
        taxes_add: function (frm) {
            frm.toggle_display('taxes', true);
        },

        taxes_remove: function (frm) {
            var hasTaxRows = !!(frm.doc.taxes && frm.doc.taxes.length);
            frm.toggle_display('taxes', hasTaxRows);
        },
    });

})();
"""


# ── Helpers (same pattern as other scripts) ───────────────────────────────────

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


def upsert_client_script():
    print(f"Installing Client Script: {SCRIPT_NAME}...")
    data = {
        "name":    SCRIPT_NAME,
        "dt":      "Sales Invoice",
        "script":  CLIENT_SCRIPT,
        "enabled": 1,
        "view":    "Form",
    }
    if api_exists("Client Script", SCRIPT_NAME):
        r = requests.put(
            f"{ERPNEXT_URL}/api/resource/Client Script/{requests.utils.quote(SCRIPT_NAME)}",
            headers=HEADERS,
            json={"data": data},
            timeout=30,
        )
        print("  Updated." if r.status_code in (200, 201) else f"  WARN {r.text[:200]}")
    else:
        result = api_post("Client Script", data)
        print(f"  Created: {result.get('name', '')}" if result else "  Failed.")


def main():
    upsert_client_script()
    print("\nDone.")
    print("Hard-refresh any open Sales Invoice (Ctrl+Shift+R) to activate.")
    print("\nWhat changed:")
    print("  - Company-currency duplicate fields hidden (base_total, base_net_total, etc.)")
    print("  - Tax Category / Shipping Rule / Incoterm hidden")
    print("  - Taxes table hidden when empty, shown once a template is selected")
    print("  - Items table: description, net_rate/amount, income/cost fields hidden")
    print("\nTo revert: go to ERPNext > Client Script > disable this script.")


if __name__ == "__main__":
    main()
