<!-- Copyright (c) 2026, Ravindu Gajanayaka -->
<!-- Licensed under GPLv3. See license.txt -->

<script setup lang="ts">
import Input from "@/components/ui/input/Input.vue";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import type { CustomerCar } from "@/types";
import { useCurrency } from "@/composables/useCurrency";
import { useCustomerStore } from "@/stores/customer";
import { usePosSessionStore } from "@/stores/posSession";
import { deskUrl } from "@/utils/deskUrl";
import { fetchAlignmentReports, type AlignmentReport } from "@/services/alignmentHistory";
import { call } from "frappe-ui";
import {
  AlertTriangle,
  Car,
  CreditCard,
  ExternalLink,
  FileText,
  Link2,
  Loader2,
  Mail,
  MapPin,
  MessageCircle,
  Phone,
  Tag,
  User,
  Wallet,
  X,
} from "lucide-vue-next";
import { onMounted, reactive, ref, watch } from "vue";

const emit = defineEmits<{ close: [] }>();
const customerStore = useCustomerStore();
const sessionStore = usePosSessionStore();
const { formatCurrency } = useCurrency();

// Editable fields
const editEmail = ref("");
const editMobile = ref("");
const editWhatsapp = ref("");
const editLoyaltyProgram = ref("");
const savingField = ref<string | null>(null);

// Tabs
const activeTab = ref('cars');

// Transactions
const transactions = ref<any[]>([]);
const loadingTx = ref(false);

// Recent alignment records
const alignmentRecords = ref<AlignmentReport[]>([]);
const loadingAlignment = ref(false);
const linkingRecord = ref<string | null>(null);

// Car detail dialog
const carDialogOpen = ref(false);
const selectedCar = ref<CustomerCar | null>(null);
const carForm = reactive({
	registration_number: "",
	make_model: "",
	current_odometer: 0,
	monthly_driven: 0,
	notes: "",
});
const savingCar = ref(false);

// Keep the editable inputs in sync with the store REACTIVELY. A one-time copy in
// onMounted left the fields blank when the panel mounted before the customer's
// denormalized values settled (header was reactive and showed them, the local
// copy did not). Re-running on every relevant change also refreshes the inputs
// after a save normalises a value or the selected customer changes.
watch(
	() => [
		customerStore.customer?.name,
		customerStore.customer?.email_id,
		customerStore.customer?.mobile_no,
		customerStore.customer?.custom_whatsapp,
		customerStore.customer?.loyalty_program,
	],
	() => {
		const c = customerStore.customer;
		if (!c) return;
		editEmail.value = c.email_id || "";
		editMobile.value = c.mobile_no || "";
		editWhatsapp.value = c.custom_whatsapp || "";
		editLoyaltyProgram.value = c.loyalty_program || "";
	},
	{ immediate: true },
);

onMounted(async () => {
	await fetchTransactions();
	await fetchRecentAlignmentRecords();
});

async function fetchTransactions() {
	if (!customerStore.customer) return;
	loadingTx.value = true;
	try {
		const data = await call("pos_prime.api.customer_profile.get_customer_pos_invoices", {
			customer: customerStore.customer.name,
			company: sessionStore.company || "",
			limit: 20,
		});
		transactions.value = data || [];
	} catch {
		transactions.value = [];
	} finally {
		loadingTx.value = false;
	}
}

async function fetchRecentAlignmentRecords() {
	loadingAlignment.value = true;
	try {
		const result = await fetchAlignmentReports(1, 5);
		alignmentRecords.value = result.reports;
	} catch {
		alignmentRecords.value = [];
	} finally {
		loadingAlignment.value = false;
	}
}

