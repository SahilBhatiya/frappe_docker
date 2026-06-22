"""
Install GSTIN auto-fetch in ERPNext.

Creates:
  1. A Server Script (whitelisted API endpoint) that proxies GSTIN lookups
  2. Client Scripts for Customer and Supplier forms that add a Fetch button

Usage:
  python gstin_setup.py

GSTIN lookup uses Apisetu.gov.in (free Indian government API).
Register at: https://apisetu.gov.in/
Then fill in GSTIN_CLIENT_ID and GSTIN_CLIENT_SECRET below.
"""

import requests
import json

ERPNEXT_URL   = "http://localhost:8080"
API_KEY       = "12d80506c40944c"
API_SECRET    = "903ef51e33f8869"

HEADERS = {
    "Authorization": f"token {API_KEY}:{API_SECRET}",
    "Content-Type": "application/json",
}

# ── Apisetu credentials (fill in after registering) ──────────────────────────
# Register free at https://apisetu.gov.in/
GSTIN_CLIENT_ID     = ""
GSTIN_CLIENT_SECRET = ""

# ── Server Script: whitelisted method to look up GSTIN ───────────────────────
SERVER_SCRIPT_NAME = "gstin_lookup"
SERVER_SCRIPT_CODE = f"""
import requests as _req

GSTIN_CLIENT_ID     = {repr(GSTIN_CLIENT_ID)}
GSTIN_CLIENT_SECRET = {repr(GSTIN_CLIENT_SECRET)}

@frappe.whitelist()
def fetch_gstin_details(gstin):
    if not GSTIN_CLIENT_ID or not GSTIN_CLIENT_SECRET:
        frappe.throw("GSTIN API credentials not configured. Edit gstin_setup.py and re-run it.")

    tok = _req.post(
        "https://apisetu.gov.in/api/v1/oauth/tokens",
        json={{"clientId": GSTIN_CLIENT_ID, "clientSecret": GSTIN_CLIENT_SECRET}},
        timeout=15,
    )
    if tok.status_code != 200:
        frappe.throw(f"GSTIN auth failed: {{tok.text[:200]}}")

    token = tok.json().get("accessToken", "")
    r = _req.get(
        f"https://apisetu.gov.in/api/gstn/v3/taxpayerDetails/{{gstin}}",
        headers={{"Authorization": f"Bearer {{token}}"}},
        timeout=15,
    )
    if r.status_code != 200:
        frappe.throw(f"GSTIN lookup failed: {{r.text[:200]}}")

    d = r.json()
    pradr = d.get("pradr") or {{}}
    adr   = pradr.get("adr", "")
    return {{
        "gstin":        gstin,
        "trade_name":   d.get("tradeNam", "") or d.get("lgnm", ""),
        "legal_name":   d.get("lgnm", ""),
        "address":      adr,
        "state":        pradr.get("stj", ""),
        "pincode":      str(pradr.get("pin", "")),
        "status":       d.get("sts", ""),
        "entity_type":  d.get("ctb", ""),
    }}
"""

# ── Client Script: adds Fetch button to Customer and Supplier forms ───────────
CLIENT_SCRIPT_CODE = """
(function() {
  var FETCH_DOCTYPES = ["Customer", "Supplier"];

  FETCH_DOCTYPES.forEach(function(dt) {
    frappe.ui.form.on(dt, {
      refresh: function(frm) {
        if (!frm.doc.tax_id) return;
        if (!frm.fields_dict.tax_id) return;
        frm.add_custom_button(__("Fetch GST Details"), function() {
          _fetchGstDetails(frm);
        }, __("GST"));
      },

      tax_id: function(frm) {
        var gstin = (frm.doc.tax_id || "").trim().toUpperCase();
        if (gstin.length === 15) {
          _fetchGstDetails(frm);
        }
      }
    });
  });

  function _fetchGstDetails(frm) {
    var gstin = (frm.doc.tax_id || "").trim();
    if (!gstin) { frappe.msgprint("Enter a GSTIN first."); return; }
    frappe.show_alert({ message: "Fetching GST details...", indicator: "blue" }, 3);

    frappe.call({
      method: "frappe.client.run_doc_method",
      args: {
        dt: "Server Script",
        dn: "gstin_lookup",
        method: "fetch_gstin_details",
        args: JSON.stringify({ gstin: gstin }),
      },
      callback: function(r) {
        if (r.exc) return;
        var d = r.message || {};
        if (!d.trade_name && !d.legal_name) {
          frappe.msgprint("No data returned for GSTIN: " + gstin);
          return;
        }
        var display_name = d.trade_name || d.legal_name;
        if (frm.doctype === "Customer") {
          frm.set_value("customer_name", display_name);
        } else {
          frm.set_value("supplier_name", display_name);
        }
        frm.set_value("gstin", gstin);

        // Build and set address
        if (d.address) {
          _ensureAddress(frm, d);
        }
        frappe.show_alert({
          message: "GST details fetched: " + display_name + " (" + (d.status || "") + ")",
          indicator: d.status === "Active" ? "green" : "orange"
        }, 5);
      }
    });
  }

  function _ensureAddress(frm, d) {
    // Create a linked address if one doesn't exist yet
    var link_dt = frm.doctype;
    var link_dn = frm.doc.name;
    frappe.call({
      method: "frappe.client.insert",
      args: {
        doc: {
          doctype: "Address",
          address_title: frm.doc.name,
          address_type: "Billing",
          address_line1: d.address,
          pincode: d.pincode || "",
          gstin: d.gstin || "",
          links: [{ link_doctype: link_dt, link_name: link_dn }],
        }
      }
    });
  }
})();
"""

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

def api_exists(doctype, name):
    r = requests.get(
        f"{ERPNEXT_URL}/api/resource/{doctype}/{requests.utils.quote(str(name))}",
        headers=HEADERS,
        timeout=10,
    )
    return r.status_code == 200

def upsert_server_script():
    print("Installing Server Script: gstin_lookup...")
    data = {
        "name": SERVER_SCRIPT_NAME,
        "script_type": "API",
        "api_method": "gstin_lookup",
        "script": SERVER_SCRIPT_CODE,
        "allow_guest": 0,
        "disabled": 0,
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

def upsert_client_script(doctype):
    name = f"GSTIN Fetch - {doctype}"
    print(f"Installing Client Script: {name}...")
    data = {
        "name": name,
        "dt": doctype,
        "script": CLIENT_SCRIPT_CODE,
        "enabled": 1,
        "view": "Form",
    }
    if api_exists("Client Script", name):
        r = requests.put(
            f"{ERPNEXT_URL}/api/resource/Client Script/{requests.utils.quote(name)}",
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
    upsert_client_script("Customer")
    upsert_client_script("Supplier")
    print("\nDone.")
    if not GSTIN_CLIENT_ID:
        print("\nNOTE: GSTIN_CLIENT_ID is empty — the fetch button will show an error.")
        print("Register free at https://apisetu.gov.in/ then re-run this script.")

if __name__ == "__main__":
    main()
