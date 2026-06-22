<!-- Copyright (c) 2026, Ravindu Gajanayaka -->
<!-- Licensed under GPLv3. See license.txt -->

<script setup lang="ts">
import CustomerDetailPanel from "@/components/customer/CustomerDetailPanel.vue";
import CustomerSelector from "@/components/customer/CustomerSelector.vue";
import Input from "@/components/ui/input/Input.vue";
import { Button } from "@/components/ui/button";
import { useCurrency } from "@/composables/useCurrency";
import { useTouchDevice } from "@/composables/useTouchDevice";
import { useCartStore } from "@/stores/cart";
import { useCustomerStore } from "@/stores/customer";
import { usePaymentStore } from "@/stores/payment";
import { useSettingsStore } from "@/stores/settings";
import { Check, CreditCard, Pause, ShoppingCart } from "lucide-vue-next";
import { computed, nextTick, ref, watch } from "vue";
import CartItemComp from "./CartItem.vue";
import CartSummary from "./CartSummary.vue";
import CouponCodeInput from "./CouponCodeInput.vue";
import InvoiceDiscount from "./InvoiceDiscount.vue";
import InvoiceOptions from "./InvoiceOptions.vue";
import NumPad from "./NumPad.vue";

const { isTouchDevice } = useTouchDevice();

const cartStore = useCartStore();
const customerStore = useCustomerStore();
const paymentStore = usePaymentStore();
const settingsStore = useSettingsStore();
const { formatCurrency } = useCurrency();

const showNumPad = ref(false);
const numPadMode = ref<"qty" | "discount" | "discountAmt" | "rate">("qty");

const availableNumPadModes = computed(() => {
	const modes: ("qty" | "discount" | "discountAmt" | "rate")[] = ["qty"];
	if (settingsStore.allowDiscountChange) {
		modes.push("discount");
		modes.push("discountAmt");
	}
	if (settingsStore.allowRateChange) modes.push("rate");
	return modes;
});

const numPadValue = computed(() => {
	if (cartStore.selectedItemIndex === null) return 0;
	const item = cartStore.items[cartStore.selectedItemIndex];
	if (!item) return 0;
	if (numPadMode.value === "qty") return item.qty;
	if (numPadMode.value === "discount") return item.discount_percentage;
	if (numPadMode.value === "discountAmt") return item.discount_amount;
	return item.rate;
});

const numPadLabel = computed(() => {
	if (numPadMode.value === "qty") return __("Quantity");
	if (numPadMode.value === "discount") return __("Discount %");
	if (numPadMode.value === "discountAmt") return __("Discount Amt");
	return __("Price");
});

function onItemSelect(index: number) {
	const item = cartStore.items[index];
	if (item?.is_free_item) return; // Free items are not editable
	cartStore.selectItem(index);
	showNumPad.value = true;
	numPadMode.value = "qty";
	// Sync keyboard input
	if (item) keyboardInput.value = String(item.qty);
}

function onUpdateQty(index: number, qty: number) {
	if (cartStore.items[index]?.is_free_item) return;
	cartStore.updateQty(index, qty);
}

function onRemove(index: number) {
	if (cartStore.items[index]?.is_free_item) return;
	cartStore.removeItem(index);
	showNumPad.value = false;
}

function onNumPadUpdate(value: number) {
	if (cartStore.selectedItemIndex === null) return;
	if (numPadMode.value === "qty") {
		cartStore.updateQty(cartStore.selectedItemIndex, value);
	} else if (numPadMode.value === "discount") {
		cartStore.updateItemDiscount(cartStore.selectedItemIndex, value);
	} else if (numPadMode.value === "discountAmt") {
		cartStore.updateItemDiscountAmount(cartStore.selectedItemIndex, value);
	} else {
		cartStore.updateRate(cartStore.selectedItemIndex, value);
	}
}

function switchNumPadMode(mode: "qty" | "discount" | "discountAmt" | "rate") {
	numPadMode.value = mode;
}

// Keyboard input for non-touch desktops
const keyboardInput = ref("");

function onKeyboardInputChange() {
	const val = parseFloat(keyboardInput.value) || 0;
	onNumPadUpdate(val);
}

function closeKeyboardInput() {
	onKeyboardInputChange();
	showNumPad.value = false;
}

