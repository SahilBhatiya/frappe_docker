from pathlib import Path


bundle_path = Path(".codex/point-of-sale.live.js")
bundle = bundle_path.read_text(encoding="utf-8")


def replace_once(source, old, new, label):
	if old not in source:
		raise SystemExit(f"Could not find bundle section: {label}")
	return source.replace(old, new, 1)


bundle = replace_once(
	bundle,
	'keys:[[1,2,3,"Quantity"],[4,5,6,"Discount"],[7,8,9,"Rate"],[".",0,"Delete","Remove"]],css_classes:[["","","","col-span-2"],["","","","col-span-2"],["","","","col-span-2"],["","","","col-span-2 remove-btn"]],fieldnames_map:{Quantity:"qty",Discount:"discount_percentage"}})',
	'keys:[[1,2,3,"Quantity"],[4,5,6,"Discount"],[7,8,9,"Rate"],[".",0,"Delete","Total"],["Remove"]],css_classes:[["","","","col-span-2"],["","","","col-span-2"],["","","","col-span-2"],["","","","col-span-2"],["col-span-5 remove-btn"]],fieldnames_map:{Quantity:"qty",Discount:"discount_percentage",Total:"pos_total_amount"}})',
	"cart numpad keys",
)

start = bundle.index("on_numpad_event(e){")
end = bundle.index("highlight_numpad_btn(e,t){", start)
bundle = (
	bundle[:start]
	+ '''on_numpad_event(e){let t=e.attr("data-button-value"),i=["qty","discount_percentage","rate","pos_total_amount"].includes(t),s=i?["rate","pos_total_amount"].includes(t)&&this.allow_rate_change||t=="discount_percentage"&&this.allow_discount_change||t=="qty":!0,n=this.prev_action===t,a=!this.prev_action,o=this.prev_action&&this.prev_action!=t;if(i){if(!s){let c=t=="rate"?"Rate".bold():t=="pos_total_amount"?"Total".bold():"Discount".bold(),_=__("Editing {0} is not allowed as per POS Profile settings",[c]);frappe.show_alert({indicator:"red",message:_}),frappe.utils.play_sound("error");return}this.highlight_numpad_btn(e,t),a||o?this.prev_action=t:n&&(this.prev_action=void 0),this.numpad_value=""}else if(t==="checkout"){this.prev_action=void 0,this.toggle_item_highlight(),this.events.numpad_event(void 0,t);return}else if(t==="remove"){this.prev_action=void 0,this.toggle_item_highlight(),this.events.numpad_event(void 0,t);return}else this.numpad_value=t==="delete"?this.numpad_value.slice(0,-1):this.numpad_value+t,this.numpad_value=this.numpad_value||0;if(!i&&a){frappe.show_alert({indicator:"red",message:__("Please select a field to edit from numpad")}),frappe.utils.play_sound("error");return}flt(this.numpad_value)>100&&this.prev_action==="discount_percentage"&&(frappe.show_alert({message:__("Discount cannot be greater than 100%"),indicator:"orange"}),frappe.utils.play_sound("error"),this.numpad_value=t),this.events.numpad_event(this.numpad_value,this.prev_action)}'''
	+ bundle[end:]
)

bundle = replace_once(
	bundle,
	'let i=e.hasClass("highlighted-numpad-btn"),s=["qty","discount_percentage","rate","done"].includes(t);',
	'let i=e.hasClass("highlighted-numpad-btn"),s=["qty","discount_percentage","rate","pos_total_amount","done"].includes(t);',
	"highlight numpad actions",
)

bundle = replace_once(
	bundle,
	'toggle_numpad_field_edit(e){["qty","discount_percentage","rate"].includes(e)&&this.$numpad_section.find(`[data-button-value="${e}"]`).click()}',
	'toggle_numpad_field_edit(e){["qty","discount_percentage","rate","pos_total_amount"].includes(e)&&this.$numpad_section.find(`[data-button-value="${e}"]`).click()}',
	"field focus map",
)

