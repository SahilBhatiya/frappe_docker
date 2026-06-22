"""
Tally XML → ERPNext Migration Script
Company: Adarsh Motor Stores
"""

from __future__ import annotations
import requests
import json
import os
import subprocess
import sys
import re
import io
from datetime import datetime
from lxml import etree

# Fix Windows console UTF-8 output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── Config ──────────────────────────────────────────────────────────────────
ERPNEXT_URL  = "http://localhost:8080"
API_KEY      = "12d80506c40944c"
API_SECRET   = "903ef51e33f8869"
COMPANY       = "ADARSH MOTOR STORES"
ABBR          = "AMS"  # ERPNext company abbreviation
# GST state code for AMS — update to match company's GST registration state
# Common codes: 06-Haryana, 07-Delhi, 08-Rajasthan, 24-Gujarat, 27-Maharashtra, 29-Karnataka
COMPANY_STATE = "24-Gujarat"
# Company GSTIN — required by india_compliance on every invoice
# Format: 2-digit state code + 10-char PAN + 1 entity no. + Z + 1 check digit
COMPANY_GSTIN = "24AADFA2635A1ZA"   # ← replace with actual GSTIN
MASTER_XML   = r"C:\Program Files\TallyPrime\Master.xml"
TRANS_XML    = r"C:\Program Files\TallyPrime\Transactions.xml"

# Used by the 'full' reset path: REST cannot delete submitted Stock/GL/Payment
# Ledger entries, so we shell into the backend container and use frappe.db.delete
# (raw SQL, bypasses doctype-level checks). Set DOCKER_CONTAINER="" to disable.
DOCKER_CONTAINER = "erpnext-backend-1"
DOCKER_SITE      = "erpnext.localhost"

HEADERS = {
    "Authorization": f"token {API_KEY}:{API_SECRET}",
    "Content-Type": "application/json",
}

# ── Logging ───────────────────────────────────────────────────────────────────
# Two log files written next to this script:
#   migration_errors.log — every failed POST/DELETE/SUBMIT/CANCEL with the
#                          request body and the parsed server message, so you
#                          can grep for a doctype/name and see *why* it failed.
#   hsn_log.log          — every HSN auto-created or attempted, for review.
LOG_DIR     = os.path.dirname(os.path.abspath(__file__))
ERROR_LOG   = os.path.join(LOG_DIR, "migration_errors.log")
HSN_LOG     = os.path.join(LOG_DIR, "hsn_log.log")


def _extract_server_msg(text):
    """Pull the human-readable error out of a Frappe error response.
    Frappe wraps exceptions in JSON with `exception`/`_server_messages`; this
    digs those out so the log shows the *real* reason, not raw HTML."""
    if not text:
        return ""
    # JSON response with `exception` field — newer Frappe
    try:
        j = json.loads(text)
        if isinstance(j, dict):
            if j.get("exception"):
                return str(j["exception"])
            sm = j.get("_server_messages")
            if sm:
                try:
                    msgs = json.loads(sm)
                    out = []
                    for m in msgs:
                        m_obj = json.loads(m) if isinstance(m, str) else m
                        if isinstance(m_obj, dict) and m_obj.get("message"):
                            out.append(re.sub(r"<[^>]+>", "", m_obj["message"]))
                    if out:
                        return " | ".join(out)
                except Exception:
                    pass
    except Exception:
        pass
    # Fallback: strip HTML tags from the raw text
    return re.sub(r"<[^>]+>", " ", text).strip()


def log_error(operation, doctype, name, status, message, request_data=None):
    """Append a structured entry to migration_errors.log. Never raises."""
    try:
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{ts}] {operation} {doctype}/{name} [{status}]\n")
            msg = _extract_server_msg(message)
            if len(msg) > 800:
                msg = msg[:800] + " …(truncated)"
            f.write(f"    error: {msg}\n")
            if request_data is not None:
                try:
                    rd = json.dumps(request_data, ensure_ascii=False, default=str)
                except Exception:
                    rd = str(request_data)
                if len(rd) > 800:
                    rd = rd[:800] + " …(truncated)"
                f.write(f"    request: {rd}\n")
            f.write("\n")
    except Exception:
        pass


def log_hsn(action, hsn, note=""):
    """Append an HSN action to hsn_log.log. Actions: CREATED, EXISTS, FAILED."""
    try:
        with open(HSN_LOG, "a", encoding="utf-8") as f:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{ts}] {action}\t{hsn}\t{note}\n")
    except Exception:
        pass

# Tally ledger names that are payment modes, not actual customers.
# When PARTYLEDGERNAME is one of these, the real buyer name comes from
# BASICBUYERNAME in the voucher.
PAYMENT_MODE_LEDGERS = {
    "Cash",
    "Net Banking Payment Sales",
}

# Pattern to detect online/UPI payments in narration or ledger names
ONLINE_PATTERN = re.compile(r'on\s*line|online|upi|neft', re.IGNORECASE)

# ── Tally group → ERPNext parent account + root_type ─────────────────────────
TALLY_GROUP_MAP = {
    "Capital Account":           ("Source of Funds (Liabilities)", "Liability"),
    "Reserves & Surplus":        ("Source of Funds (Liabilities)", "Liability"),
    "Loans (Liability)":         ("Loans (Liabilities)",           "Liability"),
    "Secured Loans":             ("Loans (Liabilities)",           "Liability"),
    "Unsecured Loans":           ("Loans (Liabilities)",           "Liability"),
    "Current Liabilities":       ("Source of Funds (Liabilities)", "Liability"),
    "Provisions":                ("Current Liabilities",           "Liability"),
    "Sundry Creditors":          ("Current Liabilities",           "Liability"),
    "Duties & Taxes":            ("Duties and Taxes",              "Liability"),
    "Fixed Assets":              ("Application of Funds (Assets)", "Asset"),
    "Current Assets":            ("Application of Funds (Assets)", "Asset"),
    "Bank Accounts":             ("Current Assets",                "Asset"),
    "Bank OD A/c":               ("Current Assets",                "Asset"),
    "Cash-in-Hand":              ("Current Assets",                "Asset"),
    "Sundry Debtors":            ("Current Assets",                "Asset"),
    "Stock-in-Hand":             ("Stock Assets",                  "Asset"),
    "Investments":               ("Investments",                   "Asset"),
    "Loans & Advances (Asset)":  ("Loans and Advances (Assets)",   "Asset"),
    "Deposits (Asset)":          ("Securities and Deposits",       "Asset"),
    "Misc. Expenses (ASSET)":    ("Application of Funds (Assets)", "Asset"),
    "Suspense A/c":              ("Temporary Accounts",            "Asset"),
    "Branch / Divisions":        ("Application of Funds (Assets)", "Asset"),
    "Income":                    ("Income",                        "Income"),
    "Direct Incomes":            ("Direct Income",                 "Income"),
    "Indirect Incomes":          ("Indirect Income",               "Income"),
    "Sales Accounts":            ("Direct Income",                 "Income"),
    "Expenses":                  ("Expenses",                      "Expense"),
    "Direct Expenses":           ("Direct Expenses",               "Expense"),
    "Indirect Expenses":         ("Indirect Expenses",             "Expense"),
    "Purchase Accounts":         ("Direct Expenses",               "Expense"),
}

# ── Core API helpers ──────────────────────────────────────────────────────────
def _is_deadlock(text):
    """MariaDB deadlock (1213) or 'record has changed' (1020) — both retryable."""
    if not text:
        return False
    t = text.lower()
    return ("querydeadlockerror" in t
            or "1020" in t and "record has changed" in t
            or "deadlock found when trying to get lock" in t
            or "1213" in t)


def _doc_name(data):
    """Best-effort name extraction from a doc payload for logging."""
    if not isinstance(data, dict):
        return "?"
    for k in ("name", "item_code", "item_name", "account_name",
              "customer_name", "supplier_name", "hsn_code"):
        if data.get(k):
            return str(data[k])
    return "?"


def api_post(doctype, data):
    url = f"{ERPNEXT_URL}/api/resource/{doctype}"
    for attempt in range(4):                     # 1 initial + 3 retries
        try:
            r = requests.post(url, headers=HEADERS, json={"data": data}, timeout=30)
            if r.status_code in (200, 201):
                return r.json().get("data", {})
            if r.status_code == 409:
                return {"name": data.get("name", data.get("account_name", ""))}
            # Retry on transient DB contention (deadlock / row-version mismatch)
            if r.status_code == 500 and _is_deadlock(r.text) and attempt < 3:
                import time
                time.sleep(0.5 * (attempt + 1))  # 0.5s, 1s, 1.5s
                continue
            print(f"  WARN [{r.status_code}] {doctype}: {r.text[:200]}")
            log_error("POST", doctype, _doc_name(data), r.status_code, r.text,
                      request_data=data)
            return None
        except Exception as e:
            print(f"  ERR {doctype}: {e}")
            log_error("POST", doctype, _doc_name(data), 0, str(e),
                      request_data=data)
            return None
    return None

def api_exists(doctype, name):
    url = f"{ERPNEXT_URL}/api/resource/{doctype}/{requests.utils.quote(name)}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        return r.status_code == 200
    except:
        return False

def api_submit(doctype, name):
    """Submit a document (docstatus 0 → 1)."""
    url = f"{ERPNEXT_URL}/api/resource/{doctype}/{requests.utils.quote(name)}"
    try:
        r = requests.put(url, headers=HEADERS, json={"data": {"docstatus": 1}}, timeout=30)
        if r.status_code in (200, 201):
            return True
        print(f"  WARN submit [{r.status_code}] {doctype}/{name}: {r.text[:200]}")
        log_error("SUBMIT", doctype, name, r.status_code, r.text)
        return False
    except Exception as e:
        print(f"  ERR submit {doctype}/{name}: {e}")
        log_error("SUBMIT", doctype, name, 0, str(e))
        return False

def api_cancel(doctype, name):
    url = f"{ERPNEXT_URL}/api/resource/{doctype}/{requests.utils.quote(name)}"
    try:
        r = requests.put(url, headers=HEADERS, json={"data": {"docstatus": 2}}, timeout=30)
        if r.status_code in (200, 201):
            return True
        log_error("CANCEL", doctype, name, r.status_code, r.text)
        return False
    except Exception as e:
        log_error("CANCEL", doctype, name, 0, str(e))
        return False

def api_delete(doctype, name):
    url = f"{ERPNEXT_URL}/api/resource/{doctype}/{requests.utils.quote(name)}"
    try:
        r = requests.delete(url, headers=HEADERS, timeout=30)
        if r.status_code in (200, 202, 204):
            return True
        log_error("DELETE", doctype, name, r.status_code, r.text)
        return False
    except Exception as e:
        log_error("DELETE", doctype, name, 0, str(e))
        return False

def tally_date(d):
    try:
        return datetime.strptime(d.strip(), "%Y%m%d").strftime("%Y-%m-%d")
    except:
        return None

def tally_amount(v):
    try:
        return abs(float(v.strip()))
    except:
        return 0.0

def parse_tally_qty(v):
    """Parse Tally qty like ' 1 NOS', '2.00 Nos', '3' → float."""
    m = re.match(r'\s*([\d,]+\.?\d*)', (v or "").strip())
    return abs(float(m.group(1).replace(',', ''))) if m else 1.0

def parse_tally_rate(v):
    """Parse Tally rate like '2900.00/NOS', '34860.50 /Nos', '500' → float."""
    m = re.match(r'\s*([\d,]+\.?\d*)', (v or "").strip())
    return abs(float(m.group(1).replace(',', ''))) if m else 0.0

# ── Item / Account caches ──────────────────────────────────────────────────────
ITEM_CACHE: set    = set()
ACCOUNT_CACHE: set = set()
BANK_ACCOUNT_MAP: dict = {}   # GL account name → Bank Account doc name
BANK_ONLY_GL: set  = set()    # subset of BANK_ACCOUNT_MAP keys where account_type == "Bank"
COMPANY_ADDRESS_NAME: str = ""  # populated by ensure_company_address()

# Maps (party_name, tally_bill_ref) → ERPNext doc name, built during invoice pass
# Used in payment pass to correctly link payments to specific invoices
BILL_REF_MAP: dict = {}   # value: ("Sales Invoice"|"Purchase Invoice", erp_name)

# Matches CGST/SGST/IGST tax accounts only — NOT "Sales GST 18%" (revenue account)
GST_LEDGER_PATTERN = re.compile(
    r'(?:(?:input|output)\s+tax\s+)?(?:cgst|sgst|igst)',
    re.IGNORECASE
)

# ── GSTIN lookup config (optional) ────────────────────────────────────────────
# Register free at https://apisetu.gov.in/ to get these credentials
GSTIN_CLIENT_ID     = ""
GSTIN_CLIENT_SECRET = ""

def parse_xml(path):
    print(f"Parsing {path} (this may take a minute for large files)...")
    with open(path, "rb") as f:
        raw = f.read()

    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8", errors="replace")

    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    text = re.sub(r'&#(\d+);', lambda m: '' if int(m.group(1)) < 32 and int(m.group(1)) not in (9,10,13) else m.group(0), text)
    text = text.replace('₹', 'INR').replace('\xa4', 'INR')

    encoded = text.encode("utf-8")
    parser = etree.XMLParser(recover=True, encoding="utf-8")
    root = etree.fromstring(encoded, parser=parser)
    print(f"  Parsed OK.")
    return root

def txt(el, tag):
    node = el.find(tag)
    return (node.text or "").strip() if node is not None else ""

# ── Voucher helpers (module-level so they can be used by payment functions) ───
def ledger_total(vch):
    """Return the largest absolute amount from ledger entries (= invoice total)."""
    max_amt = 0.0
    for leg in vch.iter("ALLLEDGERENTRIES.LIST"):
        try:
            amt = abs(float((txt(leg, "AMOUNT") or "0").strip() or "0"))
            if amt > max_amt:
                max_amt = amt
        except:
            pass
    return max_amt

def inventory_items(vch):
    """
    Build items list from INVENTORYALLOCATIONS.LIST entries.
    Handles Tally's unit-suffixed qty/rate ('1 NOS', '2900/NOS').
    Falls back to ALLINVENTORYENTRIES.LIST for older Tally exports.

    Each returned dict also carries _tyre_numbers: a list of tyre serial
    numbers extracted from DESCRIPTION or BATCHALLOCATIONS.LIST → BATCHNAME.
    These internal keys (prefix _) are stripped before the API call and used
    to populate the Sales Invoice tyre_numbers child table.
    """
    items = []
    for tag in ("INVENTORYALLOCATIONS.LIST", "ALLINVENTORYENTRIES.LIST"):
        for inv in vch.iter(tag):
            iname = sanitize_item_name(txt(inv, "STOCKITEMNAME"))
            if not iname:
                continue
            qty  = parse_tally_qty(txt(inv, "BILLEDQTY") or txt(inv, "ACTUALQTY") or "1")
            rate = parse_tally_rate(txt(inv, "RATE") or "0")
            amt  = parse_tally_rate(txt(inv, "AMOUNT") or "0")
            item_code = iname if iname in ITEM_CACHE else "Services"
            eff_rate = (amt / max(qty, 1)) if amt > 0 else rate

            # Collect tyre numbers: prefer description, fall back to batch names.
            # Skip generic Tally batch names that are not real tyre serial numbers.
            _GENERIC_BATCHES = {
                "primary batch", "not applicable", "n/a", "na", "none",
                "default", "default batch", "primary", "batch",
            }
            desc = (txt(inv, "DESCRIPTION") or txt(inv, "USERDESCRIPTION") or "").strip()
            tyre_nos: list[str] = []
            if desc:
                tyre_nos = [n.strip() for n in re.split(r'[,;\n/]+', desc)
                            if n.strip() and n.strip().lower() not in _GENERIC_BATCHES]
            if not tyre_nos:
                for ba in inv.iter("BATCHALLOCATIONS.LIST"):
                    bn = (txt(ba, "BATCHNAME") or txt(ba, "TRACKINGNUMBER") or "").strip()
                    if bn and bn.lower() not in _GENERIC_BATCHES:
                        tyre_nos.append(bn)

            items.append({
                "item_code": item_code,
                "qty": max(qty, 1),
                "rate": eff_rate,
                "_tyre_numbers": tyre_nos,   # stripped before API call
            })
        if items:
            break
    return items