async function linkAlignmentToCar(record: AlignmentReport) {
	if (!customerStore.customer || !record.vehicle_registration) return;
	linkingRecord.value = record.report_id;
	try {
		const makeModel = [record.manufacturer_name, record.model_name, record.model_year_raw]
			.filter(Boolean)
			.join(" ");
		await call("pos_prime.api.alignment.link_alignment_record", {
			report_id: record.report_id,
			registration_number: record.vehicle_registration,
			customer: customerStore.customer.name,
			customer_name: customerStore.customer.customer_name,
			customer_phone: customerStore.customer.mobile_no || "",
			make_model: makeModel,
			current_odometer: record.mileage_raw || 0,
		});
		// Refresh cars list
		await customerStore.setCustomer(customerStore.customer.name);
		// Remove linked record from list
		alignmentRecords.value = alignmentRecords.value.filter(
			(r) => r.report_id !== record.report_id,
		);
		const frappe = (window as any).frappe;
		frappe?.show_alert?.({
			message: __("Car linked to customer!"),
			indicator: "green",
		});
	} catch (e: any) {
		const frappe = (window as any).frappe;
		frappe?.show_alert?.({
			message: e?.messages?.[0] || __("Could not link car"),
			indicator: "red",
		});
	} finally {
		linkingRecord.value = null;
	}
}

function formatAlignmentDate(value?: string | null): string {
	if (!value) return "";
	const compact = value.match(/^(\d{4})(\d{2})(\d{2})$/);
	const parsed = compact
		? new Date(`${compact[1]}-${compact[2]}-${compact[3]}T00:00:00`)
		: new Date(value);
	return Number.isNaN(parsed.getTime())
		? value
		: new Intl.DateTimeFormat(undefined, { day: "2-digit", month: "short", year: "numeric" }).format(parsed);
}

async function saveField(fieldname: string) {
	if (!customerStore.customer) return;
	const value = (
		fieldname === "email_id"
			? editEmail.value
			: fieldname === "mobile_no"
				? editMobile.value
				: fieldname === "custom_whatsapp"
					? editWhatsapp.value
					: editLoyaltyProgram.value
	).trim();

	// Skip if unchanged
	const original = (customerStore.customer as any)[fieldname] || "";
	if (value === original) return;

	savingField.value = fieldname;
	try {
		await call("pos_prime.api.customers.update_customer_field", {
			customer: customerStore.customer.name,
			fieldname,
			value,
		});
		// Refresh customer data — the watch above re-syncs the local edit fields.
		await customerStore.setCustomer(customerStore.customer.name);
	} catch (e: any) {
		const frappe = (window as any).frappe;
		frappe?.show_alert?.({
			message: e.messages?.[0] || __("Failed to update"),
			indicator: "red",
		});
	} finally {
		savingField.value = null;
	}
}

// Build a wa.me link. Strips non-digits and assumes India (+91) for bare
// 10-digit numbers entered without a country code.
function waLink(num: string): string {
	const digits = (num || "").replace(/\D/g, "");
	const full = digits.length === 10 ? `91${digits}` : digits;
	return `https://wa.me/${full}`;
}

function openWhatsapp(num: string) {
	const digits = (num || "").replace(/\D/g, "");
	if (digits.length < 8) return;
	window.open(waLink(num), "_blank", "noopener");
}

function openCar(car: CustomerCar) {
	selectedCar.value = car;
	carForm.registration_number = car.registration_number || "";
	carForm.make_model = car.make_model || "";
	carForm.current_odometer = car.current_odometer || 0;
	carForm.monthly_driven = car.monthly_driven || 0;
	carForm.notes = car.notes || "";
	carDialogOpen.value = true;
}

function openCarExternal(name: string | null) {
	if (!name) return;
	window.open(deskUrl(`customer-car/${encodeURIComponent(name)}`), "_blank");
}

async function saveCarDetails() {
	if (!selectedCar.value?.name) return;
	savingCar.value = true;
	try {
		await call("pos_prime.api.customers.update_car", {
			car_name: selectedCar.value.name,
			registration_number: carForm.registration_number.trim(),
			make_model: carForm.make_model.trim(),
			current_odometer: carForm.current_odometer || 0,
			monthly_driven: carForm.monthly_driven || 0,
			notes: carForm.notes.trim(),
		});
		// Refresh cars list
		if (customerStore.customer) {
			await customerStore.setCustomer(customerStore.customer.name);
		}
		carDialogOpen.value = false;
		const frappe = (window as any).frappe;
		frappe?.show_alert?.({
			message: __("Car details saved!"),
			indicator: "green",
		});
	} catch (e: any) {
		const frappe = (window as any).frappe;
		frappe?.show_alert?.({
			message: e?.messages?.[0] || __("Could not save car details"),
			indicator: "red",
		});
	} finally {
		savingCar.value = false;
	}
}

