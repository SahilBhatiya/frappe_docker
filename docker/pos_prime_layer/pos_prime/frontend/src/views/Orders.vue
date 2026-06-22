<!-- Copyright (c) 2026, Ravindu Gajanayaka -->
<!-- Licensed under GPLv3. See license.txt -->

<script setup lang="ts">
import Input from "@/components/ui/input/Input.vue";
import OrderDetail from "@/components/orders/OrderDetail.vue";
import OrderList from "@/components/orders/OrderList.vue";
import ReturnDialog from "@/components/orders/ReturnDialog.vue";
import { useOrdersStore } from "@/stores/orders";
import { usePosSessionStore } from "@/stores/posSession";
import { useSettingsStore } from "@/stores/settings";
import { ArrowLeft, Search, X } from "lucide-vue-next";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { onMounted, onUnmounted, ref, watch } from "vue";
import { useRouter } from "vue-router";

const router = useRouter();
const ordersStore = useOrdersStore();
const sessionStore = usePosSessionStore();
const settingsStore = useSettingsStore();

const searchInput = ref("");
const showReturnDialog = ref(false);
const returnOrder = ref<Record<string, any> | null>(null);
const mobileShowDetail = ref(false);

let debounceTimer: ReturnType<typeof setTimeout>;

onUnmounted(() => {
	clearTimeout(debounceTimer);
});

const statusTabs = [
	{ label: __("All"), value: "" },
	{ label: __("Paid"), value: "Paid" },
	{ label: __("Return"), value: "Return" },
	{ label: __("Draft"), value: "Draft" },
];

onMounted(() => {
	if (sessionStore.posProfile) {
		ordersStore.fetchOrders(sessionStore.posProfile);
	}
});

watch(searchInput, (term) => {
	clearTimeout(debounceTimer);
	debounceTimer = setTimeout(() => {
		ordersStore.setSearchTerm(term);
		ordersStore.fetchOrders(sessionStore.posProfile);
	}, 300);
});

function selectStatus(status: string) {
	ordersStore.setStatusFilter(status);
	ordersStore.fetchOrders(sessionStore.posProfile);
}

async function selectOrder(name: string) {
	await ordersStore.loadOrderDetail(name);
	mobileShowDetail.value = true;
}

function handleReturn(name: string) {
	returnOrder.value = ordersStore.selectedOrder;
	showReturnDialog.value = true;
}

function onReturnCompleted() {
	showReturnDialog.value = false;
	returnOrder.value = null;
	ordersStore.fetchOrders(sessionStore.posProfile);
}

function clearSearch() {
	searchInput.value = "";
	ordersStore.setSearchTerm("");
	ordersStore.fetchOrders(sessionStore.posProfile);
}

function handlePrint(invoiceName: string) {
	const printFormat = settingsStore.posProfile?.print_format;
	if (printFormat) {
		const url = `/printview?doctype=POS+Invoice&name=${encodeURIComponent(invoiceName)}&format=${encodeURIComponent(printFormat)}&no_letterhead=0`;
		window.open(url, "_blank");
	} else {
		window.print();
	}
}
</script>

<template>
	<div class="h-full">
		<div class="h-full flex flex-col">
			<div class="px-4 py-3 flex items-center gap-3">
				<button
					@click="
						mobileShowDetail
							? (mobileShowDetail = false)
							: router.push({ name: 'POS' })
					"
					class="lg:hidden text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200"
				>
					<ArrowLeft :size="20" />
				</button>
				<h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100">
					{{ __("Past Orders") }}
				</h2>
			</div>

			<div class="flex-1 flex overflow-hidden">
				<!-- Left: Search + List -->
				<div
					class="w-full lg:w-[360px] shrink-0 flex flex-col bg-white dark:bg-gray-900 rounded-2xl"
					:class="{ 'hidden lg:flex': mobileShowDetail }"
				>
					<!-- Search -->
					<div class="p-3 border-b border-gray-200 dark:border-gray-800">
						<div class="relative">
							<Search
								class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500 pointer-events-none"
								:size="14"
							/>
							<Input
								v-model="searchInput"
								type="text"
								:placeholder="__('Search orders...')"
								class="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 pl-8 pr-8 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-950 dark:focus:ring-gray-300 placeholder-gray-400 dark:placeholder-gray-500"
							/>
							<button
								v-if="searchInput"
								@click="clearSearch"
								class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300"
							>
								<X :size="14" />
							</button>
						</div>
					</div>

					<!-- Status tabs -->
					<div class="px-3 py-2">
						<Tabs
							:model-value="ordersStore.statusFilter || ''"
							@update:model-value="(val) => selectStatus(String(val))"
							class="w-full"
						>
							<TabsList class="grid w-full grid-cols-4">
								<TabsTrigger
									v-for="tab in statusTabs"
									:key="tab.value"
									:value="tab.value"
								>
									{{ tab.label }}
								</TabsTrigger>
							</TabsList>
						</Tabs>
					</div>

					<!-- Order list -->
					<div class="flex-1 overflow-y-auto p-3">
						<Transition name="page-blur" mode="out-in">
							<div :key="ordersStore.statusFilter || 'all'">
								<OrderList
									:orders="ordersStore.orders"
									:selected-name="ordersStore.selectedOrder?.name || null"
									:loading="ordersStore.loading"
									@select="selectOrder"
								/>
							</div>
						</Transition>
					</div>
				</div>

				<!-- Right: Detail -->
				<div
					class="flex-1 bg-gray-50 dark:bg-gray-900"
					:class="{ 'hidden lg:block': !mobileShowDetail }"
				>
					<OrderDetail
						:order="ordersStore.selectedOrder"
						:loading="ordersStore.loadingDetail"
						@print="handlePrint"
						@return="handleReturn"
					/>
				</div>
			</div>
		</div>

		<!-- Return dialog -->
		<ReturnDialog
			v-if="showReturnDialog && returnOrder"
			:order="returnOrder"
			@close="showReturnDialog = false"
			@completed="onReturnCompleted"
		/>
	</div>
</template>