def _build_tyre_numbers(items, vno=""):
    """
    Pop _tyre_numbers from each item and build the tyre_numbers child-table rows.
    item_row_idx matches the 1-based idx ERPNext assigns when items are POSTed in order.

    Placeholders include the voucher number when supplied so the same item across
    multiple migrated invoices produces globally-unique tyre numbers — without it,
    the Server Script uniqueness check rejects every subsequent invoice for that
    item with HTTP 417 "Tyre number(s) already used on another invoice".

    "Services" (unmapped-item fallback) is skipped — it is never a tyre.
    Returns (cleaned_items, tyre_number_rows).
    """
    tyre_rows = []
    # Sanitize vno to a token safe to embed in a tyre serial
    vtag = re.sub(r"[^A-Za-z0-9_-]+", "_", vno).strip("_") if vno else ""
    for i, item in enumerate(items):
        tyre_nos = item.pop("_tyre_numbers", [])
        item_idx = i + 1
        qty      = int(item.get("qty", 1))
        code     = item.get("item_code", "ITEM")

        if code == "Services":
            continue

        # Pad with globally-unique placeholders when Tally gave no serials.
        prefix = f"MIGRATED-{vtag}-{code}" if vtag else f"MIGRATED-{code}"
        while len(tyre_nos) < qty:
            tyre_nos.append(f"{prefix}-{len(tyre_nos) + 1}")
        tyre_nos = tyre_nos[:qty]
        for num in tyre_nos:
            tyre_rows.append({"item_row_idx": item_idx, "tyre_number": num})
    return items, tyre_rows

# ── Bootstrap helpers ─────────────────────────────────────────────────────────
def ensure_company_address():
    """
    india_compliance requires every invoice to carry company_address so it can
    resolve the company GSTIN.  This function finds or creates that address and
    caches its name in COMPANY_ADDRESS_NAME.
    """
    global COMPANY_ADDRESS_NAME

    # Try to find an existing address linked to the company
    r = requests.get(
        f"{ERPNEXT_URL}/api/resource/Address",
        headers=HEADERS,
        params={
            "filters": json.dumps([
                ["Dynamic Link", "link_doctype", "=", "Company"],
                ["Dynamic Link", "link_name",    "=", COMPANY],
            ]),
            "fields": '["name"]',
            "limit_page_length": 1,
        },
        timeout=15,
    )
    if r.status_code == 200:
        rows = r.json().get("data", [])
        if rows:
            COMPANY_ADDRESS_NAME = rows[0]["name"]
            print(f"  Company address: {COMPANY_ADDRESS_NAME}")
            return COMPANY_ADDRESS_NAME

    # None found — create one
    addr_data = {
        "doctype":       "Address",
        "address_title": COMPANY,
        "address_type":  "Billing",
        "address_line1": COMPANY,
        "city":          "Mehsana",
        "state":         "Gujarat",
        "country":       "India",
        "pincode":       "384001",
        "gstin":         COMPANY_GSTIN,
        "links": [{"link_doctype": "Company", "link_name": COMPANY}],
    }
    result = api_post("Address", addr_data)
    if result:
        COMPANY_ADDRESS_NAME = result.get("name", "")
        print(f"  Created company address: {COMPANY_ADDRESS_NAME}")
    else:
        print("  WARN: could not create company address — india_compliance will reject invoices")
    return COMPANY_ADDRESS_NAME

def ensure_services_item():
    if api_exists("Item", "Services"):
        return
    ensure_item_group("Services")
    # Try candidate item groups in order; ERPNext must have at least one.
    for grp in ("Services", "All Item Groups", "Products", "All"):
        r = requests.get(
            f"{ERPNEXT_URL}/api/resource/Item Group/{requests.utils.quote(grp)}",
            headers=HEADERS, timeout=10,
        )
        if r.status_code == 200:
            item_group = grp
            break
    else:
        print("  ERROR: no usable Item Group found — cannot create fallback item 'Services'")
        print("         Create the 'Services' item manually in ERPNext before migrating.")
        return

    result = api_post("Item", {
        "item_name": "Services",
        "item_code": "Services",
        "item_group": item_group,
        "stock_uom": "Nos",
        "is_stock_item": 0,
        "is_purchase_item": 1,
        "is_sales_item": 1,
        "standard_rate": 0,
        "uoms": [{"uom": "Nos", "conversion_factor": 1}],
        "item_defaults": [{"company": COMPANY}],
    })
    if result:
        print(f"  Created fallback item: Services (group: {item_group})")
    else:
        print("  ERROR: could not create fallback item 'Services' — invoices with unmapped"
              " items will fail. Create the 'Services' item manually in ERPNext.")