function formatKm(n: number): string {
	if (!n) return "";
	try {
		return new Intl.NumberFormat().format(Math.round(n));
	} catch {
		return String(Math.round(n));
	}
}

function openCustomerForm() {
	if (!customerStore.customer) return;
	window.open(deskUrl(`customer/${encodeURIComponent(customerStore.customer.name)}`), "_blank");
}

function openInvoice(invoiceName: string) {
	window.open(deskUrl(`pos-invoice/${encodeURIComponent(invoiceName)}`), "_blank");
}

function statusColor(status: string, isReturn: boolean): string {
	if (isReturn) return "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400";
	if (status === "Paid")
		return "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400";
	if (status === "Consolidated")
		return "bg-gray-200 dark:bg-gray-700 text-gray-950 dark:text-gray-100";
	if (status === "Draft") return "bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400";
	return "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400";
}

function formatDate(dateStr: string): string {
	if (!dateStr) return "";
	const frappe = (window as any).frappe;
	if (frappe?.datetime?.str_to_user) {
		return frappe.datetime.str_to_user(dateStr);
	}
	return dateStr;
}

function timeAgo(dateStr: string): string {
	if (!dateStr) return "";
	const frappe = (window as any).frappe;
	if (frappe?.datetime?.comment_when) {
		return frappe.datetime.comment_when(dateStr);
	}
	return dateStr;
}
</script>

