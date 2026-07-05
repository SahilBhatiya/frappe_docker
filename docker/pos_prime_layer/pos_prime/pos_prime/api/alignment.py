# Copyright (c) 2026, Ravindu Gajanayaka
# Licensed under GPLv3. See license.txt

"""Link read-only wheel-alignment machine records to canonical Frappe records."""

import json
import re

import frappe
from frappe import _
from frappe.utils import flt

from pos_prime.api._utils import validate_pos_access


def _normalize_registration(value):
	return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _normalize_phone(value):
	digits = re.sub(r"\D", "", str(value or ""))
	return digits[-10:] if len(digits) >= 10 else digits


def _find_customer_by_phone(phone):
	normalized = _normalize_phone(phone)
	if len(normalized) < 7:
		return None

	for customer in frappe.get_all(
		"Customer",
		filters={"disabled": 0},
		fields=["name", "customer_name", "mobile_no"],
		order_by="modified desc",
		limit_page_length=0,
	):
		if _normalize_phone(customer.mobile_no) == normalized:
			return customer
	return None


def _find_car(registration_number):
	normalized = _normalize_registration(registration_number)
	if not normalized or not frappe.db.exists("DocType", "Customer Car"):
		return None

	for car in frappe.get_all(
		"Customer Car",
		fields=["name", "registration_number", "make_model", "current_odometer"],
		order_by="modified desc",
		limit_page_length=0,
	):
		if _normalize_registration(car.registration_number) == normalized:
			return car
	return None


def _linked_customer(car_name):
	if not car_name or not frappe.db.exists("DocType", "Customer Car Link"):
		return None
	return frappe.db.get_value(
		"Customer Car Link",
		{"car": car_name, "parenttype": "Customer", "parentfield": "custom_cars"},
		"parent",
	)


@frappe.whitelist()
def get_alignment_links(records=None):
	"""Resolve a page of machine records against Frappe customers and cars."""
	validate_pos_access()
	if isinstance(records, str):
		records = json.loads(records)
	if not isinstance(records, list):
		return {}

	links = {}
	for record in records[:200]:
		report_id = str(record.get("report_id") or "")
		if not report_id:
			continue
		car = _find_car(record.get("vehicle_registration"))
		customer_name = _linked_customer(car.name) if car else None
		customer = None
		if customer_name:
			customer = frappe.db.get_value(
				"Customer", customer_name, ["name", "customer_name", "mobile_no"], as_dict=True
			)
		if not customer:
			customer = _find_customer_by_phone(record.get("customer_phone"))
		links[report_id] = {
			"car": dict(car) if car else None,
			"customer": dict(customer) if customer else None,
			"is_linked": bool(car and customer_name),
		}
	return links


def _create_customer(name, phone):
	customer_group = frappe.db.get_single_value("Selling Settings", "customer_group")
	territory = frappe.db.get_single_value("Selling Settings", "territory")
	if not customer_group:
		customer_group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
	if not territory:
		territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
	if not customer_group or not territory:
		frappe.throw(_("Configure a default Customer Group and Territory first"))

	doc = frappe.new_doc("Customer")
	doc.update(
		{
			"customer_name": str(name or "Walk-in Customer").strip(),
			"customer_type": "Individual",
			"customer_group": customer_group,
			"territory": territory,
			"mobile_no": str(phone or "").strip() or None,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


def _ensure_car_link(customer_name, car_name, make_model):
	if frappe.db.exists(
		"Customer Car Link",
		{
			"parent": customer_name,
			"parenttype": "Customer",
			"parentfield": "custom_cars",
			"car": car_name,
		},
	):
		return
	customer_doc = frappe.get_doc("Customer", customer_name)
	customer_doc.append("custom_cars", {"car": car_name, "make_model": make_model})
	customer_doc.save(ignore_permissions=True)


@frappe.whitelist()
def link_alignment_record(
	report_id,
	registration_number,
	customer=None,
	customer_name=None,
	customer_phone=None,
	make_model=None,
	current_odometer=0,
):
	"""Create/reuse one canonical car and link it to one canonical customer."""
	validate_pos_access()
	if not report_id:
		frappe.throw(_("Alignment report is required"))
	if not _normalize_registration(registration_number):
		frappe.throw(_("Registration number is required"))
	if not frappe.db.exists("DocType", "Customer Car") or not frappe.db.exists(
		"DocType", "Customer Car Link"
	):
		frappe.throw(_("Customer car records are not configured on this site"))
	if not frappe.get_meta("Customer").has_field("custom_cars"):
		frappe.throw(_("Customer car links are not configured on this site"))

	if customer:
		if not frappe.db.exists("Customer", customer):
			frappe.throw(_("Selected customer does not exist"))
		customer_doc = frappe.get_doc("Customer", customer)
	else:
		customer_doc = _find_customer_by_phone(customer_phone)
		if customer_doc:
			customer_doc = frappe.get_doc("Customer", customer_doc.name)
		else:
			customer_doc = _create_customer(customer_name, customer_phone)

	car = _find_car(registration_number)
	if car:
		car_doc = frappe.get_doc("Customer Car", car.name)
	else:
		car_doc = frappe.new_doc("Customer Car")

	values = {
		"registration_number": str(registration_number).strip().upper(),
		"make_model": str(make_model or "").strip(),
		"current_odometer": flt(current_odometer),
	}
	car_meta = frappe.get_meta("Customer Car")
	for fieldname, value in values.items():
		if car_meta.has_field(fieldname) and (value or fieldname == "current_odometer"):
			car_doc.set(fieldname, value)
	if car_meta.has_field("notes"):
		note = _("Linked from alignment machine report {0}").format(report_id)
		existing = str(car_doc.get("notes") or "")
		if note not in existing:
			car_doc.set("notes", "\n".join(filter(None, [existing, note])))

	if car_doc.is_new():
		car_doc.insert(ignore_permissions=True)
	else:
		car_doc.save(ignore_permissions=True)

	previous_customer = _linked_customer(car_doc.name)
	if previous_customer and previous_customer != customer_doc.name:
		frappe.throw(
			_("Car {0} is already linked to customer {1}").format(
				values["registration_number"], previous_customer
			)
		)
	_ensure_car_link(customer_doc.name, car_doc.name, values["make_model"])

	return {
		"report_id": report_id,
		"customer": {
			"name": customer_doc.name,
			"customer_name": customer_doc.customer_name,
			"mobile_no": customer_doc.mobile_no,
		},
		"car": {
			"name": car_doc.name,
			"registration_number": values["registration_number"],
			"make_model": values["make_model"],
			"current_odometer": values["current_odometer"],
		},
		"is_linked": True,
	}


@frappe.whitelist()
def unlink_alignment_record(registration_number):
	"""Remove the link between a car and its customer."""
	validate_pos_access()
	if not _normalize_registration(registration_number):
		frappe.throw(_("Registration number is required"))

	car = _find_car(registration_number)
	if not car:
		return {"is_linked": False}

	customer_name = _linked_customer(car.name)
	if not customer_name:
		return {"is_linked": False}

	customer_doc = frappe.get_doc("Customer", customer_name)
	original_len = len(customer_doc.get("custom_cars", []))
	customer_doc.set("custom_cars", [
		row for row in customer_doc.get("custom_cars", []) if row.car != car.name
	])
	
	if len(customer_doc.get("custom_cars", [])) < original_len:
		customer_doc.save(ignore_permissions=True)

	return {
		"car": dict(car),
		"customer": None,
		"is_linked": False,
	}
