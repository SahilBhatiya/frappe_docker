<!-- Copyright (c) 2026, Ravindu Gajanayaka -->
<!-- Licensed under GPLv3. See license.txt -->

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { Button } from "@/components/ui/button";
import {
	Dialog,
	DialogContent,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { useEwaybillStore } from "@/stores/ewaybill";
import { useCartStore } from "@/stores/cart";
import { useCustomerStore } from "@/stores/customer";
import { useCurrency } from "@/composables/useCurrency";
import { Truck, CheckCircle2, AlertTriangle, Download, Loader2 } from "lucide-vue-next";

const props = defineProps<{ show: boolean }>();
const emit = defineEmits<{ close: []; done: [] }>();

const ewb = useEwaybillStore();
const cartStore = useCartStore();
const customerStore = useCustomerStore();
const { formatCurrency } = useCurrency();

const form = reactive({
	transporter: "",
	gst_transporter_id: "",
	vehicle_no: "",
	mode_of_transport: "Road",
	gst_vehicle_type: "Regular",
	distance: 0,
});

const localError = ref("");

onMounted(() => ewb.loadOptions());

function onTransporterChange() {
	const t = ewb.transporters.find((x) => x.name === form.transporter);
	if (t?.gst_transporter_id) form.gst_transporter_id = t.gst_transporter_id;
}

async function submit() {
	localError.value = "";
	if (!form.vehicle_no.trim() && !form.gst_transporter_id.trim()) {
		localError.value = __("Enter a vehicle number or a GST transporter ID.");
		return;
	}
	try {
		await ewb.generate({
			transporter: form.transporter || undefined,
			gst_transporter_id: form.gst_transporter_id.trim().toUpperCase() || undefined,
			vehicle_no: form.vehicle_no.trim().toUpperCase() || undefined,
			mode_of_transport: form.mode_of_transport,
			gst_vehicle_type: form.gst_vehicle_type,
			distance: Number(form.distance) || 0,
		});
	} catch {
		// error surfaced via ewb.error
	}
}

function finish() {
	cartStore.$reset();
	ewb.reset();
	emit("done");
}

function close() {
	if (ewb.result) {
		// A Sales Invoice was created — closing must also clear the cart.
		finish();
		return;
	}
	emit("close");
}
</script>

<template>
	<Dialog :open="props.show" @update:open="(val) => { if (!val) close() }">
		<DialogContent class="sm:max-w-md max-h-[90vh] p-0 gap-0 overflow-hidden flex flex-col" :show-close-button="false">
			<div class="p-6 overflow-y-auto no-scrollbar flex-1 flex flex-col">
				<!-- Header -->
				<DialogHeader class="flex-row items-center justify-between mb-5 space-y-0">
					<div class="flex items-center gap-3">
						<div class="w-9 h-9 bg-indigo-100 dark:bg-indigo-900/40 rounded-xl flex items-center justify-center text-indigo-600 dark:text-indigo-400">
							<Truck :size="17" />
						</div>
						<DialogTitle class="text-lg font-bold text-gray-900 dark:text-gray-100">
							{{ __("e-Way Bill") }}
						</DialogTitle>
					</div>
				</DialogHeader>

				<!-- RESULT -->
				<div v-if="ewb.result" class="space-y-4">
					<div v-if="ewb.result.ewaybill" class="text-center py-2">
						<CheckCircle2 :size="40" class="mx-auto text-emerald-500 mb-2" />
						<div class="text-sm text-gray-500 dark:text-gray-400">{{ __("e-Way Bill No.") }}</div>
						<div class="text-xl font-extrabold text-gray-900 dark:text-gray-100 tracking-wide">{{ ewb.result.ewaybill }}</div>
					</div>
					<div v-else class="rounded-xl bg-amber-50 dark:bg-amber-900/30 border border-solid border-amber-200 dark:border-amber-800 p-3 text-amber-800 dark:text-amber-300 text-xs flex gap-2">
						<AlertTriangle :size="16" class="shrink-0 mt-0.5" />
						<div>
							<div class="font-semibold">{{ __("Invoice created, but e-Way Bill failed.") }}</div>
							<div class="mt-1 opacity-90">{{ ewb.result.ewaybill_error }}</div>
						</div>
					</div>

					<div class="rounded-xl bg-gray-50 dark:bg-gray-800 p-3 text-sm space-y-1">
						<div class="flex justify-between"><span class="text-gray-500">{{ __("Sales Invoice") }}</span><span class="font-semibold text-gray-800 dark:text-gray-200">{{ ewb.result.sales_invoice }}</span></div>
						<div class="flex justify-between"><span class="text-gray-500">{{ __("Total") }}</span><span class="font-semibold text-gray-800 dark:text-gray-200">{{ formatCurrency(ewb.result.grand_total) }}</span></div>
					</div>

					<a v-if="ewb.result.ewaybill_pdf_url" :href="ewb.result.ewaybill_pdf_url" target="_blank" class="flex items-center justify-center gap-2 w-full py-2.5 rounded-xl border border-solid border-gray-200 dark:border-gray-700 text-sm font-semibold text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800">
						<Download :size="16" /> {{ __("Download e-Way Bill") }}
					</a>

					<Button @click="finish" class="w-full py-2.5 rounded-xl bg-gray-950 dark:bg-gray-100 dark:text-gray-950 text-white text-sm font-bold">{{ __("Done") }}</Button>
				</div>

				<!-- FORM -->
				<div v-else class="space-y-3">
					<p class="text-xs text-gray-500 dark:text-gray-400 -mt-1">
						{{ __("Books a B2B tax invoice for") }} <span class="font-semibold">{{ customerStore.customer?.customer_name }}</span>
						{{ __("and generates the government e-Way Bill.") }}
					</p>

					<div v-if="!ewb.hasCredentials" class="rounded-lg bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300 text-[11px] px-3 py-2">
						{{ __("Note: e-Way Bill API credentials are not configured. The invoice will be created but you'll generate the bill on the portal/Desk.") }}
					</div>

					<div>
						<label class="block text-xs font-semibold text-gray-600 dark:text-gray-400 mb-1">{{ __("Transporter") }}</label>
						<select v-model="form.transporter" @change="onTransporterChange" data-slot="select" class="w-full text-sm">
							<option value="">{{ __("— none —") }}</option>
							<option v-for="t in ewb.transporters" :key="t.name" :value="t.name">{{ t.supplier_name }}</option>
						</select>
					</div>

					<div class="grid grid-cols-2 gap-3">
						<div>
							<label class="block text-xs font-semibold text-gray-600 dark:text-gray-400 mb-1">{{ __("Vehicle No.") }}</label>
							<input v-model="form.vehicle_no" type="text" placeholder="GJ01AB1234" data-slot="input" class="w-full text-sm uppercase" />
						</div>
						<div>
							<label class="block text-xs font-semibold text-gray-600 dark:text-gray-400 mb-1">{{ __("GST Transporter ID") }}</label>
							<input v-model="form.gst_transporter_id" type="text" data-slot="input" class="w-full text-sm uppercase" />
						</div>
					</div>

					<div class="grid grid-cols-3 gap-3">
						<div>
							<label class="block text-xs font-semibold text-gray-600 dark:text-gray-400 mb-1">{{ __("Mode") }}</label>
							<select v-model="form.mode_of_transport" data-slot="select" class="w-full text-sm">
								<option v-for="m in ewb.modesOfTransport" :key="m" :value="m">{{ m }}</option>
							</select>
						</div>
						<div>
							<label class="block text-xs font-semibold text-gray-600 dark:text-gray-400 mb-1">{{ __("Type") }}</label>
							<select v-model="form.gst_vehicle_type" data-slot="select" class="w-full text-sm">
								<option v-for="v in ewb.gstVehicleTypes" :key="v" :value="v">{{ v }}</option>
							</select>
						</div>
						<div>
							<label class="block text-xs font-semibold text-gray-600 dark:text-gray-400 mb-1">{{ __("Dist (km)") }}</label>
							<input v-model.number="form.distance" type="number" min="0" data-slot="input" class="w-full text-sm" />
						</div>
					</div>

					<div v-if="localError || ewb.error" class="text-xs text-red-600 dark:text-red-400">{{ localError || ewb.error }}</div>

					<Button @click="submit" :disabled="ewb.generating" class="w-full py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-bold flex items-center justify-center gap-2">
						<Loader2 v-if="ewb.generating" :size="16" class="animate-spin" />
						<Truck v-else :size="16" />
						{{ ewb.generating ? __("Generating…") : __("Create Invoice & e-Way Bill") }}
					</Button>
				</div>
			</div>
		</DialogContent>
	</Dialog>
</template>
