<!-- Copyright (c) 2026, Ravindu Gajanayaka -->
<!-- Licensed under GPLv3. See license.txt -->

<script setup lang="ts">
import NewCustomerDialog from "@/components/customer/NewCustomerDialog.vue";
import Input from "@/components/ui/input/Input.vue";
import { useCurrency } from "@/composables/useCurrency";
import { useCustomerStore } from "@/stores/customer";
import { usePosSessionStore } from "@/stores/posSession";
import { AlertTriangle, ChevronRight, Phone, Plus, Search, Tag, User, X } from "lucide-vue-next";
import { onUnmounted, ref, watch } from "vue";

const { formatCurrency } = useCurrency();

const emit = defineEmits<{
	openDetail: [];
}>();

const customerStore = useCustomerStore();
const sessionStore = usePosSessionStore();
const searchTerm = ref("");
const results = ref<
	{ name: string; customer_name: string; mobile_no?: string; email_id?: string }[]
>([]);
const showDropdown = ref(false);
let debounceTimer: ReturnType<typeof setTimeout>;

// Quick Entry state
const showQuickEntry = ref(false);

onUnmounted(() => {
	clearTimeout(debounceTimer);
});

watch(searchTerm, (term) => {
	clearTimeout(debounceTimer);
	if (term.length < 2) {
		results.value = [];
		showDropdown.value = false;
		return;
	}
	debounceTimer = setTimeout(async () => {
		results.value = await customerStore.searchCustomers(term, sessionStore.posProfile);
		showDropdown.value = results.value.length > 0;
	}, 300);
});

async function selectCustomer(name: string) {
	await customerStore.setCustomer(name);
	searchTerm.value = "";
	results.value = [];
	showDropdown.value = false;
}

function clearCustomer() {
	customerStore.$reset();
}

function openQuickEntry() {
	showQuickEntry.value = true;
}

function closeQuickEntry() {
	showQuickEntry.value = false;
}

function onCustomerCreated() {
	closeQuickEntry();
	searchTerm.value = "";
	results.value = [];
	showDropdown.value = false;
}
</script>

