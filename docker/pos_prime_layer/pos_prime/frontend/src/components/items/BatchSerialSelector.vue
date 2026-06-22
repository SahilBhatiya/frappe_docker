<!-- Copyright (c) 2026, Ravindu Gajanayaka -->
<!-- Licensed under GPLv3. See license.txt -->

<script setup lang="ts">
import Input from "@/components/ui/input/Input.vue";
import { toast } from "@/composables/useToast";
import { useSettingsStore } from "@/stores/settings";
import { call } from "frappe-ui";
import { Check, X, Zap } from "lucide-vue-next";
import { computed, onMounted, ref } from "vue";

const props = defineProps<{
	itemCode: string;
	itemName: string;
	hasBatchNo: boolean;
	hasSerialNo: boolean;
	qty?: number;
}>();

const emit = defineEmits<{
	close: [];
	confirm: [batch_no: string | null, serial_no: string | null];
}>();

const settingsStore = useSettingsStore();
const warehouse = settingsStore.posProfile?.warehouse || "";

const batches = ref<any[]>([]);
const serialNos = ref<any[]>([]);
const selectedBatch = ref<string | null>(null);
const selectedSerials = ref<string[]>([]);
const loading = ref(false);
const serialInput = ref("");

onMounted(async () => {
	loading.value = true;
	try {
		if (props.hasBatchNo) {
			batches.value =
				(await call("pos_prime.api.stock.get_batch_nos", {
					item_code: props.itemCode,
					warehouse,
				})) || [];
		}
		if (props.hasSerialNo && !props.hasBatchNo) {
			serialNos.value =
				(await call("pos_prime.api.stock.get_serial_nos", {
					item_code: props.itemCode,
					warehouse,
				})) || [];
		}
	} finally {
		loading.value = false;
	}
});

async function selectBatch(batchNo: string) {
	selectedBatch.value = batchNo;
	if (props.hasSerialNo) {
		loading.value = true;
		try {
			serialNos.value =
				(await call("pos_prime.api.stock.get_serial_nos", {
					item_code: props.itemCode,
					warehouse,
					batch_no: batchNo,
				})) || [];
		} finally {
			loading.value = false;
		}
	}
}

function toggleSerial(serialNo: string) {
	const idx = selectedSerials.value.indexOf(serialNo);
	if (idx >= 0) {
		selectedSerials.value.splice(idx, 1);
	} else {
		selectedSerials.value.push(serialNo);
	}
}

function addSerialManual() {
	const sn = serialInput.value.trim();
	if (sn && !selectedSerials.value.includes(sn)) {
		selectedSerials.value.push(sn);
		serialInput.value = "";
	}
}

const autoFetching = ref(false);

async function autoFetchSerials() {
	const needed = props.qty || 1;
	autoFetching.value = true;
	try {
		const result =
			(await call("pos_prime.api.stock.auto_fetch_serial_nos", {
				item_code: props.itemCode,
				warehouse,
				qty: needed,
				batch_no: selectedBatch.value || undefined,
			})) || [];
		selectedSerials.value = result;
		if (result.length < needed) {
			toast.warning(`Only ${result.length} serial numbers available (requested ${needed})`);
		}
	} catch (e: any) {
		toast.error(e.message || "Failed to auto-fetch serial numbers");
	} finally {
		autoFetching.value = false;
	}
}

const canConfirm = computed(() => {
	if (props.hasBatchNo && !selectedBatch.value) return false;
	if (props.hasSerialNo && selectedSerials.value.length === 0) return false;
	return true;
});

function confirm() {
	emit(
		"confirm",
		selectedBatch.value,
		selectedSerials.value.length > 0 ? selectedSerials.value.join("\n") : null,
	);
}
</script>

