// Copyright (c) 2026, Ravindu Gajanayaka
// Licensed under GPLv3. See license.txt

import { defineStore } from "pinia";
import { ref } from "vue";
import { call } from "frappe-ui";

export interface TransporterDetails {
	transporter?: string;
	gst_transporter_id?: string;
	vehicle_no?: string;
	mode_of_transport?: string;
	gst_vehicle_type?: string;
	distance?: number;
}

export interface EWayBillResult {
	sales_invoice: string;
	ewaybill: string | null;
	ewaybill_pdf_url: string | null;
	ewaybill_error: string | null;
	grand_total: number;
	place_of_supply?: string | null;
}

export const useEwaybillStore = defineStore("ewaybill", () => {
	const threshold = ref(50000);
	const hasCredentials = ref(false);
	const modesOfTransport = ref<string[]>(["Road", "Air", "Rail", "Ship"]);
	const gstVehicleTypes = ref<string[]>(["Regular", "Over Dimensional Cargo (ODC)"]);
	const transporters = ref<{ name: string; supplier_name: string; gst_transporter_id: string | null }[]>([]);
	const optionsLoaded = ref(false);

	const generating = ref(false);
	const result = ref<EWayBillResult | null>(null);
	const error = ref("");

	async function loadOptions() {
		if (optionsLoaded.value) return;
		try {
			const data = await call("pos_prime.api.ewaybill.get_ewaybill_options");
			modesOfTransport.value = data.modes_of_transport || modesOfTransport.value;
			gstVehicleTypes.value = data.gst_vehicle_types || gstVehicleTypes.value;
			transporters.value = data.transporters || [];
			threshold.value = data.threshold || threshold.value;
			optionsLoaded.value = true;
		} catch {
			// keep defaults
		}
	}

	/** Book the current cart as a B2B Sales Invoice and generate its e-Way Bill. */
	async function generate(transporter: TransporterDetails): Promise<EWayBillResult> {
		const { useCartStore } = await import("@/stores/cart");
		const { useCustomerStore } = await import("@/stores/customer");
		const { usePosSessionStore } = await import("@/stores/posSession");

		const cart = useCartStore();
		const customerStore = useCustomerStore();
		const session = usePosSessionStore();

		generating.value = true;
		error.value = "";
		try {
			const data: EWayBillResult = await call(
				"pos_prime.api.ewaybill.create_invoice_with_ewaybill",
				{
					customer: customerStore.customer?.name,
					pos_profile: session.posProfile,
					items: cart.items.map((item) => ({
						item_code: item.item_code,
						qty: item.qty,
						rate: item.rate,
						discount_percentage: item.discount_percentage || 0,
						discount_amount: item.discount_amount || 0,
						uom: item.uom || "",
						conversion_factor: item.conversion_factor || 1,
						item_tax_template: item.item_tax_template || null,
					})),
					transporter_details: transporter,
					customer_address: customerStore.selectedAddress || undefined,
					shipping_address_name:
						customerStore.selectedShippingAddress || customerStore.selectedAddress || undefined,
					additional_discount_percentage: cart.additionalDiscountPercentage,
					discount_amount: cart.additionalDiscountAmount,
					apply_discount_on: cart.applyDiscountOn,
				},
			);
			result.value = data;
			return data;
		} catch (e: any) {
			error.value = e?.messages?.[0] || e?.message || "Failed to create e-Way Bill invoice";
			throw e;
		} finally {
			generating.value = false;
		}
	}

	function reset() {
		result.value = null;
		error.value = "";
		generating.value = false;
	}

	return {
		threshold,
		hasCredentials,
		modesOfTransport,
		gstVehicleTypes,
		transporters,
		generating,
		result,
		error,
		loadOptions,
		generate,
		reset,
	};
});
