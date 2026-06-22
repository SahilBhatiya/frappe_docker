"""
Install fuzzy item search for Link fields in ERPNext.

Problem: tyre sizes like "4.00-8 MRF TUBE" can't be found by typing "4008"
because the default LIKE '%4008%' doesn't match "4.00-8".

Solution:
  1. Server Script (API) — item_fuzzy_search
     SQL that ALSO searches a normalized version of item_code / item_name
     (strips . - / and spaces) so "4008" matches "4.00-8", "185/65R15" via "18565R15", etc.
     Exact/prefix matches are sorted first.

  2. Client Script (Sales Invoice — Form)
     Intercepts frappe.call for Item link-field searches (frappe.desk.search.search_link)
     and redirects them to item_fuzzy_search. Transforms the response back to the
     format ControlLink expects. The patch is global so it persists for the session
     (benefits all Item link fields, not just Sales Invoice).

Usage: python fuzzy_item_search.py
"""

import requests

ERPNEXT_URL = "http://localhost:8080"
API_KEY     = "12d80506c40944c"
API_SECRET  = "903ef51e33f8869"

HEADERS = {
    "Authorization": f"token {API_KEY}:{API_SECRET}",
    "Content-Type":  "application/json",
}

SERVER_SCRIPT_NAME = "item_fuzzy_search"
CLIENT_SCRIPT_NAME = "Sales Invoice - Fuzzy Item Search"

# ── Server-side: fuzzy SQL search ────────────────────────────────────────────
SERVER_SCRIPT_CODE = r'''
import re
from frappe.utils import cint

@frappe.whitelist()
def item_fuzzy_search(txt, norm_txt=None, page_len=20):
    txt      = (txt or "").strip()
    page_len = cint(page_len) or 20

    if not txt:
        return []

    # Strip ALL non-alphanumeric characters — handles any separator the user omits
    if not norm_txt:
        norm_txt = re.sub(r"[^a-zA-Z0-9]", "", txt)

    like_txt  = "%" + txt            + "%"
    like_norm = "%" + norm_txt.lower() + "%"

    # REGEXP_REPLACE strips every non-alphanumeric char from the stored code/name
    # so "4.00-8 MRF TUBE" → "4008mrftube" and "185/65R15" → "18565r15"
    rows = frappe.db.sql("""
        SELECT item_code, item_name, item_group
        FROM   `tabItem`
        WHERE  disabled       = 0
          AND  is_sales_item  = 1
          AND  (
               item_code  LIKE %(like_txt)s
            OR item_name  LIKE %(like_txt)s
            OR REGEXP_REPLACE(LOWER(item_code), '[^a-z0-9]', '') LIKE %(like_norm)s
            OR REGEXP_REPLACE(LOWER(item_name), '[^a-z0-9]', '') LIKE %(like_norm)s
          )
        ORDER BY
            CASE
                WHEN item_code LIKE %(like_txt)s THEN 0
                WHEN item_name LIKE %(like_txt)s THEN 1
                ELSE 2
            END,
            item_code ASC
        LIMIT %(page_len)s
    """, {"like_txt": like_txt, "like_norm": like_norm, "page_len": page_len})

    return [[r[0], r[1], r[2]] for r in rows]
'''

# ── Client-side: intercept frappe.call for Item searches ─────────────────────
CLIENT_SCRIPT_CODE = r"""
(function () {
    'use strict';

    /* ── Patch is global so it persists across pages once SI is visited.
          Guard prevents double-patching if multiple SI forms are opened. ── */
    if (window.__itemFuzzyPatched) return;
    window.__itemFuzzyPatched = true;

    var _orig = frappe.call.bind(frappe);

    /* Strip ALL non-alphanumeric — mirrors server-side REGEXP_REPLACE('[^a-z0-9]') */
    function normalize(s) {
        return (s || '').replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
    }

    frappe.call = function (opts) {
        /* Pass through everything except Item link-field searches */
        if (!opts
                || typeof opts !== 'object'
                || opts.method !== 'frappe.desk.search.search_link'
                || !opts.args
                || opts.args.doctype !== 'Item') {
            return _orig.apply(frappe, arguments);
        }

        var txt     = opts.args.txt      || '';
        var norm    = normalize(txt);
        var origCb  = opts.callback;
        var pageLen = opts.args.page_length || 20;

        return _orig.call(frappe, {
            method:   'item_fuzzy_search',
            args:     { txt: txt, norm_txt: norm, page_len: pageLen },
            callback: function (r) {
                /* Server returns r.message = [[item_code, item_name, item_group], ...]
                   ControlLink expects  r.results = [{value, description}, ...]        */
                var raw     = r.message || [];
                var results = raw.map(function (row) {
                    if (!Array.isArray(row)) return row;
                    /* Show "item_code  ·  item_name" in the dropdown */
                    var desc = (row[1] && row[1] !== row[0]) ? row[1] : '';
                    if (row[2]) desc += (desc ? '  ·  ' : '') + row[2];
                    return { value: row[0], description: desc };
                });
                if (origCb) origCb({ results: results });
            },
        });
    };

})();
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

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


def upsert_server_script():
    print(f"Installing Server Script: {SERVER_SCRIPT_NAME}...")
    data = {
        "name":        SERVER_SCRIPT_NAME,
        "script_type": "API",
        "api_method":  SERVER_SCRIPT_NAME,
        "script":      SERVER_SCRIPT_CODE,
        "allow_guest": 0,
        "disabled":    0,
    }
    if api_exists("Server Script", SERVER_SCRIPT_NAME):
        r = requests.put(
            f"{ERPNEXT_URL}/api/resource/Server Script/{requests.utils.quote(SERVER_SCRIPT_NAME)}",
            headers=HEADERS,
            json={"data": data},
            timeout=30,
        )
        print("  Updated." if r.status_code in (200, 201) else f"  WARN {r.text[:200]}")
    else:
        result = api_post("Server Script", data)
        print(f"  Created: {result.get('name', '')}" if result else "  Failed.")


def upsert_client_script():
    print(f"Installing Client Script: {CLIENT_SCRIPT_NAME}...")
    data = {
        "name":    CLIENT_SCRIPT_NAME,
        "dt":      "Sales Invoice",
        "script":  CLIENT_SCRIPT_CODE,
        "enabled": 1,
        "view":    "Form",
    }
    if api_exists("Client Script", CLIENT_SCRIPT_NAME):
        r = requests.put(
            f"{ERPNEXT_URL}/api/resource/Client Script/{requests.utils.quote(CLIENT_SCRIPT_NAME)}",
            headers=HEADERS,
            json={"data": data},
            timeout=30,
        )
        print("  Updated." if r.status_code in (200, 201) else f"  WARN {r.text[:200]}")
    else:
        result = api_post("Client Script", data)
        print(f"  Created: {result.get('name', '')}" if result else "  Failed.")


def main():
    upsert_server_script()
    upsert_client_script()
    print("\nDone.")
    print("Hard-refresh the Sales Invoice form (Ctrl+Shift+R) to activate.")
    print("\nFuzzy examples:")
    print("  '4008'    → matches  4.00-8, 4.00-8 MRF TUBE, etc.")
    print("  '400'     → matches  4.00-8, 4.00-10, 4.00-12, etc.")
    print("  '18565'   → matches  185/65R15, 185-65R15, etc.")
    print("  '10020'   → matches  10.00-20, 10.00/20, etc.")
    print("  '165'     → matches  165/65R13, 165/80R14, etc.")


if __name__ == "__main__":
    main()