def fetch_gstin_details(gstin):
    """
    Fetch taxpayer name/address from Apisetu.gov.in GSTN API (free, needs signup).
    Returns dict with keys: name, legal_name, address, state, status.
    Returns {} if credentials not set or lookup fails.
    """
    if not GSTIN_CLIENT_ID or not GSTIN_CLIENT_SECRET or not gstin:
        return {}
    try:
        tok_r = requests.post(
            "https://apisetu.gov.in/api/v1/oauth/tokens",
            json={"clientId": GSTIN_CLIENT_ID, "clientSecret": GSTIN_CLIENT_SECRET},
            timeout=15,
        )
        if tok_r.status_code != 200:
            return {}
        token = tok_r.json().get("accessToken", "")
        r = requests.get(
            f"https://apisetu.gov.in/api/gstn/v3/taxpayerDetails/{gstin}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        if r.status_code != 200:
            return {}
        d = r.json()
        adr = (d.get("pradr") or {}).get("adr", "")
        return {
            "name":       d.get("tradeNam") or d.get("lgnm", ""),
            "legal_name": d.get("lgnm", ""),
            "address":    adr,
            "state":      (d.get("pradr") or {}).get("stj", ""),
            "pincode":    str((d.get("pradr") or {}).get("pin", "")),
            "status":     d.get("sts", ""),
        }
    except Exception as e:
        print(f"  WARN GSTIN lookup {gstin}: {e}")
        return {}

def preload_accounts():
    """Cache all ERPNext account names + Bank Account map for fast lookups."""
    global ACCOUNT_CACHE, BANK_ACCOUNT_MAP
    ACCOUNT_CACHE = set()
    url = f"{ERPNEXT_URL}/api/resource/Account"
    start = 0
    while True:
        params = {"fields": '["name"]', "limit_page_length": 500, "limit_start": start}
        r = requests.get(url, headers=HEADERS, params=params, timeout=30)
        if r.status_code != 200:
            break
        batch = r.json().get("data", [])
        ACCOUNT_CACHE.update(d["name"] for d in batch)
        if len(batch) < 500:
            break
        start += 500
    print(f"  Account cache loaded: {len(ACCOUNT_CACHE)} accounts")

    # Build GL account → Bank Account name map
    BANK_ACCOUNT_MAP = {}
    ba_url = f"{ERPNEXT_URL}/api/resource/Bank Account"
    params = {
        "filters": json.dumps([["is_company_account", "=", 1]]),
        "fields": '["name","account"]',
        "limit_page_length": 200,
    }
    r = requests.get(ba_url, headers=HEADERS, params=params, timeout=30)
    if r.status_code == 200:
        for ba in r.json().get("data", []):
            if ba.get("account"):
                BANK_ACCOUNT_MAP[ba["account"]] = ba["name"]
    print(f"  Bank Account map: {len(BANK_ACCOUNT_MAP)} accounts")

    # Identify which GL accounts are truly account_type=Bank (for Bank Transaction filter)
    global BANK_ONLY_GL
    BANK_ONLY_GL = set()
    for gl_acc in BANK_ACCOUNT_MAP:
        acc_r = requests.get(
            f"{ERPNEXT_URL}/api/resource/Account/{requests.utils.quote(gl_acc)}",
            headers=HEADERS, timeout=10,
        )
        if acc_r.status_code == 200:
            atype = acc_r.json().get("data", {}).get("account_type", "")
            if atype == "Bank":
                BANK_ONLY_GL.add(gl_acc)
    print(f"  Bank-type GL accounts: {len(BANK_ONLY_GL)}")

def preload_items():
    """Cache all ERPNext item codes to avoid per-item API calls during migration."""
    global ITEM_CACHE
    url = f"{ERPNEXT_URL}/api/resource/Item"
    ITEM_CACHE = set()
    start = 0
    while True:
        params = {"fields": '["item_code"]', "limit_page_length": 500, "limit_start": start}
        r = requests.get(url, headers=HEADERS, params=params, timeout=30)
        if r.status_code != 200:
            break
        batch = r.json().get("data", [])
        ITEM_CACHE.update(d["item_code"] for d in batch)
        if len(batch) < 500:
            break
        start += 500
    print(f"  Item cache loaded: {len(ITEM_CACHE)} items")

def extract_gst_taxes(vch, items=None):
    """
    Scan ALLLEDGERENTRIES.LIST for GST ledgers (CGST/SGST/IGST/Sales GST/etc.)
    and return ERPNext tax rows.

    Uses charge_type='On Net Total' with a computed rate (tax_amount / net_total * 100)
    when items are provided — this avoids the ERPNext validation:
        "Actual type tax cannot be included in Item rate"
    which `india_compliance` triggers when its hooks coerce included_in_print_rate=1
    on Actual-type rows. Percentage-based rows sidestep the validation entirely.

    Falls back to charge_type='Actual' (with included_in_print_rate=0 and
    included_in_paid_amount=0) when net_total can't be computed.

    Works for both Sales and Purchase invoices since ledger names differ.
    """
    # Compute invoice net total from items for rate calculation
    net_total = 0.0
    if items:
        for it in items:
            try:
                net_total += float(it.get("qty", 1)) * float(it.get("rate", 0))
            except (TypeError, ValueError):
                pass

    taxes = []
    party = txt(vch, "PARTYLEDGERNAME").strip()
    seen = set()
    for leg in vch.iter("ALLLEDGERENTRIES.LIST"):
        lname = (txt(leg, "LEDGERNAME") or "").strip()
        if not lname or lname == party or lname in seen:
            continue
        if not GST_LEDGER_PATTERN.search(lname):
            continue
        try:
            amt = abs(float((txt(leg, "AMOUNT") or "0").strip() or "0"))
        except:
            amt = 0.0
        if amt <= 0:
            continue
        acc = f"{lname} - {ABBR}"
        if acc not in ACCOUNT_CACHE:
            continue

        # Prefer percentage-based row (sidesteps india_compliance validation).
        # Snap to common GST rates (2.5/6/9/14 for CGST+SGST half-rates, 5/12/18/28 for IGST).
        if net_total > 0:
            raw_rate = (amt / net_total) * 100
            common = [2.5, 6, 9, 14, 5, 12, 18, 28, 0.1, 0.5, 1, 1.5, 3]
            snapped = min(common, key=lambda c: abs(c - raw_rate))
            rate = snapped if abs(snapped - raw_rate) < 0.5 else round(raw_rate, 3)
            taxes.append({
                "charge_type":             "On Net Total",
                "account_head":            acc,
                "rate":                    rate,
                "description":             lname,
                "included_in_print_rate":  0,
                "included_in_paid_amount": 0,
                "category":                "Total",
            })
        else:
            # Fallback: keep amount-based Actual row but with both flags explicit
            taxes.append({
                "charge_type":             "Actual",
                "account_head":            acc,
                "rate":                    0,
                "tax_amount":              amt,
                "description":             lname,
                "included_in_print_rate":  0,
                "included_in_paid_amount": 0,
                "category":                "Total",
            })
        seen.add(lname)
    return taxes

def extract_bank_ref(vch):
    """
    Pull UTR / cheque number + date from BANKALLOCATIONS.LIST in the bank ledger leg.
    Returns (ref_no, ref_date_str, transfer_mode).
    """
    for leg in vch.iter("ALLLEDGERENTRIES.LIST"):
        for ba in leg.iter("BANKALLOCATIONS.LIST"):
            utr  = txt(ba, "UNIQUEREFERENCENUMBER").strip()
            raw_date = txt(ba, "DATE").strip()
            mode = (txt(ba, "TRANSACTIONTYPE") or txt(ba, "TRANSFERMODE")).strip()
            if utr:
                return utr, (tally_date(raw_date) if raw_date else None), mode
    return "", None, ""

def register_bill_refs(vch, party, doc_name, doctype):
    """
    After creating an invoice, scan ALLLEDGERENTRIES > BILLALLOCATIONS for
    BILLTYPE="New Ref" entries and store them in BILL_REF_MAP so that payment
    vouchers can later link to the correct ERPNext invoice.
    """
    for leg in vch.iter("ALLLEDGERENTRIES.LIST"):
        lname = (txt(leg, "LEDGERNAME") or "").strip()
        is_party = txt(leg, "ISPARTYLEDGER").strip().lower() == "yes"
        if not (is_party or lname == party):
            continue
        for ba in leg.iter("BILLALLOCATIONS.LIST"):
            bill_ref  = txt(ba, "NAME").strip()
            bill_type = txt(ba, "BILLTYPE").strip().lower()
            if bill_ref and bill_type == "new ref":
                BILL_REF_MAP[(party, bill_ref)] = (doctype, doc_name)

def build_payment_refs(vch, party, is_purchase):
    """
    For a Payment/Receipt voucher, resolve BILLALLOCATIONS "Agst Ref" entries
    to ERPNext invoice names via BILL_REF_MAP.
    Returns list of Payment Entry reference rows.
    """
    refs = []
    for leg in vch.iter("ALLLEDGERENTRIES.LIST"):
        lname    = (txt(leg, "LEDGERNAME") or "").strip()
        is_party = txt(leg, "ISPARTYLEDGER").strip().lower() == "yes"
        if not (is_party or lname == party):
            continue
        for ba in leg.iter("BILLALLOCATIONS.LIST"):
            bill_ref  = txt(ba, "NAME").strip()
            bill_type = txt(ba, "BILLTYPE").strip().lower()
            try:
                amt = abs(float(txt(ba, "AMOUNT") or "0"))
            except:
                amt = 0.0
            if bill_type == "agst ref" and bill_ref and amt > 0:
                mapped = BILL_REF_MAP.get((party, bill_ref))
                if mapped:
                    doctype, doc_name = mapped
                    refs.append({
                        "reference_doctype": doctype,
                        "reference_name": doc_name,
                        "allocated_amount": amt,
                    })
    return refs

def _cancel_doc(doctype, name):
    """
    Cancel a submitted document via the Frappe cancel endpoint.
    Tries the resource PUT first (works on most ERPNext versions),
    then falls back to frappe.client.set_value as a last resort.
    """
    # Primary: PUT docstatus=2 through the document resource endpoint
    url = f"{ERPNEXT_URL}/api/resource/{requests.utils.quote(doctype)}/{requests.utils.quote(name)}"
    r = requests.put(url, headers=HEADERS,
                     json={"data": {"docstatus": 2}}, timeout=30)
    if r.status_code in (200, 201):
        return True
    # Fallback: run_doc_method cancel
    r2 = requests.post(
        f"{ERPNEXT_URL}/api/method/frappe.client.set_value",
        headers=HEADERS,
        json={"doctype": doctype, "name": name,
              "fieldname": "docstatus", "value": 2},
        timeout=30,
    )
    return r2.status_code in (200, 201)

NO_COMPANY_FIELD = {
    "Bank Transaction", "Item", "Item Group", "Customer", "Supplier",
    "Address", "Contact", "UOM",
    "Bin", "Item Price",                 # caches keyed off Item, not Company
    "Item Tax Template", "Item Tax",     # global; usage is per-Item not per-company
}

def _try_delete(doctype, name, rest_url):
    """Try DELETE on the resource, then fallback to frappe.client.delete.
    Returns (ok, status_code, message)."""
    del_url = f"{rest_url}/{requests.utils.quote(name)}"
    try:
        r = requests.delete(del_url, headers=HEADERS, timeout=30)
        if r.status_code in (200, 202, 204):
            return True, r.status_code, ""
        msg = r.text
        # Fallback: frappe.client.delete (slightly different path, may succeed
        # where the raw REST DELETE refuses, e.g. for submitted child docs)
        r2 = requests.post(
            f"{ERPNEXT_URL}/api/method/frappe.client.delete",
            headers=HEADERS,
            json={"doctype": doctype, "name": name},
            timeout=30,
        )
        if r2.status_code in (200, 201):
            return True, r2.status_code, ""
        return False, r.status_code, msg
    except Exception as e:
        return False, 0, str(e)


def _extract_link_hint(msg):
    """Pull the linked-doctype hint out of a Frappe LinkExistsError message."""
    if not msg:
        return ""
    # Frappe error pages contain HTML; the readable bit is in <title> or in
    # the JSON `_server_messages`. Just grep for the doctype name.
    m = re.search(r"linked with\s+([^<\"]{1,80})", msg, re.IGNORECASE)
    if m:
        return f"linked with {m.group(1).strip()}"
    m = re.search(r"Cannot delete[^<\"]{1,200}", msg, re.IGNORECASE)
    if m:
        return m.group(0).strip()
    return ""


def delete_all_of(doctype, max_passes=1):
    """
    Delete ALL documents of a doctype for this company (draft/submitted/cancelled).
    Cancels submitted docs before deletion to satisfy Frappe constraints.

    `max_passes` > 1 re-runs the delete loop to handle tree doctypes (Account,
    Item Group) — leaves die in pass 1, then their parents become leaves and
    die in pass 2, etc. Stops early if a pass deletes nothing.
    """
    rest_url = f"{ERPNEXT_URL}/api/resource/{requests.utils.quote(doctype)}"
    has_company = doctype not in NO_COMPANY_FIELD
    total_deleted = 0

    for pass_idx in range(max_passes):
        seen = set()
        all_docs = []
        for ds in (0, 1, 2):
            start = 0
            while True:
                filters = [["docstatus", "=", ds]]
                if has_company:
                    filters.insert(0, ["company", "=", COMPANY])
                params = {
                    "filters": json.dumps(filters),
                    "fields": '["name","docstatus"]',
                    "limit_page_length": 500,
                    "limit_start": start,
                }
                r = requests.get(rest_url, headers=HEADERS, params=params, timeout=30)
                if r.status_code != 200:
                    break
                batch = r.json().get("data", [])
                for doc in batch:
                    if doc["name"] not in seen:
                        seen.add(doc["name"])
                        all_docs.append(doc)
                if len(batch) < 500:
                    break
                start += 500

        if not all_docs:
            break

        count = 0
        sample_err = ""
        for doc in all_docs:
            name = doc["name"]
            ds   = doc.get("docstatus", 0)
            if ds == 1:
                _cancel_doc(doctype, name)
            ok, code, msg = _try_delete(doctype, name, rest_url)
            if ok:
                count += 1
            else:
                # Surface what's actually blocking the first few failures
                if not sample_err:
                    sample_err = _extract_link_hint(msg) or (msg[:160] if msg else "")
                    print(f"  WARN: could not delete {name} [{code}] {sample_err}")
                else:
                    print(f"  WARN: could not delete {name} [{code}]")
        total_deleted += count
        print(f"  Pass {pass_idx + 1}: deleted {count}/{len(all_docs)} {doctype}s")
        if count == 0:
            break  # nothing budged, more passes won't help

    if max_passes > 1:
        print(f"  Total deleted: {total_deleted} {doctype}s")

def clear_transactions():
    """Delete all migrated transactions so we can re-import cleanly."""
    print("\n=== Clearing all transactions ===")
    # Order matters: Bank Transactions link to Payment Entries, so clear them first.
    # Payment Entries link to invoices, so clear before invoices.
    for doctype in ("Bank Transaction", "Payment Entry", "Journal Entry",
                    "Sales Invoice", "Purchase Invoice", "Stock Reconciliation"):
        print(f"\n--- {doctype} ---")
        delete_all_of(doctype)

def purge_ledger_records():
    """Best-effort REST cleanup of cache/ledger records. Used by the REST-only
    fallback path; the docker-bench path is far more reliable (see docker_nuke)."""
    print("\n=== Purging auxiliary ledger records (REST) ===")
    for doctype in ("Bin", "Item Price",
                    "Stock Ledger Entry", "GL Entry", "Payment Ledger Entry",
                    "Stock Reservation Entry", "Repost Item Valuation",
                    "Serial and Batch Bundle"):
        print(f"\n--- {doctype} ---")
        delete_all_of(doctype)


# ── Docker / bench fallback for true reset ───────────────────────────────────
# REST cannot delete docstatus=1 records like Stock Ledger Entry, GL Entry,
# Payment Ledger Entry, Repost Item Valuation. The only clean way is to run
# `frappe.db.delete` (raw SQL) inside the bench environment. We shell into the
# backend container and run a python script with frappe initialised.

def _docker_available():
    if not DOCKER_CONTAINER:
        return False
    try:
        r = subprocess.run(
            ["docker", "exec", DOCKER_CONTAINER, "true"],
            capture_output=True, timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


def _build_nuke_script(company, *, transactions=True, items=False,
                       parties=False, accounts=False):
    """Build a python script for the backend container that runs raw
    `frappe.db.delete` (bypasses docstatus/link checks).

    Scope flags compose:
      - transactions: SI/PI/PE/JE/Stock Recon/Bank Tx + their auto-generated
                      ledger entries (SLE/GLE/Payment Ledger/Repost Item Valuation)
      - items:        Bin/Item Price/Item Tax/Item Default + Item Tax Template + Item
      - parties:      Address/Contact/Customer/Supplier/Bank Account
      - accounts:     Account tree + Item Group tree

    Doubled braces in f-strings preserve dict literals in the emitted code.
    """
    parts = []
    if transactions:
        parts.append('''
PER_COMPANY = [
    "Bank Transaction",
    "Stock Ledger Entry", "GL Entry", "Payment Ledger Entry",
    "Repost Item Valuation", "Stock Reservation Entry", "Serial and Batch Bundle",
    "Sales Invoice", "Purchase Invoice", "Payment Entry",
    "Journal Entry", "Stock Reconciliation",
]
for dt in PER_COMPANY:
    n = frappe.db.count(dt, {"company": COMPANY})
    if n:
        frappe.db.delete(dt, {"company": COMPANY})
        print(f"  - {dt}: {n}")
''')
    if items:
        # Bin & Item Price are global caches keyed on Item — must die before Items.
        parts.append('''
for dt in ["Bin", "Item Price", "Item Tax", "Item Default",
           "Item Tax Template", "Item"]:
    n = frappe.db.count(dt)
    if n:
        frappe.db.delete(dt)
        print(f"  - {dt}: {n}")
''')
    if parties:
        parts.append('''
for dt in ["Address", "Contact", "Customer", "Supplier", "Bank Account"]:
    n = frappe.db.count(dt)
    if n:
        frappe.db.delete(dt)
        print(f"  - {dt}: {n}")
''')
    if accounts:
        parts.append('''
for _ in range(20):
    leaves = frappe.db.get_all("Account",
        filters={"company": COMPANY, "is_group": 0}, pluck="name")
    if not leaves:
        break
    for nm in leaves:
        frappe.db.delete("Account", {"name": nm})
remaining = frappe.db.count("Account", {"company": COMPANY})
if remaining:
    frappe.db.delete("Account", {"company": COMPANY})
    print(f"  - Account: {remaining} group rows force-deleted")

for _ in range(20):
    rows = frappe.db.sql(
        "SELECT name FROM `tabItem Group` WHERE is_group=0 "
        "AND name NOT IN (SELECT DISTINCT parent_item_group "
        "FROM `tabItem Group` WHERE parent_item_group IS NOT NULL)"
    )
    if not rows:
        break
    for (nm,) in rows:
        try:
            frappe.db.delete("Item Group", {"name": nm})
        except Exception:
            pass
''')

    body = "\n".join(parts)
    return (
        f"import frappe\n"
        f"frappe.init(site={DOCKER_SITE!r})\n"
        f"frappe.connect()\n"
        f"COMPANY = {company!r}\n"
        f"{body}\n"
        f"frappe.db.commit()\n"
        f"print('NUKE_DONE')\n"
    )


def ensure_standard_coa():
    """Re-create ERPNext's standard chart of accounts for the company.

    Why this exists: the Company doc carries default_receivable_account /
    default_income_account / default_cost_of_goods_sold_account / etc. that
    are populated at install time (e.g. 'Debtors - AMS', 'Sales - AMS').
    The 'full' nuke wipes every Account row for the company, but the Company
    doc keeps the dangling references. Tally only knows about its own ledger
    names ('Sundry Debtors', 'Sales Accounts'), so the migration never
    re-creates these standard names — and every Sales/Purchase Invoice fails
    at submit with LinkValidationError until they exist.

    Calls Company.create_default_accounts() inside bench. Idempotent — skips
    accounts that already exist. Also re-runs default warehouse / cost-center
    creation since those were nuked too."""
    if not _docker_available():
        print(f"  Docker container {DOCKER_CONTAINER!r} not reachable —")
        print(f"  manually: bench --site {DOCKER_SITE} execute "
              f"'frappe.get_doc(\"Company\", {COMPANY!r}).create_default_accounts'")
        return False
    print(f"\n=== Bootstrapping standard CoA via bench ===")
    script = (
        f"import frappe\n"
        f"frappe.init(site={DOCKER_SITE!r})\n"
        f"frappe.connect()\n"
        f"co = frappe.get_doc('Company', {COMPANY!r})\n"
        f"before = frappe.db.count('Account', {{'company': {COMPANY!r}}})\n"
        f"co.create_default_accounts()\n"
        f"try:\n"
        f"    co.create_default_warehouses()\n"
        f"except Exception as e:\n"
        f"    print(f'  warehouses: {{e}}')\n"
        f"try:\n"
        f"    from erpnext.setup.doctype.company.company import "
        f"install_country_fixtures\n"
        f"    install_country_fixtures({COMPANY!r})\n"
        f"except Exception:\n"
        f"    pass\n"
        f"frappe.db.commit()\n"
        f"after = frappe.db.count('Account', {{'company': {COMPANY!r}}})\n"
        f"print(f'  - Accounts: {{before}} -> {{after}}')\n"
        f"print('COA_DONE')\n"
    )
    try:
        r = subprocess.run(
            ["docker", "exec", "-i", DOCKER_CONTAINER, "sh", "-c",
             "cat > /tmp/tally_coa.py && "
             "cd /home/frappe/frappe-bench/sites && "
             "/home/frappe/frappe-bench/env/bin/python /tmp/tally_coa.py"],
            input=script, text=True, capture_output=True, timeout=180,
        )
        out = (r.stdout or "") + "\n" + (r.stderr or "")
        ok = "COA_DONE" in out
        if ok:
            for line in out.splitlines():
                if line.strip().startswith("- "):
                    print(f"  {line.rstrip()}")
        else:
            print("  CoA bootstrap failed:")
            for line in out.splitlines():
                if line.strip():
                    print(f"    {line.rstrip()}")
        return ok
    except Exception as e:
        print(f"  ERR running CoA bootstrap: {e}")
        return False


def docker_nuke(*, transactions=True, items=True, parties=True, accounts=True):
    """Run frappe.db.delete inside the backend container for a true wipe.
    Returns True on success, False if docker isn't usable (caller should fall
    back to the REST-only path). Scope flags forwarded to _build_nuke_script."""
    if not _docker_available():
        print(f"  Docker container {DOCKER_CONTAINER!r} not reachable — skipping bench nuke.")
        return False

    scope = ",".join(s for s, f in [("transactions", transactions),
                                    ("items", items),
                                    ("parties", parties),
                                    ("accounts", accounts)] if f)
    print(f"\n=== Bench nuke via docker (scope: {scope}) ===")
    script = _build_nuke_script(COMPANY, transactions=transactions, items=items,
                                parties=parties, accounts=accounts)
    try:
        # frappe.init() resolves the site relative to CWD, so we must cd into
        # the `sites` directory (where the per-site folder lives) before
        # invoking python.
        r = subprocess.run(
            ["docker", "exec", "-i", DOCKER_CONTAINER, "sh", "-c",
             "cat > /tmp/tally_nuke.py && "
             "cd /home/frappe/frappe-bench/sites && "
             "/home/frappe/frappe-bench/env/bin/python /tmp/tally_nuke.py"],
            input=script, text=True, capture_output=True, timeout=600,
        )
        out = (r.stdout or "") + "\n" + (r.stderr or "")
        ok = "NUKE_DONE" in out
        if ok:
            for line in out.splitlines():
                if line.strip().startswith("- "):
                    print(f"  {line.rstrip()}")
        else:
            # Surface the full failure — caller decides whether to fall back.
            print("  Bench script failed. Output:")
            for line in out.splitlines():
                if line.strip():
                    print(f"    {line.rstrip()}")
        return ok
    except Exception as e:
        print(f"  ERR running bench nuke: {e}")
        return False


def reset_items():
    """Delete transactions + items + their cache records.
    Tries docker-bench first (handles submitted SLE/GLE), falls back to REST."""
    if docker_nuke(transactions=True, items=True, parties=False, accounts=False):
        return
    print("\n=== REST fallback ===")
    clear_transactions()
    purge_ledger_records()
    print("\n=== Resetting items ===")
    for doctype in ("Item Tax Template", "Item"):
        print(f"\n--- {doctype} ---")
        delete_all_of(doctype)


def reset_full():
    """Nuclear reset. Prefers docker_nuke (true wipe); falls back to REST.

    REST-only order is load-bearing:
      1. transactions     — must die before their ledger entries cascade
      2. ledger records   — block Item/Account/Party deletion
      3. items
      4. Address/Contact  — Dynamic Link rows point AT Customer/Supplier
      5. Customer/Supplier
      6. Bank Account     — has account=<GL Account> link
      7. Account / Item Group — trees, leaves first (multi-pass)
    """
    if docker_nuke(transactions=True, items=True, parties=True, accounts=True):
        return

    print("\n=== Falling back to REST-only reset (limited — submitted docs may remain) ===")
    clear_transactions()
    purge_ledger_records()
    print("\n=== Resetting items ===")
    for doctype in ("Item Tax Template", "Item"):
        print(f"\n--- {doctype} ---")
        delete_all_of(doctype)
    print("\n=== Resetting master data ===")
    for doctype in ("Address", "Contact",
                    "Customer", "Supplier",
                    "Bank Account"):
        print(f"\n--- {doctype} ---")
        delete_all_of(doctype)
    for doctype in ("Account", "Item Group"):
        print(f"\n--- {doctype} (tree, multi-pass) ---")
        delete_all_of(doctype, max_passes=10)

def ensure_payment_terms():
    """
    Create 'Net 0' payment terms template so due_date = posting_date.
    Fixes "Due Date cannot be before Posting Date" when importing backdated invoices.
    """
    if api_exists("Payment Terms Template", "Net 0"):
        return "Net 0"
    if not api_exists("Payment Term", "Net 0"):
        api_post("Payment Term", {
            "payment_term_name": "Net 0",
            "invoice_portion": 100.0,
            "credit_days_based_on": "Day(s) after invoice date",
            "credit_days": 0,
        })
    api_post("Payment Terms Template", {
        "template_name": "Net 0",
        "terms": [{
            "payment_term": "Net 0",
            "invoice_portion": 100.0,
            "credit_days_based_on": "Day(s) after invoice date",
            "credit_days": 0,
        }]
    })
    print("  Created: Net 0 payment terms")
    return "Net 0"

def ensure_walkin_customer():
    """Create a generic Walk-in Customer for anonymous counter sales."""
    if not api_exists("Customer", "Walk-in Customer"):
        api_post("Customer", {
            "customer_name": "Walk-in Customer",
            "customer_type": "Individual",
            "customer_group": "Commercial",
            "territory": "India",
        })
        print("  Created: Walk-in Customer")

def ensure_upi_mode():
    """Create UPI mode of payment linked to Net Banking Payment Sales account."""
    upi_acc = f"Net Banking Payment Sales - {ABBR}"
    # Create the ledger account if master migration didn't create it
    if not api_exists("Account", upi_acc):
        api_post("Account", {
            "account_name": "Net Banking Payment Sales",
            "account_type": "Bank",
            "parent_account": f"Bank Accounts - {ABBR}",
            "company": COMPANY,
            "is_group": 0,
        })
        print(f"  Created account: Net Banking Payment Sales")

    if api_exists("Mode of Payment", "UPI"):
        return
    data = {"mode_of_payment": "UPI", "type": "Bank"}
    if api_exists("Account", upi_acc):
        data["accounts"] = [{"company": COMPANY, "default_account": upi_acc}]
    api_post("Mode of Payment", data)
    print("  Created: UPI mode of payment")

# ── Opening balance helpers ───────────────────────────────────────────────────
def ensure_temporary_opening_account():
    """Ensure Temporary Opening account exists for balancing opening JEs."""
    name = f"Temporary Opening - {ABBR}"
    if name in ACCOUNT_CACHE or api_exists("Account", name):
        ACCOUNT_CACHE.add(name)
        return name
    parent = f"Temporary Accounts - {ABBR}"
    if parent not in ACCOUNT_CACHE and not api_exists("Account", parent):
        parent = f"Temporary Opening - {ABBR}"
    api_post("Account", {
        "account_name": "Temporary Opening",
        "is_group": 0,
        "company": COMPANY,
        "root_type": "Asset",
        "parent_account": f"Application of Funds (Assets) - {ABBR}",
    })
    ACCOUNT_CACHE.add(name)
    return name

def _get_ar_account():
    """Return the Accounts Receivable account for journal entries."""
    for cand in (f"Debtors - {ABBR}", f"Accounts Receivable - {ABBR}",
                 f"Sundry Debtors - {ABBR}"):
        if cand in ACCOUNT_CACHE or api_exists("Account", cand):
            return cand
    return None

def _get_ap_account():
    """Return the Accounts Payable account for journal entries."""
    for cand in (f"Creditors - {ABBR}", f"Accounts Payable - {ABBR}",
                 f"Sundry Creditors - {ABBR}"):
        if cand in ACCOUNT_CACHE or api_exists("Account", cand):
            return cand
    return None

def migrate_opening_balances(root):
    """
    Create is_opening Journal Entries for each party ledger that has a
    non-zero OPENINGBALANCE in Master.xml.

    Tally sign convention (for Sundry Creditors/Debtors):
      - Sundry Creditor + positive balance → company OWES supplier
          Dr: Temporary Opening   Cr: AP account (party = Supplier)
      - Sundry Debtor + positive balance → customer OWES company
          Dr: AR account (party = Customer)   Cr: Temporary Opening
    """
    print("\n=== Opening Balances ===")
    temp_acc = ensure_temporary_opening_account()
    ar_acc   = _get_ar_account()
    ap_acc   = _get_ap_account()
    if not ar_acc:
        print("  WARN: AR account not found, skipping customer opening balances")
    if not ap_acc:
        print("  WARN: AP account not found, skipping supplier opening balances")

    count = 0
    for ledger in root.iter("LEDGER"):
        name   = ledger.get("NAME", "").strip()
        parent = txt(ledger, "PARENT").strip()
        ob_str = txt(ledger, "OPENINGBALANCE").strip()
        if not ob_str or not name:
            continue
        try:
            ob = float(ob_str.replace(",", ""))
        except:
            continue
        if abs(ob) < 0.01:
            continue

        start_str = txt(ledger, "STARTINGFROM").strip()
        ob_date   = tally_date(start_str) if start_str else "2023-04-01"

        if parent == "Sundry Creditors" and ap_acc:
            if not api_exists("Supplier", name):
                continue
            je_data = {
                "doctype": "Journal Entry",
                "posting_date": ob_date,
                "is_opening": "Yes",
                "company": COMPANY,
                "user_remark": f"Opening balance: {name}",
                "accounts": [
                    {
                        "account": temp_acc,
                        "debit_in_account_currency":  abs(ob),
                        "credit_in_account_currency": 0,
                    },
                    {
                        "account": ap_acc,
                        "party_type": "Supplier",
                        "party": name,
                        "debit_in_account_currency":  0,
                        "credit_in_account_currency": abs(ob),
                    },
                ],
            }
            r = api_post("Journal Entry", je_data)
            if r:
                je_name = r.get("name", "")
                if je_name:
                    api_submit("Journal Entry", je_name)
                count += 1
                print(f"  + OB supplier {name}: {abs(ob):,.2f}")

        elif parent == "Sundry Debtors" and ar_acc:
            if not api_exists("Customer", name):
                continue
            je_data = {
                "doctype": "Journal Entry",
                "posting_date": ob_date,
                "is_opening": "Yes",
                "company": COMPANY,
                "user_remark": f"Opening balance: {name}",
                "accounts": [
                    {
                        "account": ar_acc,
                        "party_type": "Customer",
                        "party": name,
                        "debit_in_account_currency":  abs(ob),
                        "credit_in_account_currency": 0,
                    },
                    {
                        "account": temp_acc,
                        "debit_in_account_currency":  0,
                        "credit_in_account_currency": abs(ob),
                    },
                ],
            }
            r = api_post("Journal Entry", je_data)
            if r:
                je_name = r.get("name", "")
                if je_name:
                    api_submit("Journal Entry", je_name)
                count += 1
                print(f"  + OB customer {name}: {abs(ob):,.2f}")

    print(f"  Party opening balance entries: {count}")

    # ── GL account opening balances (banks, cash, fixed assets, capital, etc.) ──
    print("\n--- GL Account Opening Balances ---")
    gl_count = 0
    SKIP_PARENTS = {"Sundry Debtors", "Sundry Creditors", ""}  # already handled above
    P_AND_L_NAME = "Profit & Loss A/c"

    for ledger in root.iter("LEDGER"):
        name   = ledger.get("NAME", "").strip()
        parent = txt(ledger, "PARENT").strip()
        ob_str = txt(ledger, "OPENINGBALANCE").strip()
        if not ob_str or not name or parent in SKIP_PARENTS:
            continue
        try:
            ob = float(ob_str.replace(",", ""))
        except:
            continue
        if abs(ob) < 1:
            continue

        start_str = txt(ledger, "STARTINGFROM").strip()
        ob_date   = tally_date(start_str) if start_str else "2023-04-01"

        # Resolve ERPNext account name
        if name == P_AND_L_NAME:
            # P&L opening goes to Retained Earnings
            acc_erpname = f"Retained Earnings - {ABBR}"
            if acc_erpname not in ACCOUNT_CACHE:
                acc_erpname = f"Reserves and Surplus - {ABBR}"
            if acc_erpname not in ACCOUNT_CACHE:
                continue
        else:
            acc_erpname = f"{name} - {ABBR}"
            if acc_erpname not in ACCOUNT_CACHE:
                continue

        # Tally sign: negative OB = debit balance (assets), positive = credit (liabilities)
        if ob < 0:
            # Asset / debit-normal account: DR account, CR temp opening
            je_accounts = [
                {"account": acc_erpname,
                 "debit_in_account_currency": abs(ob),
                 "credit_in_account_currency": 0},
                {"account": temp_acc,
                 "debit_in_account_currency": 0,
                 "credit_in_account_currency": abs(ob)},
            ]
        else:
            # Liability / credit-normal account: CR account, DR temp opening
            je_accounts = [
                {"account": temp_acc,
                 "debit_in_account_currency": abs(ob),
                 "credit_in_account_currency": 0},
                {"account": acc_erpname,
                 "debit_in_account_currency": 0,
                 "credit_in_account_currency": abs(ob)},
            ]

        r = api_post("Journal Entry", {
            "doctype": "Journal Entry",
            "posting_date": ob_date,
            "is_opening": "Yes",
            "company": COMPANY,
            "user_remark": f"Opening balance: {name}",
            "accounts": je_accounts,
        })
        if r:
            je_name = r.get("name", "")
            if je_name:
                api_submit("Journal Entry", je_name)
            gl_count += 1
            print(f"  + OB GL {name[:40]}: {ob:,.2f}")

    print(f"  GL opening balance entries: {gl_count}")
    print(f"  Total: {count + gl_count} opening balance journal entries")

# ── Counter-sale / payment helpers ────────────────────────────────────────────
def get_buyer_info(vch):
    """
    Extract actual buyer name + GSTIN from the voucher.
    Used when PARTYLEDGERNAME is a payment mode ledger (Cash / Net Banking).
    PARTYMAILINGNAME holds the real customer name in Tally counter sales.
    """
    # PARTYMAILINGNAME is the actual buyer name for counter sales
    for field in ("PARTYMAILINGNAME", "BASICBUYERNAME", "BUYERNAME"):
        val = txt(vch, field).strip()
        # Skip if it's the same as a payment ledger name (not a real person)
        if val and val not in PAYMENT_MODE_LEDGERS and val.upper() not in ("NA", "N/A", ""):
            return val, ""
    return "", ""

def ensure_counter_customer(buyer_name, gstin=""):
    """Return existing customer or create a new one for a counter sale buyer."""
    if not buyer_name:
        return "Walk-in Customer"
    if api_exists("Customer", buyer_name):
        return buyer_name
    data = {
        "customer_name": buyer_name,
        "customer_type": "Individual",
        "customer_group": "Commercial",
        "territory": "India",
    }
    if gstin:
        data["tax_id"] = gstin
    r = api_post("Customer", data)
    if r:
        print(f"  + counter customer: {buyer_name}")
        return buyer_name
    return "Walk-in Customer"

def detect_payments(vch, vtype, narr):
    """
    Analyse a sales voucher and return a list of (mode, amount) tuples.

    mode values:
      "Cash"    – paid in cash
      "UPI"     – paid via net banking / UPI / online (On Line)
      "Credit"  – not yet paid; customer will pay later via RTGS / cheque

    Logic (in priority order):
    1. BASICORDERTERMS = "On Line" / "ONLINE" / "online" → UPI
    2. BASICDUEDATEOFPYMT tells payment mode: "Cash" or "Debit"
    3. Scan ALLLEDGERENTRIES.LIST for Cash / Net Banking ledger names.
    4. Fall back to voucher type name ("CASH" → Cash, "DEBIT" → check online else Credit)
    """
    # Check Tally's explicit payment mode fields first
    order_terms = txt(vch, "BASICORDERTERMS").strip()        # "On Line", "Cash", etc.
    due_mode    = txt(vch, "BASICDUEDATEOFPYMT").strip()     # "Debit", "Cash", etc.
    is_online   = bool(ONLINE_PATTERN.search(order_terms)) or bool(ONLINE_PATTERN.search(narr or ""))

    # Scan ledger entries for cash / net-banking payment amounts
    cash_total = 0.0
    upi_total  = 0.0

    for leg in vch.iter("ALLLEDGERENTRIES.LIST"):
        lname = (txt(leg, "LEDGERNAME") or "").strip()
        lname_lower = lname.lower()
        try:
            lamt = abs(float((txt(leg, "AMOUNT") or "0").strip() or "0"))
        except:
            lamt = 0.0
        if lamt == 0:
            continue

        if lname_lower == "cash" or lname_lower.startswith("cash "):
            cash_total += lamt
        elif "net banking" in lname_lower or "upi" in lname_lower:
            upi_total += lamt
        elif ONLINE_PATTERN.search(lname):
            upi_total += lamt

    payments = []
    if cash_total > 0:
        payments.append(("Cash", cash_total))
    if upi_total > 0:
        payments.append(("UPI", upi_total))

    # Fallback: nothing explicit in entries → use Tally mode fields or voucher type
    if not payments:
        total = ledger_total(vch)
        if total == 0:
            return []
        vtype_lower = vtype.lower()
        if "cash" in vtype_lower or due_mode.lower() == "cash":
            payments.append(("Cash", total))
        elif "debit" in vtype_lower or due_mode.lower() == "debit":
            if is_online:
                payments.append(("UPI", total))
            else:
                payments.append(("Credit", total))  # pending RTGS / not yet paid
        # "GST TAX INVOICE" (no mode) → credit sale, no payment entry

    return payments

def create_payment_for_si(si_name, customer, mode, amount, vdate):
    """
    Create a Payment Entry (Receive) linked to a submitted Sales Invoice.
    Returns the created doc dict or None.
    """
    if mode == "Cash":
        paid_to = f"Cash - {ABBR}"
        mop = "Cash"
    elif mode == "UPI":
        paid_to = f"Net Banking Payment Sales - {ABBR}"
        mop = "UPI"
    else:
        return None  # Credit / pending: leave invoice as outstanding

    if paid_to not in ACCOUNT_CACHE and not api_exists("Account", paid_to):
        print(f"  SKIP PE: account {paid_to!r} not found")
        return None

    data = {
        "doctype": "Payment Entry",
        "payment_type": "Receive",
        "posting_date": vdate,
        "company": COMPANY,
        "paid_amount": amount,
        "received_amount": amount,
        "party_type": "Customer",
        "party": customer,
        "paid_to": paid_to,
        "mode_of_payment": mop,
        "references": [{
            "reference_doctype": "Sales Invoice",
            "reference_name": si_name,
            "allocated_amount": amount,
        }]
    }
    # Bank transactions require a reference number
    if mode == "UPI":
        data["reference_no"]   = si_name
        data["reference_date"] = vdate
    result = api_post("Payment Entry", data)
    if result:
        pe_name = result.get("name", "")
        if pe_name:
            api_submit("Payment Entry", pe_name)
    return result

# ── Bank / Cash account type map ─────────────────────────────────────────────
# Tally parent group → ERPNext account_type
TALLY_ACCOUNT_TYPE = {
    "Bank Accounts": "Bank",
    "Bank OD A/c":   "Bank",
    "Cash-in-Hand":  "Cash",
    "Sundry Debtors":   "Receivable",
    "Sundry Creditors": "Payable",
    "Duties & Taxes":   "Tax",
}

def _clean_bank_name(account_name):
    """Extract a short bank name from a Tally account name."""
    name = re.sub(r'\s*-\s*AMS$', '', account_name, flags=re.IGNORECASE).strip()
    name = re.sub(r'\s*\(.*?\)', '', name).strip()   # strip "(A/c 17412)" etc.
    name = re.sub(r'\s+(C/a|O\.D\.|Ltd|Ltd\.)$', '', name, flags=re.IGNORECASE).strip()
    return name or account_name

def _ensure_bank_master(bank_name):
    """Create a Bank master if it doesn't exist."""
    if api_exists("Bank", bank_name):
        return bank_name
    api_post("Bank", {"bank_name": bank_name})
    return bank_name

def _ensure_account_is_group(acc_name):
    """
    Convert an existing ledger account into a group so children can be created
    under it. ERPNext rejects 'Parent account ... can not be a ledger' otherwise.
    Safe no-op if the account is already a group or doesn't exist.
    """
    url = f"{ERPNEXT_URL}/api/resource/Account/{requests.utils.quote(acc_name)}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return
        is_group = r.json().get("data", {}).get("is_group", 0)
        if is_group:
            return
        # Convert ledger → group. Only works if the account has no GL entries yet,
        # which is the case in pass-1 (ledgers run before transactions).
        requests.put(url, headers=HEADERS,
                     json={"data": {"is_group": 1}}, timeout=15)
    except Exception:
        pass


def _collect_leaf_accounts(parent_acc, acc_type, results, seen):
    """
    Recursively collect all non-group (leaf) accounts under parent_acc.
    Tally sometimes creates sub-groups like 'Axis Bank' under 'Bank Accounts',
    with the actual leaf 'Axis Current A/c' one level deeper.
    A flat parent_account= query misses those; this traversal catches them all.
    """
    r = requests.get(
        f"{ERPNEXT_URL}/api/resource/Account",
        headers=HEADERS,
        params={
            "filters": json.dumps([
                ["company", "=", COMPANY],
                ["parent_account", "=", parent_acc],
            ]),
            "fields": '["name","account_name","is_group"]',
            "limit_page_length": 200,
        },
        timeout=30,
    )
    if r.status_code != 200:
        return
    for acc in r.json().get("data", []):
        if acc["name"] in seen:
            continue
        seen.add(acc["name"])
        if acc.get("is_group"):
            _collect_leaf_accounts(acc["name"], acc_type, results, seen)
        else:
            results.append((acc["name"], acc["account_name"], acc_type))

def migrate_bank_accounts():
    """
    1. Set account_type='Bank'/'Cash' on every ledger account that was
       created without it (Tally doesn't export account_type explicitly).
    2. Create Bank master + Bank Account for every bank GL account.
    Recurses through sub-groups so nested accounts (e.g. Axis Bank → leaf)
    are not missed.
    """
    print("\n=== Bank Accounts ===")

    all_accounts = []
    seen = set()
    for top_parent, acc_type in [
        (f"Bank Accounts - {ABBR}", "Bank"),
        (f"Bank OD A/c - {ABBR}",   "Bank"),
        (f"Cash-in-Hand - {ABBR}",  "Cash"),
    ]:
        _collect_leaf_accounts(top_parent, acc_type, all_accounts, seen)

    # Also pick up any Cash accounts already typed (avoids re-calling API for each)
    r = requests.get(
        f"{ERPNEXT_URL}/api/resource/Account",
        headers=HEADERS,
        params={
            "filters": json.dumps([
                ["company", "=", COMPANY],
                ["account_type", "=", "Cash"],
                ["is_group", "=", 0],
            ]),
            "fields": '["name","account_name"]',
            "limit_page_length": 50,
        },
        timeout=30,
    )
    if r.status_code == 200:
        for acc in r.json().get("data", []):
            if acc["name"] not in seen:
                seen.add(acc["name"])
                all_accounts.append((acc["name"], acc["account_name"], "Cash"))

    created_bank_accounts = 0
    for acc_full, acc_name, acc_type in all_accounts:
        # Step 1: update account_type if not already set
        r = requests.put(
            f"{ERPNEXT_URL}/api/resource/Account/{requests.utils.quote(acc_full)}",
            headers=HEADERS,
            json={"data": {"account_type": acc_type}},
            timeout=15,
        )
        if r.status_code not in (200, 201):
            print(f"  WARN update account_type {acc_full}: {r.text[:100]}")

        if acc_type != "Bank":
            continue  # Cash accounts don't need Bank Account records

        # Step 2: create Bank Account record
        bank_name = _clean_bank_name(acc_full)
        _ensure_bank_master(bank_name)

        ba_data = {
            "doctype": "Bank Account",
            "account_name": acc_name,
            "account": acc_full,
            "bank": bank_name,
            "is_company_account": 1,
            "company": COMPANY,
        }
        result = api_post("Bank Account", ba_data)
        if result:
            created_bank_accounts += 1
            print(f"  + Bank Account: {acc_name} → {bank_name}")

    print(f"  Done. {created_bank_accounts} Bank Account records created.")

# ── 1. UOM ───────────────────────────────────────────────────────────────────
def migrate_uom(root):
    print("\n=== UOM ===")
    done = set()
    for unit in root.iter("UNIT"):
        name = unit.get("NAME", "").strip()
        if not name or name in done:
            continue
        done.add(name)
        if api_exists("UOM", name):
            print(f"  skip {name}")
            continue
        api_post("UOM", {"uom_name": name, "must_be_whole_number": 0})
        print(f"  + {name}")

# ── 2. Account Groups ────────────────────────────────────────────────────────
def migrate_groups(root):
    print("\n=== Account Groups ===")
    done = set()
    for grp in root.iter("GROUP"):
        name = grp.get("NAME", "").strip()
        if not name or name in done:
            continue
        done.add(name)

        acc_name = f"{name} - {ABBR}"
        if api_exists("Account", acc_name):
            print(f"  skip {name}")
            continue

        tally_parent = txt(grp, "PARENT").strip()
        if tally_parent and tally_parent in TALLY_GROUP_MAP:
            parent_acc = f"{tally_parent} - {ABBR}"
            root_type  = TALLY_GROUP_MAP[tally_parent][1]
        elif name in TALLY_GROUP_MAP:
            parent_name, root_type = TALLY_GROUP_MAP[name]
            parent_acc = f"{parent_name} - {ABBR}"
        else:
            print(f"  SKIP (no parent mapping): {name}")
            continue

        if not api_exists("Account", parent_acc):
            print(f"  SKIP (parent not found '{parent_acc}'): {name}")
            continue

        data = {
            "doctype": "Account",
            "account_name": name,
            "is_group": 1,
            "company": COMPANY,
            "root_type": root_type,
            "parent_account": parent_acc,
        }
        api_post("Account", data)
        print(f"  + {name}")

# ── 3. Ledgers → Accounts / Customers / Suppliers ────────────────────────────
def _extract_party_info(ledger):
    """Pull name, GSTIN, GST category, and address from a LEDGER element."""
    name   = ledger.get("NAME", "").strip()
    gstin  = txt(ledger, "PARTYGSTIN").strip()
    if not gstin:
        node = ledger.find("GSTREGISTRATIONDETAILS.LIST")
        if node is not None:
            gstin = txt(node, "GSTIN").strip()

    gst_reg = txt(ledger, "GSTREGISTRATIONTYPE").strip()
    GST_CAT_MAP = {
        "Regular":        "Registered Regular",
        "Composition":    "Registered Composition",
        "Unregistered":   "Unregistered",
        "Consumer":       "Consumer",
        "Overseas":       "Overseas",
        "SEZ":            "SEZ",
        "Deemed Export":  "Deemed Export",
    }
    gst_category = GST_CAT_MAP.get(gst_reg, "")

    # Address
    addr_parts = []
    for adr in ledger.iter("ADDRESS.LIST"):
        for line in adr.findall("ADDRESS"):
            v = (line.text or "").strip()
            if v:
                addr_parts.append(v)
    state   = txt(ledger, "STATENAME").strip()
    pincode = txt(ledger, "PINCODE").strip()
    email   = txt(ledger, "EMAIL").strip()
    phone   = (txt(ledger, "LEDGERPHONE") or txt(ledger, "PHONENUMBER")).strip()
    pan     = txt(ledger, "INCOMETAXNUMBER").strip()

    return {
        "name": name, "gstin": gstin, "gst_category": gst_category,
        "address": addr_parts, "state": state, "pincode": pincode,
        "email": email, "phone": phone, "pan": pan,
    }

GSTIN_STATE_MAP = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab",
    "04": "Chandigarh", "05": "Uttarakhand", "06": "Haryana",
    "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh",
    "13": "Nagaland", "14": "Manipur", "15": "Mizoram",
    "16": "Tripura", "17": "Meghalaya", "18": "Assam",
    "19": "West Bengal", "20": "Jharkhand", "21": "Odisha",
    "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "25": "Dadra and Nagar Haveli and Daman and Diu",
    "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra", "28": "Andhra Pradesh", "29": "Karnataka",
    "30": "Goa", "31": "Lakshadweep", "32": "Kerala",
    "33": "Tamil Nadu", "34": "Puducherry", "35": "Andaman and Nicobar Islands",
    "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh",
    "97": "Other Territory", "99": "Centre Jurisdiction",
}

def _state_from_gstin(gstin):
    """Map GSTIN's first 2 digits → state name; india_compliance validates this."""
    g = (gstin or "").strip().upper()
    if len(g) >= 2 and g[:2].isdigit():
        return GSTIN_STATE_MAP.get(g[:2])
    return None


def _create_address(party_name, link_doctype, info):
    """Create an Address record and link it to the party."""
    if not any([info["address"], info["state"], info["pincode"], info["gstin"]]):
        return
    addr_line1 = info["address"][0] if info["address"] else ""
    addr_line2 = ", ".join(info["address"][1:]) if len(info["address"]) > 1 else ""
    # GSTIN's first 2 digits MUST match the state — india_compliance enforces this.
    # When a GSTIN is present, derive state from it (ignore Tally's STATENAME).
    state = _state_from_gstin(info.get("gstin")) or info["state"] or "Gujarat"
    data = {
        "doctype": "Address",
        "address_title": party_name,
        "address_type": "Billing",
        "address_line1": addr_line1 or party_name,
        "address_line2": addr_line2,
        "city": state,
        "state": state,
        "pincode": info["pincode"],
        "country": "India",
        "gstin": info["gstin"],
        "links": [{"link_doctype": link_doctype, "link_name": party_name}],
    }
    api_post("Address", data)

def migrate_ledgers(root):
    print("\n=== Ledgers ===")
    customers, suppliers = [], []
    for ledger in root.iter("LEDGER"):
        info   = _extract_party_info(ledger)
        name   = info["name"]
        parent = txt(ledger, "PARENT")
        if not name:
            continue

        if parent == "Sundry Debtors":
            customers.append(info)
        elif parent == "Sundry Creditors":
            suppliers.append(info)
        else:
            acc_name = f"{name} - {ABBR}"
            if api_exists("Account", acc_name):
                continue
            parent_acc = f"{parent} - {ABBR}" if parent else None
            root_type = "Asset"
            if parent in TALLY_GROUP_MAP:
                root_type = TALLY_GROUP_MAP[parent][1]
            data = {
                "doctype": "Account",
                "account_name": name,
                "is_group": 0,
                "company": COMPANY,
                "root_type": root_type,
            }
            if parent in TALLY_ACCOUNT_TYPE:
                data["account_type"] = TALLY_ACCOUNT_TYPE[parent]
            if parent_acc and api_exists("Account", parent_acc):
                _ensure_account_is_group(parent_acc)
                data["parent_account"] = parent_acc
            else:
                continue
            api_post("Account", data)
            print(f"  + account: {name}")

    print(f"\n=== Customers ({len(customers)}) ===")
    for c in customers:
        if api_exists("Customer", c["name"]):
            print(f"  skip {c['name']}")
            continue
        data = {
            "customer_name": c["name"],
            "customer_type": "Company",
            "customer_group": "Commercial",
            "territory": "India",
        }
        if c["gstin"]:
            data["tax_id"] = c["gstin"]
        if c["gst_category"]:
            data["gst_category"] = c["gst_category"]
        r = api_post("Customer", data)
        if r:
            _create_address(c["name"], "Customer", c)
        print(f"  + {c['name']}")

    print(f"\n=== Suppliers ({len(suppliers)}) ===")
    for s in suppliers:
        if api_exists("Supplier", s["name"]):
            print(f"  skip {s['name']}")
            continue
        data = {
            "supplier_name": s["name"],
            "supplier_type": "Company",
            "supplier_group": "Local",
        }
        if s["gstin"]:
            data["tax_id"] = s["gstin"]
        if s["gst_category"]:
            data["gst_category"] = s["gst_category"]
        r = api_post("Supplier", data)
        if r:
            _create_address(s["name"], "Supplier", s)
        print(f"  + {s['name']}")

# ── HSN extractor ─────────────────────────────────────────────────────────────
# Indian HSN codes are 4, 6, or 8 digits. The original regex was tyre-only
# (Chapter 40), which silently dropped HSNs for valves (8481…), sensors
# (9026…), inflators (8414), patches (4016/4014), etc. — those items then
# failed Item creation with MandatoryError because india_compliance requires
# gst_hsn_code on every Item. The pattern below matches any plausible HSN,
# including ones wrapped in parens like "VALVE ( 84818090 )".
_HSN_RE = re.compile(r"(?<!\d)(\d{4}(?:\s*\d{2}){0,2})(?!\d)")

def extract_hsn(text):
    """Pull an HSN code from a name/group like 'MRF TYRE (CAR) 4011 10 10' or
    'VALVE ( 84818090 )' → '40111010' / '84818090'.
    Returns the longest match found, padded to 8 digits."""
    if not text:
        return ""
    best = ""
    for m in _HSN_RE.finditer(text):
        cand = re.sub(r"\s", "", m.group(1))
        # Prefer the longest valid HSN we can find in the string
        if len(cand) > len(best):
            best = cand
    return best.ljust(8, "0")[:8] if best else ""


# Tally item names carry trailing tax-rate noise like "(18%)" / "(28 %)" that
# is meaningless in ERPNext (rate comes from item_tax_template). We strip it
# at every entry point — both when CREATING the Item and when LOOKING UP the
# item_code from voucher INVENTORY entries — so the cache key stays consistent.
_TAX_SUFFIX_RE   = re.compile(r"\(\s*\d+(?:\.\d+)?\s*%\s*\)")
_WHITESPACE_RE   = re.compile(r"\s+")
_TUBE_ITEM_RE    = re.compile(r"(?<!LESS\s)\bTUBE\b(?!\s*LESS)", re.IGNORECASE)
_TYRE_ITEM_RE    = re.compile(r"\b(TYRE|TIRE|TYBE)\b", re.IGNORECASE)
_FLAP_ITEM_RE    = re.compile(r"\bFLAP\b", re.IGNORECASE)
_SERVICE_ITEM_RE = re.compile(
    r"\b(LABOU?R|FITTING|ALIGN?MENT|ALINGMENT|BALANCING|PUNCTURE)\b",
    re.IGNORECASE,
)

def sanitize_item_name(name):
    """Strip Tally cruft from a stock-item name. Idempotent."""
    if not name:
        return ""
    n = _TAX_SUFFIX_RE.sub("", name)
    n = _WHITESPACE_RE.sub(" ", n).strip()
    return n


def preferred_item_group(item_name, source_group=""):
    """Route common tyre accessories/services into stable top-level groups."""
    source_bucket = item_group_bucket(source_group)
    if source_bucket and source_group and source_group != "All Item Groups":
        return source_group

    item_bucket = item_group_bucket(item_name)
    if item_bucket:
        return item_bucket

    return source_group or "All Item Groups"


def item_group_bucket(name):
    """Return the top-level bucket for a stock item/group name, if obvious."""
    if _FLAP_ITEM_RE.search(name or ""):
        return "Flaps"
    if _TUBE_ITEM_RE.search(name or "") and not _TYRE_ITEM_RE.search(name or ""):
        return "Tubes"
    if _SERVICE_ITEM_RE.search(name or ""):
        return "Services"
    return ""


def ensure_item_group(name, parent="All Item Groups", is_group=1):
    if api_exists("Item Group", name):
        return True
    return bool(api_post("Item Group", {
        "item_group_name": name,
        "parent_item_group": parent,
        "is_group": is_group,
    }))


# Cache HSN existence checks across the run. Negative results aren't cached
# (we either succeed in creating, or we log and skip — no repeated probes).
HSN_CACHE: set = set()


def ensure_hsn(hsn):
    """Make sure a GST HSN Code exists; create it if missing.
    Returns the code on success, "" if it couldn't be created (caller should
    drop gst_hsn_code from the Item payload to avoid a LinkValidationError)."""
    if not hsn:
        return ""
    if hsn in HSN_CACHE:
        return hsn
    if api_exists("GST HSN Code", hsn):
        HSN_CACHE.add(hsn)
        log_hsn("EXISTS", hsn)
        return hsn
    r = api_post("GST HSN Code", {
        "hsn_code": hsn,
        "description": "Auto-created from Tally migration",
    })
    if r:
        HSN_CACHE.add(hsn)
        log_hsn("CREATED", hsn)
        return hsn
    log_hsn("FAILED", hsn, note="see migration_errors.log")
    return ""

# ── 4. Stock Items → ERPNext Items ───────────────────────────────────────────
def migrate_items(root):
    print("\n=== Item Groups ===")
    done = set()
    group_hsn = {}
    for name in ("Tubes", "Flaps", "Services"):
        if ensure_item_group(name):
            print(f"  + ensured group: {name}")
    for sg in root.iter("STOCKGROUP"):
        name = sg.get("NAME", "").strip()
        if not name or name in done:
            continue
        done.add(name)
        hsn = extract_hsn(name)
        if hsn:
            group_hsn[name] = hsn
        if api_exists("Item Group", name):
            continue
        parent = txt(sg, "PARENT") or "All Item Groups"
        parent = item_group_bucket(name) or parent
        if not api_exists("Item Group", parent):
            parent = "All Item Groups"
        api_post("Item Group", {"item_group_name": name, "parent_item_group": parent})
        print(f"  + group: {name}")

    print("\n=== Items ===")
    for item in root.iter("STOCKITEM"):
        raw_name = item.get("NAME", "").strip()
        name = sanitize_item_name(raw_name)
        if not name:
            continue
        if api_exists("Item", name):
            print(f"  skip {name}")
            continue
        source_group = txt(item, "PARENT") or "All Item Groups"
        group = preferred_item_group(name, source_group)
        _uom_raw = (txt(item, "BASEUNITS") or "Nos").strip()
        _UOM_MAP = {
            "NOS": "Nos", "NO": "Nos", "PCS": "Nos", "PIECE": "Nos", "PIECES": "Nos",
            "KGS": "Kg", "KG": "Kg", "KILO": "Kg",
            "LTR": "Ltr", "LITRE": "Ltr", "LITER": "Ltr",
            "MTR": "Meter", "METER": "Meter", "METRES": "Meter",
            "SET": "Set",
            "BOX": "Box",
        }
        uom = _UOM_MAP.get(_uom_raw.upper(), "Nos")
        rate  = tally_amount(txt(item, "LASTPURCHASECOST") or "0")

        hsn = (txt(item, "HSNDETAILS.LIST/HSNCODE") or
               txt(item, "HSN") or
               group_hsn.get(source_group, "")).strip()
        hsn = re.sub(r'\s', '', hsn)[:8]
        # Auto-create the HSN code if india_compliance hasn't preinstalled it;
        # ensure_hsn returns "" if creation failed so we drop the field safely.
        if hsn:
            hsn = ensure_hsn(hsn)

        data = {
            "item_name": name,
            "item_code": name,
            "item_group": group if api_exists("Item Group", group) else "All Item Groups",
            "stock_uom": uom,
            "is_stock_item": 1,
            "standard_rate": rate,
            "uoms": [{"uom": uom, "conversion_factor": 1}],
        }
        if hsn:
            data["gst_hsn_code"] = hsn
        api_post("Item", data)
        print(f"  + {name}")

# ── 5. Vouchers → Transactions (two-pass) ─────────────────────────────────────
SALES_TYPES = {
    "Sales", "Sales Invoice",
    "GST TAX INVOICE CASH", "GST TAX INVOICE DEBIT", "GST TAX INVOICE",
    "GST SERVICE DEBIT INVOICE", "GST SERVICE CASH INVOICE",
}
PURCHASE_TYPES = {"Purchase", "Purchase Invoice"}
PAYMENT_TYPES  = {"Payment", "Receipt"}
JOURNAL_TYPES  = {"Journal", "Contra", "Credit Note", "Debit Note"}

def _is_igst(taxes):
    """Return True if any tax row uses an IGST account (inter-state transaction)."""
    return any("igst" in t.get("account_head", "").lower() for t in taxes)

_GSTIN_RE = re.compile(r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$')

def _gst_invoice_fields(party_gstin, taxes, is_purchase=False):
    """Return GST-specific fields for Sales/Purchase Invoice payloads."""
    gstin = (party_gstin or "").strip().upper()
    has_valid_gstin = bool(gstin and _GSTIN_RE.match(gstin))
    gst_category = "Registered Regular" if has_valid_gstin else "Unregistered"
    # For inter-state (IGST), ERPNext resolves place_of_supply from party address;
    # for intra-state (CGST+SGST) default to the company's own state.
    place = None if _is_igst(taxes) else COMPANY_STATE
    fields = {"gst_category": gst_category}
    if place:
        fields["place_of_supply"] = place
    return fields

def _make_je_accounts(vch):
    """Build Journal Entry account rows from ALLLEDGERENTRIES, skipping unknown accounts."""
    rows = []
    for leg in vch.iter("ALLLEDGERENTRIES.LIST"):
        lname = txt(leg, "LEDGERNAME")
        if not lname:
            continue
        acc = f"{lname} - {ABBR}"
        if acc not in ACCOUNT_CACHE:
            continue
        try:
            amt = float((txt(leg, "AMOUNT") or "0").strip() or "0")
        except:
            amt = 0.0
        rows.append({
            "account": acc,
            "debit_in_account_currency":  abs(amt) if amt < 0 else 0,
            "credit_in_account_currency": amt       if amt > 0 else 0,
        })
    return rows

def _pass1_invoices(root, counts):
    """Pass 1: create Sales + Purchase invoices; populate BILL_REF_MAP."""
    for vch in root.iter("VOUCHER"):
        vtype = txt(vch, "VOUCHERTYPENAME")
        vno   = txt(vch, "VOUCHERNUMBER")
        vdate = tally_date(txt(vch, "DATE"))
        party = txt(vch, "PARTYLEDGERNAME")
        narr  = txt(vch, "NARRATION")
        if not vdate:
            counts["skip"] += 1
            continue

        # ── Sales Invoice ────────────────────────────────────────────────────
        if vtype in SALES_TYPES:
            cust_gstin = ""
            if party in PAYMENT_MODE_LEDGERS:
                buyer_name, cust_gstin = get_buyer_info(vch)
                customer = ensure_counter_customer(buyer_name, cust_gstin)
            elif party and api_exists("Customer", party):
                customer = party
            else:
                counts["skip"] += 1
                continue

            items = inventory_items(vch)
            if not items:
                total = ledger_total(vch)
                items = [{"item_code": "Services", "qty": 1, "rate": total,
                          "_tyre_numbers": []}]

            # Narration fallback: when inventory extraction found no tyre serials,
            # try to pull them from the voucher-level NARRATION (already in `narr`).
            # Tyre serials in narration are comma/semicolon/slash/newline separated.
            _GENERIC_TOKENS = {
                "primary batch", "not applicable", "n/a", "na", "none",
                "default", "default batch", "primary", "batch",
            }
            narr_serials = []
            if narr:
                narr_serials = [n.strip() for n in re.split(r'[,;\n/]+', narr)
                                if n.strip() and n.strip().lower() not in _GENERIC_TOKENS]

            if narr_serials:
                tyre_items = [it for it in items if it.get("item_code") != "Services"]
                total_needed = sum(int(it.get("qty", 1)) for it in tyre_items)
                # Only apply when narration count matches total qty needed (exact or
                # has exactly enough tokens); avoids mis-assigning for non-tyre narrations.
                if len(narr_serials) >= total_needed:
                    serial_pool = iter(narr_serials)
                    for it in tyre_items:
                        if not it.get("_tyre_numbers"):
                            qty = int(it.get("qty", 1))
                            it["_tyre_numbers"] = [next(serial_pool) for _ in range(qty)]

            items, tyre_rows = _build_tyre_numbers(items, vno=vno)

            taxes = extract_gst_taxes(vch, items=items)
            gst_fields = _gst_invoice_fields(cust_gstin, taxes)
            data = {
                "doctype": "Sales Invoice",
                "customer": customer,
                "posting_date": vdate,
                "set_posting_time": 1,
                "payment_terms_template": "Net 0",
                "company": COMPANY,
                "taxes_and_charges": "",
                "items": items,
                "remarks": narr,
                **gst_fields,
            }
            if COMPANY_ADDRESS_NAME:
                data["company_address"] = COMPANY_ADDRESS_NAME
            if taxes:
                data["taxes"] = taxes
            if tyre_rows:
                data["tyre_numbers"] = tyre_rows
            result = api_post("Sales Invoice", data)
            if result:
                si_name = result.get("name", "")
                if si_name:
                    api_submit("Sales Invoice", si_name)
                    register_bill_refs(vch, customer, si_name, "Sales Invoice")
                    # Also register by vno for counter sales that use vno as bill ref
                    if vno:
                        BILL_REF_MAP[(customer, vno)] = ("Sales Invoice", si_name)
                counts["Sales Invoice"] += 1
                print(f"  + SI {vno} {customer}")

                if si_name:
                    payments = detect_payments(vch, vtype, narr)
                    for mode, amt in payments:
                        if mode in ("Cash", "UPI"):
                            pe = create_payment_for_si(si_name, customer, mode, amt, vdate)
                            if pe:
                                counts["Payment Entry"] += 1
                                print(f"    + PE({mode}) {amt:.2f}")

        # ── Purchase Invoice ─────────────────────────────────────────────────
        elif vtype in PURCHASE_TYPES:
            if not party or not api_exists("Supplier", party):
                counts["skip"] += 1
                continue
            items = inventory_items(vch)
            if not items:
                total = ledger_total(vch)
                items = [{"item_code": "Services", "qty": 1, "rate": total}]
            for it in items:
                it.pop("_tyre_numbers", None)  # not needed on Purchase Invoice
            taxes = extract_gst_taxes(vch, items=items)
            # Fetch supplier GSTIN to determine gst_category
            supp_r = requests.get(
                f"{ERPNEXT_URL}/api/resource/Supplier/{requests.utils.quote(party)}",
                headers=HEADERS, timeout=10,
            )
            supp_gstin = ""
            if supp_r.status_code == 200:
                supp_gstin = supp_r.json().get("data", {}).get("tax_id", "")
            gst_fields = _gst_invoice_fields(supp_gstin, taxes, is_purchase=True)
            gstin_clean = (supp_gstin or "").strip().upper()
            data = {
                "doctype": "Purchase Invoice",
                "supplier": party,
                "posting_date": vdate,
                "set_posting_time": 1,
                "due_date": vdate,
                "company": COMPANY,
                "bill_no": vno,
                "bill_date": vdate,
                "taxes_and_charges": "",
                "items": items,
                "remarks": narr,
                **gst_fields,
            }
            if gstin_clean and _GSTIN_RE.match(gstin_clean):
                data["supplier_gstin"] = gstin_clean
            if COMPANY_ADDRESS_NAME:
                data["company_address"] = COMPANY_ADDRESS_NAME
            if taxes:
                data["taxes"] = taxes
            result = api_post("Purchase Invoice", data)
            if result:
                pi_name = result.get("name", "")
                if pi_name:
                    api_submit("Purchase Invoice", pi_name)
                    register_bill_refs(vch, party, pi_name, "Purchase Invoice")
                    if vno:
                        BILL_REF_MAP[(party, vno)] = ("Purchase Invoice", pi_name)
                counts["Purchase Invoice"] += 1
                print(f"  + PI {vno} {party}")

def _pass2_payments(root, counts):
    """Pass 2: create Payment Entries (linked to invoices) + Journal/Contra entries."""
    for vch in root.iter("VOUCHER"):
        vtype = txt(vch, "VOUCHERTYPENAME")
        vno   = txt(vch, "VOUCHERNUMBER")
        vdate = tally_date(txt(vch, "DATE"))
        party = txt(vch, "PARTYLEDGERNAME")
        narr  = txt(vch, "NARRATION")
        if not vdate:
            return

        # ── Payment / Receipt ────────────────────────────────────────────────
        if vtype in PAYMENT_TYPES:
            is_payment = vtype == "Payment"
            ptype      = "Pay" if is_payment else "Receive"
            party_type = "Supplier" if is_payment else "Customer"
            party_exists = party and api_exists(party_type, party)

            # Find the bank/cash account and its amount
            bank_acc, bank_amount = "", 0.0
            for leg in vch.iter("ALLLEDGERENTRIES.LIST"):
                lname = (txt(leg, "LEDGERNAME") or "").strip()
                acc   = f"{lname} - {ABBR}"
                if acc not in ACCOUNT_CACHE:
                    continue
                try:
                    amt = abs(float(txt(leg, "AMOUNT") or "0"))
                except:
                    amt = 0.0
                # Pick the bank/cash leg (not the party leg)
                if lname != party and amt > bank_amount:
                    bank_acc    = acc
                    bank_amount = amt

            amount = bank_amount or ledger_total(vch)
            if amount == 0:
                counts["skip"] += 1
                continue

            # Get UTR / cheque reference from bank allocations
            utr, utr_date, tx_mode = extract_bank_ref(vch)

            if party_exists and amount > 0:
                # Build bill-wise references if available
                refs = build_payment_refs(vch, party, is_payment)

                data = {
                    "doctype": "Payment Entry",
                    "payment_type": ptype,
                    "posting_date": vdate,
                    "company": COMPANY,
                    "paid_amount": amount,
                    "received_amount": amount,
                    "remarks": narr or vno,
                    "party_type": party_type,
                    "party": party,
                }
                # Bank leg account
                if is_payment:
                    if bank_acc:
                        data["paid_from"] = bank_acc
                        if bank_acc in BANK_ACCOUNT_MAP:
                            data["paid_from_account_currency"] = "INR"
                            data["bank_account"] = BANK_ACCOUNT_MAP[bank_acc]
                else:
                    if bank_acc:
                        data["paid_to"] = bank_acc
                        if bank_acc in BANK_ACCOUNT_MAP:
                            data["paid_to_account_currency"] = "INR"
                            data["bank_account"] = BANK_ACCOUNT_MAP[bank_acc]

                # UTR / cheque reference (mandatory for bank transactions)
                if utr:
                    data["reference_no"]   = utr
                    data["reference_date"] = utr_date or vdate
                elif bank_acc and "bank" in bank_acc.lower():
                    data["reference_no"]   = vno or "N/A"
                    data["reference_date"] = vdate

                if refs:
                    data["references"] = refs

                r = api_post("Payment Entry", data)
                if r:
                    pe_name = r.get("name", "")
                    if pe_name:
                        api_submit("Payment Entry", pe_name)
                    counts["Payment Entry"] += 1
                    ref_info = f" ({len(refs)} invoice refs)" if refs else ""
                    print(f"  + PE {vno} {party}{ref_info}")
            else:
                # Fall back to Journal Entry if no party or amount
                rows = _make_je_accounts(vch)
                if len(rows) >= 2:
                    r = api_post("Journal Entry", {
                        "doctype": "Journal Entry",
                        "posting_date": vdate,
                        "company": COMPANY,
                        "accounts": rows,
                        "user_remark": narr or vno,
                    })
                    if r:
                        counts["Journal Entry"] += 1
                        print(f"  + JE(payment) {vno}")
                else:
                    counts["skip"] += 1

        # ── Journal / Contra / Credit Note / Debit Note ──────────────────────
        elif vtype in JOURNAL_TYPES:
            rows = _make_je_accounts(vch)
            if len(rows) >= 2:
                je_type = "Contra Entry" if vtype == "Contra" else "Journal Entry"
                r = api_post("Journal Entry", {
                    "doctype": "Journal Entry",
                    "voucher_type": je_type,
                    "posting_date": vdate,
                    "company": COMPANY,
                    "accounts": rows,
                    "user_remark": narr or vno,
                })
                if r:
                    counts["Journal Entry"] += 1
                    print(f"  + JE({vtype}) {vno}")
            else:
                counts["skip"] += 1

def migrate_vouchers(root):
    global BILL_REF_MAP
    BILL_REF_MAP = {}
    counts = {
        "Sales Invoice": 0, "Purchase Invoice": 0,
        "Payment Entry": 0, "Journal Entry": 0, "skip": 0,
    }
    print("\n=== Pass 1: Invoices ===")
    _pass1_invoices(root, counts)
    print(f"\n  BILL_REF_MAP entries: {len(BILL_REF_MAP)}")
    print("\n=== Pass 2: Payments & Journals ===")
    _pass2_payments(root, counts)
    print("\n── Migration Summary ──")
    for k, v in counts.items():
        print(f"  {k}: {v}")

# ── Backfill: create missing payments for already-migrated invoices ───────────
def _fetch_outstanding_sales_invoices():
    """Return all submitted Sales Invoices with outstanding_amount > 0.
    Paginated. Fields chosen so we can re-link each SI to its Tally voucher."""
    url = f"{ERPNEXT_URL}/api/resource/Sales Invoice"
    rows = []
    start = 0
    while True:
        params = {
            "filters": json.dumps([
                ["docstatus", "=", 1],
                ["outstanding_amount", ">", 0],
                ["company", "=", COMPANY],
            ]),
            "fields": '["name","customer","remarks","outstanding_amount",'
                      '"grand_total","posting_date"]',
            "limit_page_length": 500,
            "limit_start": start,
        }
        r = requests.get(url, headers=HEADERS, params=params, timeout=60)
        if r.status_code != 200:
            print(f"  WARN: could not fetch Sales Invoices [{r.status_code}]")
            break
        batch = r.json().get("data", [])
        rows.extend(batch)
        if len(batch) < 500:
            break
        start += 500
    return rows


# Pulls the Tally voucher number out of a migrated invoice's remarks, e.g.
#   "GST TAX INVOICE CASH NO - C001"  → "C001"
#   "GST TAX INVOICE NO -165"         → "165"
_REMARK_VNO_RE = re.compile(r'\bNO\b\s*-?\s*([A-Za-z0-9/]+)\s*$', re.IGNORECASE)


def _vno_from_remark(remark):
    m = _REMARK_VNO_RE.search((remark or "").strip())
    return m.group(1).strip() if m else ""


def _build_si_index(rows):
    """Index outstanding SIs for voucher lookup.

    Two keys per invoice (a voucher number may map to either):
      - the SI `name` (counter-sale SIs are named after the Tally voucher, e.g. C001)
      - the trailing voucher token parsed out of `remarks`
    Returns dict: key → list of SI dicts (lists handle the rare key collision,
    disambiguated later by posting_date + grand_total)."""
    index = {}
    def add(key, si):
        if key:
            index.setdefault(key, []).append(si)
    for si in rows:
        add(si["name"], si)
        # Also index by the bare trailing token of the name (handles series
        # prefixes like "LABOUR/D00175" → "D00175").
        if "/" in si["name"]:
            add(si["name"].rsplit("/", 1)[-1], si)
        add(_vno_from_remark(si.get("remarks")), si)
    return index


def _match_si(index, vno, vdate, total):
    """Resolve a Tally voucher to one outstanding SI. Prefers an exact unique
    key hit; disambiguates collisions by grand_total (±1) then posting_date."""
    # Dedupe by name: a single SI can be indexed under several keys (name,
    # series-stripped name, remark token), so the same invoice may appear more
    # than once for one lookup. Collapse those before counting candidates.
    seen, candidates = set(), []
    for c in index.get(vno, []):
        if c["name"] not in seen:
            seen.add(c["name"])
            candidates.append(c)
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        return None
    # Multiple SIs share this key — narrow by amount, then date.
    by_amt = [c for c in candidates
              if abs(float(c.get("grand_total") or 0) - total) <= 1.0] or candidates
    if len(by_amt) == 1:
        return by_amt[0]
    by_date = [c for c in by_amt if c.get("posting_date") == vdate]
    return by_date[0] if len(by_date) == 1 else None


CASH_CUSTOMER = "Cash"   # counter-sale customer that means "paid in cash"


def backfill_payments(root, cash_sweep=True):
    """Create the Payment Entries that should exist for already-migrated,
    still-outstanding Sales Invoices — WITHOUT re-importing the invoices.

    Two passes:

    1. XML pass — for every sales voucher in Transactions.xml we re-run
       detect_payments() (identical Cash / UPI / online-marker / split logic to
       the main import), match it to the existing outstanding invoice, and post
       the missing Cash/UPI payments. This is the accurate pass: it honours the
       "net banking is paid only when the online term is set" rule and splits a
       half-cash/half-online voucher into two entries.

    2. Cash sweep (cash_sweep=True) — any invoice still outstanding whose
       customer is "Cash" is paid in full by cash. This enforces the business
       rule "cash is always paid to the cash" for the counter-sale invoices the
       XML pass couldn't match (voucher-number drift, undetected cash leg, etc.).
       Net-banking invoices are deliberately NOT swept — they stay outstanding
       unless the XML marked them paid online.

    Idempotent: only outstanding SIs are considered and each payment is capped
    at the invoice's current outstanding, so re-running never over-pays."""
    preload_accounts()
    ensure_upi_mode()

    print("\n=== Backfill Payments ===")
    print("  Loading outstanding Sales Invoices…")
    rows = _fetch_outstanding_sales_invoices()
    # Live, mutable outstanding balance per SI (so split/multi-voucher cases and
    # the per-payment cap stay correct within this run).
    outstanding = {si["name"]: float(si.get("outstanding_amount") or 0) for si in rows}
    index = _build_si_index(rows)
    print(f"  {len(rows)} outstanding invoices loaded.")

    stats = {"matched": 0, "unmatched": 0, "no_payment": 0,
             "pe_cash": 0, "pe_upi": 0, "amt_cash": 0.0, "amt_upi": 0.0,
             "skipped_paid": 0, "sweep_cash": 0, "sweep_amt": 0.0}
    unmatched_samples = []

    for vch in root.iter("VOUCHER"):
        vtype = txt(vch, "VOUCHERTYPENAME")
        if vtype not in SALES_TYPES:
            continue
        vno   = txt(vch, "VOUCHERNUMBER")
        vdate = tally_date(txt(vch, "DATE"))
        narr  = txt(vch, "NARRATION")
        total = ledger_total(vch)

        payments = [(m, a) for (m, a) in detect_payments(vch, vtype, narr)
                    if m in ("Cash", "UPI")]
        if not payments:
            stats["no_payment"] += 1
            continue

        si = _match_si(index, vno, vdate, total)
        if not si:
            stats["unmatched"] += 1
            if len(unmatched_samples) < 15:
                unmatched_samples.append(f"{vno} ({vdate}, {total:.0f})")
            continue
        stats["matched"] += 1

        si_name = si["name"]
        remaining = outstanding.get(si_name, 0.0)
        if remaining <= 0.009:
            stats["skipped_paid"] += 1
            continue

        for mode, amt in payments:
            pay = min(amt, remaining)
            if pay <= 0.009:
                break
            pe = create_payment_for_si(si_name, si["customer"], mode, round(pay, 2), vdate)
            if pe:
                remaining -= pay
                outstanding[si_name] = remaining
                if mode == "Cash":
                    stats["pe_cash"] += 1; stats["amt_cash"] += pay
                else:
                    stats["pe_upi"]  += 1; stats["amt_upi"]  += pay
                print(f"  + PE({mode}) {pay:.2f} → {si_name} ({si['customer']})")

    # ── Pass 2: unconditional cash sweep ─────────────────────────────────────
    if cash_sweep:
        print("\n  Cash sweep: clearing any remaining 'Cash' invoices…")
        for si in rows:
            if si.get("customer") != CASH_CUSTOMER:
                continue
            si_name = si["name"]
            remaining = outstanding.get(si_name, 0.0)
            if remaining <= 0.009:
                continue
            pe = create_payment_for_si(si_name, CASH_CUSTOMER, "Cash",
                                       round(remaining, 2),
                                       si.get("posting_date"))
            if pe:
                outstanding[si_name] = 0.0
                stats["sweep_cash"] += 1
                stats["sweep_amt"] += remaining
                print(f"  + PE(Cash,sweep) {remaining:.2f} → {si_name}")

    print("\n── Backfill Summary ──")
    print(f"  Vouchers matched to an outstanding invoice : {stats['matched']}")
    print(f"  Vouchers with no Cash/UPI payment (credit) : {stats['no_payment']}")
    print(f"  Matched but already paid (skipped)         : {stats['skipped_paid']}")
    print(f"  Cash Payment Entries (XML)   : {stats['pe_cash']:>5}  (₹{stats['amt_cash']:,.2f})")
    print(f"  UPI  Payment Entries (XML)   : {stats['pe_upi']:>5}  (₹{stats['amt_upi']:,.2f})")
    print(f"  Cash Payment Entries (sweep) : {stats['sweep_cash']:>5}  (₹{stats['sweep_amt']:,.2f})")
    print(f"  Unmatched vouchers (had a payment, no outstanding SI): {stats['unmatched']}")
    if unmatched_samples:
        print("    e.g. " + ", ".join(unmatched_samples))

# ── 6. Item Tax Templates — link GST rate to every item based on HSN / name ──
GST_RATE_PATTERN = re.compile(
    r'\b(28|18|12|5)\s*%|\((\d+)%\)',
    re.IGNORECASE
)
NIL_PATTERN = re.compile(r'\bnil\b|\bexempt\b|\bzero\b', re.IGNORECASE)

# HSN-code prefix → GST rate (%). Longer prefixes (6/8-digit) beat shorter ones.
# Rates sourced from CBIC official schedule & IndiaFilings Chapter 40 / 87 tables (2026).
HSN_GST_MAP: dict[str, int] = {
    # ── Chapter 40 – Rubber & rubber articles ────────────────────────────────
    "4001": 5,    # Natural rubber in primary forms
    "4002": 18,   # Synthetic rubber
    "4003": 18,   # Reclaimed rubber
    "4004": 5,    # Waste / scrap rubber
    "4005": 18,   # Compounded unvulcanised rubber
    "4006": 18,   # Other unvulcanised rubber shapes
    "4007": 18,   # Vulcanised rubber thread & cord
    "4008": 18,   # Vulcanised rubber plates / sheets / strip
    "4009": 18,   # Rubber tubes, pipes & hoses
    "4010": 18,   # Conveyor / transmission belts of rubber
    "4011": 18,   # New pneumatic tyres (all types) — 18% per current CBIC schedule
    "4012": 18,   # Retreaded / used pneumatic tyres & tyre treads
    "4013": 18,   # Inner tubes of rubber (all types)
    "4014": 12,   # Hygienic / pharmaceutical rubber articles
    "4015": 18,   # Rubber apparel & gloves
    "401511": 12, # Surgical rubber gloves (6-digit override → 12%)
    "4016": 18,   # Other vulcanised rubber articles (flaps, seals, gaskets, etc.)
    "4017": 18,   # Hard rubber articles
    # ── Chapter 85 – Electrical equipment ────────────────────────────────────
    "8507": 28,   # Electric accumulators — lead-acid (vehicle batteries)
    "850760": 18, # Lithium-ion batteries (6-digit override → 18%)
    "8511": 18,   # Electrical ignition / starting equipment for engines
    "8512": 18,   # Electrical lighting & signalling equipment for vehicles
    "8536": 18,   # Electrical switches, fuses, connectors
    # ── Chapter 87 – Motor vehicles & parts ──────────────────────────────────
    "8701": 12,   # Tractors (12–28% by type; 12% is default for agricultural)
    "8708": 28,   # Parts & accessories of motor vehicles — 28% (AAAR AP ruling)
    "870810": 18, # Bumpers/parts for tractors (6-digit override → 18%)
    "8711": 28,   # Motorcycles & mopeds
    "8712": 12,   # Non-motorised bicycles
    "8714": 28,   # Parts & accessories for motorcycles / cycles
    "871420": 18, # Baby carriage parts (6-digit override → 18%)
    "8715": 18,   # Baby carriages & parts
    "8716": 18,   # Trailers & semi-trailers; other non-motorised vehicles
    # ── Chapter 27 / 34 – Lubricants & petroleum products ────────────────────
    "2710": 18,   # Petroleum oils & lubricating oils
    "3403": 18,   # Lubricating preparations
    "3819": 18,   # Hydraulic brake fluids & anti-freeze preparations
    # ── Chapter 82 – Tools ───────────────────────────────────────────────────
    "8205": 18,   # Hand tools (spanners, hammers, etc.)
    "8207": 18,   # Interchangeable tools (drills, reamers, dies)
    # ── Miscellaneous ─────────────────────────────────────────────────────────
    "3401": 18,   # Soaps & surface-active products
    "3926": 18,   # Other articles of plastics
    "7320": 18,   # Springs and leaves for springs of steel
}

def _rate_from_hsn(hsn: str) -> int | None:
    """Return GST rate for an HSN code by matching longest prefix first."""
    h = re.sub(r'\s', '', str(hsn or ""))
    for length in (8, 6, 4):
        if h[:length] in HSN_GST_MAP:
            return HSN_GST_MAP[h[:length]]
    return None

def _infer_gst_rate(item_code: str, hsn: str = "") -> str:
    """
    Return the Item Tax Template name for an item.
    Priority: HSN code → rate in item name → 18% default.
    """
    rate = _rate_from_hsn(hsn)
    if rate is None:
        m = GST_RATE_PATTERN.search(item_code)
        if m:
            r = int(m.group(1) or m.group(2))
            if r in (5, 12, 18, 28):
                rate = r
    if rate is None:
        if NIL_PATTERN.search(item_code):
            return f"Nil-Rated - {ABBR}"
        rate = 18   # default for unclassified items
    return f"GST {rate}% - {ABBR}"

def migrate_item_tax_templates():
    """Link Item Tax Templates to items based on GST rate in item name."""
    print("\n=== Item Tax Templates ===")

    # Fetch all items including HSN code (primary source for GST rate)
    items = []
    offset = 0
    while True:
        r = requests.get(
            f"{ERPNEXT_URL}/api/resource/Item",
            headers=HEADERS,
            params={"fields": '["name","taxes","gst_hsn_code"]',
                    "limit_page_length": 500, "limit_start": offset},
            timeout=30,
        )
        batch = r.json().get("data", [])
        items.extend(batch)
        if len(batch) < 500:
            break
        offset += 500
    print(f"  Total items: {len(items)}")

    # Verify templates exist
    existing_templates = set()
    for rate in (5, 12, 18, 28):
        name = f"GST {rate}% - {ABBR}"
        if api_exists("Item Tax Template", name):
            existing_templates.add(name)
    nil_tmpl = f"Nil-Rated - {ABBR}"
    if api_exists("Item Tax Template", nil_tmpl):
        existing_templates.add(nil_tmpl)

    linked = skipped = no_match = 0
    for item in items:
        code = item["name"]
        if item.get("taxes"):          # already has a tax template
            skipped += 1
            continue
        tmpl = _infer_gst_rate(code, hsn=item.get("gst_hsn_code") or "")
        if not tmpl or tmpl not in existing_templates:
            no_match += 1
            continue
        r = requests.put(
            f"{ERPNEXT_URL}/api/resource/Item/{requests.utils.quote(code)}",
            headers=HEADERS,
            json={"data": {"taxes": [{"item_tax_template": tmpl}]}},
            timeout=20,
        )
        if r.status_code in (200, 201):
            linked += 1
        else:
            print(f"  WARN {code}: {r.text[:100]}")

    print(f"  Linked: {linked}, Already set: {skipped}, No rate in name: {no_match}")

# ── 7. Opening stock — Stock Reconciliation for items with OPENINGBALANCE ──────
def migrate_opening_stock(root):
    """
    Create a Stock Reconciliation for every STOCKITEM with non-zero OPENINGBALANCE.
    Uses OPENINGRATE as valuation_rate; falls back to abs(OPENINGVALUE/qty).
    All stock placed in 'Main Location - AMS' warehouse.
    """
    print("\n=== Opening Stock ===")
    warehouse      = f"Main Location - {ABBR}"
    temp_acc       = ensure_temporary_opening_account()

    # Preload item cache
    preload_items()

    # Fetch stock items (is_stock_item=1) so we skip services/non-stock
    stock_item_set: set = set()
    offset = 0
    while True:
        r = requests.get(
            f"{ERPNEXT_URL}/api/resource/Item",
            headers=HEADERS,
            params={
                "fields": '["name"]',
                "filters": json.dumps([["is_stock_item", "=", 1]]),
                "limit_page_length": 500,
                "limit_start": offset,
            },
            timeout=30,
        )
        batch = r.json().get("data", [])
        stock_item_set.update(b["name"] for b in batch)
        if len(batch) < 500:
            break
        offset += 500
    print(f"  Stock items in ERPNext: {len(stock_item_set)}")

    rows = []
    for item in root.iter("STOCKITEM"):
        name   = item.get("NAME", "").strip()
        ob_str = (item.findtext("OPENINGBALANCE") or "").strip()
        if not ob_str or ob_str in ("0", "0.0"):
            continue

        # Parse qty — format: "7 NOS" or "7.00"
        qty_str = ob_str.split()[0].replace(",", "")
        try:
            qty = abs(float(qty_str))
        except:
            continue
        if qty < 0.001:
            continue

        # Resolve item code; skip non-stock items
        item_code = name if name in ITEM_CACHE else None
        if not item_code or item_code not in stock_item_set:
            continue

        # Parse rate: OPENINGRATE format "11873.99/NOS"
        rate_str  = (item.findtext("OPENINGRATE") or "").strip().split("/")[0].replace(",", "")
        val_str   = (item.findtext("OPENINGVALUE") or "").strip().replace(",", "")
        try:
            rate = abs(float(rate_str)) if rate_str else 0.0
        except:
            rate = 0.0
        if rate == 0.0:
            try:
                rate = abs(float(val_str)) / qty if qty else 0.0
            except:
                rate = 0.0

        if rate <= 0.0:
            continue  # ERPNext requires valuation_rate > 0 for Stock Reconciliation

        rows.append({
            "item_code":       item_code,
            "warehouse":       warehouse,
            "qty":             qty,
            "valuation_rate":  round(rate, 2),
        })

    if not rows:
        print("  No opening stock items found.")
        return

    print(f"  Items to reconcile: {len(rows)}")

    # ERPNext allows max ~200 items per Stock Reconciliation; split into batches
    BATCH = 200
    batches = [rows[i:i+BATCH] for i in range(0, len(rows), BATCH)]
    total_ok = 0
    for idx, batch in enumerate(batches):
        data = {
            "doctype":          "Stock Reconciliation",
            "posting_date":     "2023-04-01",
            "company":          COMPANY,
            "purpose":          "Opening Stock",
            "expense_account":  temp_acc,   # must be Asset/Liability for opening entries
            "items":            batch,
        }
        r = api_post("Stock Reconciliation", data)
        if r:
            sr_name = r.get("name", "")
            if sr_name:
                ok = api_submit("Stock Reconciliation", sr_name)
                if ok:
                    total_ok += len(batch)
                    print(f"  Batch {idx+1}/{len(batches)} submitted: {sr_name} ({len(batch)} items)")
                else:
                    print(f"  Batch {idx+1} created but submit failed: {sr_name}")
            else:
                print(f"  Batch {idx+1} created (no name returned)")
        else:
            print(f"  Batch {idx+1} FAILED")

    print(f"  Total items in submitted SR: {total_ok}/{len(rows)}")

# ── 8. Bank Transactions — one record per bank leg for reconciliation ──────────
def migrate_bank_transactions(root):
    """
    Create Bank Transaction docs from Receipt, Payment, and Contra vouchers.
    Bank Transactions are used for bank reconciliation (matched against Payment
    Entries and other bank entries). They are separate from Payment Entries.

    Tally sign convention in ALLLEDGERENTRIES:
      negative AMOUNT on bank leg = DEBIT = money in  → deposit
      positive AMOUNT on bank leg = CREDIT = money out → withdrawal
    """
    print("\n=== Bank Transactions ===")
    preload_accounts()

    ALL_BANK_TYPES = PAYMENT_TYPES | {"Contra"}
    ok = skip = 0

    for vch in root.iter("VOUCHER"):
        vtype = txt(vch, "VOUCHERTYPENAME")
        if vtype not in ALL_BANK_TYPES:
            continue

        vno   = txt(vch, "VOUCHERNUMBER")
        vdate = tally_date(txt(vch, "DATE"))
        narr  = txt(vch, "NARRATION")
        if not vdate:
            skip += 1
            continue

        party = txt(vch, "PARTYLEDGERNAME")
        utr, utr_date, _ = extract_bank_ref(vch)

        desc_parts = [p for p in (party, narr) if p]
        desc = " | ".join(desc_parts)[:140] if desc_parts else (vno or "")

        # A single voucher may touch multiple bank accounts (rare but possible)
        for leg in vch.iter("ALLLEDGERENTRIES.LIST"):
            lname = (txt(leg, "LEDGERNAME") or "").strip()
            # Skip Tally payment-mode clearing ledgers (they aren't real banks)
            if lname in PAYMENT_MODE_LEDGERS:
                continue
            acc   = f"{lname} - {ABBR}"
            # Only real Bank-type accounts — skip payment clearing accounts
            if acc not in BANK_ONLY_GL:
                continue

            try:
                amt = float((txt(leg, "AMOUNT") or "0").strip() or "0")
            except:
                amt = 0.0
            if amt == 0:
                continue

            bank_acct  = BANK_ACCOUNT_MAP[acc]
            deposit    = round(abs(amt), 2) if amt < 0 else 0.0
            withdrawal = round(amt,       2) if amt > 0 else 0.0

            data = {
                "doctype":      "Bank Transaction",
                "bank_account": bank_acct,
                "date":         vdate,
                "deposit":      deposit,
                "withdrawal":   withdrawal,
                "currency":     "INR",
                "description":  desc,
                "company":      COMPANY,
            }
            if utr:
                data["reference_number"] = utr
            elif vno:
                data["reference_number"] = vno

            r = api_post("Bank Transaction", data)
            if r:
                bt_name = r.get("name", "")
                if bt_name:
                    api_submit("Bank Transaction", bt_name)
                direction = "DEP" if deposit else "WDL"
                amt_show  = deposit or withdrawal
                print(f"  + BT {vno} [{direction} {amt_show:.0f}] {bank_acct}")
                ok += 1
            else:
                skip += 1

    print(f"  Bank Transactions created: {ok}, skipped: {skip}")


# ── 9. Submit all existing drafts (run after a previous partial migration) ────
def submit_all_drafts():
    """Submit any draft Sales/Purchase Invoices left from a previous run."""
    for doctype in ("Purchase Invoice", "Sales Invoice"):
        print(f"\n=== Submit draft {doctype}s ===")
        url = f"{ERPNEXT_URL}/api/resource/{doctype}"
        params = {
            "filters": json.dumps([
                ["docstatus", "=", 0],
                ["company", "=", COMPANY],
            ]),
            "fields": '["name"]',
            "limit_page_length": 500,
        }
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=30)
            docs = r.json().get("data", []) if r.status_code == 200 else []
        except Exception as e:
            print(f"  ERR fetching drafts: {e}")
            docs = []

        count = 0
        for doc in docs:
            name = doc.get("name")
            if name and api_submit(doctype, name):
                count += 1
                print(f"  submitted: {name}")
        print(f"  Total submitted: {count}")

def _fix_invoice_taxes():
    """
    Patch all Sales/Purchase Invoices that have Actual-type tax rows with
    included_in_print_rate=1. ERPNext forbids that combination.
    Safe to re-run: only touches rows that need fixing.
    """
    print("\n=== Fix invoice tax rows (included_in_print_rate) ===")
    fixed = 0
    for doctype in ("Sales Invoice", "Purchase Invoice"):
        start = 0
        while True:
            r = requests.get(
                f"{ERPNEXT_URL}/api/resource/{requests.utils.quote(doctype)}",
                headers=HEADERS,
                params={
                    "filters": json.dumps([["company", "=", COMPANY], ["docstatus", "in", [0, 1]]]),
                    "fields": '["name","docstatus"]',
                    "limit_page_length": 200,
                    "limit_start": start,
                },
                timeout=30,
            )
            if r.status_code != 200:
                break
            batch = r.json().get("data", [])
            for doc in batch:
                name = doc["name"]
                ds   = doc.get("docstatus", 0)
                doc_r = requests.get(
                    f"{ERPNEXT_URL}/api/resource/{requests.utils.quote(doctype)}/{requests.utils.quote(name)}",
                    headers=HEADERS, timeout=15,
                )
                if doc_r.status_code != 200:
                    continue
                taxes = doc_r.json().get("data", {}).get("taxes", [])
                needs_fix = any(
                    t.get("charge_type") == "Actual" and t.get("included_in_print_rate")
                    for t in taxes
                )
                if not needs_fix:
                    continue
                for t in taxes:
                    if t.get("charge_type") == "Actual":
                        t["included_in_print_rate"] = 0
                # Must cancel → amend or just update draft; submitted docs need cancel+resubmit
                if ds == 1:
                    if not _cancel_doc(doctype, name):
                        print(f"  WARN: could not cancel {name}")
                        continue
                upd = requests.put(
                    f"{ERPNEXT_URL}/api/resource/{requests.utils.quote(doctype)}/{requests.utils.quote(name)}",
                    headers=HEADERS,
                    json={"data": {"taxes": taxes}},
                    timeout=30,
                )
                if upd.status_code in (200, 201):
                    if ds == 1:
                        api_submit(doctype, name)
                    fixed += 1
                    print(f"  fixed {name}")
                else:
                    print(f"  WARN: could not patch {name} [{upd.status_code}]")
            if len(batch) < 200:
                break
            start += 200
    print(f"  Total fixed: {fixed}")


# ── Interactive selection menu ────────────────────────────────────────────────
# (key, label) — `key` is what run_steps() dispatches on, kept in declaration
# order because later steps depend on data created by earlier ones.
IMPORT_STEPS = [
    ("uom",              "UOMs"),
    ("groups",           "Account Groups"),
    ("ledgers",          "Ledgers (Accounts + Customers + Suppliers)"),
    ("items",            "Items + Item Groups"),
    ("bank_accounts",    "Bank Accounts (mark accounts as Bank, create Bank Account records)"),
    ("opening",          "Opening Balances (Journal Entry)"),
    ("opening_stock",    "Opening Stock (Stock Reconciliation)"),
    ("item_taxes",       "Item Tax Templates"),
    ("transactions",     "Transactions (Sales/Purchase Invoices, Payments, Journals)"),
    ("bank_transactions","Bank Transactions"),
    ("backfill_payments","Backfill Payments (pay outstanding migrated invoices, no re-import)"),
]

RESET_OPTIONS = [
    ("none",         "Don't reset — just add to existing data"),
    ("transactions", "Reset transactions only (Bank Tx, PE, JE, SI/PI, Stock Recon)"),
    ("trans_items",  "Reset transactions + items + item tax templates"),
    ("full",         "Full reset via bench (TRUE wipe of company data — uses docker exec)"),
]

def _prompt(text, default=""):
    try:
        raw = input(text).strip()
    except EOFError:
        raw = ""
    return raw or default

def interactive_menu():
    """Ask the user what to import and whether to reset first.
    Returns (selected_keys, reset_key) — or (None, None) if aborted."""
    print("\n" + "=" * 60)
    print(" Tally → ERPNext Migration")
    print("=" * 60)

    print("\nWhat do you want to import?")
    for i, (_, label) in enumerate(IMPORT_STEPS, 1):
        print(f"  {i:>2}. {label}")
    print("  all. Everything (all of the above, in order)")

    raw = _prompt("\nSelect (e.g. '1,2,3' or 'all') [all]: ", "all").lower()
    if raw == "all":
        selected = [key for key, _ in IMPORT_STEPS]
    else:
        try:
            indices = [int(x.strip()) for x in raw.split(",") if x.strip()]
            selected = [IMPORT_STEPS[i - 1][0] for i in indices
                        if 1 <= i <= len(IMPORT_STEPS)]
        except ValueError:
            print("  Invalid selection.")
            return None, None
    if not selected:
        print("  Nothing selected. Aborting.")
        return None, None

    print("\nReset existing Frappe data before importing?")
    for i, (_, label) in enumerate(RESET_OPTIONS):
        print(f"  {i}. {label}")
    raw = _prompt(f"\nReset choice (0-{len(RESET_OPTIONS) - 1}) [0]: ", "0")
    try:
        reset = RESET_OPTIONS[int(raw)][0]
    except (ValueError, IndexError):
        reset = "none"

    print("\n=== Plan ===")
    label_by_key = dict(IMPORT_STEPS)
    print("  Import:")
    for key in selected:
        print(f"    - {label_by_key[key]}")
    reset_label = next(l for k, l in RESET_OPTIONS if k == reset)
    print(f"  Reset: {reset_label}")
    if reset == "full":
        print("  WARNING: 'full' wipes ALL customers, suppliers, accounts, items.")

    confirm = _prompt("\nProceed? [Y/n]: ", "y").lower()
    if confirm not in ("y", "yes"):
        print("  Aborted.")
        return None, None

    return selected, reset

def _preflight(selected):
    """Ensure each selected step has its dependencies; auto-insert missing
    prerequisite steps so the user doesn't have to know the dependency graph.

    Failure modes this prevents (all seen in real runs):
      - Opening Stock needs `Application of Funds (Assets) - {ABBR}` so the
        Temporary Opening account can be created under it.
      - Transactions need Debtors / Sales / COGS / Stores GL accounts and at
        least one Item.
    """
    sel = list(selected)
    out = list(selected)
    label = dict(IMPORT_STEPS)

    def insert_before(key, before_keys):
        """Add `key` to the run just before the first of `before_keys` that
        appears in `out`, preserving the natural import order."""
        nonlocal out
        if key in out:
            return
        idx = min((out.index(b) for b in before_keys if b in out), default=len(out))
        out.insert(idx, key)
        print(f"  PREFLIGHT: auto-adding '{label[key]}' before '{label[before_keys[0]]}' "
              f"(it's required)")

    def items_count():
        try:
            r = requests.get(
                f"{ERPNEXT_URL}/api/method/frappe.client.get_count",
                params={"doctype": "Item"}, headers=HEADERS, timeout=15,
            )
            if r.status_code == 200:
                return int(r.json().get("message", 0))
        except Exception:
            pass
        return 0

    # Opening / Opening Stock → need account groups (parent accounts).
    if "opening" in sel or "opening_stock" in sel:
        if not api_exists("Account", f"Application of Funds (Assets) - {ABBR}"):
            insert_before("groups", ["opening", "opening_stock"])

    # Transactions → need the standard COA + at least one Item.
    if "transactions" in sel or "bank_transactions" in sel:
        coa_missing = not all(
            api_exists("Account", f"{n} - {ABBR}")
            for n in ("Debtors", "Sales", "Cost of Goods Sold")
        )
        if coa_missing:
            # Bootstrap the ERPNext standard CoA via bench. Without it, every
            # SI/PI fails at submit because Company.default_* fields point at
            # accounts the Tally migration doesn't know how to create.
            print("\n  PREFLIGHT: standard CoA missing — running bootstrap")
            ensure_standard_coa()
            # Then layer the Tally accounts on top.
            insert_before("groups",  ["transactions", "bank_transactions", "ledgers"])
            insert_before("ledgers", ["transactions", "bank_transactions"])
        if items_count() == 0:
            insert_before("items", ["transactions", "bank_transactions"])

    if out != list(selected):
        print()  # spacer after preflight notices
    return out


def run_steps(selected, reset):
    """Execute reset + selected import steps. `selected` is a list of keys
    from IMPORT_STEPS; `reset` is one of RESET_OPTIONS keys."""
    if reset == "transactions":
        clear_transactions()
    elif reset == "trans_items":
        clear_transactions()
        reset_items()
    elif reset == "full":
        reset_full()

    selected = _preflight(selected)
    sel = set(selected)
    needs_master = bool(sel & {"uom", "groups", "ledgers", "items",
                               "bank_accounts", "opening", "opening_stock"})
    master_root = parse_xml(MASTER_XML) if needs_master else None

    if "uom" in sel:
        migrate_uom(master_root)
    if "groups" in sel:
        migrate_groups(master_root)
    if "ledgers" in sel:
        migrate_ledgers(master_root)
    if "items" in sel:
        migrate_items(master_root)
    if "bank_accounts" in sel:
        migrate_bank_accounts()
    if "opening" in sel:
        preload_accounts()
        migrate_opening_balances(master_root)
    if "opening_stock" in sel:
        migrate_opening_stock(master_root)
    if "item_taxes" in sel:
        migrate_item_tax_templates()

    if master_root is not None:
        del master_root

    needs_trans = bool(sel & {"transactions", "bank_transactions", "backfill_payments"})
    trans_root = parse_xml(TRANS_XML) if needs_trans else None

    if "transactions" in sel:
        ensure_services_item()
        ensure_payment_terms()
        ensure_walkin_customer()
        ensure_upi_mode()
        ensure_company_address()
        # Item Tax Templates must be set on every Item before invoices, otherwise
        # SI/PI lines have no item_tax_template → ERPNext shows the tax row at 0%
        # per line even when the invoice-level tax template is applied. Idempotent.
        if "item_taxes" not in sel:
            print("\n  (auto-running item_taxes — required for per-line GST)")
            migrate_item_tax_templates()
        preload_items()
        preload_accounts()
        migrate_vouchers(trans_root)
    if "bank_transactions" in sel:
        preload_accounts()
        migrate_bank_transactions(trans_root)
    if "backfill_payments" in sel:
        backfill_payments(trans_root)

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    # Default: interactive menu. CLI args remain for scripted/repeat runs.
    mode = sys.argv[1] if len(sys.argv) > 1 else "interactive"

    if mode == "interactive":
        selected, reset = interactive_menu()
        if selected:
            run_steps(selected, reset)
        print("\nDone.")
        return

    if mode == "fix_taxes":
        _fix_invoice_taxes()
        print("\nDone.")
        return

    if mode == "bank_accounts":
        preload_accounts()
        migrate_bank_accounts()
        print("\nDone.")
        return

    if mode == "submit":
        submit_all_drafts()
        print("\nDone.")
        return

    if mode == "bootstrap_coa":
        ensure_standard_coa()
        print("\nDone.")
        return

    if mode == "backfill_payments":
        trans_root = parse_xml(TRANS_XML)
        backfill_payments(trans_root)
        print("\nDone.")
        return

    if mode == "clear":
        clear_transactions()
        print("\nDone.")
        return

    if mode == "clear_full":
        reset_full()
        print("\nDone.")
        return

    if mode == "clear_all":
        clear_transactions()
        print("\n--- Item ---")
        delete_all_of("Item")
        # fall through to re-import

    if mode in ("masters", "all", "clear_all"):
        master_root = parse_xml(MASTER_XML)
        migrate_uom(master_root)
        migrate_groups(master_root)
        migrate_ledgers(master_root)
        migrate_items(master_root)
        migrate_bank_accounts()   # set account_type + create Bank Account records

    if mode in ("opening", "all", "clear_all"):
        if "master_root" not in dir():
            master_root = parse_xml(MASTER_XML)
        preload_accounts()
        migrate_opening_balances(master_root)

    if mode in ("opening_stock", "all", "clear_all"):
        if "master_root" not in dir():
            master_root = parse_xml(MASTER_XML)
        migrate_opening_stock(master_root)

    if mode in ("item_taxes", "all", "clear_all"):
        migrate_item_tax_templates()

    if "master_root" in dir():
        del master_root

    if mode in ("transactions", "all", "clear_all"):
        ensure_services_item()
        ensure_payment_terms()    # must run before Sales Invoice creation
        ensure_walkin_customer()  # fallback for anonymous counter sales
        ensure_upi_mode()         # UPI payment mode for net banking entries
        ensure_company_address()  # india_compliance: company GSTIN on invoices
        preload_items()           # cache all item codes (avoids N×API calls)
        preload_accounts()        # cache all account names for GST tax rows
        trans_root = parse_xml(TRANS_XML)
        migrate_vouchers(trans_root)
        if "trans_root" in dir():
            migrate_bank_transactions(trans_root)

    if mode == "bank_transactions":
        preload_accounts()
        trans_root = parse_xml(TRANS_XML)
        migrate_bank_transactions(trans_root)

    print("\nDone.")

if __name__ == "__main__":
    main()