<template>
	<div
		class="customer-detail-overlay fixed inset-0 z-50 flex items-stretch justify-end"
		role="dialog"
		aria-modal="true"
		@keydown.escape="emit('close')"
	>
		<!-- Backdrop -->
		<div
			class="customer-detail-backdrop absolute inset-0 bg-black/20 dark:bg-black/50 backdrop-blur-sm"
			@click="emit('close')"
		/>

		<!-- Panel (slide-in from right) -->
		<div
			class="customer-detail-panel relative w-full m-2 rounded-2xl max-w-md bg-white/90 backdrop-blur-xl dark:bg-gray-900 shadow-2xl dark:shadow-black/50 flex flex-col overflow-hidden"
		>
			<!-- Header -->
			<div
				class="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900"
			>
				<h3 class="text-sm font-bold text-gray-900 dark:text-gray-100">
					{{ __("Customer Details") }}
				</h3>
				<div class="flex items-center gap-1">
					<button
						@click="openCustomerForm"
						class="w-7 h-7 rounded-lg flex items-center justify-center text-gray-400 dark:text-gray-500 hover:text-gray-950 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
						:title="__('Open Full Form')"
					>
						<ExternalLink :size="14" />
					</button>
					<button
						@click="emit('close')"
						class="w-7 h-7 rounded-lg flex items-center justify-center text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
					>
						<X :size="16" />
					</button>
				</div>
			</div>

			<!-- Scrollable content -->
			<div v-if="customerStore.customer" class="flex-1 overflow-y-auto">
				<!-- Customer identity -->
				<div class="px-4 py-4 border-b border-gray-100 dark:border-gray-800">
					<div class="flex items-center gap-3">
						<div
							class="w-12 h-12 bg-gray-200 dark:bg-gray-700 rounded-xl flex items-center justify-center shrink-0"
						>
							<User :size="22" class="text-gray-950 dark:text-gray-100" />
						</div>
						<div class="min-w-0">
							<div
								class="text-base font-bold text-gray-900 dark:text-gray-100 truncate"
							>
								{{ customerStore.customer.customer_name }}
							</div>
							<div class="text-xs text-gray-500 dark:text-gray-400">
								{{ customerStore.customer.name }}
							</div>
							<div
								v-if="customerStore.customer.customer_group"
								class="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5"
							>
								{{ customerStore.customer.customer_group }}
								<span v-if="customerStore.customer.territory">
									&middot; {{ customerStore.customer.territory }}</span
								>
							</div>
						</div>
					</div>

					<!-- Quick stats -->
					<div class="flex gap-2 mt-3 flex-wrap">
						<div
							v-if="customerStore.loyaltyPoints > 0"
							class="flex items-center gap-1 px-2 py-1 bg-violet-50 dark:bg-violet-900/20 rounded-lg"
						>
							<Tag :size="12" class="text-violet-500" />
							<span
								class="text-xs font-semibold text-violet-700 dark:text-violet-400"
								>{{ customerStore.loyaltyPoints }} {{ __("pts") }}</span
							>
						</div>
						<div
							v-if="customerStore.outstanding > 0"
							class="flex items-center gap-1 px-2 py-1 bg-amber-50 dark:bg-amber-900/20 rounded-lg"
						>
							<AlertTriangle :size="12" class="text-amber-500" />
							<span class="text-xs font-semibold text-amber-700 dark:text-amber-400"
								>{{ __("Outstanding") }}:
								{{ formatCurrency(customerStore.outstanding) }}</span
							>
						</div>
						<div
							v-if="customerStore.creditLimit > 0"
							class="flex items-center gap-1 px-2 py-1 rounded-lg"
							:class="
								customerStore.outstanding > customerStore.creditLimit
									? 'bg-red-50 dark:bg-red-900/20'
									: 'bg-gray-50 dark:bg-gray-800'
							"
						>
							<CreditCard
								:size="12"
								:class="
									customerStore.outstanding > customerStore.creditLimit
										? 'text-red-500'
										: 'text-gray-400'
								"
							/>
							<span
								class="text-xs font-semibold"
								:class="
									customerStore.outstanding > customerStore.creditLimit
										? 'text-red-700 dark:text-red-400'
										: 'text-gray-600 dark:text-gray-400'
								"
								>{{ __("Limit") }}:
								{{ formatCurrency(customerStore.creditLimit) }}</span
							>
						</div>
						<div
							v-if="customerStore.storeCredit > 0"
							class="flex items-center gap-1 px-2 py-1 bg-green-50 dark:bg-green-900/20 rounded-lg"
						>
							<Wallet :size="12" class="text-green-500" />
							<span class="text-xs font-semibold text-green-700 dark:text-green-400"
								>{{ __("Credit") }}:
								{{ formatCurrency(customerStore.storeCredit) }}</span
							>
						</div>
					</div>
				</div>

				<!-- Editable fields -->
				<div class="px-4 py-3 border-b border-gray-100 dark:border-gray-800 space-y-3">
					<div
						class="text-[10px] font-bold text-gray-400 dark:text-gray-500 uppercase tracking-wider"
					>
						{{ __("Contact Details") }}
					</div>

					<!-- Email -->
					<div>
						<label
							class="text-[10px] font-medium text-gray-500 dark:text-gray-400 mb-1 block"
							>{{ __("Email") }}</label
						>
						<div class="flex items-center gap-2">
							<Mail :size="14" class="text-gray-400 shrink-0" />
							<Input
								v-model="editEmail"
								type="email"
								:placeholder="__('Email address')"
								@blur="saveField('email_id')"
								@keydown.enter="($event.target as HTMLInputElement).blur()"
								:disabled="savingField === 'email_id'"
								class="flex-1 text-sm text-gray-800 dark:text-gray-200 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-gray-950 focus:border-gray-950 dark:focus:ring-gray-300 dark:focus:border-gray-300 transition-colors disabled:opacity-50 placeholder-gray-400 dark:placeholder-gray-500"
							/>
							<span
								v-if="savingField === 'email_id'"
								class="text-[10px] text-gray-700 dark:text-gray-300 shrink-0"
								>{{ __("Saving...") }}</span
							>
						</div>
					</div>

					<!-- Mobile -->
					<div>
						<label
							class="text-[10px] font-medium text-gray-500 dark:text-gray-400 mb-1 block"
							>{{ __("Mobile") }}</label
						>
						<div class="flex items-center gap-2">
							<Phone :size="14" class="text-gray-400 shrink-0" />
							<Input
								v-model="editMobile"
								type="tel"
								:placeholder="__('Mobile number')"
								@blur="saveField('mobile_no')"
								@keydown.enter="($event.target as HTMLInputElement).blur()"
								:disabled="savingField === 'mobile_no'"
								class="flex-1 text-sm text-gray-800 dark:text-gray-200 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-gray-950 focus:border-gray-950 dark:focus:ring-gray-300 dark:focus:border-gray-300 transition-colors disabled:opacity-50 placeholder-gray-400 dark:placeholder-gray-500"
							/>
							<span
								v-if="savingField === 'mobile_no'"
								class="text-[10px] text-gray-700 dark:text-gray-300 shrink-0"
								>{{ __("Saving...") }}</span
							>
						</div>
					</div>

					<!-- WhatsApp -->
					<div>
						<label
							class="text-[10px] font-medium text-gray-500 dark:text-gray-400 mb-1 block"
							>{{ __("WhatsApp") }}</label
						>
						<div class="flex items-center gap-2">
							<MessageCircle :size="14" class="text-[#25D366] shrink-0" />
							<Input
								v-model="editWhatsapp"
								type="tel"
								:placeholder="__('WhatsApp number')"
								@blur="saveField('custom_whatsapp')"
								@keydown.enter="($event.target as HTMLInputElement).blur()"
								:disabled="savingField === 'custom_whatsapp'"
								class="flex-1 text-sm text-gray-800 dark:text-gray-200 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-gray-950 focus:border-gray-950 dark:focus:ring-gray-300 dark:focus:border-gray-300 transition-colors disabled:opacity-50 placeholder-gray-400 dark:placeholder-gray-500"
							/>
							<span
								v-if="savingField === 'custom_whatsapp'"
								class="text-[10px] text-gray-700 dark:text-gray-300 shrink-0"
								>{{ __("Saving...") }}</span
							>
							<button
								v-else-if="editWhatsapp"
								type="button"
								@click="openWhatsapp(editWhatsapp)"
								:title="__('Open chat in WhatsApp')"
								class="shrink-0 inline-flex items-center gap-1 px-2 py-1.5 rounded-md bg-[#25D366]/10 text-[#1fa855] dark:text-[#25D366] hover:bg-[#25D366]/20 transition-colors text-[11px] font-semibold"
							>
								{{ __("Chat") }}
								<ExternalLink :size="11" />
							</button>
						</div>
					</div>

					<!-- Loyalty Program -->
					<div
						v-if="customerStore.customer.loyalty_program || editLoyaltyProgram"
						class="flex items-center gap-2"
					>
						<Tag :size="14" class="text-gray-400 shrink-0" />
						<span class="text-sm text-gray-600 dark:text-gray-400">{{
							editLoyaltyProgram || __("No loyalty program")
						}}</span>
					</div>

					<!-- Primary Address -->
					<div v-if="customerStore.addresses.length > 0" class="flex items-start gap-2">
						<MapPin :size="14" class="text-gray-400 shrink-0 mt-0.5" />
						<div class="text-xs text-gray-600 dark:text-gray-400">
							<span class="font-medium text-gray-700 dark:text-gray-300">
								{{
									customerStore.addresses.find((a) => a.is_primary_address)
										?.address_title || customerStore.addresses[0].address_title
								}}
							</span>
							<br />
							{{
								customerStore.addresses.find((a) => a.is_primary_address)
									?.address_line1 || customerStore.addresses[0].address_line1
							}}
							<span
								v-if="
									(
										customerStore.addresses.find(
											(a) => a.is_primary_address,
										) || customerStore.addresses[0]
									).city
								"
							>
								,
								{{
									(
										customerStore.addresses.find(
											(a) => a.is_primary_address,
										) || customerStore.addresses[0]
									).city
								}}
							</span>
						</div>
					</div>
				</div>

				<!-- Tabs -->
				<Tabs
					:model-value="activeTab"
					@update:model-value="(val) => activeTab = String(val)"
					class="w-full !flex-col"
				>
					<div class="px-4 py-2">
						<TabsList class="grid w-full grid-cols-2">
							<TabsTrigger value="cars">
								<Car :size="13" />
								{{ __("Cars") }}
								<span
									v-if="customerStore.cars.length > 0"
									class="ml-1 px-1.5 py-0.5 rounded-full text-[9px] font-bold bg-gray-300 dark:bg-gray-600 text-gray-700 dark:text-gray-200"
								>{{ customerStore.cars.length }}</span>
							</TabsTrigger>
							<TabsTrigger value="transactions">
								<FileText :size="13" />
								{{ __("Transactions") }}
								<span
									v-if="transactions.length > 0"
									class="ml-1 px-1.5 py-0.5 rounded-full text-[9px] font-bold bg-gray-300 dark:bg-gray-600 text-gray-700 dark:text-gray-200"
								>{{ transactions.length }}</span>
							</TabsTrigger>
						</TabsList>
					</div>

				<!-- Cars Tab -->
				<TabsContent value="cars" class="mt-0">
					<div class="px-4 py-3 space-y-4">
						<!-- Customer's own cars -->
						<div>
							<div class="text-[10px] font-bold text-gray-400 dark:text-gray-500 uppercase tracking-wider mb-2">
								{{ __("Customer Cars") }}
							</div>
							<div v-if="customerStore.cars.length === 0" class="py-4 text-center">
								<Car :size="22" class="text-gray-300 dark:text-gray-600 mx-auto mb-1" />
								<span class="text-xs text-gray-400 dark:text-gray-500">{{ __("No cars linked") }}</span>
							</div>
							<div v-else class="space-y-1.5">
								<button
									v-for="(c, i) in customerStore.cars"
									:key="c.name || i"
									type="button"
									@click="openCar(c)"
									class="w-full flex items-start gap-2.5 px-2.5 py-2 rounded-lg text-left hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors group cursor-pointer"
								>
									<div class="w-7 h-7 rounded-lg bg-gray-100 dark:bg-gray-800 flex items-center justify-center shrink-0 mt-0.5">
										<Car :size="14" class="text-gray-500 dark:text-gray-400" />
									</div>
									<div class="flex-1 min-w-0">
										<div class="flex items-center gap-1.5">
											<span class="text-sm font-semibold text-gray-800 dark:text-gray-200 truncate">
												{{ c.registration_number || c.make_model || __("Car") }}
											</span>
											<span v-if="c.registration_number && c.make_model" class="text-xs text-gray-500 dark:text-gray-400 truncate">
												&middot; {{ c.make_model }}
											</span>
										</div>
										<div v-if="c.current_odometer || c.monthly_driven" class="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5">
											<span v-if="c.current_odometer">{{ formatKm(c.current_odometer) }} {{ __("km") }}</span>
											<span v-if="c.current_odometer && c.monthly_driven"> &middot; </span>
											<span v-if="c.monthly_driven">~{{ formatKm(c.monthly_driven) }}/{{ __("mo") }}</span>
										</div>
										<div v-if="c.notes" class="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5 truncate">{{ c.notes }}</div>
									</div>
									<!-- External link as separate button -->
									<button
										v-if="c.name"
										type="button"
										@click.stop="openCarExternal(c.name)"
										class="shrink-0 mt-1 w-5 h-5 flex items-center justify-center rounded hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
										:title="__('Open in Frappe')"
									>
										<ExternalLink :size="11" class="text-gray-400 dark:text-gray-500" />
									</button>
								</button>
							</div>
						</div>

						<!-- Recent Alignment Records -->
						<div class="border-t border-gray-100 dark:border-gray-800 pt-3">
							<div class="text-[10px] font-bold text-gray-400 dark:text-gray-500 uppercase tracking-wider mb-2">
								{{ __("Recent Alignment Records") }}
							</div>
							<div v-if="loadingAlignment" class="py-4 text-center">
								<Loader2 :size="18" class="text-gray-300 dark:text-gray-600 mx-auto animate-spin" />
							</div>
							<div v-else-if="alignmentRecords.length === 0" class="py-4 text-center">
								<span class="text-xs text-gray-400 dark:text-gray-500">{{ __("No recent alignment records") }}</span>
							</div>
							<div v-else class="space-y-1.5">
								<div
									v-for="rec in alignmentRecords"
									:key="rec.report_id"
									class="flex items-center gap-2.5 px-2.5 py-2 rounded-lg bg-gray-50 dark:bg-gray-800/60"
								>
									<div class="w-7 h-7 rounded-lg bg-blue-50 dark:bg-blue-900/30 flex items-center justify-center shrink-0">
										<Car :size="14" class="text-blue-500 dark:text-blue-400" />
									</div>
									<div class="flex-1 min-w-0">
										<div class="text-xs font-semibold text-gray-800 dark:text-gray-200 truncate">
											{{ rec.vehicle_registration || __("Unknown Plate") }}
										</div>
										<div class="text-[10px] text-gray-400 dark:text-gray-500 truncate">
											<span v-if="rec.manufacturer_name || rec.model_name">
												{{ [rec.manufacturer_name, rec.model_name].filter(Boolean).join(" ") }}
												<span v-if="rec.report_date_raw"> &middot; </span>
											</span>
											{{ formatAlignmentDate(rec.report_date_raw) }}
										</div>
									</div>
									<button
										v-if="rec.vehicle_registration"
										type="button"
										@click="linkAlignmentToCar(rec)"
										:disabled="linkingRecord === rec.report_id"
										class="shrink-0 inline-flex items-center gap-1 px-2 py-1 rounded-md bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900 text-[10px] font-semibold hover:bg-gray-700 dark:hover:bg-gray-300 disabled:opacity-50 transition-colors"
									>
										<Loader2 v-if="linkingRecord === rec.report_id" :size="10" class="animate-spin" />
										<Link2 v-else :size="10" />
										{{ __("Link") }}
									</button>
								</div>
							</div>
						</div>
					</div>
				</TabsContent>

				<!-- Transactions Tab -->
				<TabsContent value="transactions" class="mt-0">
					<div class="px-4 py-3">
					<div class="flex items-center justify-between mb-2">
						<div class="text-[10px] font-bold text-gray-400 dark:text-gray-500 uppercase tracking-wider">
							{{ __("Recent Transactions") }}
						</div>
						<span v-if="transactions.length > 0" class="text-[10px] text-gray-400 dark:text-gray-500">
							{{ __("Last") }}: {{ timeAgo(transactions[0]?.posting_date) }}
						</span>
					</div>

					<div v-if="loadingTx" class="py-6 text-center">
						<span class="text-xs text-gray-400 dark:text-gray-500">{{ __("Loading...") }}</span>
					</div>

					<div v-else-if="transactions.length === 0" class="py-6 text-center">
						<FileText :size="24" class="text-gray-300 dark:text-gray-600 mx-auto mb-1" />
						<span class="text-xs text-gray-400 dark:text-gray-500">{{ __("No transactions found") }}</span>
					</div>

					<div v-else class="space-y-1">
						<button
							v-for="tx in transactions"
							:key="tx.name"
							@click="openInvoice(tx.name)"
							class="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors text-left group"
						>
							<div class="flex-1 min-w-0">
								<div class="flex items-center gap-1.5">
									<span class="text-xs font-semibold text-gray-800 dark:text-gray-200">{{ tx.name }}</span>
									<span
										class="inline-flex px-1.5 py-0.5 rounded text-[9px] font-bold"
										:class="statusColor(tx.status, tx.is_return)"
									>{{ tx.is_return ? __("Return") : tx.status }}</span>
								</div>
								<div class="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5">
									{{ formatDate(tx.posting_date) }}
								</div>
							</div>
							<div class="text-right shrink-0">
								<div
									class="text-sm font-bold"
									:class="tx.is_return ? 'text-red-600 dark:text-red-400' : 'text-gray-800 dark:text-gray-200'"
								>{{ tx.is_return ? "-" : "" }}{{ formatCurrency(tx.grand_total) }}</div>
								<div class="text-[10px] text-gray-400 dark:text-gray-500">{{ tx.total_qty }} {{ __("items") }}</div>
							</div>
							<ExternalLink :size="12" class="text-gray-300 dark:text-gray-600 group-hover:text-gray-950 dark:group-hover:text-gray-100 shrink-0" />
						</button>
					</div>
					</div>
				</TabsContent>
				</Tabs>
			</div>
		</div>
	</div>

		<!-- Car Detail Dialog -->
		<Dialog :open="carDialogOpen" @update:open="carDialogOpen = $event">
			<DialogContent class="sm:max-w-sm">
				<DialogHeader>
					<div class="flex items-center gap-2.5">
						<div class="w-9 h-9 rounded-xl bg-gray-100 dark:bg-gray-800 flex items-center justify-center shrink-0">
							<Car :size="18" class="text-gray-600 dark:text-gray-300" />
						</div>
						<div>
							<DialogTitle class="text-base font-bold text-gray-900 dark:text-gray-100">
								{{ carForm.registration_number || __('Car Details') }}
							</DialogTitle>
							<p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{{ __('Edit car information') }}</p>
						</div>
					</div>
				</DialogHeader>

				<div class="space-y-3 mt-1">
					<!-- Registration Number -->
					<div>
						<label class="text-[11px] font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide block mb-1">{{ __('Registration Number') }}</label>
						<Input v-model="carForm.registration_number" type="text" :placeholder="__('e.g. GJ02CA6176')" class="w-full text-sm font-mono uppercase" />
					</div>

					<!-- Make / Model -->
					<div>
						<label class="text-[11px] font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide block mb-1">{{ __('Make / Model') }}</label>
						<Input v-model="carForm.make_model" type="text" :placeholder="__('e.g. Maruti Suzuki Ertiga')" class="w-full text-sm" />
					</div>

					<!-- Odometer + Monthly -->
					<div class="grid grid-cols-2 gap-3">
						<div>
							<label class="text-[11px] font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide block mb-1">{{ __('Odometer (km)') }}</label>
							<Input v-model.number="carForm.current_odometer" type="number" min="0" :placeholder="__('e.g. 45000')" class="w-full text-sm" />
						</div>
						<div>
							<label class="text-[11px] font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide block mb-1">{{ __('Monthly (km)') }}</label>
							<Input v-model.number="carForm.monthly_driven" type="number" min="0" :placeholder="__('e.g. 1200')" class="w-full text-sm" />
						</div>
					</div>

					<!-- Notes -->
					<div>
						<label class="text-[11px] font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide block mb-1">{{ __('Notes') }}</label>
						<textarea
							v-model="carForm.notes"
							:placeholder="__('Any additional notes...')"
							rows="2"
							class="w-full text-sm text-gray-800 dark:text-gray-200 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-gray-950 focus:border-gray-950 dark:focus:ring-gray-300 dark:focus:border-gray-300 transition-colors resize-none placeholder-gray-400 dark:placeholder-gray-500"
						/>
					</div>
				</div>

				<DialogFooter class="mt-2 flex gap-2">
					<button type="button" @click="carDialogOpen = false" class="flex-1 px-3 py-2 rounded-lg text-sm font-medium text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors">
						{{ __('Cancel') }}
					</button>
					<button type="button" @click="saveCarDetails" :disabled="savingCar" class="flex-1 px-3 py-2 rounded-lg text-sm font-semibold text-white bg-gray-900 dark:bg-gray-100 dark:text-gray-900 hover:bg-gray-700 dark:hover:bg-gray-300 disabled:opacity-50 transition-colors flex items-center justify-center gap-1.5">
						<Loader2 v-if="savingCar" :size="13" class="animate-spin" />
						{{ savingCar ? __('Saving...') : __('Save') }}
					</button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
