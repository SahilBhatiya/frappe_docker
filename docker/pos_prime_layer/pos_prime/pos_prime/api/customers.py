# Copyright (c) 2026, Ravindu Gajanayaka
# Licensed under GPLv3. See license.txt

import re
import frappe
from frappe import _
from frappe.utils import flt
from pos_prime.api._utils import validate_pos_access


@frappe.whitelist()
def search_customers(search_term="", pos_profile=""):
    """Search customers by name, phone, or email.

    If pos_profile has customer_groups configured, only returns customers
    belonging to those groups.

    Phone numbers are normalized so local format (07xxxxxxxx) matches
    international format (+947xxxxxxxx) and vice versa.
    """
    validate_pos_access(pos_profile or None)
    if not search_term or len(search_term) < 2:
        return []

    search = f"%{search_term}%"

    # Normalize phone: extract last 9 digits to match regardless of country code
    digits_only = re.sub(r"\D", "", search_term)
    phone_suffix_condition = ""
    params = {"search": search}

    if len(digits_only) >= 7:
        core_digits = digits_only[-9:]
        params["phone_suffix"] = f"%{core_digits}"
        phone_suffix_condition = "OR mobile_no LIKE %(phone_suffix)s"

    # Check if POS Profile restricts customer groups
    group_filter = ""

    if pos_profile:
        profile_groups = frappe.get_all(
            "POS Customer Group",
            filters={"parent": pos_profile, "parenttype": "POS Profile"},
            pluck="customer_group",
        )
        if profile_groups:
            group_filter = "AND customer_group IN %(groups)s"
            params["groups"] = profile_groups

    customers = frappe.db.sql(
        f"""
        SELECT name, customer_name, mobile_no, email_id
        FROM `tabCustomer`
        WHERE disabled = 0
        {group_filter}
        AND (
            customer_name LIKE %(search)s
            OR name LIKE %(search)s
            OR mobile_no LIKE %(search)s
            OR email_id LIKE %(search)s
            {phone_suffix_condition}
        )
        ORDER BY customer_name ASC
        LIMIT 20
    """,
        params,
        as_dict=True,
    )

    return customers


@frappe.whitelist()
def get_recent_customers(pos_profile="", limit=20):
    """Return customers who had recent POS invoices, ordered by latest transaction.

    If pos_profile is provided, only returns customers with invoices from that
    profile's company, and respects customer_group filtering.
    """
    validate_pos_access(pos_profile or None)
    params = {"limit": int(limit)}
    company_filter = ""
    group_filter = ""

    if pos_profile:
        company = frappe.db.get_value("POS Profile", pos_profile, "company")
        if company:
            company_filter = "AND inv.company = %(company)s"
            params["company"] = company

        profile_groups = frappe.get_all(
            "POS Customer Group",
            filters={"parent": pos_profile, "parenttype": "POS Profile"},
            pluck="customer_group",
        )
        if profile_groups:
            group_filter = "AND c.customer_group IN %(groups)s"
            params["groups"] = profile_groups

    return frappe.db.sql(
        f"""
        SELECT c.name, c.customer_name, c.mobile_no, c.email_id,
               MAX(inv.posting_date) AS last_invoice_date
        FROM `tabCustomer` c
        INNER JOIN `tabPOS Invoice` inv ON inv.customer = c.name
        WHERE c.disabled = 0
          AND inv.docstatus = 1
          {company_filter}
          {group_filter}
        GROUP BY c.name
        ORDER BY last_invoice_date DESC
        LIMIT %(limit)s
    """,
        params,
        as_dict=True,
    )

@frappe.whitelist()
def get_top_customers(pos_profile="", limit=100):
    """Return top customers ordered by creation date."""
    validate_pos_access(pos_profile or None)
    params = {"limit": int(limit)}
    group_filter = ""

    if pos_profile:
        profile_groups = frappe.get_all(
            "POS Customer Group",
            filters={"parent": pos_profile, "parenttype": "POS Profile"},
            pluck="customer_group",
        )
        if profile_groups:
            group_filter = "AND customer_group IN %(groups)s"
            params["groups"] = profile_groups

    return frappe.db.sql(
        f"""
        SELECT name, customer_name, mobile_no, email_id
        FROM `tabCustomer`
        WHERE disabled = 0
        {group_filter}
        ORDER BY creation DESC
        LIMIT %(limit)s
    """,
        params,
        as_dict=True,
    )



