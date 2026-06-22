<script setup lang="ts">
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useCustomerDisplayStore } from "@/stores/customerDisplay";
import { useSettingsStore } from "@/stores/settings";
import type { CustomerCar } from "@/types";
import { deskUrl } from "@/utils/deskUrl";
import {
	Award, Car, CreditCard, ExternalLink, FileText, History, Mail, MapPin,
	Plus, ReceiptText, Star, User, WalletCards,
} from "lucide-vue-next";
import { computed, reactive, ref } from "vue";

const store = useCustomerDisplayStore();
const settingsStore = useSettingsStore();
const activeTab = ref("overview");
const showAddCar = ref(false);
const editingCar = ref<CustomerCar | null>(null);
const savingCar = ref(false);
const carError = ref("");
const carForm = reactive({
	registration_number: "",
	make_model: "",
	current_odometer: 0,
	monthly_driven: 0,
	notes: "",
});

const stats = computed(() => [
	{ label: __("Outstanding"), value: formatCurrency(store.outstanding.outstanding), icon: CreditCard, color: "text-orange-500" },
	{ label: __("Loyalty Points"), value: String(store.selectedCustomer?.loyalty_points || 0), icon: Award, color: "text-purple-500" },
	{ label: __("Invoices"), value: String(store.invoices.length), icon: FileText, color: "text-gray-700 dark:text-gray-300" },
]);

function formatCurrency(amount = 0, currency?: string) {
	const cur = currency || settingsStore.currency || "USD";
	try {
		return new Intl.NumberFormat(undefined, { style: "currency", currency: cur, minimumFractionDigits: 2 }).format(amount);
	} catch {
		return `${cur} ${Number(amount).toFixed(2)}`;
	}
}

