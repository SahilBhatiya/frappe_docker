<script setup lang="ts">
import { fetchAlignmentReport, fetchAlignmentReports, type AlignmentReport } from "@/services/alignmentHistory";
import { usePosSessionStore } from "@/stores/posSession";
import { call } from "frappe-ui";
import {
	ArrowRight,
	Car,
	CheckCircle2,
	Gauge,
	Link2,
	Loader2,
	Phone,
	RefreshCw,
	Search,
	User,
	X,
} from "lucide-vue-next";
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";

type CustomerMatch = { name: string; customer_name: string; mobile_no?: string };
type CarMatch = { name: string; registration_number: string; make_model?: string; current_odometer?: number };
type AlignmentLink = { customer: CustomerMatch | null; car: CarMatch | null; is_linked: boolean };

const sessionStore = usePosSessionStore();
const reports = ref<AlignmentReport[]>([]);
const links = ref<Record<string, AlignmentLink>>({});
const selected = ref<AlignmentReport | null>(null);
const loading = ref(false);
const loadingMore = ref(false);
const detailLoading = ref(false);
const linking = ref(false);
const unlinking = ref(false);
const error = ref("");
const page = ref(1);
const pageSize = 30;
const total = ref(0);
const search = ref("");
const customerSearch = ref("");
const customerResults = ref<CustomerMatch[]>([]);
const selectedCustomer = ref<CustomerMatch | null>(null);
const scrollContainer = ref<HTMLElement | null>(null);
const loadMoreSentinel = ref<HTMLElement | null>(null);
let searchTimer: ReturnType<typeof setTimeout> | undefined;
let customerTimer: ReturnType<typeof setTimeout> | undefined;
let loadMoreObserver: IntersectionObserver | undefined;

const hasMore = computed(() => reports.value.length < total.value);
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
	const resolved = await call("pos_prime.api.alignment.get_alignment_links", { records: payload }) || {};
	links.value = { ...links.value, ...resolved };
}