@frappe.whitelist()
def get_customer(customer_name):
    """Get customer details for POS.

    Returns essential customer fields without requiring direct Customer
    doctype read permission (uses ignore_permissions internally).
    """
    validate_pos_access()
    if not frappe.db.exists("Customer", customer_name):
        frappe.throw(_("Customer {0} does not exist").format(customer_name))

    fields = [
        "name", "customer_name", "email_id", "mobile_no",
        "loyalty_program", "territory", "customer_group", "tax_id",
    ]
    # custom_whatsapp is shipped by this app's patch; guard for installs that
    # haven't migrated yet so get_value doesn't error on a missing column.
    if frappe.db.has_column("Customer", "custom_whatsapp"):
        fields.append("custom_whatsapp")
    # GST fields (india_compliance). Guarded so the API works on non-India sites.
    for gst_field in ("gstin", "gst_category"):
        if frappe.db.has_column("Customer", gst_field):
            fields.append(gst_field)

    data = frappe.db.get_value("Customer", customer_name, fields, as_dict=True)
    return data


@frappe.whitelist()
def get_customer_cars(customer):
    """Return the customer's cars (from the Customer.custom_cars child table).

    Each row links to a Customer Car record; we enrich it with that record's
    registration, make/model, odometer and notes so the POS can show them.
    Returns [] gracefully on installs without the Express Tally car doctypes.
    """
    validate_pos_access()
    if not customer or not frappe.db.exists("DocType", "Customer Car Link"):
        return []
    if not frappe.db.exists("Customer", customer):
        return []

    links = frappe.get_all(
        "Customer Car Link",
        filters={
            "parent": customer,
            "parenttype": "Customer",
            "parentfield": "custom_cars",
        },
        fields=["car", "make_model"],
        order_by="idx asc",
    )

    cars = []
    for link in links:
        car_name = link.get("car")
        detail = {}
        if car_name and frappe.db.exists("Customer Car", car_name):
            detail = frappe.db.get_value(
                "Customer Car",
                car_name,
                ["registration_number", "make_model", "current_odometer", "monthly_driven", "notes"],
                as_dict=True,
            ) or {}
        cars.append({
            "name": car_name,
            "registration_number": detail.get("registration_number") or "",
            "make_model": detail.get("make_model") or link.get("make_model") or "",
            "current_odometer": detail.get("current_odometer") or 0,
            "monthly_driven": detail.get("monthly_driven") or 0,
            "notes": detail.get("notes") or "",
        })
    return cars


@frappe.whitelist()
def create_customer_car(customer, registration_number, make_model="", current_odometer=0,
                        monthly_driven=0, notes=""):
    """Create a Customer Car and link it to the selected Customer."""
    validate_pos_access()
    if not customer or not frappe.db.exists("Customer", customer):
        frappe.throw(_("Customer does not exist"))
    if not registration_number or not str(registration_number).strip():
        frappe.throw(_("Registration number is required"))
    if not frappe.db.exists("DocType", "Customer Car") or not frappe.db.exists(
        "DocType", "Customer Car Link"
    ):
        frappe.throw(_("Customer car records are not configured on this site"))

    customer_meta = frappe.get_meta("Customer")
    if not customer_meta.has_field("custom_cars"):
        frappe.throw(_("Customer car links are not configured on this site"))

    car = frappe.new_doc("Customer Car")
    values = {
        "registration_number": str(registration_number).strip(),
        "make_model": str(make_model or "").strip(),
        "current_odometer": flt(current_odometer),
        "monthly_driven": flt(monthly_driven),
        "notes": str(notes or "").strip(),
    }
    car_meta = frappe.get_meta("Customer Car")
    for fieldname, value in values.items():
        if car_meta.has_field(fieldname):
            car.set(fieldname, value)
    car.insert(ignore_permissions=True)

    customer_doc = frappe.get_doc("Customer", customer)
    customer_doc.append(
        "custom_cars",
        {"car": car.name, "make_model": values["make_model"]},
    )
    customer_doc.save(ignore_permissions=True)
    return {
        "name": car.name,
        **values,
    }


