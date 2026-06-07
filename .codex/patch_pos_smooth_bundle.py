from pathlib import Path


bundle_path = Path(".codex/point-of-sale.live.js")
bundle = bundle_path.read_text(encoding="utf-8")

replacements = {
	"async on_cart_update(e){frappe.dom.freeze(),this.frm.doc.set_warehouse!==this.settings.warehouse&&this.frm.set_value": "async on_cart_update(e){this.frm.doc.set_warehouse!==this.settings.warehouse&&this.frm.set_value",
	"finally{return frappe.dom.unfreeze(),t}}raise_customer_selection_alert(){frappe.dom.unfreeze(),frappe.show_alert": "finally{return t}}raise_customer_selection_alert(){frappe.show_alert",
	"remove_item_from_cart(){frappe.dom.freeze();let{doctype:e,name:t,current_item:i}=this.item_details;return frappe.model.set_value(e,t,\"qty\",0).then(()=>{frappe.model.clear_doc(e,t),this.update_cart_html(i,!0),this.item_details.toggle_item_details_section(null),frappe.dom.unfreeze()}).catch(s=>console.log(s))}": "remove_item_from_cart(){let{doctype:e,name:t,current_item:i}=this.item_details;return frappe.model.set_value(e,t,\"qty\",0).then(()=>{frappe.model.clear_doc(e,t),this.update_cart_html(i,!0),this.item_details.toggle_item_details_section(null)}).catch(s=>console.log(s))}",
}

for old, new in replacements.items():
	if old not in bundle:
		raise SystemExit(f"Could not find expected bundle text: {old[:80]}")
	bundle = bundle.replace(old, new, 1)

bundle_path.write_text(bundle, encoding="utf-8")
print("patched smooth POS bundle", len(bundle))
