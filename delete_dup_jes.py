"""
Force-delete the 135 duplicate opening balance Journal Entries.
Run via: bench --site erpnext.localhost execute frappe.custom.delete_dup_jes.execute
"""
import frappe


def execute():
    # All cancelled duplicate JEs (ACC-JV-2026-00366 to 00498, plus 00681 and 00728)
    names = frappe.db.get_all(
        "Journal Entry",
        filters={
            "docstatus": 2,   # cancelled
            "is_opening": "Yes",
            "user_remark": ["like", "Opening balance:%"],
        },
        pluck="name",
    )
    print(f"Cancelled opening balance JEs to delete: {len(names)}")

    for name in names:
        try:
            # Delete child rows first
            frappe.db.sql("DELETE FROM `tabJournal Entry Account` WHERE parent = %s", name)
            # Delete GL entries (both original and reversal) for this voucher
            frappe.db.sql("DELETE FROM `tabGL Entry` WHERE voucher_no = %s", name)
            frappe.db.sql("DELETE FROM `tabPayment Ledger Entry` WHERE voucher_no = %s", name)
            # Delete the JE itself
            frappe.db.sql("DELETE FROM `tabJournal Entry` WHERE name = %s", name)
        except Exception as e:
            print(f"  ERR {name}: {e}")

    frappe.db.commit()
    print(f"Deleted {len(names)} duplicate opening balance JEs.")