<template>
	<div class="relative">
		<!-- Selected customer display (ERPNext-style: circular avatar + name/desc) -->
		<div
			v-if="customerStore.customer"
			class="flex items-center gap-3 bg-gray-50 rounded-2xl p-2 border border-gray-100"
		>
			<button
				@click="emit('openDetail')"
				class="flex items-center gap-3 flex-1 min-w-0 text-left cursor-pointer"
			>
				<!-- Circular avatar (ERPNext-style) -->
				<div
					class="w-10 h-10 rounded-full flex items-center justify-center shrink-0 bg-gray-100 dark:bg-gray-800"
				>
					<User :size="18" class="text-gray-500 dark:text-gray-400" />
				</div>
				<div class="flex-1 min-w-0">
					<div class="text-sm font-bold text-gray-900 dark:text-gray-100 truncate">
						{{ customerStore.customer.customer_name }}
					</div>
					<div class="flex items-center gap-1.5 flex-wrap mt-0.5">
						<span
							v-if="customerStore.customer.mobile_no"
							class="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-0.5 font-medium"
						>
							<Phone :size="10" />
							{{ customerStore.customer.mobile_no }}
						</span>
						<span
							v-if="customerStore.customer.email_id"
							class="text-xs text-gray-500 dark:text-gray-400 font-medium"
						>
							{{ customerStore.customer.mobile_no ? "·" : "" }}
							{{ customerStore.customer.email_id }}
						</span>
						<span
							v-else-if="customerStore.customer.customer_group"
							class="text-xs text-gray-400 dark:text-gray-500 font-medium"
						>
							{{ customerStore.customer.mobile_no ? "·" : "" }}
							{{ customerStore.customer.customer_group }}
						</span>
					</div>
					<div
						v-if="
							customerStore.loyaltyPoints > 0 ||
							customerStore.outstanding > 0 ||
							customerStore.creditLimit > 0
						"
						class="flex items-center gap-1.5 flex-wrap mt-1"
					>
						<span
							v-if="customerStore.loyaltyPoints > 0"
							class="inline-flex items-center gap-0.5 px-1.5 py-0.5 bg-violet-100 dark:bg-violet-900/40 text-violet-600 dark:text-violet-400 rounded-md text-[9px] font-bold"
						>
							<Tag :size="8" />
							{{ customerStore.loyaltyPoints }} pts
						</span>
						<span
							v-if="customerStore.outstanding > 0"
							class="inline-flex items-center gap-0.5 px-1.5 py-0.5 bg-amber-100 dark:bg-amber-900/40 text-amber-600 dark:text-amber-400 rounded-md text-[9px] font-bold"
						>
							<AlertTriangle :size="8" />
							{{ formatCurrency(customerStore.outstanding) }}
						</span>
						<span
							v-if="customerStore.creditLimit > 0"
							class="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md text-[9px] font-bold"
							:class="
								customerStore.outstanding > customerStore.creditLimit
									? 'bg-red-100 dark:bg-red-900/40 text-red-600 dark:text-red-400'
									: 'bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400'
							"
						>
							{{ __("Limit") }}: {{ formatCurrency(customerStore.creditLimit) }}
						</span>
					</div>
				</div>
				<ChevronRight :size="14" class="text-gray-400 dark:text-gray-500 shrink-0" />
			</button>
			<button
				@click="clearCustomer"
				class="w-7 h-7 rounded-md flex items-center justify-center text-gray-400 dark:text-gray-500 hover:text-red-500 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors shrink-0 cursor-pointer"
				aria-label="Clear customer"
			>
				<X :size="14" />
			</button>
		</div>

		<!-- Customer search -->
		<div v-else>
			<div class="relative flex items-center">
				<Search
					class="absolute left-3 text-gray-400 dark:text-gray-500 pointer-events-none"
					:size="14"
				/>
				<Input
					v-model="searchTerm"
					type="text"
					:placeholder="__('Search by customer name, phone, email.')"
					aria-label="Search customer"
					class="customer-search-input h-10 w-full rounded-2xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 hover:bg-white dark:hover:bg-gray-700 text-gray-900 dark:text-gray-100 pl-8 pr-10 text-sm focus:outline-none focus:ring-2 focus:ring-gray-950 focus:border-gray-950 dark:focus:ring-gray-300 dark:focus:border-gray-300 focus:bg-white dark:focus:bg-gray-700 transition-all duration-200 placeholder-gray-400 dark:placeholder-gray-500"
					@focus="showDropdown = results.length > 0"
				/>
				<button
					@click="openQuickEntry"
					class="absolute right-2 w-7 h-7 rounded-md flex items-center justify-center text-gray-400 dark:text-gray-500 hover:text-gray-950 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
					:title="__('New Customer')"
					:aria-label="__('New Customer')"
				>
					<Plus :size="16" />
				</button>
			</div>

			<!-- Dropdown -->
			<Transition name="dropdown">
				<div
					v-if="showDropdown"
					class="absolute z-20 left-0 right-0 mt-1.5 bg-white/50 backdrop-blur-xl dark:bg-gray-900 border border-gray-100 dark:border-gray-700 rounded-2xl shadow-[0_1px_30px_rgba(0,0,0,.3)] dark:shadow-black/30 max-h-48 overflow-y-auto"
				>
					<button
						v-for="c in results"
						:key="c.name"
						@click="selectCustomer(c.name)"
						class="w-full text-left px-4 py-4 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors first:rounded-t-lg last:rounded-b-lg"
					>
						<div class="text-sm font-semibold text-gray-800 dark:text-gray-200">
							{{ c.customer_name }}
						</div>
						<div class="text-[10px] text-gray-500 dark:text-gray-400 mt-0.5">
							{{ c.name }}
							<span v-if="c.mobile_no"> · {{ c.mobile_no }}</span>
						</div>
					</button>
				</div>
			</Transition>
		</div>

		<NewCustomerDialog
			:show="showQuickEntry"
			:initial-name="searchTerm"
			@close="closeQuickEntry"
			@created="onCustomerCreated"
		/>
	</div>
</template>

<style scoped>
.customer-search-input:focus-visible {
	outline: none !important;
}

.dropdown-enter-active {
	transition: all 0.15s ease-out;
}
.dropdown-leave-active {
	transition: all 0.1s ease-in;
}
.dropdown-enter-from {
	opacity: 0;
	transform: translateY(-4px);
}
.dropdown-leave-to {
	opacity: 0;
	transform: translateY(-4px);
}
</style>
