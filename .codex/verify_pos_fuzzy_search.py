import frappe

from erpnext.selling.page.point_of_sale.point_of_sale import get_items, get_parent_item_group


def main():
	frappe.init(site="erpnext.localhost", sites_path="/home/frappe/frappe-bench/sites")
	frappe.connect()

	try:
		profile = frappe.db.get_value(
			"POS Profile",
			{},
			["name", "selling_price_list"],
			as_dict=True,
		)
		if not profile:
			print("No POS Profile found")
			return

		item_group = get_parent_item_group(profile.name)
		for term in ("4008", "4008m", "4008m 99"):
			result = get_items(
				start=0,
				page_length=12,
				price_list=profile.selling_price_list,
				item_group=item_group,
				pos_profile=profile.name,
				search_term=term,
			)
			items = result.get("items", [])
			print(f"{term}: {len(items)} result(s)")
			for item in items[:8]:
				print(f"  {item.get('item_code')} | {item.get('item_name')}")
	finally:
		frappe.destroy()


if __name__ == "__main__":
	main()
