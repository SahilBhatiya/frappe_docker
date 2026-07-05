<!-- Copyright (c) 2026, Ravindu Gajanayaka -->
<!-- Licensed under GPLv3. See license.txt -->

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useGstReportStore } from "@/stores/gstReport";
import { usePosSessionStore } from "@/stores/posSession";
import { useSettingsStore } from "@/stores/settings";
import { useCurrency } from "@/composables/useCurrency";
import { Download, FileBarChart, Loader2 } from "lucide-vue-next";

const store = useGstReportStore();
const sessionStore = usePosSessionStore();
const settingsStore = useSettingsStore();
const { formatCurrency } = useCurrency();

const company = computed(
	() => sessionStore.company || (settingsStore.posProfile as any)?.company || "",
);

function ymd(d: Date): string {
	return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

type PresetId = "this_month" | "last_month" | "this_quarter" | "this_fy" | "custom";
const preset = ref<PresetId>("this_month");
const fromDate = ref("");
const toDate = ref("");

function applyPreset(id: PresetId) {
	preset.value = id;
	const now = new Date();
	const y = now.getFullYear();
	const m = now.getMonth();
	if (id === "this_month") {
		fromDate.value = ymd(new Date(y, m, 1));
		toDate.value = ymd(new Date(y, m + 1, 0));
	} else if (id === "last_month") {
		fromDate.value = ymd(new Date(y, m - 1, 1));
		toDate.value = ymd(new Date(y, m, 0));
	} else if (id === "this_quarter") {
		const qStart = Math.floor(m / 3) * 3;
		fromDate.value = ymd(new Date(y, qStart, 1));
		toDate.value = ymd(new Date(y, qStart + 3, 0));
	} else if (id === "this_fy") {
		// Indian FY: April 1 – March 31
		const fyStart = m >= 3 ? y : y - 1;
		fromDate.value = ymd(new Date(fyStart, 3, 1));
		toDate.value = ymd(new Date(fyStart + 1, 2, 31));
	}
	if (id !== "custom") run();
}

const presets: { id: PresetId; label: string }[] = [
	{ id: "this_month", label: __("This Month") },
	{ id: "last_month", label: __("Last Month") },
	{ id: "this_quarter", label: __("This Quarter") },
	{ id: "this_fy", label: __("This FY") },
	{ id: "custom", label: __("Custom") },
];

function run() {
	if (!fromDate.value || !toDate.value) return;
	store.loadSummary(company.value, fromDate.value, toDate.value);
}

function loadMore() {
	if (store.hasMore && !store.loadingMore) {
		store.loadInvoices(company.value, fromDate.value, toDate.value, true);
	}
}

function downloadCsv() {
	const csv = store.toCsv();
	const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
	const url = URL.createObjectURL(blob);
	const a = document.createElement("a");
	a.href = url;
	a.download = `gst-${fromDate.value}-to-${toDate.value}.csv`;
	a.click();
	URL.revokeObjectURL(url);
}

onMounted(() => applyPreset("this_month"));
</script>

<template>
	<div class="h-full overflow-y-auto bg-gray-50 dark:bg-gray-900">
		<div class="max-w-5xl mx-auto p-4 sm:p-6 space-y-5">
			<!-- Header -->
			<div class="flex items-center gap-3">
				<div class="w-10 h-10 rounded-xl bg-emerald-100 dark:bg-emerald-900/40 flex items-center justify-center">
					<FileBarChart :size="20" class="text-emerald-600 dark:text-emerald-400" />
				</div>
				<div>
					<h1 class="text-lg font-bold text-gray-900 dark:text-gray-100">{{ __("GST Payable") }}</h1>
					<p class="text-xs text-gray-500 dark:text-gray-400">{{ __("Output GST collected on sales — the GST to remit") }}</p>
				</div>
			</div>

			<!-- Date range -->
			<div class="flex flex-wrap items-center gap-2">
				<button
					v-for="p in presets"
					:key="p.id"
					@click="applyPreset(p.id)"
					:class="[
						'px-3 py-1.5 rounded-lg text-xs font-semibold border border-solid transition-colors',
						preset === p.id
							? 'bg-emerald-600 text-white border-emerald-600'
							: 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-700 hover:border-emerald-400',
					]"
				>
					{{ p.label }}
				</button>
			</div>

			<div v-if="preset === 'custom'" class="flex flex-wrap items-end gap-2">
				<label class="text-xs text-gray-500 dark:text-gray-400">
					{{ __("From") }}
					<input type="date" v-model="fromDate" class="block mt-1 rounded-lg border border-solid border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-1.5 text-sm" />
				</label>
				<label class="text-xs text-gray-500 dark:text-gray-400">
					{{ __("To") }}
					<input type="date" v-model="toDate" class="block mt-1 rounded-lg border border-solid border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-1.5 text-sm" />
				</label>
				<button @click="run" class="px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm font-semibold">{{ __("Apply") }}</button>
			</div>

			<!-- Loading -->
			<div v-if="store.loading" class="flex items-center justify-center py-16 text-gray-400">
				<Loader2 :size="28" class="animate-spin" />
			</div>

			<div v-else-if="store.error" class="rounded-xl bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 p-4 text-sm">
				{{ store.error }}
			</div>

			<template v-else-if="store.summary">
				<!-- Summary cards -->
				<div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
					<div class="rounded-xl bg-white dark:bg-gray-800 border border-solid border-gray-100 dark:border-gray-700 p-4">
						<div class="text-[11px] uppercase tracking-wider text-gray-400 font-semibold">{{ __("Taxable Value") }}</div>
						<div class="text-lg font-bold text-gray-900 dark:text-gray-100 mt-1">{{ formatCurrency(store.summary.taxable_amount) }}</div>
					</div>
					<div class="rounded-xl bg-white dark:bg-gray-800 border border-solid border-gray-100 dark:border-gray-700 p-4">
						<div class="text-[11px] uppercase tracking-wider text-gray-400 font-semibold">CGST</div>
						<div class="text-lg font-bold text-gray-900 dark:text-gray-100 mt-1">{{ formatCurrency(store.summary.cgst) }}</div>
					</div>
					<div class="rounded-xl bg-white dark:bg-gray-800 border border-solid border-gray-100 dark:border-gray-700 p-4">
						<div class="text-[11px] uppercase tracking-wider text-gray-400 font-semibold">SGST</div>
						<div class="text-lg font-bold text-gray-900 dark:text-gray-100 mt-1">{{ formatCurrency(store.summary.sgst) }}</div>
					</div>
					<div class="rounded-xl bg-white dark:bg-gray-800 border border-solid border-gray-100 dark:border-gray-700 p-4">
						<div class="text-[11px] uppercase tracking-wider text-gray-400 font-semibold">IGST</div>
						<div class="text-lg font-bold text-gray-900 dark:text-gray-100 mt-1">{{ formatCurrency(store.summary.igst) }}</div>
					</div>
				</div>

				<!-- Total payable -->
				<div class="rounded-xl bg-emerald-600 text-white p-5 flex items-center justify-between">
					<div>
						<div class="text-xs uppercase tracking-wider opacity-90 font-semibold">{{ __("Total GST Payable") }}</div>
						<div class="text-[11px] opacity-80 mt-0.5">{{ store.summary.invoice_count }} {{ __("invoices") }} · {{ store.summary.from_date }} → {{ store.summary.to_date }}</div>
					</div>
					<div class="text-2xl font-extrabold">{{ formatCurrency(store.summary.total_gst) }}</div>
				</div>

				<!-- By rate -->
				<div v-if="store.summary.by_rate.length" class="rounded-xl bg-white dark:bg-gray-800 border border-solid border-gray-100 dark:border-gray-700 overflow-hidden">
					<div class="px-4 py-2.5 text-xs font-semibold text-gray-500 dark:text-gray-400 border-b border-gray-100 dark:border-gray-700">{{ __("By GST Rate") }}</div>
					<table class="w-full text-sm">
						<thead>
							<tr class="text-[11px] uppercase tracking-wider text-gray-400 text-left">
								<th class="px-4 py-2 font-semibold">{{ __("Rate") }}</th>
								<th class="px-4 py-2 font-semibold text-right">{{ __("Taxable") }}</th>
								<th class="px-4 py-2 font-semibold text-right">CGST</th>
								<th class="px-4 py-2 font-semibold text-right">SGST</th>
								<th class="px-4 py-2 font-semibold text-right">IGST</th>
								<th class="px-4 py-2 font-semibold text-right">{{ __("Total") }}</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="r in store.summary.by_rate" :key="r.gst_rate" class="border-t border-gray-50 dark:border-gray-700/50">
								<td class="px-4 py-2 font-semibold text-gray-700 dark:text-gray-300">{{ r.gst_rate }}%</td>
								<td class="px-4 py-2 text-right text-gray-600 dark:text-gray-400">{{ formatCurrency(r.taxable_amount) }}</td>
								<td class="px-4 py-2 text-right text-gray-600 dark:text-gray-400">{{ formatCurrency(r.cgst) }}</td>
								<td class="px-4 py-2 text-right text-gray-600 dark:text-gray-400">{{ formatCurrency(r.sgst) }}</td>
								<td class="px-4 py-2 text-right text-gray-600 dark:text-gray-400">{{ formatCurrency(r.igst) }}</td>
								<td class="px-4 py-2 text-right font-semibold text-gray-800 dark:text-gray-200">{{ formatCurrency(r.total_gst) }}</td>
							</tr>
						</tbody>
					</table>
				</div>

				<!-- Invoices -->
				<div class="rounded-xl bg-white dark:bg-gray-800 border border-solid border-gray-100 dark:border-gray-700 overflow-hidden">
					<div class="px-4 py-2.5 flex items-center justify-between border-b border-gray-100 dark:border-gray-700">
						<span class="text-xs font-semibold text-gray-500 dark:text-gray-400">{{ __("Invoices") }}</span>
						<button v-if="store.invoices.length" @click="downloadCsv" class="flex items-center gap-1.5 text-xs font-semibold text-emerald-600 hover:text-emerald-700">
							<Download :size="14" /> {{ __("CSV") }}
						</button>
					</div>
					<div v-if="!store.invoices.length" class="p-8 text-center text-sm text-gray-400">{{ __("No GST invoices in this period.") }}</div>
					<table v-else class="w-full text-sm">
						<tbody>
							<tr v-for="inv in store.invoices" :key="inv.name" class="border-t border-gray-50 dark:border-gray-700/50">
								<td class="px-4 py-2">
									<div class="font-medium text-gray-800 dark:text-gray-200">{{ inv.name }}<span v-if="inv.is_return" class="ml-1 text-[10px] text-red-500 font-semibold">RET</span></div>
									<div class="text-[11px] text-gray-400">{{ inv.posting_date }} · {{ inv.customer_name || inv.customer }}</div>
								</td>
								<td class="px-4 py-2 text-right font-semibold text-gray-800 dark:text-gray-200">{{ formatCurrency(inv.total_gst) }}</td>
							</tr>
						</tbody>
					</table>
					<button v-if="store.hasMore" @click="loadMore" :disabled="store.loadingMore" class="w-full py-2.5 text-xs font-semibold text-gray-500 hover:text-gray-700 border-t border-gray-100 dark:border-gray-700">
						{{ store.loadingMore ? __("Loading…") : __("Load more") }}
					</button>
				</div>

				<p class="text-[11px] text-gray-400 dark:text-gray-500 text-center">
					{{ __("Shows output GST collected. Net cash payable (after input tax credit on purchases) is not yet included.") }}
				</p>
			</template>
		</div>
	</div>
</template>
