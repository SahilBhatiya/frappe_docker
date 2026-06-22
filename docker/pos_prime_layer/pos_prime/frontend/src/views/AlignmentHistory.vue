<script setup lang="ts">
import { fetchAlignmentReport, fetchAlignmentReports, type AlignmentReport } from "@/services/alignmentHistory";
import { usePosSessionStore } from "@/stores/posSession";
import { call } from "frappe-ui";
import {
	ArrowLeft,
	ArrowRight,
	Car,
	CheckCircle2,
	Gauge,
	History,
	Link2,
	Loader2,
	Phone,
	RefreshCw,
	Search,
	User,
	X,
} from "lucide-vue-next";
import { computed, onMounted, ref, watch } from "vue";

type CustomerMatch = { name: string; customer_name: string; mobile_no?: string };
type CarMatch = { name: string; registration_number: string; make_model?: string; current_odometer?: number };
type AlignmentLink = { customer: CustomerMatch | null; car: CarMatch | null; is_linked: boolean };

const sessionStore = usePosSessionStore();
const reports = ref<AlignmentReport[]>([]);
const links = ref<Record<string, AlignmentLink>>({});
const selected = ref<AlignmentReport | null>(null);
const loading = ref(false);
const detailLoading = ref(false);
const linking = ref(false);
const error = ref("");
const page = ref(1);
const pageSize = 30;
const total = ref(0);
const search = ref("");
const customerSearch = ref("");
const customerResults = ref<CustomerMatch[]>([]);
const selectedCustomer = ref<CustomerMatch | null>(null);
let searchTimer: ReturnType<typeof setTimeout> | undefined;
let customerTimer: ReturnType<typeof setTimeout> | undefined;

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize)));
const selectedLink = computed(() => selected.value ? links.value[selected.value.report_id] : null);
const makeModel = computed(() => {
	if (!selected.value) return "";
	return [selected.value.manufacturer_name, selected.value.model_name, selected.value.model_year_raw]
		.filter(Boolean)
		.join(" ");
});

function formatDate(value?: string | null) {
	if (!value) return "Date unavailable";
	const compact = value.match(/^(\d{4})(\d{2})(\d{2})$/);
	const parsed = compact
		? new Date(`${compact[1]}-${compact[2]}-${compact[3]}T00:00:00`)
		: new Date(value);
	return Number.isNaN(parsed.getTime())
		? value
		: new Intl.DateTimeFormat(undefined, { day: "2-digit", month: "short", year: "numeric" }).format(parsed);
}

function measurementState(item: NonNullable<AlignmentReport["measurements"]>[number]) {
	const after = Number(item.after_value);
	const min = Number(item.min_value);
	const max = Number(item.max_value);
	if (![after, min, max].every(Number.isFinite)) return "unknown";
	return after >= min && after <= max ? "good" : "bad";
}

async function resolveLinks(rows: AlignmentReport[]) {
	if (!rows.length) return;
	const payload = rows.map((row) => ({
		report_id: row.report_id,
		vehicle_registration: row.vehicle_registration,
		customer_phone: row.customer_phone,
	}));
	links.value = await call("pos_prime.api.alignment.get_alignment_links", { records: payload }) || {};
}

async function loadReports() {
	loading.value = true;
	error.value = "";
	try {
		const result = await fetchAlignmentReports(page.value, pageSize, search.value);
		reports.value = result.reports;
		total.value = result.total;
		await resolveLinks(result.reports);
		if (selected.value && !result.reports.some((row) => row.report_id === selected.value?.report_id)) {
			selected.value = null;
		}
	} catch (e: any) {
		error.value = e?.message || __("Could not load alignment history");
	} finally {
		loading.value = false;
	}
}

async function openReport(report: AlignmentReport) {
	selected.value = report;
	selectedCustomer.value = null;
	customerSearch.value = "";
	customerResults.value = [];
	detailLoading.value = true;
	try {
		selected.value = (await fetchAlignmentReport(report.report_id)) || report;
	} catch (e: any) {
		error.value = e?.message || __("Could not load alignment measurements");
	} finally {
		detailLoading.value = false;
	}
}

async function searchCustomers() {
	if (customerSearch.value.trim().length < 2) {
		customerResults.value = [];
		return;
	}
	customerResults.value = await call("pos_prime.api.customers.search_customers", {
		search_term: customerSearch.value,
		pos_profile: sessionStore.posProfile || "",
	}) || [];
}

