import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    """Add referral-tracking custom fields.

    Customer:
      - custom_referred_by    : who referred this customer (Link -> Customer)
      - custom_referral_credit: credit earned by a customer AS a referrer (Currency)
      - custom_referral_rewarded: set once the referred customer's first service
                                  has granted the reward (idempotency guard)
    POS Invoice:
      - custom_referral_credit_used: referral credit redeemed on this sale

    Idempotent — create_custom_fields skips existing fields.
    """
    fields = {}

    if frappe.db.exists("DocType", "Customer"):
        fields["Customer"] = [
            {
                "fieldname": "custom_referred_by",
                "label": "Referred By",
                "fieldtype": "Link",
                "options": "Customer",
                "insert_after": "custom_whatsapp",
            },
            {
                "fieldname": "custom_referral_credit",
                "label": "Referral Credit",
                "fieldtype": "Currency",
                "insert_after": "custom_referred_by",
                "read_only": 1,
            },
            {
                "fieldname": "custom_referral_rewarded",
                "label": "Referral Rewarded",
                "fieldtype": "Check",
                "insert_after": "custom_referral_credit",
                "read_only": 1,
            },
        ]

    if frappe.db.exists("DocType", "POS Invoice"):
        fields["POS Invoice"] = [
            {
                "fieldname": "custom_referral_credit_used",
                "label": "Referral Credit Used",
                "fieldtype": "Currency",
                "insert_after": "discount_amount",
                "read_only": 1,
            }
        ]

    if fields:
        create_custom_fields(fields, ignore_validate=True)