@frappe.whitelist()
def update_customer_car(customer, car, registration_number, make_model="", current_odometer=0,
                        monthly_driven=0, notes=""):
    """Update a car only when it is linked to the selected customer."""
    validate_pos_access()
    if not customer or not frappe.db.exists("Customer", customer):
        frappe.throw(_("Customer does not exist"))
    if not car or not frappe.db.exists("Customer Car", car):
        frappe.throw(_("Car does not exist"))
    if not registration_number or not str(registration_number).strip():
        frappe.throw(_("Registration number is required"))

    car_link = frappe.db.exists(
        "Customer Car Link",
        {
            "parent": customer,
            "parenttype": "Customer",
            "parentfield": "custom_cars",
            "car": car,
        },
    )
    if not car_link:
        frappe.throw(
            _("This car is not linked to the selected customer"),
            frappe.PermissionError,
        )

    values = {
        "registration_number": str(registration_number).strip(),
        "make_model": str(make_model or "").strip(),
        "current_odometer": flt(current_odometer),
        "monthly_driven": flt(monthly_driven),
        "notes": str(notes or "").strip(),
    }
    car_doc = frappe.get_doc("Customer Car", car)
    car_meta = frappe.get_meta("Customer Car")
    for fieldname, value in values.items():
        if car_meta.has_field(fieldname):
            car_doc.set(fieldname, value)
    car_doc.save(ignore_permissions=True)

    frappe.db.set_value("Customer Car Link", car_link, "make_model", values["make_model"])
    return {"name": car_doc.name, **values}


@frappe.whitelist()
def get_quick_entry_options(pos_profile=""):
    """Return dropdown options needed for the new-customer quick entry dialog.

    Returns customer_groups, customer_type options, and quick_entry fields
    from the Customer doctype meta so the frontend can render a matching form.
    """
    validate_pos_access(pos_profile or None)

    # Customer groups — prefer POS Profile groups, fall back to leaf groups
    customer_groups = []
    if pos_profile:
        customer_groups = frappe.get_all(
            "POS Customer Group",
            filters={"parent": pos_profile, "parenttype": "POS Profile"},
            pluck="customer_group",
        )
    if not customer_groups:
        customer_groups = frappe.get_list(
            "Customer Group",
            filters={"is_group": 0},
            pluck="name",
            order_by="name asc",
            limit_page_length=50,
        )

    # Customer type options from the Select field
    meta = frappe.get_meta("Customer")
    ct_field = meta.get_field("customer_type")
    customer_types = (ct_field.options or "").split("\n") if ct_field else ["Individual"]

    # Quick entry fields (reqd or allow_in_quick_entry)
    quick_fields = []
    for f in meta.fields:
        if (f.reqd or f.allow_in_quick_entry) and not f.read_only and f.fieldtype not in (
            "Tab Break", "Section Break", "Column Break", "Table",
        ):
            quick_fields.append({
                "fieldname": f.fieldname,
                "label": f.label,
                "fieldtype": f.fieldtype,
                "options": f.options,
                "reqd": f.reqd,
                "default": f.default,
            })

    # Country options for address
    countries = frappe.get_list(
        "Country", pluck="name", order_by="name asc", limit_page_length=0,
    )

    # Default country from system settings
    default_country = frappe.db.get_default("country") or ""

    # Defaults
    default_group = (
        frappe.db.get_single_value("Selling Settings", "customer_group")
        or (customer_groups[0] if customer_groups else "")
    )

    return {
        "customer_groups": customer_groups,
        "customer_types": [t for t in customer_types if t.strip()],
        "quick_fields": quick_fields,
        "default_customer_group": default_group,
        "default_customer_type": "Individual",
        "default_territory": frappe.db.get_single_value("Selling Settings", "territory")
            or "All Territories",
        "countries": countries,
        "default_country": default_country,
    }