function formatDate(dateStr: string) {
	if (!dateStr) return "";
	return new Date(`${dateStr}T00:00:00`).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function invoiceUrl(inv: { doctype?: string; name: string }) {
	const route = inv.doctype === "Sales Invoice" ? "sales-invoice" : "pos-invoice";
	return deskUrl(`${route}/${encodeURIComponent(inv.name)}`);
}

function paymentUrl(name: string) {
	return deskUrl(`payment-entry/${encodeURIComponent(name)}`);
}

function paymentHistoryUrl(payment: { name: string; source_doctype?: string }) {
	return payment.source_doctype === "POS Invoice"
		? deskUrl(`pos-invoice/${encodeURIComponent(payment.name)}`)
		: paymentUrl(payment.name);
}

function resetCarForm() {
	Object.assign(carForm, { registration_number: "", make_model: "", current_odometer: 0, monthly_driven: 0, notes: "" });
	editingCar.value = null;
	carError.value = "";
}

function openAddCar() {
	resetCarForm();
	showAddCar.value = true;
}

function openCarEditor(car: CustomerCar) {
	editingCar.value = car;
	Object.assign(carForm, {
		registration_number: car.registration_number || "",
		make_model: car.make_model || "",
		current_odometer: car.current_odometer || 0,
		monthly_driven: car.monthly_driven || 0,
		notes: car.notes || "",
	});
	carError.value = "";
	showAddCar.value = true;
}

async function createCar() {
	if (!carForm.registration_number.trim()) {
		carError.value = __("Registration number is required");
		return;
	}
	savingCar.value = true;
	carError.value = "";
	try {
		const values = { ...carForm, registration_number: carForm.registration_number.trim() };
		if (editingCar.value?.name) {
			await store.updateCar(editingCar.value.name, values);
		} else {
			await store.addCar(values);
		}
		showAddCar.value = false;
		resetCarForm();
	} catch (error: any) {
		carError.value = error?.messages?.[0] || error?.message || __("Could not save car");
	} finally {
		savingCar.value = false;
	}
}
</script>

<template>
	<div v-if="store.selectedCustomer" class="max-w-5xl mx-auto p-4 lg:p-6 space-y-4">
		<div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-5">
			<div class="flex items-start justify-between gap-4">
				<div class="min-w-0">
					<h3 class="text-xl font-bold text-gray-900 dark:text-gray-100 truncate">{{ store.selectedCustomer.customer_name }}</h3>
					<p class="text-sm text-gray-500 dark:text-gray-400 mt-0.5">{{ store.selectedCustomer.name }}</p>
					<div class="flex flex-wrap items-center gap-2 mt-2 text-xs text-gray-500 dark:text-gray-400">
						<span v-if="store.selectedCustomer.customer_group" class="bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded-full">{{ store.selectedCustomer.customer_group }}</span>
						<span v-if="store.selectedCustomer.territory" class="bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded-full">{{ store.selectedCustomer.territory }}</span>
					</div>
				</div>
				<a :href="deskUrl(`customer/${encodeURIComponent(store.selectedCustomer.name)}`)" target="_blank" class="flex shrink-0 items-center gap-1 text-xs text-gray-900 dark:text-gray-100 hover:underline">
					{{ __("Open in ERPNext") }} <ExternalLink :size="12" />
				</a>
			</div>
		</div>

		<div class="grid grid-cols-3 gap-3">
			<div v-for="stat in stats" :key="stat.label" class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-3 sm:p-4 text-center">
				<component :is="stat.icon" :size="18" class="mx-auto mb-1.5" :class="stat.color" />
				<div class="text-sm sm:text-lg font-bold text-gray-900 dark:text-gray-100 truncate">{{ stat.value }}</div>
				<div class="text-[10px] sm:text-xs text-gray-500 dark:text-gray-400">{{ stat.label }}</div>
			</div>
		</div>

		<Tabs v-model="activeTab" default-value="overview" class="!flex-col gap-4 w-full">
			<div class="w-full overflow-x-auto pb-1">
				<TabsList class="min-w-max w-full justify-start">
					<TabsTrigger value="overview"><User :size="14" />{{ __("Overview") }}</TabsTrigger>
					<TabsTrigger value="transactions"><History :size="14" />{{ __("Transactions") }} <span class="tab-count">{{ store.transactions.length }}</span></TabsTrigger>
					<TabsTrigger value="payments"><WalletCards :size="14" />{{ __("Payments") }} <span class="tab-count">{{ store.payments.length }}</span></TabsTrigger>
					<TabsTrigger value="cars"><Car :size="14" />{{ __("Cars") }} <span class="tab-count">{{ store.cars.length }}</span></TabsTrigger>
					<TabsTrigger value="invoices"><ReceiptText :size="14" />{{ __("Invoices") }} <span class="tab-count">{{ store.invoices.length }}</span></TabsTrigger>
				</TabsList>
			</div>

			<Transition name="customer-tab-blur" mode="out-in">
			<TabsContent v-if="activeTab === 'overview'" value="overview" class="w-full space-y-4 mt-0">
				<div class="detail-card">
					<h4 class="detail-heading">{{ __("Basic Info") }}</h4>
					<div class="grid sm:grid-cols-2 gap-3 text-sm">
						<div class="info-row"><User :size="14" /> <span>{{ store.selectedCustomer.customer_name }}</span></div>
						<div class="info-row"><CreditCard :size="14" /> <span>{{ __("Credit Limit") }}: {{ formatCurrency(store.outstanding.credit_limit) }}</span></div>
						<div v-if="store.selectedCustomer.mobile_no" class="info-row"><WalletCards :size="14" /> <span>{{ store.selectedCustomer.mobile_no }}</span></div>
						<div v-if="store.selectedCustomer.email_id" class="info-row"><Mail :size="14" /> <span>{{ store.selectedCustomer.email_id }}</span></div>
						<div v-if="store.selectedCustomer.tax_id" class="info-row"><FileText :size="14" /> <span>{{ __("Tax ID") }}: {{ store.selectedCustomer.tax_id }}</span></div>
					</div>
				</div>

				<div v-if="store.addresses.length" class="detail-card">
					<h4 class="detail-heading">{{ __("Addresses") }} ({{ store.addresses.length }})</h4>
					<div class="grid md:grid-cols-2 gap-3">
						<div v-for="addr in store.addresses" :key="addr.name" class="rounded-lg bg-gray-50 dark:bg-gray-700/60 p-3">
							<div class="flex items-center gap-2 text-xs font-medium text-gray-800 dark:text-gray-200"><MapPin :size="13" />{{ addr.address_title || addr.name }}<span v-if="addr.is_primary_address" class="badge">{{ __("Primary") }}</span></div>
							<div class="mt-1 ml-5 text-xs text-gray-500 dark:text-gray-400" v-html="addr.display" />
						</div>
					</div>
				</div>

				<div v-if="store.contacts.length" class="detail-card">
					<h4 class="detail-heading">{{ __("Contacts") }} ({{ store.contacts.length }})</h4>
					<div class="grid md:grid-cols-2 gap-3">
						<div v-for="contact in store.contacts" :key="contact.name" class="rounded-lg bg-gray-50 dark:bg-gray-700/60 p-3 text-xs text-gray-500 dark:text-gray-400">
							<div class="flex items-center gap-2 font-medium text-gray-800 dark:text-gray-200"><User :size="13" />{{ contact.full_name }}<span v-if="contact.is_primary_contact" class="badge">{{ __("Primary") }}</span></div>
							<div v-if="contact.mobile_no || contact.phone" class="mt-1 ml-5">{{ contact.mobile_no || contact.phone }}</div>
							<div v-if="contact.email_id" class="ml-5">{{ contact.email_id }}</div>
						</div>
					</div>
				</div>

				<div v-if="store.loyaltyData" class="detail-card">
					<h4 class="detail-heading"><Star :size="14" class="inline text-purple-500 mr-1" />{{ __("Loyalty Program") }}</h4>
					<div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
						<div><span class="text-gray-400">{{ __("Program") }}</span><div class="font-medium mt-1">{{ store.loyaltyData.loyalty_program }}</div></div>
						<div><span class="text-gray-400">{{ __("Points") }}</span><div class="font-medium mt-1">{{ store.loyaltyData.loyalty_points }}</div></div>
						<div><span class="text-gray-400">{{ __("Conversion") }}</span><div class="font-medium mt-1">{{ store.loyaltyData.conversion_factor }}</div></div>
						<div><span class="text-gray-400">{{ __("Redeemable") }}</span><div class="font-medium mt-1">{{ formatCurrency(store.loyaltyData.max_redeemable_amount) }}</div></div>
					</div>
				</div>
			</TabsContent>

			<TabsContent v-else-if="activeTab === 'transactions'" value="transactions" class="w-full mt-0"><div class="detail-card"><h4 class="detail-heading">{{ __("All Transactions") }}</h4>
				<div v-if="!store.transactions.length" class="empty-state">{{ __("No transactions found") }}</div>
				<div v-else class="divide-y divide-gray-100 dark:divide-gray-700">
					<a v-for="(tx, index) in store.transactions" :key="`${tx.type}-${tx.name}-${tx.mode_of_payment}-${index}`" :href="tx.type === 'payment' ? paymentHistoryUrl(tx) : invoiceUrl(tx)" target="_blank" class="flex items-center gap-3 py-3 hover:bg-gray-50 dark:hover:bg-gray-700/40 px-2 rounded-lg">
						<div class="icon-box"><WalletCards v-if="tx.type === 'payment'" :size="15" /><ReceiptText v-else :size="15" /></div>
						<div class="min-w-0 flex-1"><div class="text-sm font-medium truncate">{{ tx.name }}</div><div class="text-xs text-gray-400">{{ tx.type === 'payment' ? __("Payment") : tx.doctype }} - {{ formatDate(tx.posting_date) }}</div></div>
						<div class="text-right"><div class="text-sm font-semibold">{{ formatCurrency(tx.amount, tx.currency) }}</div><div class="text-[10px] text-gray-400">{{ tx.status }}</div></div>
					</a>
				</div></div>
			</TabsContent>

			<TabsContent v-else-if="activeTab === 'payments'" value="payments" class="w-full mt-0"><div class="detail-card"><h4 class="detail-heading">{{ __("Payment History") }}</h4>
				<div v-if="!store.payments.length" class="empty-state">{{ __("No payments found") }}</div>
				<div v-else class="table-wrap"><table class="detail-table"><thead><tr><th>{{ __("Payment") }}</th><th>{{ __("Date") }}</th><th>{{ __("Method") }}</th><th>{{ __("Type") }}</th><th class="text-right">{{ __("Amount") }}</th></tr></thead><tbody>
					<tr v-for="(payment, index) in store.payments" :key="`${payment.source_doctype}-${payment.name}-${payment.mode_of_payment}-${index}`"><td><a :href="paymentHistoryUrl(payment)" target="_blank" class="link">{{ payment.name }}</a></td><td>{{ formatDate(payment.posting_date) }}</td><td>{{ payment.mode_of_payment || "-" }}</td><td>{{ payment.payment_type }}</td><td class="text-right font-medium">{{ formatCurrency(payment.received_amount || payment.paid_amount) }}</td></tr>
				</tbody></table></div></div>
			</TabsContent>

			<TabsContent v-else-if="activeTab === 'cars'" value="cars" class="w-full mt-0"><div class="detail-card">
				<div class="flex items-center justify-between mb-3"><h4 class="detail-heading mb-0">{{ __("Cars") }}</h4><Button @click="openAddCar"><Plus :size="14" />{{ __("Add Car") }}</Button></div>
				<div v-if="!store.cars.length" class="empty-state"><Car :size="28" class="mx-auto mb-2" />{{ __("No cars added yet") }}</div>
				<div v-else class="grid sm:grid-cols-2 gap-3"><button v-for="car in store.cars" :key="car.name || car.registration_number" type="button" @click="openCarEditor(car)" class="rounded-xl border border-gray-200 dark:border-gray-700 p-4 text-left hover:bg-gray-50 dark:hover:bg-gray-700/40 transition-colors">
					<div class="flex gap-3"><div class="icon-box"><Car :size="17" /></div><div class="min-w-0"><div class="font-semibold text-sm">{{ car.registration_number || __("Car") }}</div><div class="text-xs text-gray-500 mt-0.5">{{ car.make_model || __("Make and model not set") }}</div><div v-if="car.current_odometer" class="text-xs text-gray-400 mt-2">{{ Number(car.current_odometer).toLocaleString() }} km</div><div v-if="car.notes" class="text-xs text-gray-400 mt-1 truncate">{{ car.notes }}</div></div></div>
				</button></div>
			</div></TabsContent>

			<TabsContent v-else value="invoices" class="w-full mt-0"><div class="detail-card"><h4 class="detail-heading">{{ __("Invoices") }}</h4>
				<div v-if="!store.invoices.length" class="empty-state">{{ __("No invoices found") }}</div>
				<div v-else class="table-wrap"><table class="detail-table"><thead><tr><th>{{ __("Invoice") }}</th><th>{{ __("Date") }}</th><th>{{ __("Type") }}</th><th class="text-right">{{ __("Qty") }}</th><th class="text-right">{{ __("Total") }}</th><th>{{ __("Status") }}</th></tr></thead><tbody>
					<tr v-for="inv in store.invoices" :key="`${inv.doctype}-${inv.name}`"><td><a :href="invoiceUrl(inv)" target="_blank" class="link">{{ inv.name }}</a></td><td>{{ formatDate(inv.posting_date) }}</td><td>{{ inv.doctype }}</td><td class="text-right">{{ inv.total_qty }}</td><td class="text-right font-medium">{{ formatCurrency(inv.grand_total, inv.currency) }}</td><td><span class="badge">{{ inv.is_return ? __("Return") : inv.status }}</span></td></tr>
				</tbody></table></div></div>
			</TabsContent>
			</Transition>
		</Tabs>

		<Dialog v-model:open="showAddCar">
			<DialogContent class="car-dialog sm:max-w-lg !gap-0 !rounded-2xl !p-0 [&_*]:box-border">
				<DialogHeader class="border-b border-gray-100 dark:border-gray-700 px-6 py-5">
					<DialogTitle>{{ editingCar ? __("Edit Car") : __("Add Car") }}</DialogTitle>
				</DialogHeader>
				<form @submit.prevent="createCar">
					<div class="space-y-4 px-6 py-5">
						<div><label class="form-label">{{ __("Registration Number") }} *</label><input v-model="carForm.registration_number" autofocus class="car-form-control" :placeholder="__('e.g. MH 01 AB 1234')" /></div>
						<div><label class="form-label">{{ __("Make and Model") }}</label><input v-model="carForm.make_model" class="car-form-control" :placeholder="__('e.g. Hyundai Creta')" /></div>
						<div class="grid grid-cols-1 gap-4 sm:grid-cols-2"><div><label class="form-label">{{ __("Odometer (km)") }}</label><input v-model.number="carForm.current_odometer" class="car-form-control" type="number" min="0" /></div><div><label class="form-label">{{ __("Monthly Driving (km)") }}</label><input v-model.number="carForm.monthly_driven" class="car-form-control" type="number" min="0" /></div></div>
						<div><label class="form-label">{{ __("Notes") }}</label><textarea v-model="carForm.notes" rows="3" class="car-form-control car-form-textarea" /></div>
						<p v-if="carError" class="text-xs text-red-600">{{ carError }}</p>
					</div>
					<DialogFooter class="!m-0 !rounded-b-2xl !px-6 !py-4"><Button type="button" variant="outline" @click="showAddCar = false">{{ __("Cancel") }}</Button><Button type="submit" :disabled="savingCar">{{ savingCar ? __("Saving...") : editingCar ? __("Save Changes") : __("Add Car") }}</Button></DialogFooter>
				</form>
			</DialogContent>
		</Dialog>
	</div>
</template>

<style scoped>
.detail-card { @apply bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 sm:p-5; }
.detail-heading { @apply text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3; }
.info-row { @apply flex items-center gap-2 text-gray-600 dark:text-gray-400; }
.info-row svg { @apply text-gray-400 shrink-0; }
.badge { @apply inline-flex px-1.5 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 text-[10px] text-gray-600 dark:text-gray-300; }
.tab-count { @apply rounded-full bg-white/70 dark:bg-gray-700 px-1.5 py-0.5 text-[10px]; }
.empty-state { @apply py-10 text-center text-xs text-gray-400 dark:text-gray-500; }
.icon-box { @apply w-9 h-9 rounded-lg bg-gray-100 dark:bg-gray-700 flex items-center justify-center shrink-0 text-gray-500; }
.table-wrap { @apply overflow-x-auto -mx-5 px-5; }
.detail-table { @apply w-full min-w-[640px] text-xs; }
.detail-table th { @apply text-left text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700 pb-2 pr-3 font-medium; }
.detail-table td { @apply py-3 pr-3 text-gray-600 dark:text-gray-400 border-b border-gray-100 dark:border-gray-700; }
.link { @apply font-medium text-gray-900 dark:text-gray-100 hover:underline; }
.form-label { @apply block text-xs font-medium text-gray-600 dark:text-gray-300 mb-1.5; }
.car-form-control {
	display: block;
	width: 100%;
	height: 40px;
	box-sizing: border-box;
	border: 1px solid rgb(229 231 235);
	border-radius: 0.75rem;
	background: rgb(249 250 251);
	padding: 0.5rem 0.75rem;
	font: inherit;
	font-size: 0.875rem;
	line-height: 1.25rem;
	color: rgb(17 24 39);
	outline: none;
	transition: border-color 150ms ease, box-shadow 150ms ease, background-color 150ms ease;
}
.car-form-control:focus {
	border-color: rgb(156 163 175);
	background: white;
	box-shadow: 0 0 0 3px rgb(17 24 39 / 0.06);
}
.car-form-textarea {
	height: 88px;
	resize: vertical;
}
:global(.dark) .car-form-control {
	border-color: rgb(55 65 81);
	background: rgb(31 41 55);
	color: rgb(243 244 246);
}
:global(.dark) .car-form-control:focus {
	border-color: rgb(107 114 128);
	background: rgb(31 41 55);
	box-shadow: 0 0 0 3px rgb(255 255 255 / 0.08);
}

.customer-tab-blur-enter-active,
.customer-tab-blur-leave-active {
	transition:
		opacity 180ms ease,
		filter 180ms ease,
		transform 180ms ease;
}

.customer-tab-blur-enter-from,
.customer-tab-blur-leave-to {
	opacity: 0;
	filter: blur(10px);
	transform: translateY(5px);
}

@media (prefers-reduced-motion: reduce) {
	.customer-tab-blur-enter-active,
	.customer-tab-blur-leave-active {
		transition-duration: 1ms;
	}

	.customer-tab-blur-enter-from,
	.customer-tab-blur-leave-to {
		filter: none;
		transform: none;
	}
}
</style>