async function linkRecord() {
	if (!selected.value) return;
	linking.value = true;
	error.value = "";
	try {
		const result = await call("pos_prime.api.alignment.link_alignment_record", {
			report_id: selected.value.report_id,
			registration_number: selected.value.vehicle_registration || "",
			customer: selectedCustomer.value?.name || "",
			customer_name: selected.value.customer_name || "",
			customer_phone: selected.value.customer_phone || "",
			make_model: makeModel.value,
			current_odometer: selected.value.mileage_raw || 0,
		});
		links.value[selected.value.report_id] = result;
		selectedCustomer.value = null;
		customerResults.value = [];
		customerSearch.value = "";
	} catch (e: any) {
		error.value = e?.messages?.[0] || e?.message || __("Could not link this alignment record");
	} finally {
		linking.value = false;
	}
}

watch(search, () => {
	clearTimeout(searchTimer);
	searchTimer = setTimeout(() => {
		page.value = 1;
		loadReports();
	}, 350);
});

watch(customerSearch, () => {
	clearTimeout(customerTimer);
	customerTimer = setTimeout(searchCustomers, 250);
});

onMounted(loadReports);
</script>

<template>
	<div class="h-full min-h-0 flex flex-col bg-gray-50 dark:bg-gray-900 overflow-hidden">
		<header class="px-4 sm:px-6 py-4 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950">
			<div class="flex flex-col sm:flex-row sm:items-center gap-3">
				<div class="flex items-center gap-3 min-w-0">
					<div class="w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-950 text-blue-600 flex items-center justify-center">
						<History :size="21" />
					</div>
					<div>
						<h1 class="text-lg font-bold text-gray-950 dark:text-white">{{ __("Alignment History") }}</h1>
						<p class="text-xs text-gray-500">{{ total.toLocaleString() }} {{ __("machine reports") }}</p>
					</div>
				</div>
				<div class="sm:ms-auto flex items-center gap-2">
					<div class="relative flex-1 sm:w-80">
						<Search class="absolute start-3 top-1/2 -translate-y-1/2 text-gray-400" :size="17" />
						<input v-model="search" class="w-full h-10 ps-10 pe-3 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 text-sm outline-none focus:border-blue-400" :placeholder="__('Search car, customer or phone')" />
					</div>
					<button class="w-10 h-10 rounded-xl border border-gray-200 dark:border-gray-700 flex items-center justify-center hover:bg-gray-50 dark:hover:bg-gray-800" :disabled="loading" @click="loadReports">
						<RefreshCw :size="17" :class="loading && 'animate-spin'" />
					</button>
				</div>
			</div>
		</header>

		<div v-if="error" class="mx-4 sm:mx-6 mt-3 px-4 py-3 rounded-xl bg-red-50 text-red-700 text-sm flex items-center justify-between gap-3">
			<span>{{ error }}</span><button @click="error = ''"><X :size="16" /></button>
		</div>

		<div class="flex-1 min-h-0 flex overflow-hidden">
			<section class="flex-1 min-w-0 flex flex-col" :class="selected ? 'hidden lg:flex' : 'flex'">
				<div class="flex-1 overflow-y-auto p-4 sm:p-6">
					<div v-if="loading && !reports.length" class="h-full flex items-center justify-center text-gray-500 gap-2"><Loader2 class="animate-spin" :size="20" /> {{ __("Loading machine history...") }}</div>
					<div v-else-if="!reports.length" class="h-full flex flex-col items-center justify-center text-center text-gray-500"><Car :size="38" class="mb-3 text-gray-300" /><p class="font-semibold text-gray-700 dark:text-gray-300">{{ __("No alignment records found") }}</p></div>
					<div v-else class="grid grid-cols-1 xl:grid-cols-2 gap-3">
						<button v-for="report in reports" :key="report.report_id" class="text-start p-4 rounded-2xl border bg-white dark:bg-gray-950 transition hover:border-blue-300 hover:shadow-sm" :class="selected?.report_id === report.report_id ? 'border-blue-400 ring-2 ring-blue-100' : 'border-gray-200 dark:border-gray-800'" @click="openReport(report)">
							<div class="flex items-start gap-3">
								<div class="w-11 h-11 shrink-0 rounded-xl bg-gray-100 dark:bg-gray-800 flex items-center justify-center"><Car :size="20" /></div>
								<div class="min-w-0 flex-1">
									<div class="flex items-center gap-2"><h2 class="font-bold text-gray-950 dark:text-white truncate">{{ report.vehicle_registration || __('Unknown car') }}</h2><CheckCircle2 v-if="links[report.report_id]?.is_linked" class="text-emerald-500 shrink-0" :size="16" /></div>
									<p class="text-sm text-gray-600 dark:text-gray-400 truncate">{{ [report.manufacturer_name, report.model_name].filter(Boolean).join(' ') || __('Model unavailable') }}</p>
								</div>
								<span class="text-xs font-medium text-gray-500 whitespace-nowrap">{{ formatDate(report.report_date_raw) }}</span>
							</div>
							<div class="mt-4 grid grid-cols-3 gap-2 text-xs">
								<div class="rounded-lg bg-gray-50 dark:bg-gray-900 p-2"><span class="block text-gray-400">{{ __('Customer') }}</span><strong class="block truncate text-gray-700 dark:text-gray-200">{{ report.customer_name || '-' }}</strong></div>
								<div class="rounded-lg bg-gray-50 dark:bg-gray-900 p-2"><span class="block text-gray-400">{{ __('Odometer') }}</span><strong class="block truncate text-gray-700 dark:text-gray-200">{{ report.mileage_raw || '-' }}</strong></div>
								<div class="rounded-lg bg-gray-50 dark:bg-gray-900 p-2"><span class="block text-gray-400">{{ __('Readings') }}</span><strong class="block text-gray-700 dark:text-gray-200">{{ report.measurement_count || 0 }}</strong></div>
							</div>
						</button>
					</div>
				</div>
				<footer v-if="reports.length" class="px-4 sm:px-6 py-3 bg-white dark:bg-gray-950 border-t border-gray-200 dark:border-gray-800 flex items-center justify-between text-sm">
					<span class="text-gray-500">{{ __('Page') }} {{ page }} / {{ pageCount }}</span>
					<div class="flex gap-2"><button class="h-9 px-3 rounded-lg border disabled:opacity-40" :disabled="page <= 1 || loading" @click="page--; loadReports()"><ArrowLeft :size="16" /></button><button class="h-9 px-3 rounded-lg border disabled:opacity-40" :disabled="page >= pageCount || loading" @click="page++; loadReports()"><ArrowRight :size="16" /></button></div>
				</footer>
			</section>

			<aside v-if="selected" class="w-full lg:w-[460px] xl:w-[520px] shrink-0 bg-white dark:bg-gray-950 border-s border-gray-200 dark:border-gray-800 overflow-y-auto">
				<div class="sticky top-0 z-10 bg-white/95 dark:bg-gray-950/95 backdrop-blur border-b border-gray-200 dark:border-gray-800 px-5 py-4 flex items-center gap-3">
					<button class="lg:hidden w-9 h-9 rounded-lg border flex items-center justify-center" @click="selected = null"><ArrowLeft :size="17" /></button>
					<div class="min-w-0 flex-1"><h2 class="font-bold text-lg truncate">{{ selected.vehicle_registration }}</h2><p class="text-xs text-gray-500">{{ formatDate(selected.report_date_raw) }} · #{{ selected.report_id }}</p></div>
					<button class="hidden lg:flex w-9 h-9 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 items-center justify-center" @click="selected = null"><X :size="18" /></button>
				</div>

				<div class="p-5 space-y-5">
					<div class="grid grid-cols-2 gap-3 text-sm">
						<div class="p-3 rounded-xl bg-gray-50 dark:bg-gray-900"><Car :size="16" class="text-gray-400 mb-2" /><span class="block text-xs text-gray-400">{{ __('Vehicle') }}</span><strong>{{ makeModel || '-' }}</strong></div>
						<div class="p-3 rounded-xl bg-gray-50 dark:bg-gray-900"><Gauge :size="16" class="text-gray-400 mb-2" /><span class="block text-xs text-gray-400">{{ __('Odometer') }}</span><strong>{{ selected.mileage_raw || '-' }}</strong></div>
						<div class="p-3 rounded-xl bg-gray-50 dark:bg-gray-900"><User :size="16" class="text-gray-400 mb-2" /><span class="block text-xs text-gray-400">{{ __('Machine customer') }}</span><strong class="block truncate">{{ selected.customer_name || '-' }}</strong></div>
						<div class="p-3 rounded-xl bg-gray-50 dark:bg-gray-900"><Phone :size="16" class="text-gray-400 mb-2" /><span class="block text-xs text-gray-400">{{ __('Phone') }}</span><strong>{{ selected.customer_phone || '-' }}</strong></div>
					</div>

					<div class="rounded-2xl border p-4" :class="selectedLink?.is_linked ? 'border-emerald-200 bg-emerald-50/50 dark:bg-emerald-950/20' : 'border-blue-200 bg-blue-50/50 dark:bg-blue-950/20'">
						<div v-if="selectedLink?.is_linked" class="flex gap-3"><CheckCircle2 class="text-emerald-600 shrink-0" :size="21" /><div><h3 class="font-bold text-emerald-900 dark:text-emerald-200">{{ __('Linked to customer dataset') }}</h3><p class="text-sm text-emerald-800 dark:text-emerald-300">{{ selectedLink.customer?.customer_name }} · {{ selectedLink.car?.registration_number }}</p></div></div>
						<div v-else>
							<div class="flex gap-3 mb-3"><Link2 class="text-blue-600 shrink-0" :size="20" /><div><h3 class="font-bold text-blue-950 dark:text-blue-100">{{ __('Create and link car') }}</h3><p class="text-xs text-blue-700 dark:text-blue-300">{{ __('Choose an existing customer, or leave blank to match by phone and create the customer when needed.') }}</p></div></div>
							<div class="relative">
								<Search class="absolute start-3 top-3 text-gray-400" :size="16" /><input v-model="customerSearch" class="w-full h-10 ps-9 pe-3 rounded-xl border border-blue-200 bg-white dark:bg-gray-900 text-sm outline-none" :placeholder="__('Find existing customer (optional)')" />
								<div v-if="customerResults.length && !selectedCustomer" class="absolute z-20 top-11 inset-x-0 bg-white dark:bg-gray-900 border rounded-xl shadow-lg overflow-hidden"><button v-for="customer in customerResults" :key="customer.name" class="w-full text-start px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-800 text-sm" @click="selectedCustomer = customer; customerSearch = customer.customer_name; customerResults = []"><strong class="block">{{ customer.customer_name }}</strong><span class="text-xs text-gray-500">{{ customer.mobile_no }}</span></button></div>
							</div>
							<button class="mt-3 w-full h-10 rounded-xl bg-blue-600 hover:bg-blue-700 text-white font-semibold text-sm flex items-center justify-center gap-2 disabled:opacity-50" :disabled="linking" @click="linkRecord"><Loader2 v-if="linking" class="animate-spin" :size="16" /><Link2 v-else :size="16" />{{ selectedCustomer ? __('Link car to selected customer') : __('Match or create customer and car') }}</button>
						</div>
					</div>

					<div>
						<div class="flex items-center justify-between mb-2"><h3 class="font-bold">{{ __('Alignment readings') }}</h3><span class="text-xs text-gray-500">{{ selected.measurements?.length || 0 }}</span></div>
						<div v-if="detailLoading" class="py-8 flex justify-center"><Loader2 class="animate-spin text-gray-400" /></div>
						<div v-else class="rounded-xl border border-gray-200 dark:border-gray-800 divide-y divide-gray-100 dark:divide-gray-800 overflow-hidden">
							<div v-for="item in selected.measurements" :key="item.param_id" class="grid grid-cols-[1fr_auto_auto] gap-3 items-center px-3 py-2.5 text-sm"><span class="truncate">{{ item.param_name }}</span><span class="text-xs text-gray-400">{{ item.before_value ?? '-' }} →</span><strong class="min-w-14 text-end" :class="measurementState(item) === 'good' ? 'text-emerald-600' : measurementState(item) === 'bad' ? 'text-red-600' : ''">{{ item.after_value ?? '-' }}</strong></div>
							<div v-if="!selected.measurements?.length" class="p-5 text-center text-sm text-gray-500">{{ __('No measurement details available') }}</div>
						</div>
					</div>
				</div>
			</aside>
		</div>
	</div>
</template>
