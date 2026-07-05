# Copyright (c) 2026, Ravindu Gajanayaka
# Licensed under GPLv3. See license.txt

"""Send WhatsApp reminders to customers via a self-hosted WAHA (WhatsApp HTTP API).

Templates are persisted globally (shared across terminals) in the DefaultValue table
via frappe.db.get_default / set_default — no new DocType, no migration required.

WAHA connection is read from site config (migration-free, persists on the sites volume):
    pos_prime_waha_url      default http://host.docker.internal:3100
    pos_prime_waha_session  default "default"
    pos_prime_waha_api_key  optional; sent as X-Api-Key only when set
"""

import json
import re

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, formatdate, now, nowdate

from pos_prime.api._utils import validate_pos_access

TEMPLATES_KEY = "pos_prime_reminder_templates"
WAHA_TIMEOUT = 20

DEFAULT_TEMPLATES = [
	{
		"id": "alignment-due",
		"title": "Wheel Alignment Due",
		"color": "blue",
		"body": (
			"Hi {first_name}, this is a reminder from {shop_name}. "
			"Your vehicle's wheel alignment is due. Please visit us at your "
			"convenience to keep your tyres in top condition. Thank you!"
		),
	},
	{
		"id": "service-due",
		"title": "Service Due",
		"color": "amber",
		"body": (
			"Hi {first_name}, your vehicle is due for a service check at {shop_name}. "
			"Book a slot with us today. Thank you!"
		),
	},
	{
		"id": "payment-due",
		"title": "Payment Reminder",
		"color": "rose",
		"body": (
			"Dear {customer_name}, this is a gentle reminder from {shop_name} regarding "
			"your pending balance. Kindly clear it at your earliest convenience. Thank you!"
		),
	},
	{
		"id": "festive-offer",
		"title": "Festive Offer",
		"color": "violet",
		"body": (
			"Hi {first_name}! {shop_name} has a special offer running this season on "
			"tyres and alignment. Visit us to grab the deal. Thank you!"
		),
	},
	{
		"id": "next-service",
		"title": "Next Service Reminder",
		"color": "emerald",
		"body": (
			"Hi {customer_name}, thank you for choosing {shop_name}.\n\n"
			"Your {vehicle} has completed {odometer} km.\n\n"
			"For a smoother, safer, and more comfortable drive, your next wheel "
			"alignment is due around {next_alignment_date} or {next_alignment_km} km, "
			"and wheel balancing around {next_balancing_date} or {next_balancing_km} km.\n\n"
			"Keep your tyres performing at their best!\n\n"
			"_Refer a friend who isn't registered with us yet and earn ₹50 off "
			"your next service._"
		),
	},
	{
		"id": "win-back",
		"title": "Win Back Old Customers",
		"color": "cyan",
		"body": (
			"Dear {customer_name},\n\n"
			"If it has been some time since your last *wheel alignment* or "
			"*balancing*, we recommend getting it checked once.\n\n"
			"Timely alignment and balancing helps protect your tyres, improve "
			"driving comfort, and keep your vehicle safer on the road.\n\n"
			"Visit *ADARSH MOTOR STORES*, *Mehsana's* trusted tyre care shop.\n\n"
			"We will be happy to serve you again.\n\n\n"
			"*ADARSH MOTOR STORES (Since 1971)*\n"
			"#1 MRF and CEAT AUTHORIZED DEALER\n"
			"9825883600\n"
			"https://maps.app.goo.gl/mPcb4px9sbjjSaw67"
		),
	},
]


def _waha_config():
	conf = frappe.conf
	url = (conf.get("pos_prime_waha_url") or "http://host.docker.internal:3100").rstrip("/")
	session = conf.get("pos_prime_waha_session") or "default"
	api_key = conf.get("pos_prime_waha_api_key") or None
	return url, session, api_key


def _waha_headers(api_key):
	headers = {"Content-Type": "application/json"}
	if api_key:
		headers["X-Api-Key"] = api_key
	return headers