@frappe.whitelist()
def quick_create_customer(customer_name, mobile_no=None, email_id=None,
                          customer_type=None, customer_group=None,
                          territory=None, pos_profile="",
                          first_name=None, last_name=None,
                          address_line1=None, address_line2=None,
                          city=None, state=None, pincode=None, country=None,
                          gstin=None, gst_category=None,
                          **extra_fields):
    """Create a customer record from the POS quick entry dialog.

    Accepts all quick_entry fields from the Customer doctype plus
    contact (first_name, last_name) and address fields. ERPNext's
    Customer on_update hook auto-creates Contact and Address records.
    """
    validate_pos_access(pos_profile or None)
    if not customer_name or not customer_name.strip():
        frappe.throw(_("Customer name is required"))

    customer_name = customer_name.strip()

    if len(customer_name) > 140:
        frappe.throw(_("Customer name must not exceed 140 characters"))

    if email_id:
        email_pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
        if not re.match(email_pattern, email_id):
            frappe.throw(_("Invalid email address format"))

    # Resolve defaults
    if not customer_group and pos_profile:
        profile_groups = frappe.get_all(
            "POS Customer Group",
            filters={"parent": pos_profile, "parenttype": "POS Profile"},
            pluck="customer_group",
            limit=1,
        )
        if profile_groups:
            customer_group = profile_groups[0]

    doc_data = {
        "doctype": "Customer",
        "customer_name": customer_name,
        "customer_type": customer_type or "Individual",
        "customer_group": customer_group
            or frappe.db.get_single_value("Selling Settings", "customer_group")
            or "All Customer Groups",
        "territory": territory
            or frappe.db.get_single_value("Selling Settings", "territory")
            or "All Territories",
    }

    if mobile_no:
        doc_data["mobile_no"] = mobile_no
    if email_id:
        doc_data["email_id"] = email_id

    # Contact name fields — Customer on_update uses these to create Contact
    if first_name:
        doc_data["first_name"] = first_name
    if last_name:
        doc_data["last_name"] = last_name

    # Address fields — Customer on_update uses these to create Address
    if address_line1:
        doc_data["address_line1"] = address_line1
    if address_line2:
        doc_data["address_line2"] = address_line2
    if city:
        doc_data["city"] = city
    if state:
        doc_data["state"] = state
    if pincode:
        doc_data["pincode"] = pincode
    if country:
        doc_data["country"] = country

    meta = frappe.get_meta("Customer")

    # GST (india_compliance). GSTIN is validated by india_compliance on insert.
    # A registered GSTIN implies a registered category if none was supplied.
    if gstin and meta.has_field("gstin"):
        doc_data["gstin"] = str(gstin).strip().upper()
        if not gst_category:
            gst_category = "Registered Regular"
    if gst_category and meta.has_field("gst_category"):
        doc_data["gst_category"] = gst_category

    # Apply any extra quick_entry fields (e.g. custom_nic_number)
    allowed_quick = {
        f.fieldname for f in meta.fields
        if (f.reqd or f.allow_in_quick_entry)
        and not f.read_only
        and f.fieldtype not in ("Tab Break", "Section Break", "Column Break", "Table")
    }
    for key, value in extra_fields.items():
        if key in allowed_quick and value:
            doc_data[key] = value

    # Referral capture: record who referred this customer (read-only field, so it
    # isn't picked up by the quick-entry loop above).
    referred_by = extra_fields.get("custom_referred_by")
    if (
        referred_by
        and meta.has_field("custom_referred_by")
        and referred_by != customer_name
        and frappe.db.exists("Customer", referred_by)
    ):
        doc_data["custom_referred_by"] = referred_by

    customer = frappe.get_doc(doc_data)
    customer.insert(ignore_permissions=True)

    return customer.name


