"""
Full data wipe for ADARSH MOTOR STORES ERPNext.
Deletes ALL migrated data: transactions, GL entries, customers, suppliers, items, item groups.
Does NOT delete: company, chart of accounts, UOM, users, settings.
After running, execute: python tally_migrate.py all
"""

import subprocess
import sys

SITE = "erpnext.localhost"
CONTAINER = "erpnext-backend-1"
COMPANY = "ADARSH MOTOR STORES"

def bench_delete(doctype, filters_str):
    """Run frappe.db.delete inside Docker bench."""
    cmd = [
        "docker", "exec", CONTAINER,
        "bench", "--site", SITE,
        "execute", "frappe.db.delete",
        "--args", f"['{doctype}', {filters_str}]"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  WARN: {result.stderr[:200]}")
    else:
        print(f"  OK: {doctype}")

def bench_sql(sql):
    """Run raw SQL inside Docker bench."""
    cmd = [
        "docker", "exec", CONTAINER,
        "bench", "--site", SITE,
        "execute", "frappe.db.sql",
        "--args", f'["{sql}"]'
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  WARN: {result.stderr[:200]}")
    else:
        print(f"  OK: {sql[:60]}...")

print("=== FULL DATA WIPE ===")
print(f"Company: {COMPANY}")
print()

print("--- Accounting entries ---")
bench_delete("GL Entry",            f"{{'company': '{COMPANY}'}}")
bench_delete("Stock Ledger Entry",  f"{{'company': '{COMPANY}'}}")
bench_delete("Payment Ledger Entry",f"{{'company': '{COMPANY}'}}")
bench_sql("DELETE FROM `tabBin`")

print()
print("--- Transactions ---")
bench_delete("Payment Entry",    f"{{'company': '{COMPANY}'}}")
bench_delete("Journal Entry",    f"{{'company': '{COMPANY}'}}")
bench_delete("Sales Invoice",    f"{{'company': '{COMPANY}'}}")
bench_delete("Purchase Invoice", f"{{'company': '{COMPANY}'}}")

print()
print("--- Customers & Suppliers ---")
bench_sql("DELETE FROM `tabDynamic Link` WHERE link_doctype='Customer'")
bench_sql("DELETE FROM `tabDynamic Link` WHERE link_doctype='Supplier'")
bench_sql("DELETE FROM `tabAddress`")
bench_sql("DELETE FROM `tabContact`")
bench_sql("DELETE FROM `tabCustomer`")
bench_sql("DELETE FROM `tabSupplier`")

print()
print("--- Items ---")
bench_sql("DELETE FROM `tabItem Default`")
bench_sql("DELETE FROM `tabItem`")
bench_sql("DELETE FROM `tabItem Group` WHERE name != 'All Item Groups'")

print()
print("=== DONE ===")
print()
print("Run the full migration:")
print("  python tally_migrate.py all")