</template>


<style>
.customer-drawer-enter-active,
.customer-drawer-leave-active {
	transition: opacity 240ms ease;
}

.customer-drawer-leave-active {
	transition-duration: 180ms;
}

.customer-detail-backdrop {
	transition:
		opacity 240ms ease,
		backdrop-filter 240ms ease;
}

.customer-detail-panel {
	transition:
		opacity 240ms ease,
		filter 240ms ease,
		transform 240ms cubic-bezier(0.22, 1, 0.36, 1);
	will-change: opacity, filter, transform;
}

.customer-drawer-leave-active .customer-detail-backdrop,
.customer-drawer-leave-active .customer-detail-panel {
	transition-duration: 180ms;
	transition-timing-function: ease-in;
}

.customer-drawer-enter-from,
.customer-drawer-leave-to {
	opacity: 0;
}

.customer-drawer-enter-from .customer-detail-backdrop,
.customer-drawer-leave-to .customer-detail-backdrop {
	backdrop-filter: blur(0);
}

.customer-drawer-enter-from .customer-detail-panel,
.customer-drawer-leave-to .customer-detail-panel {
	opacity: 0;
	filter: blur(10px);
	transform: translateX(32px) scale(0.992);
}

@media (prefers-reduced-motion: reduce) {
	.customer-drawer-enter-active,
	.customer-drawer-leave-active,
	.customer-detail-backdrop,
	.customer-detail-panel {
		transition-duration: 1ms;
	}

	.customer-drawer-enter-from .customer-detail-panel,
	.customer-drawer-leave-to .customer-detail-panel {
		filter: none;
		transform: none;
	}
}
</style>