@frappe.whitelist()
def update_customer_field(customer, fieldname, value=""):
    """Update a customer contact field from POS.

    Mirrors ERPNext's built-in POS approach: updates both the Contact doctype
    (primary contact with email_ids/phone_nos child tables) and the Customer
    doctype's denormalized fields.
    """
    validate_pos_access()

    allowed_fields = {"email_id", "mobile_no", "loyalty_program", "custom_whatsapp", "custom_referred_by", "gstin", "gst_category"}
    if fieldname not in allowed_fields:
        frappe.throw(_("Field {0} cannot be updated from POS").format(fieldname))

    if not frappe.db.exists("Customer", customer):
        frappe.throw(_("Customer {0} does not exist").format(customer))

    if fieldname == "email_id" and value:
        email_pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
        if not re.match(email_pattern, value):
            frappe.throw(_("Invalid email address format"))

    if fieldname == "custom_referred_by":
        if value and value == customer:
            frappe.throw(_("A customer cannot be referred by themselves"))
        if value and not frappe.db.exists("Customer", value):
            frappe.throw(_("Referrer {0} does not exist").format(value))

    # GST fields go through the Customer doc so india_compliance validates the
    # GSTIN format/checksum and keeps gst_category consistent.
    if fieldname in ("gstin", "gst_category"):
        cust_doc = frappe.get_doc("Customer", customer)
        new_value = (value or "").strip().upper() if fieldname == "gstin" else (value or None)
        cust_doc.set(fieldname, new_value or None)
        if fieldname == "gstin" and new_value and not cust_doc.get("gst_category"):
            cust_doc.gst_category = "Registered Regular"
        cust_doc.save(ignore_permissions=True)
        return customer

    # Plain Customer fields (not mirrored onto the primary Contact).
    if fieldname in ("loyalty_program", "custom_whatsapp", "custom_referred_by"):
        frappe.db.set_value("Customer", customer, fieldname, value or None)
        return customer

    # Get or create primary contact (same logic as ERPNext's set_customer_info)
    contact = frappe.get_cached_value("Customer", customer, "customer_primary_contact")

    if not contact:
        contacts = frappe.db.sql(
            """
            SELECT parent FROM `tabDynamic Link`
            WHERE parenttype = 'Contact'
              AND parentfield = 'links'
              AND link_doctype = 'Customer'
              AND link_name = %s
            """,
            (customer,),
            as_dict=True,
        )
        contact = contacts[0].get("parent") if contacts else None

    if not contact:
        new_contact = frappe.new_doc("Contact")
        new_contact.is_primary_contact = 1
        new_contact.first_name = frappe.db.get_value("Customer", customer, "customer_name") or customer
        new_contact.set("links", [{"link_doctype": "Customer", "link_name": customer}])
        new_contact.save(ignore_permissions=True)
        contact = new_contact.name
        frappe.db.set_value("Customer", customer, "customer_primary_contact", contact)

    # Update the Contact doctype and Customer denormalized field
    contact_doc = frappe.get_doc("Contact", contact)

    if fieldname == "email_id":
        contact_doc.set("email_ids", [{"email_id": value, "is_primary": 1}] if value else [])
        frappe.db.set_value("Customer", customer, "email_id", value)
    elif fieldname == "mobile_no":
        contact_doc.set("phone_nos", [{"phone": value, "is_primary_mobile_no": 1}] if value else [])
        frappe.db.set_value("Customer", customer, "mobile_no", value)

    contact_doc.save(ignore_permissions=True)

    return customer


@frappe.whitelist()
def get_referral_summary(customer):
    """Referral info for a customer: who referred them, their accrued referral
    credit (as a referrer), and how many customers they've referred."""
    validate_pos_access()
    if not frappe.db.exists("Customer", customer):
        frappe.throw(_("Customer {0} does not exist").format(customer))

    meta = frappe.get_meta("Customer")
    if not meta.has_field("custom_referred_by"):
        return {"referred_by": None, "referred_by_name": None, "referral_credit": 0, "referred_count": 0}

    referred_by = frappe.db.get_value("Customer", customer, "custom_referred_by")
    referred_by_name = (
        frappe.db.get_value("Customer", referred_by, "customer_name") if referred_by else None
    )
    return {
        "referred_by": referred_by,
        "referred_by_name": referred_by_name,
        "referral_credit": flt(frappe.db.get_value("Customer", customer, "custom_referral_credit")),
        "referred_count": frappe.db.count("Customer", {"custom_referred_by": customer}),
    }