async function loadReports() {
	page.value = 1;
	loading.value = true;
	error.value = "";
	try {
		const result = await fetchAlignmentReports(page.value, pageSize, search.value);
		reports.value = result.reports;
		total.value = result.total;
		links.value = {};
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

async function loadMoreReports() {
	if (loading.value || loadingMore.value || !hasMore.value) return;
	loadingMore.value = true;
	const nextPage = page.value + 1;
	try {
		const result = await fetchAlignmentReports(nextPage, pageSize, search.value);
		const existingIds = new Set(reports.value.map((report) => report.report_id));
		const newReports = result.reports.filter((report) => !existingIds.has(report.report_id));
		reports.value.push(...newReports);
		total.value = result.total;
		page.value = nextPage;
		await resolveLinks(newReports);
	} catch (e: any) {
		error.value = e?.message || __("Could not load more alignment history");
	} finally {
		loadingMore.value = false;
	}
}

function setupInfiniteScroll() {
	loadMoreObserver?.disconnect();
	if (!scrollContainer.value || !loadMoreSentinel.value) return;
	loadMoreObserver = new IntersectionObserver(
		(entries) => {
			if (entries.some((entry) => entry.isIntersecting)) loadMoreReports();
		},
		{ root: scrollContainer.value, rootMargin: "300px 0px", threshold: 0 },
	);
	loadMoreObserver.observe(loadMoreSentinel.value);
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

async function unlinkRecord() {
	if (!selected.value) return;
	const regNo = selectedLink.value?.car?.registration_number || selected.value.vehicle_registration;
	if (!regNo) return;
	
	unlinking.value = true;
	error.value = "";
	try {
		const result = await call("pos_prime.api.alignment.unlink_alignment_record", {
			registration_number: regNo,
		});
		links.value[selected.value.report_id] = result;
	} catch (e: any) {
		error.value = e?.messages?.[0] || e?.message || __("Could not unlink this alignment record");
	} finally {
		unlinking.value = false;
	}
}

watch(search, () => {
	clearTimeout(searchTimer);
	searchTimer = setTimeout(() => {
		loadReports();
	}, 350);
});

watch(customerSearch, () => {
	clearTimeout(customerTimer);
	customerTimer = setTimeout(searchCustomers, 250);
});

onMounted(async () => {
	await loadReports();
	await nextTick();
	setupInfiniteScroll();
});

onUnmounted(() => {
	clearTimeout(searchTimer);
	clearTimeout(customerTimer);
	loadMoreObserver?.disconnect();
});
</script>

<template>
	<div class="h-full">
		<div
			class="alignment-layout flex h-full overflow-hidden"
			style="gap: var(--margin-md, 8px); padding: 0.5%"
		>
			<section
				class="flex min-w-0 flex-1 flex-col overflow-hidden rounded-2xl bg-white dark:bg-gray-900"
			>
				<div class="flex items-center gap-2 px-3 py-2">
					<div class="hidden sm:flex min-w-0 shrink-0 flex-col">
						<span class="whitespace-nowrap text-base font-bold text-gray-900 dark:text-gray-100">{{ __("Alignment History") }}</span>
						<span class="text-[11px] text-gray-400 dark:text-gray-500">{{ total.toLocaleString() }} {{ __("machine reports") }}</span>
					</div>

					<div class="relative flex h-10 min-w-0 flex-1 items-center rounded-xl bg-gray-100 transition-all duration-200 focus-within:ring-2 focus-within:ring-gray-900/10 dark:bg-gray-800 dark:focus-within:ring-white/15">
						<Search class="ms-3 shrink-0 text-gray-400 dark:text-gray-500" :size="16" />
						<input
							v-model="search"
							class="h-full min-w-0 flex-1 bg-transparent px-2 text-sm text-gray-900 outline-none placeholder-gray-400 dark:text-gray-100 dark:placeholder-gray-500"
							:placeholder="__('Search car, customer or phone')"
							:aria-label="__('Search alignment history')"
						/>
						<button
							v-if="search"
							class="me-1.5 flex size-7 items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-white hover:text-gray-600 dark:text-gray-500 dark:hover:bg-gray-700 dark:hover:text-gray-300"
							:aria-label="__('Clear search')"
							@click="search = ''"
						>
							<X :size="14" />
						</button>
					</div>

					<button
						class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-gray-100 text-gray-500 transition-colors hover:bg-gray-200 hover:text-gray-900 disabled:opacity-60 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700 dark:hover:text-gray-100"
						:disabled="loading"
						:title="__('Refresh')"
						:aria-label="__('Refresh alignment history')"
						@click="loadReports"
					>
						<RefreshCw :size="17" :class="loading && 'animate-spin'" />
					</button>
				</div>

				<div v-if="error" class="mx-3 mb-2 flex items-center justify-between gap-3 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-300">
					<span>{{ error }}</span>
					<button class="shrink-0" @click="error = ''"><X :size="16" /></button>
				</div>
				<div
					ref="scrollContainer"
					class="relative flex-1 overflow-y-auto"
					style="container-type: inline-size; container-name: alignment-results;"
				>
					<div v-if="loading && !reports.length" class="h-full flex items-center justify-center text-gray-500 gap-2"><Loader2 class="animate-spin" :size="20" /> {{ __("Loading machine history...") }}</div>
					<div v-else-if="!reports.length" class="h-full flex flex-col items-center justify-center text-center text-gray-500"><Car :size="38" class="mb-3 text-gray-300" /><p class="font-semibold text-gray-700 dark:text-gray-300">{{ __("No alignment records found") }}</p></div>
					<div v-else role="table" :aria-label="__('Alignment machine history')">
						<div
							role="row"
							class="alignment-table-grid sticky top-0 z-10 mx-2 grid gap-3 bg-white/95 px-3.5 py-3 text-xs font-medium text-gray-500 backdrop-blur-md dark:bg-gray-950/95 dark:text-gray-400"
						>
							<span role="columnheader">{{ __('Vehicle') }}</span>
							<span role="columnheader" class="alignment-customer">{{ __('Customer') }}</span>
							<span role="columnheader" class="alignment-date">{{ __('Date') }}</span>
							<span role="columnheader" class="text-right">{{ __('Odometer') }}</span>
							<span role="columnheader" class="alignment-readings text-center">{{ __('Readings') }}</span>
							<span role="columnheader" class="alignment-status text-center">{{ __('Status') }}</span>
							<span role="columnheader" class="text-right text-gray-400/60 font-normal">..</span>
						</div>
						<div role="rowgroup" class="px-2 pb-3 space-y-2">
							<button
								v-for="(report, index) in reports"
								:key="report.report_id"
								role="row"
								type="button"
								class="alignment-table-grid group grid min-h-[58px] w-full items-center gap-3 rounded-xl border border-zinc-100 px-3.5 py-2.5 text-start transition-all duration-150 hover:-translate-y-0.5 hover:border-orange-500 hover:bg-orange-500 hover:text-white hover:shadow-lg hover:shadow-orange-500/15 active:translate-y-0 active:scale-[0.99] dark:border-gray-800 dark:hover:border-orange-500 dark:hover:bg-orange-500 dark:hover:text-white"
								:class="[
									index % 2 ? 'bg-gray-50/70 dark:bg-zinc-900/40' : 'bg-white dark:bg-gray-900',
									selected?.report_id === report.report_id ? 'border-orange-400 ring-2 ring-orange-100 dark:ring-orange-950' : '',
								]"
								@click="openReport(report)"
							>
								<span role="cell" class="flex min-w-0 items-center gap-2.5">
									<span class="flex size-9 shrink-0 items-center justify-center rounded-lg bg-gray-50 text-gray-400 transition-colors group-hover:bg-white/20 group-hover:text-white dark:bg-gray-800">
										<Car :size="18" />
									</span>
									<span class="min-w-0">
										<span class="block truncate text-sm font-semibold text-gray-900 transition-colors group-hover:text-white dark:text-gray-100">{{ report.vehicle_registration || __('Unknown car') }}</span>
										<span class="mt-0.5 block truncate text-[11px] text-gray-400 transition-colors group-hover:text-white/70">{{ [report.manufacturer_name, report.model_name].filter(Boolean).join(' ') || __('Model unavailable') }}</span>
									</span>
								</span>
								<span role="cell" class="alignment-customer min-w-0">
									<span class="block truncate text-xs font-medium text-gray-700 transition-colors group-hover:text-white dark:text-gray-300">{{ links[report.report_id]?.customer?.customer_name || report.customer_name || '-' }}</span>
									<span class="mt-0.5 block truncate text-[10px] text-gray-400 transition-colors group-hover:text-white/70">{{ links[report.report_id]?.customer?.mobile_no || report.customer_phone || '-' }}</span>
								</span>
								<span role="cell" class="alignment-date whitespace-nowrap text-xs text-gray-500 transition-colors group-hover:text-white/80 dark:text-gray-400">{{ formatDate(report.report_date_raw) }}</span>
								<span role="cell" class="text-right text-sm font-semibold text-gray-800 transition-colors group-hover:text-white dark:text-gray-200">{{ report.mileage_raw || '-' }}</span>
								<span role="cell" class="alignment-readings text-center">
									<span class="inline-flex min-w-8 items-center justify-center rounded-md bg-gray-100 px-1.5 py-0.5 text-[10px] font-bold text-gray-600 transition-colors group-hover:bg-white/20 group-hover:text-white dark:bg-gray-800 dark:text-gray-300">{{ report.measurement_count || 0 }}</span>
								</span>
								<span role="cell" class="alignment-status flex justify-center">
									<span v-if="links[report.report_id]?.is_linked" class="inline-flex items-center gap-1 rounded-md bg-orange-50 px-2 py-1 text-[10px] font-semibold text-orange-700 group-hover:bg-white/20 group-hover:text-white dark:bg-orange-900/30 dark:text-orange-400"><CheckCircle2 :size="12" />{{ __('Linked') }}</span>
									<span v-else class="inline-flex rounded-md bg-amber-50 px-2 py-1 text-[10px] font-semibold text-amber-700 group-hover:bg-white/20 group-hover:text-white dark:bg-amber-900/30 dark:text-amber-400">{{ __('Unlinked') }}</span>
								</span>
								<span role="cell" class="flex size-8 items-center justify-center rounded-lg bg-gray-50 text-gray-400 transition-colors group-hover:bg-white group-hover:text-orange-500 dark:bg-gray-800"><ArrowRight :size="15" /></span>
							</button>
						</div>
					</div>
					<div ref="loadMoreSentinel" class="min-h-16 px-4 py-4 flex items-center justify-center text-xs text-gray-400">
						<span v-if="loadingMore" class="inline-flex items-center gap-2"><Loader2 class="animate-spin" :size="16" />{{ __('Loading more reports...') }}</span>
						<span v-else-if="reports.length && !hasMore">{{ __('All reports loaded') }}</span>
					</div>
					<div class="pointer-events-none sticky bottom-0 left-0 right-0 h-10 bg-gradient-to-t from-white to-transparent dark:from-gray-900 dark:to-transparent" />
				</div>
			</section>

			<div
				v-if="selected"
				class="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-3 backdrop-blur-sm sm:p-5"
				role="dialog"
				aria-modal="true"
				:aria-label="__('Alignment report details')"
				@click.self="selected = null"
			>
				<div class="flex max-h-[92vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl shadow-black/20 dark:bg-gray-900">
				<div class="sticky top-0 z-10 bg-white/95 dark:bg-gray-900/95 backdrop-blur border-b border-gray-100 dark:border-gray-800 px-5 py-4 flex items-center gap-3">
					<div class="min-w-0 flex-1"><h2 class="font-bold text-lg truncate">{{ selected.vehicle_registration }}</h2><p class="text-xs text-gray-500">{{ formatDate(selected.report_date_raw) }} · #{{ selected.report_id }}</p></div>
					<button class="flex w-9 h-9 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 items-center justify-center" :aria-label="__('Close')" @click="selected = null"><X :size="18" /></button>
				</div>

				<div class="p-5 space-y-5 overflow-y-auto">
					<div class="grid grid-cols-2 gap-3 text-sm">
						<div class="p-3 rounded-xl bg-gray-50 dark:bg-gray-900"><Car :size="16" class="text-gray-400 mb-2" /><span class="block text-xs text-gray-400">{{ __('Vehicle') }}</span><strong>{{ makeModel || '-' }}</strong></div>
						<div class="p-3 rounded-xl bg-gray-50 dark:bg-gray-900"><Gauge :size="16" class="text-gray-400 mb-2" /><span class="block text-xs text-gray-400">{{ __('Odometer') }}</span><strong>{{ selected.mileage_raw || '-' }}</strong></div>
						<div class="p-3 rounded-xl bg-gray-50 dark:bg-gray-900"><User :size="16" class="text-gray-400 mb-2" /><span class="block text-xs text-gray-400">{{ __('Machine customer') }}</span><strong class="block truncate">{{ selected.customer_name || '-' }}</strong></div>
						<div class="p-3 rounded-xl bg-gray-50 dark:bg-gray-900"><Phone :size="16" class="text-gray-400 mb-2" /><span class="block text-xs text-gray-400">{{ __('Phone') }}</span><strong>{{ selected.customer_phone || '-' }}</strong></div>
					</div>

					<div class="rounded-2xl border p-4" :class="selectedLink?.is_linked ? 'border-orange-200 bg-orange-50/40 dark:border-orange-900/50 dark:bg-orange-950/20' : 'border-orange-200 bg-orange-50/40 dark:border-orange-900/50 dark:bg-orange-950/20'">
						<div v-if="selectedLink?.is_linked" class="flex gap-3">
							<CheckCircle2 class="text-orange-600 shrink-0 dark:text-orange-400" :size="21" />
							<div class="flex-1">
								<h3 class="font-bold text-gray-950 dark:text-gray-100">{{ __('Linked to customer dataset') }}</h3>
								<p class="text-sm text-gray-600 dark:text-gray-400">{{ selectedLink.customer?.customer_name }} · {{ selectedLink.car?.registration_number }}</p>
							</div>
							<button class="shrink-0 h-8 flex items-center justify-center gap-1.5 px-3 rounded-lg border border-orange-200 bg-white text-xs font-semibold text-orange-700 shadow-sm transition-colors hover:border-orange-300 hover:bg-orange-100 disabled:opacity-50 dark:border-orange-900/60 dark:bg-orange-950/30 dark:text-orange-300 dark:hover:bg-orange-900/40" @click="unlinkRecord" :disabled="unlinking">
								<Loader2 v-if="unlinking" class="animate-spin" :size="14" />
								<span v-else>{{ __('Unlink') }}</span>
							</button>
						</div>
						<div v-else>
							<div class="flex gap-3 mb-3"><Link2 class="text-orange-600 shrink-0 dark:text-orange-400" :size="20" /><div><h3 class="font-bold text-gray-950 dark:text-gray-100">{{ __('Create and link car') }}</h3><p class="text-xs text-gray-600 dark:text-gray-400">{{ __('Choose an existing customer, or leave blank to match by phone and create the customer when needed.') }}</p></div></div>
							<div class="relative">
								<Search class="absolute start-3 top-3 text-gray-400" :size="16" /><input v-model="customerSearch" class="w-full h-10 ps-9 pe-3 rounded-xl border border-orange-200 bg-white text-sm outline-none transition-all duration-200 focus:border-orange-400 focus:ring-2 focus:ring-orange-400/20 dark:border-orange-900/60 dark:bg-gray-900 dark:focus:border-orange-500 dark:focus:ring-orange-500/20" :placeholder="__('Find existing customer (optional)')" />
								<div v-if="customerResults.length && !selectedCustomer" class="absolute z-20 top-11 inset-x-0 bg-white dark:bg-gray-900 border rounded-xl shadow-lg overflow-hidden"><button v-for="customer in customerResults" :key="customer.name" class="w-full text-start px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-800 text-sm" @click="selectedCustomer = customer; customerSearch = customer.customer_name; customerResults = []"><strong class="block">{{ customer.customer_name }}</strong><span class="text-xs text-gray-500">{{ customer.mobile_no }}</span></button></div>
							</div>
							<button class="mt-3 w-full h-10 rounded-xl bg-orange-500 text-white font-semibold text-sm flex items-center justify-center gap-2 shadow-lg shadow-orange-500/15 transition-colors hover:bg-orange-600 disabled:opacity-50" :disabled="linking" @click="linkRecord"><Loader2 v-if="linking" class="animate-spin" :size="16" /><Link2 v-else :size="16" />{{ selectedCustomer ? __('Link car to selected customer') : __('Match or create customer and car') }}</button>
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
				</div>
			</div>
		</div>
	</div>
</template>

<style scoped>
.alignment-table-grid {
	grid-template-columns: minmax(11rem, 1.5fr) minmax(9rem, 1.15fr) 7.25rem 6rem 4.5rem 5.75rem 2rem;
}

@container alignment-results (max-width: 820px) {
	.alignment-table-grid {
		grid-template-columns: minmax(10rem, 1.5fr) minmax(8rem, 1fr) 6rem 4.5rem 2rem;
	}

	.alignment-date,
	.alignment-status {
		display: none;
	}
}

@container alignment-results (max-width: 560px) {
	.alignment-table-grid {
		grid-template-columns: minmax(9rem, 1fr) 5.5rem 2rem;
	}

	.alignment-customer,
	.alignment-readings {
		display: none;
	}
}

@media screen and (max-width: 640px) {
	.alignment-layout {
		padding: 4px !important;
	}
}
</style>