def _resolve_shop_name():
	"""Best-effort shop/company name for template placeholders.

	The Reminders page has no open shift, so the frontend can't rely on a loaded
	POS Profile — resolve a sensible company name server-side instead.
	"""
	company = frappe.defaults.get_global_default("company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)
	if not company:
		company = frappe.db.get_value("Company", {}, "name")
	return company or ""


def _normalize_phone(value):
	"""Return digits-only phone with an Indian country code for bare local numbers."""
	digits = re.sub(r"\D", "", str(value or ""))
	if len(digits) == 10:
		return "91" + digits
	if len(digits) == 11 and digits.startswith("0"):
		return "91" + digits[1:]
	return digits


# ---------------------------------------------------------------------------
# WhatsApp (WAHA) status & sending
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_whatsapp_status():
	"""Return whether the WAHA WhatsApp session is connected and ready to send."""
	validate_pos_access()
	import requests

	url, session, api_key = _waha_config()
	try:
		resp = requests.get(
			f"{url}/api/sessions/{session}",
			headers=_waha_headers(api_key),
			timeout=WAHA_TIMEOUT,
		)
		resp.raise_for_status()
		data = resp.json() or {}
	except Exception as e:  # noqa: BLE001 - surface a friendly status, never 500 the page
		return {
			"connected": False,
			"status": "UNREACHABLE",
			"error": str(e),
			"session": session,
			"shop_name": _resolve_shop_name(),
		}

	status = data.get("status") or "UNKNOWN"
	return {
		"connected": status == "WORKING",
		"status": status,
		"session": session,
		"dashboard_url": f"{url}/dashboard",
		"shop_name": _resolve_shop_name(),
	}


@frappe.whitelist()
def send_whatsapp_reminders(messages):
	"""Send one WhatsApp text per recipient via WAHA.

	`messages` is a JSON list of {customer, phone, text}. Returns a per-recipient
	result list so partial failures are visible; never throws on a single bad number.
	"""
	validate_pos_access()
	import requests

	if isinstance(messages, str):
		messages = json.loads(messages)
	if not isinstance(messages, list):
		frappe.throw(_("messages must be a list"))

	url, session, api_key = _waha_config()
	headers = _waha_headers(api_key)
	results = []
	sent = []

	for item in messages[:500]:
		customer = (item or {}).get("customer")
		raw_phone = (item or {}).get("phone")
		text = str((item or {}).get("text") or "").strip()
		phone = _normalize_phone(raw_phone)

		if not phone or len(phone) < 11:
			results.append({"customer": customer, "ok": False, "error": _("Invalid phone number")})
			continue
		if not text:
			results.append({"customer": customer, "ok": False, "error": _("Empty message")})
			continue

		try:
			resp = requests.post(
				f"{url}/api/sendText",
				headers=headers,
				json={"session": session, "chatId": f"{phone}@c.us", "text": text},
				timeout=WAHA_TIMEOUT,
			)
			if resp.status_code >= 400:
				detail = resp.text[:300]
				results.append({"customer": customer, "ok": False, "error": detail or f"HTTP {resp.status_code}"})
			else:
				results.append({"customer": customer, "ok": True})
				sent.append({"customer": customer, "phone": str(raw_phone or ""), "text": text})
		except Exception as e:  # noqa: BLE001
			results.append({"customer": customer, "ok": False, "error": str(e)})

	if sent:
		_record_sent_reminders(sent)

	return {"results": results}


RECENT_KEY = "pos_prime_recent_reminders"
RECENT_CAP = 50


def _record_sent_reminders(sent):
	"""Prepend successfully-messaged recipients to the recent-sent log (deduped)."""
	try:
		raw = frappe.db.get_default(RECENT_KEY)
		log = json.loads(raw) if raw else []
		if not isinstance(log, list):
			log = []
	except (ValueError, TypeError):
		log = []

	now_ts = now()
	for entry in sent:
		customer = entry.get("customer")
		if not customer:
			continue
		customer_name = frappe.db.get_value("Customer", customer, "customer_name") or customer
		mobile_no = entry.get("phone") or frappe.db.get_value("Customer", customer, "mobile_no") or ""
		log = [e for e in log if e.get("customer") != customer]
		log.insert(0, {
			"customer": customer,
			"customer_name": customer_name,
			"mobile_no": mobile_no,
			"text": (entry.get("text") or "")[:1000],
			"sent_at": now_ts,
		})

	frappe.db.set_default(RECENT_KEY, json.dumps(log[:RECENT_CAP]))


@frappe.whitelist()
def get_recent_reminders(limit=20):
	"""Return the most-recently-messaged recipients (newest first)."""
	validate_pos_access()
	try:
		limit = max(1, min(int(limit), RECENT_CAP))
	except (ValueError, TypeError):
		limit = 20
	raw = frappe.db.get_default(RECENT_KEY)
	try:
		log = json.loads(raw) if raw else []
	except (ValueError, TypeError):
		log = []
	return log[:limit] if isinstance(log, list) else []


# ---------------------------------------------------------------------------
# Templates (persisted globally in DefaultValue)
# ---------------------------------------------------------------------------

def _clean_templates(templates):
	cleaned = []
	for t in templates or []:
		title = str((t or {}).get("title") or "").strip()
		body = str((t or {}).get("body") or "").strip()
		if not title and not body:
			continue
		tid = str((t or {}).get("id") or "").strip() or frappe.generate_hash(length=10)
		color = str((t or {}).get("color") or "").strip()
		cleaned.append({"id": tid, "title": title or _("Untitled"), "body": body, "color": color})
	return cleaned


@frappe.whitelist()
def get_reminder_templates():
	"""Return saved reminder templates, seeding sensible defaults on first use."""
	validate_pos_access()
	raw = frappe.db.get_default(TEMPLATES_KEY)
	if raw:
		try:
			parsed = json.loads(raw)
			if isinstance(parsed, list) and parsed:
				return parsed
		except (ValueError, TypeError):
			pass
	return DEFAULT_TEMPLATES


@frappe.whitelist()
def save_reminder_templates(templates):
	"""Persist the reminder templates globally (shared across all terminals)."""
	validate_pos_access()
	if isinstance(templates, str):
		templates = json.loads(templates)
	cleaned = _clean_templates(templates)
	frappe.db.set_default(TEMPLATES_KEY, json.dumps(cleaned))
	return cleaned


# ---------------------------------------------------------------------------
# Customer picker
# ---------------------------------------------------------------------------

def _page_args(limit, offset, default_limit=50):
	"""Sanitise (limit, offset) for paginated list endpoints."""
	try:
		limit = int(limit)
	except (ValueError, TypeError):
		limit = default_limit
	try:
		offset = int(offset)
	except (ValueError, TypeError):
		offset = 0
	return max(1, min(limit, 200)), max(0, offset)


@frappe.whitelist()
def list_customers(search="", pos_profile="", limit=50, offset=0):
	"""Search customers for the reminders picker, returning the best WhatsApp number.

	Mirrors the phone-normalisation + POS customer-group filtering of
	customers.search_customers, and additionally returns custom_whatsapp when present.
	Supports `offset` for infinite-scroll pagination.
	"""
	validate_pos_access(pos_profile or None)

	limit, offset = _page_args(limit, offset, default_limit=50)

	has_whatsapp = frappe.db.has_column("Customer", "custom_whatsapp")
	whatsapp_select = ", custom_whatsapp" if has_whatsapp else ""

	params = {"limit": limit, "offset": offset}
	where = ["disabled = 0"]

	# Optional POS Profile customer-group restriction (same as search_customers)
	if pos_profile:
		profile_groups = frappe.get_all(
			"POS Customer Group",
			filters={"parent": pos_profile, "parenttype": "POS Profile"},
			pluck="customer_group",
		)
		if profile_groups:
			where.append("customer_group IN %(groups)s")
			params["groups"] = profile_groups

	search = (search or "").strip()
	if search:
		params["search"] = f"%{search}%"
		conditions = [
			"customer_name LIKE %(search)s",
			"name LIKE %(search)s",
			"mobile_no LIKE %(search)s",
			"email_id LIKE %(search)s",
		]
		digits_only = re.sub(r"\D", "", search)
		if len(digits_only) >= 7:
			params["phone_suffix"] = f"%{digits_only[-9:]}"
			conditions.append("mobile_no LIKE %(phone_suffix)s")
			if has_whatsapp:
				conditions.append("custom_whatsapp LIKE %(phone_suffix)s")
		where.append("(" + " OR ".join(conditions) + ")")

	rows = frappe.db.sql(
		f"""
		SELECT name, customer_name, mobile_no, email_id{whatsapp_select}
		FROM `tabCustomer`
		WHERE {" AND ".join(where)}
		ORDER BY customer_name ASC
		LIMIT %(limit)s OFFSET %(offset)s
		""",
		params,
		as_dict=True,
	)
	return rows


@frappe.whitelist()
def recently_added_customers(pos_profile="", limit=20, offset=0):
	"""Customers ordered by creation (newest first) for the 'Recently Added' tab.

	Supports `offset` for infinite-scroll pagination.
	"""
	validate_pos_access(pos_profile or None)

	limit, offset = _page_args(limit, offset, default_limit=20)

	has_whatsapp = frappe.db.has_column("Customer", "custom_whatsapp")
	whatsapp_select = ", custom_whatsapp" if has_whatsapp else ""

	params = {"limit": limit, "offset": offset}
	where = ["disabled = 0"]
	if pos_profile:
		profile_groups = frappe.get_all(
			"POS Customer Group",
			filters={"parent": pos_profile, "parenttype": "POS Profile"},
			pluck="customer_group",
		)
		if profile_groups:
			where.append("customer_group IN %(groups)s")
			params["groups"] = profile_groups

	return frappe.db.sql(
		f"""
		SELECT name, customer_name, mobile_no, email_id{whatsapp_select}
		FROM `tabCustomer`
		WHERE {" AND ".join(where)}
		ORDER BY creation DESC
		LIMIT %(limit)s OFFSET %(offset)s
		""",
		params,
		as_dict=True,
	)


# ---------------------------------------------------------------------------
# Data-driven car context (next service due, derived from Customer Car data)
# ---------------------------------------------------------------------------

def _primary_car(customer):
	"""Return the customer's primary Customer Car detail dict, or None.

	Primary = first row of Customer.custom_cars (same source as
	customers.get_customer_cars). Returns None gracefully when the Express Tally
	car doctypes aren't installed or the customer has no car.
	"""
	if not frappe.db.exists("DocType", "Customer Car Link") or not frappe.db.exists(
		"DocType", "Customer Car"
	):
		return None
	links = frappe.get_all(
		"Customer Car Link",
		filters={"parent": customer, "parenttype": "Customer", "parentfield": "custom_cars"},
		fields=["car"],
		order_by="idx asc",
		limit_page_length=1,
	)
	if not links or not links[0].get("car"):
		return None
	return frappe.db.get_value(
		"Customer Car",
		links[0].car,
		["registration_number", "make_model", "current_odometer", "monthly_driven"],
		as_dict=True,
	)


def _service_context(car):
	"""Compute next alignment/balancing km + dates from a car's odometer & usage."""
	conf = frappe.conf
	alignment_km = flt(conf.get("pos_prime_alignment_km")) or 5000
	balancing_km = flt(conf.get("pos_prime_balancing_km")) or 10000
	fallback_months = int(flt(conf.get("pos_prime_usage_fallback_months")) or 6)

	odometer = flt((car or {}).get("current_odometer"))
	monthly = flt((car or {}).get("monthly_driven"))

	def due_date(interval_km):
		if monthly > 0:
			days = round(interval_km * 30.44 / monthly)
			return formatdate(add_days(nowdate(), days))
		return formatdate(add_months(nowdate(), fallback_months))

	def km(value):
		return f"{int(round(value)):,}"

	return {
		"vehicle": (car or {}).get("make_model") or (car or {}).get("registration_number") or "",
		"registration": (car or {}).get("registration_number") or "",
		"odometer": km(odometer) if odometer else "",
		"monthly_driven": km(monthly) if monthly else "",
		"next_alignment_km": km(odometer + alignment_km),
		"next_balancing_km": km(odometer + balancing_km),
		"next_alignment_date": due_date(alignment_km),
		"next_balancing_date": due_date(balancing_km),
	}


def _empty_service_context():
	return {
		"vehicle": "",
		"registration": "",
		"odometer": "",
		"monthly_driven": "",
		"next_alignment_km": "",
		"next_balancing_km": "",
		"next_alignment_date": "",
		"next_balancing_date": "",
	}


@frappe.whitelist()
def get_reminder_car_context(customers):
	"""Per-customer service-due context for the data-driven reminder template.

	`customers` is a JSON list of customer names. Returns a map keyed by name with
	the computed placeholders. Customers without a car get blank values.
	"""
	validate_pos_access()
	if isinstance(customers, str):
		customers = json.loads(customers)
	if not isinstance(customers, list):
		frappe.throw(_("customers must be a list"))

	context = {}
	for name in customers[:500]:
		if not name or not frappe.db.exists("Customer", name):
			context[name] = _empty_service_context()
			continue
		car = _primary_car(name)
		context[name] = _service_context(car) if car else _empty_service_context()
	return context