start = bundle.index("render_form(e){", bundle.index("erpnext.PointOfSale.ItemDetails=class"))
end = bundle.index("resize_serial_control(e){", start)
bundle = (
	bundle[:start]
	+ '''render_form(e){let t=this.get_form_fields(e);this.$form_container.html(""),t.forEach((i,s)=>{this.$form_container.append(`<div class="${i}-control" data-fieldname="${i}"></div>`);let n=i==="pos_total_amount"?this.get_total_amount_field():this.item_meta.fields.find(o=>o.fieldname===i);i==="discount_percentage"&&(n.label=__("Discount (%)"));let a=this;this[`${i}_control`]=frappe.ui.form.make_control({df:u(m({},n),{onchange:function(){i==="pos_total_amount"?a.updating_total_amount_control||a.update_rate_from_total_amount(this.value):a.events.form_updated(a.current_item,i,this.value)}}),parent:this.$form_container.find(`.${i}-control`),render_input:!0});let o=i==="pos_total_amount"?this.get_total_amount_value(e):e[i];this[`${i}_control`].set_value(o)}),this.resize_serial_control(e),this.make_auto_serial_selection_btn(e),this.bind_custom_control_change_event()}get_form_fields(e){let t=["qty","uom","rate","pos_total_amount","description","conversion_factor","discount_percentage","warehouse","actual_qty","price_list_rate"];return(e.has_serial_no||e.serial_no)&&t.push("serial_no"),(e.has_batch_no||e.batch_no)&&t.push("batch_no"),t}get_total_amount_field(){return{fieldname:"pos_total_amount",fieldtype:"Currency",label:__("Total Price"),options:"currency"}}get_total_amount_value(e){return flt(e.amount||flt(e.qty)*flt(e.rate),2)}update_total_amount_control(e){this.pos_total_amount_control&&(this.updating_total_amount_control=!0,this.pos_total_amount_control.set_value(this.get_total_amount_value(e)),this.updating_total_amount_control=!1)}update_rate_from_total_amount(e){let t=flt(this.qty_control&&this.qty_control.get_value())||flt(this.current_item.qty);if(!t)return;let i=flt(e)/t;return this.events.form_updated(this.current_item,"rate",i).then(()=>{let s=frappe.get_doc(this.doctype,this.name),n=this.events.get_frm().doc;this.rate_control&&this.rate_control.set_value(s.rate),this.$item_price.html(format_currency(s.rate,n.currency)),this.render_discount_dom(s),this.update_total_amount_control(s)})}'''
	+ bundle[end:]
)

start = bundle.index("bind_custom_control_change_event(){", bundle.index("erpnext.PointOfSale.ItemDetails=class"))
end = bundle.index("async auto_update_batch_no(){", start)
bundle = (
	bundle[:start]
	+ '''bind_custom_control_change_event(){let e=this;this.qty_control&&(this.qty_control.df.onchange=function(){(this.value||flt(this.value)===0)&&e.events.form_updated(e.current_item,"qty",this.value).then(()=>{let i=frappe.get_doc(e.doctype,e.name);e.update_total_amount_control(i)})},this.qty_control.refresh()),this.rate_control&&(this.rate_control.df.onchange=function(){(this.value||flt(this.value)===0)&&e.events.form_updated(e.current_item,"rate",this.value).then(()=>{let i=frappe.get_doc(e.doctype,e.name),s=e.events.get_frm().doc;e.$item_price.html(format_currency(i.rate,s.currency)),e.render_discount_dom(i),e.update_total_amount_control(i)})},this.rate_control.df.read_only=!this.allow_rate_change,this.rate_control.refresh()),this.discount_percentage_control&&!this.allow_discount_change&&(this.discount_percentage_control.df.read_only=1,this.discount_percentage_control.refresh()),this.warehouse_control&&(this.warehouse_control.df.reqd=1,this.warehouse_control.df.onchange=function(){this.value&&e.events.form_updated(e.current_item,"warehouse",this.value).then(()=>{e.item_stock_map=e.events.get_item_stock_map();let i=e.item_stock_map[e.item_row.item_code][this.value][0],s=Boolean(e.item_stock_map[e.item_row.item_code][this.value][1]);if(i===void 0)e.events.get_available_stock(e.item_row.item_code,this.value).then(()=>{e.warehouse_control.set_value(this.value)});else if(i===0&&s){e.warehouse_control.set_value("");let n=e.item_row.item_code.bold(),a=this.value.bold();frappe.throw(__("Item Code: {0} is not available under warehouse {1}.",[n,a]))}e.actual_qty_control.set_value(i)})},this.warehouse_control.df.get_query=()=>({filters:{company:this.events.get_frm().doc.company,is_group:0}}),this.warehouse_control.refresh()),this.serial_no_control&&(this.serial_no_control.df.reqd=1,this.serial_no_control.df.onchange=async function(){!e.current_item.batch_no&&await e.auto_update_batch_no(),e.events.form_updated(e.current_item,"serial_no",this.value)},this.serial_no_control.refresh()),this.batch_no_control&&(this.batch_no_control.df.reqd=1,this.batch_no_control.df.get_query=()=>({query:"erpnext.controllers.queries.get_batch_no",filters:{item_code:e.item_row.item_code,warehouse:e.item_row.warehouse,posting_date:e.events.get_frm().doc.posting_date}}),this.batch_no_control.refresh()),this.uom_control&&(this.uom_control.df.onchange=function(){e.events.form_updated(e.current_item,"uom",this.value);let i=frappe.get_doc(e.doctype,e.name);e.conversion_factor_control.df.read_only=i.stock_uom==this.value,e.conversion_factor_control.refresh()},this.uom_control.df.get_query=()=>({query:"erpnext.controllers.queries.get_item_uom_query",filters:{item_code:e.current_item.item_code}}),this.uom_control.refresh());let t=this.events.get_frm().doc.doctype;frappe.model.on(`${t} Item`,"*",(i,s,n)=>{let a=this[`${i}_control`],o=this.compare_with_current_item(n);o&&["qty","rate","amount"].includes(i)&&this.update_total_amount_control(n),o&&a&&a.get_value()!==s&&s==n[i]&&(a.set_value(s),cur_pos.update_cart_html(n))})}'''
	+ bundle[end:]
)

bundle_path.write_text(bundle, encoding="utf-8")
print("patched", bundle_path, len(bundle))