function openPayment() {
	paymentStore.openPaymentDialog();
}

const showCustomerDetail = ref(false);
const cartScrollContainer = ref<HTMLElement | null>(null);

// Auto-scroll cart to bottom when items are added
watch(
	() => cartStore.items.length,
	() => {
		nextTick(() => {
			if (cartScrollContainer.value) {
				cartScrollContainer.value.scrollTo({
					top: cartScrollContainer.value.scrollHeight,
					behavior: "smooth",
				});
			}
		});
	},
);

const emit = defineEmits<{
	holdOrder: [];
}>();
</script>

<template>
	<div class="flex flex-col h-full bg-white dark:bg-gray-900">
		<!-- Customer section (ERPNext-style: separate area at top) -->
		<div class="px-3 py-2 border-b border-gray-100 dark:border-gray-800">
			<CustomerSelector @open-detail="showCustomerDetail = true" />
		</div>

		<!-- Customer detail panel -->
		<Transition name="customer-drawer">
			<CustomerDetailPanel
				v-if="showCustomerDetail && customerStore.customer"
				@close="showCustomerDetail = false"
			/>
		</Transition>

		<!-- Cart label + column headers (ERPNext-style) -->
		<div class="px-3 pt-2 pb-1.5">
			<div class="text-sm font-bold text-gray-900 dark:text-gray-100 mb-1.5">
				{{ __("Cart") }}
			</div>
			<div
				v-if="cartStore.items.length > 0"
				class="flex items-center text-[11px] font-medium text-gray-400 dark:text-gray-500 uppercase tracking-wider"
			>
				<span class="flex-1">{{ __("Item") }}</span>
				<span class="w-[88px] text-center">{{ __("Qty") }}</span>
				<span class="w-[72px] text-right">{{ __("Amount") }}</span>
				<span class="w-7" />
			</div>
		</div>

		<!-- Cart items -->
		<div ref="cartScrollContainer" class="flex-1 overflow-y-auto px-2 py-1">
			<div
				v-if="cartStore.items.length === 0"
				class="flex flex-col items-center justify-center h-full rounded-2xl"
			>
				<ShoppingCart :size="28" class="text-gray-300 dark:text-gray-600 mb-2" />
				<span class="text-sm font-medium text-gray-400 dark:text-gray-500">{{
					__("No items in cart")
				}}</span>
			</div>
			<TransitionGroup v-else name="cart-item" tag="div">
				<CartItemComp
					v-for="(item, index) in cartStore.items"
					:key="`${item.item_code}-${item.batch_no || ''}-${index}`"
					:item="item"
					:index="index"
					:selected="cartStore.selectedItemIndex === index"
					@select="onItemSelect"
					@update-qty="onUpdateQty"
					@remove="onRemove"
				/>
			</TransitionGroup>
		</div>

		<!-- NumPad for touch devices -->
		<Transition name="numpad">
			<div
				v-if="isTouchDevice && showNumPad && cartStore.selectedItemIndex !== null"
				class="px-2 pb-2 border-t border-gray-100 dark:border-gray-800"
			>
				<div class="flex gap-1 my-2">
					<button
						v-for="mode in availableNumPadModes"
						:key="mode"
						@click="switchNumPadMode(mode)"
						class="flex-1 py-1.5 text-[10px] font-bold rounded-lg transition-all duration-150 uppercase tracking-wider"
						:class="
							numPadMode === mode
								? 'bg-gray-950 text-white shadow-sm'
								: 'bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
						"
					>
						{{
							mode === "qty"
								? __("Qty")
								: mode === "discount"
									? __("Disc%")
									: mode === "discountAmt"
										? __("Disc$")
										: __("Price")
						}}
					</button>
				</div>
				<NumPad
					:value="numPadValue"
					:label="numPadLabel"
					@update:value="onNumPadUpdate"
					@close="showNumPad = false"
				/>
			</div>
		</Transition>

		<!-- Keyboard input for non-touch desktops -->
		<Transition name="numpad">
			<div
				v-if="!isTouchDevice && showNumPad && cartStore.selectedItemIndex !== null"
				class="px-3 py-2 border-t border-gray-100 dark:border-gray-800"
			>
				<div class="flex gap-1 mb-2">
					<button
						v-for="mode in availableNumPadModes"
						:key="mode"
						@click="
							() => {
								switchNumPadMode(mode);
								const item = cartStore.items[cartStore.selectedItemIndex!];
								if (item)
									keyboardInput = String(
										mode === 'qty'
											? item.qty
											: mode === 'discount'
												? item.discount_percentage
												: mode === 'discountAmt'
													? item.discount_amount
													: item.rate,
									);
							}
						"
						class="flex-1 py-1.5 text-[10px] font-bold rounded-lg transition-all duration-150 uppercase tracking-wider"
						:class="
							numPadMode === mode
								? 'bg-gray-950 text-white shadow-sm'
								: 'bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
						"
					>
						{{
							mode === "qty"
								? __("Qty")
								: mode === "discount"
									? __("Disc%")
									: mode === "discountAmt"
										? __("Disc$")
										: __("Price")
						}}
					</button>
				</div>
				<div class="flex items-center gap-2">
					<span
						class="text-[10px] font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider shrink-0"
						>{{ numPadLabel }}</span
					>
					<Input
						v-model="keyboardInput"
						type="number"
						step="any"
						min="0"
						@input="onKeyboardInputChange"
						@keydown.enter="closeKeyboardInput"
						class="flex-1 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 px-3 py-1.5 text-sm font-semibold text-right focus:outline-none focus:ring-1 focus:ring-gray-950 focus:border-gray-950 dark:focus:ring-gray-300 dark:focus:border-gray-300"
						autofocus
					/>
					<button
						@click="closeKeyboardInput"
						class="flex items-center gap-1 text-[10px] font-semibold text-gray-700 dark:text-gray-300 hover:text-black dark:hover:text-white transition-colors px-2 py-1.5 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800"
					>
						<Check :size="12" />
						{{ __("Done") }}
					</button>
				</div>
			</div>
		</Transition>

		<!-- Totals + Actions (sticky bottom, ERPNext-style) -->
		<div class="border-t border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900">
			<!-- Expandable extras -->
			<div v-if="cartStore.items.length > 0" class="px-3 pt-1.5 space-y-1">
				<InvoiceDiscount />
				<CouponCodeInput />
				<InvoiceOptions />
			</div>

			<!-- Summary -->
			<div class="px-3 pt-1.5 pb-1.5">
				<CartSummary />
			</div>

			<!-- Action Buttons -->
			<div class="px-3 pb-2 flex gap-2">
				<Button
					@click="emit('holdOrder')"
					:disabled="cartStore.items.length === 0"
					class="py-2.5 px-4 rounded-xl text-sm font-bold transition-all duration-150 flex items-center justify-center gap-1.5 disabled:opacity-40 disabled:cursor-not-allowed active:scale-95 bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700"
					title="Hold Order"
				>
					<Pause :size="16" />
				</Button>
				<Button
					@click="openPayment"
					:disabled="cartStore.items.length === 0 || !customerStore.customer"
					class="checkout-btn flex-1 text-sm font-bold duration-200 text-white disabled:cursor-not-allowed"
					:class="
						cartStore.items.length > 0 && customerStore.customer
							? 'bg-gray-950 hover:bg-black dark:bg-gray-100 dark:text-gray-950 dark:hover:bg-white'
							: 'bg-gray-400 dark:bg-gray-700 opacity-70'
					"
				>
					<CreditCard :size="16" />
					{{ __("Checkout") }}
					{{ cartStore.items.length > 0 ? formatCurrency(cartStore.roundedTotal) : "" }}
				</Button>
			</div>
		</div>
	</div>
</template>

<style scoped>
.cart-item-enter-active {
	transition: all 0.25s ease-out;
}
.cart-item-leave-active {
	transition: all 0.2s ease-in;
}
.cart-item-enter-from {
	opacity: 0;
	transform: translateX(-20px);
}
.cart-item-leave-to {
	opacity: 0;
	transform: translateX(20px);
}
.cart-item-move {
	transition: transform 0.25s ease;
}

.numpad-enter-active {
	transition: all 0.2s ease-out;
}
.numpad-leave-active {
	transition: all 0.15s ease-in;
}
.numpad-enter-from,
.numpad-leave-to {
	opacity: 0;
	max-height: 0;
}
.numpad-enter-to,
.numpad-leave-from {
	max-height: 400px;
}
</style>
