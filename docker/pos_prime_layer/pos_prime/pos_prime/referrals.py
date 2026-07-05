# Copyright (c) 2026, Ravindu Gajanayaka
# Licensed under GPLv3. See license.txt

"""Referral rewards: credit a referrer when their referred friend's first service
is billed, and handle redemption of accrued referral credit.

Wired via doc_events on POS Invoice (see hooks.py). Uses frappe.db.set_value so it
never triggers a recursive document save from within submit/cancel.
"""

import frappe
from frappe.utils import flt


def _referral_amount():
	return flt(frappe.conf.get("pos_prime_referral_credit")) or 50


def _has_fields():
	"""Guard: referral custom fields must exist (created via patch / live DB)."""
	meta = frappe.get_meta("Customer")
	return (
		meta.has_field("custom_referred_by")
		and meta.has_field("custom_referral_credit")
		and meta.has_field("custom_referral_rewarded")
	)


def credit_referrer_on_first_service(doc, method=None):
	"""POS Invoice on_submit: grant the referrer their reward (once) and apply any
	referral-credit redemption used on this sale."""
	if getattr(doc, "is_return", 0) or not doc.get("customer"):
		return
	if not _has_fields():
		return

	customer = doc.customer

	# --- 1) Reward the referrer when this is the referred customer's first service ---
	referred_by, rewarded = frappe.db.get_value(
		"Customer", customer, ["custom_referred_by", "custom_referral_rewarded"]
	) or (None, None)
	if referred_by and not rewarded and frappe.db.exists("Customer", referred_by):
		amount = _referral_amount()
		current = flt(frappe.db.get_value("Customer", referred_by, "custom_referral_credit"))
		frappe.db.set_value(
			"Customer", referred_by, "custom_referral_credit", current + amount,
			update_modified=False,
		)
		frappe.db.set_value(
			"Customer", customer, "custom_referral_rewarded", 1, update_modified=False
		)

	# --- 2) Redemption: decrement this customer's own credit by what they used ---
	used = flt(doc.get("custom_referral_credit_used"))
	if used > 0:
		current = flt(frappe.db.get_value("Customer", customer, "custom_referral_credit"))
		frappe.db.set_value(
			"Customer", customer, "custom_referral_credit", max(current - used, 0),
			update_modified=False,
		)


def restore_referral_on_cancel(doc, method=None):
	"""POS Invoice on_cancel: reverse whatever credit_referrer_on_first_service did."""
	if getattr(doc, "is_return", 0) or not doc.get("customer"):
		return
	if not _has_fields():
		return

	customer = doc.customer

	# Restore redeemed credit
	used = flt(doc.get("custom_referral_credit_used"))
	if used > 0:
		current = flt(frappe.db.get_value("Customer", customer, "custom_referral_credit"))
		frappe.db.set_value(
			"Customer", customer, "custom_referral_credit", current + used,
			update_modified=False,
		)

	# Reverse the referrer reward if this invoice was the one that granted it.
	# Heuristic: if the referred customer is marked rewarded and has no other
	# submitted, non-return POS Invoice, undo the reward and clear the flag.
	referred_by, rewarded = frappe.db.get_value(
		"Customer", customer, ["custom_referred_by", "custom_referral_rewarded"]
	) or (None, None)
	if referred_by and rewarded and frappe.db.exists("Customer", referred_by):
		other = frappe.db.count(
			"POS Invoice",
			{
				"customer": customer,
				"docstatus": 1,
				"is_return": 0,
				"name": ["!=", doc.name],
			},
		)
		if not other:
			amount = _referral_amount()
			current = flt(frappe.db.get_value("Customer", referred_by, "custom_referral_credit"))
			frappe.db.set_value(
				"Customer", referred_by, "custom_referral_credit", max(current - amount, 0),
				update_modified=False,
			)
			frappe.db.set_value(
				"Customer", customer, "custom_referral_rewarded", 0, update_modified=False
			)