<template>
	<div
		class="fixed inset-0 z-50 flex items-center justify-center p-4"
		role="dialog"
		aria-modal="true"
		:aria-label="__('Select Batch or Serial Number')"
		@keydown.escape="emit('close')"
	>
		<div
			class="absolute inset-0 bg-black/20 dark:bg-black/50 backdrop-blur-md"
			@click="emit('close')"
		/>
		<div
			class="relative bg-white dark:bg-gray-900 rounded-xl shadow-xl dark:shadow-black/30 w-full max-w-md max-h-[80vh] overflow-y-auto"
		>
			<div
				class="sticky top-0 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 px-4 py-3 flex items-center justify-between rounded-t-xl z-10"
			>
				<div>
					<h3 class="text-base font-semibold text-gray-900 dark:text-gray-100">
						{{ __("Select") }} {{ hasBatchNo ? __("Batch") : ""
						}}{{ hasBatchNo && hasSerialNo ? " & " : ""
						}}{{ hasSerialNo ? __("Serial No") : "" }}
					</h3>
					<p class="text-xs text-gray-500 dark:text-gray-400">{{ itemName }}</p>
				</div>
				<button
					@click="emit('close')"
					class="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300"
				>
					<X :size="18" />
				</button>
			</div>

			<div class="p-4 space-y-4">
				<div
					v-if="loading"
					class="text-center py-8 text-gray-400 dark:text-gray-500 text-sm"
				>
					{{ __("Loading...") }}
				</div>

				<!-- Batch Selection -->
				<div v-if="hasBatchNo && !loading">
					<h4 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
						{{ __("Available Batches") }}
					</h4>
					<div
						v-if="batches.length === 0"
						class="text-sm text-gray-400 dark:text-gray-500 py-4 text-center"
					>
						{{ __("No batches available") }}
					</div>
					<div v-else class="space-y-1.5">
						<button
							v-for="batch in batches"
							:key="batch.batch_no"
							@click="selectBatch(batch.batch_no)"
							class="w-full text-left px-3 py-2 rounded-lg border transition-colors"
							:class="
								selectedBatch === batch.batch_no
									? 'border-gray-400 dark:border-gray-500 bg-gray-100 dark:bg-gray-800'
									: 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
							"
						>
							<div class="flex justify-between items-center">
								<span
									class="text-sm font-medium text-gray-800 dark:text-gray-200"
									>{{ batch.batch_no }}</span
								>
								<span class="text-xs text-gray-500 dark:text-gray-400"
									>{{ __("Qty") }}: {{ batch.qty }}</span
								>
							</div>
							<div
								v-if="batch.expiry_date"
								class="text-xs text-gray-400 dark:text-gray-500 mt-0.5"
							>
								{{ __("Expires") }}: {{ batch.expiry_date }}
							</div>
						</button>
					</div>
				</div>

				<!-- Serial Number Selection -->
				<div v-if="hasSerialNo && (!hasBatchNo || selectedBatch) && !loading">
					<h4 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
						{{ __("Serial Numbers") }}
					</h4>

					<!-- Manual input -->
					<div class="flex gap-2 mb-2">
						<Input
							v-model="serialInput"
							type="text"
							:placeholder="__('Enter or scan serial no...')"
							class="flex-1 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-gray-950 dark:focus:ring-gray-300 placeholder-gray-400 dark:placeholder-gray-500"
							@keydown.enter="addSerialManual"
						/>
						<button
							@click="addSerialManual"
							class="px-3 py-1.5 bg-gray-100 dark:bg-gray-800 text-gray-950 dark:text-gray-100 rounded-lg text-sm font-medium hover:bg-gray-200 dark:hover:bg-gray-700"
						>
							{{ __("Add") }}
						</button>
					</div>

					<!-- Auto Fetch button -->
					<button
						@click="autoFetchSerials"
						:disabled="autoFetching"
						class="w-full mb-2 py-1.5 bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 rounded-lg text-xs font-medium hover:bg-green-100 dark:hover:bg-green-900/30 transition-colors flex items-center justify-center gap-1.5 disabled:opacity-50"
					>
						<Zap :size="12" />
						{{
							autoFetching ? __("Fetching...") : `${__("Auto Fetch")} (${qty || 1})`
						}}
					</button>

					<!-- Selected serials -->
					<div v-if="selectedSerials.length > 0" class="flex flex-wrap gap-1 mb-2">
						<span
							v-for="sn in selectedSerials"
							:key="sn"
							class="inline-flex items-center gap-1 px-2 py-0.5 bg-gray-200 dark:bg-gray-700 text-gray-950 dark:text-gray-100 rounded-full text-xs"
						>
							{{ sn }}
							<button
								@click="toggleSerial(sn)"
								class="hover:text-black dark:hover:text-white"
							>
								<X :size="10" />
							</button>
						</span>
					</div>

					<!-- Available serials -->
					<div v-if="serialNos.length > 0" class="max-h-40 overflow-y-auto space-y-1">
						<button
							v-for="sn in serialNos"
							:key="sn.name"
							@click="toggleSerial(sn.name)"
							class="w-full text-left px-3 py-1.5 rounded text-sm transition-colors"
							:class="
								selectedSerials.includes(sn.name)
									? 'bg-gray-100 dark:bg-gray-800 text-gray-950 dark:text-gray-100'
									: 'hover:bg-gray-50 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300'
							"
						>
							{{ sn.name }}
						</button>
					</div>
				</div>

				<button
					@click="confirm"
					:disabled="!canConfirm"
					class="w-full py-2.5 bg-gray-950 text-white rounded-lg text-sm font-semibold hover:bg-black dark:bg-gray-100 dark:text-gray-950 dark:hover:bg-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
				>
					<Check :size="16" />
					{{ __("Confirm") }}
				</button>
			</div>
		</div>
	</div>
</template>
