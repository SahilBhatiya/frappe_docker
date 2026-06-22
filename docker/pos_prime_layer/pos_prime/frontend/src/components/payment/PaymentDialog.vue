<!-- Copyright (c) 2026, Ravindu Gajanayaka -->
<!-- Licensed under GPLv3. See license.txt -->

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useCartStore } from '@/stores/cart'
import { usePaymentStore } from '@/stores/payment'
import { useCustomerStore } from '@/stores/customer'
import { usePosSessionStore } from '@/stores/posSession'
import { useSettingsStore } from '@/stores/settings'
import { useCurrency } from '@/composables/useCurrency'
import { useTouchDevice } from '@/composables/useTouchDevice'
import { X, Check, Banknote, CreditCard, Wallet, WalletCards, Coins, Award, Eraser, Delete, Loader2, AlertTriangle, BadgeDollarSign, Lock, Info, Star } from 'lucide-vue-next'

const { isTouchDevice } = useTouchDevice()

const cartStore = useCartStore()
const paymentStore = usePaymentStore()
const customerStore = useCustomerStore()
const sessionStore = usePosSessionStore()
const settingsStore = useSettingsStore()
const { formatCurrency } = useCurrency()

const error = ref('')
const errorMessages = ref<string[]>([])
const applyWriteOff = ref(false)
const redeemLoyalty = ref(false)
const loyaltyPointsToRedeem = ref(0)
const loyaltyApplied = ref(false)

// Store credit
const applyStoreCredit = ref(false)
const storeCreditAmount = ref(0)

watch(applyStoreCredit, (on) => {
  if (on && customerStore.storeCredit > 0) {
    // Default: min of available credit and remaining grand total
    const maxApplicable = Math.min(customerStore.storeCredit, cartStore.roundedTotal)
    storeCreditAmount.value = Math.round(maxApplicable * 100) / 100
  } else if (!on) {
    storeCreditAmount.value = 0
  }
})

const storeCreditAppliedAmount = computed(() => {
  if (!applyStoreCredit.value || storeCreditAmount.value <= 0) return 0
  return Math.min(storeCreditAmount.value, customerStore.storeCredit, cartStore.roundedTotal)
})

// Auto-populate and apply loyalty points when checkbox is toggled on
watch(redeemLoyalty, (on) => {
  if (on && customerStore.loyaltyPoints > 0) {
    loyaltyPointsToRedeem.value = customerStore.loyaltyPoints
    loyaltyApplied.value = true
  } else if (!on) {
    loyaltyPointsToRedeem.value = 0
    loyaltyApplied.value = false
  }
})

// Reset applied state only when user manually changes the points value
watch(loyaltyPointsToRedeem, (newVal, oldVal) => {
  // Skip reset when auto-populated by the checkbox toggle
  if (oldVal === 0 && newVal === customerStore.loyaltyPoints) return
  loyaltyApplied.value = false
})

const loyaltyRedemptionAmount = computed(() => {
  if (!loyaltyApplied.value || !redeemLoyalty.value || loyaltyPointsToRedeem.value <= 0) return 0
  const cf = customerStore.loyaltyData?.conversion_factor || 0
  return Math.min(
    loyaltyPointsToRedeem.value * cf,
    cartStore.roundedTotal
  )
})

function applyLoyaltyPoints() {
  if (loyaltyPointsToRedeem.value <= 0) return
  if (loyaltyPointsToRedeem.value > customerStore.loyaltyPoints) {
    loyaltyPointsToRedeem.value = customerStore.loyaltyPoints
  }
  loyaltyApplied.value = true
}

const remainingCreditLimit = computed(() => {
  if (!customerStore.creditLimit || customerStore.creditLimit <= 0) return 0
  return Math.max(0, customerStore.creditLimit - customerStore.outstanding)
})

onMounted(() => {
  paymentStore.initializePayments(
    settingsStore.paymentMethods,
    cartStore.roundedTotal,
    settingsStore.disableGrandTotalToDefaultMop
  )
})

function onEscapeKey(e: KeyboardEvent) {
  if (e.key === 'Escape') paymentStore.closePaymentDialog()
}
onMounted(() => document.addEventListener('keydown', onEscapeKey))
onUnmounted(() => document.removeEventListener('keydown', onEscapeKey))

const activeAmount = computed(() => {
  const payment = paymentStore.payments.find(
    (p) => p.mode_of_payment === paymentStore.activePaymentMethod
  )
  return payment?.amount ?? 0
})

const displayValue = ref('')
watch(activeAmount, (v) => {
  displayValue.value = v > 0 ? String(v) : ''
}, { immediate: true })

watch(() => paymentStore.activePaymentMethod, () => {
  const payment = paymentStore.payments.find(
    (p) => p.mode_of_payment === paymentStore.activePaymentMethod
  )
  displayValue.value = payment?.amount ? String(payment.amount) : ''
})

const effectiveGrandTotal = computed(() => {
  let total = cartStore.roundedTotal
  if (storeCreditAppliedAmount.value > 0) total -= storeCreditAppliedAmount.value
  if (loyaltyRedemptionAmount.value > 0) total -= loyaltyRedemptionAmount.value
  if (applyWriteOff.value && possibleWriteOff.value > 0) total -= possibleWriteOff.value
  return Math.max(0, total)
})

const change = computed(() => Math.round(Math.max(0, paymentStore.totalPaid - effectiveGrandTotal.value) * 100) / 100)
const remaining = computed(() => Math.round(Math.max(0, effectiveGrandTotal.value - paymentStore.totalPaid) * 100) / 100)
const possibleWriteOff = computed(() => {
  const baseRemaining = Math.max(0, cartStore.roundedTotal - loyaltyRedemptionAmount.value - paymentStore.totalPaid)
  if (baseRemaining > 0 && baseRemaining <= settingsStore.writeOffLimit) return baseRemaining
  return 0
})

const paidPercentage = computed(() => {
  // A zero grand total with nothing paid is "unpaid" (empty bar), not fully paid.
  if (effectiveGrandTotal.value <= 0) return paymentStore.totalPaid > 0 ? 100 : 0
  return Math.min(100, (paymentStore.totalPaid / effectiveGrandTotal.value) * 100)
})

const isPartialPayment = computed(() => {
  return paymentStore.totalPaid < effectiveGrandTotal.value
})

const newOutstanding = computed(() => {
  return Math.max(0, effectiveGrandTotal.value - paymentStore.totalPaid)
})

const wouldExceedCreditLimit = computed(() => {
  if (!customerStore.creditLimit || customerStore.creditLimit <= 0) return false
  return (customerStore.outstanding + newOutstanding.value) > customerStore.creditLimit
})

const canSubmit = computed(() => {
  // Partial / pay-later (credit) payments are always permitted across the POS.
  // The only hard requirement is that a submit isn't already in flight; a
  // credit-limit excess is surfaced as a warning below, not a hard block.
  if (paymentStore.submitting) return false
  return true
})

const showPartialConfirm = ref(false)

const isCashMethod = computed(() => {
  const mode = paymentStore.activePaymentMethod.toLowerCase()
  return mode === 'cash'
})

const cashShortcuts = computed(() => {
  const gt = effectiveGrandTotal.value
  if (gt <= 0) return []
  const values = [
    Math.ceil(gt),
    Math.ceil(gt / 10) * 10,
    Math.ceil(gt / 50) * 50,
    Math.ceil(gt / 100) * 100,
    Math.ceil(gt / 500) * 500,
    Math.ceil(gt / 1000) * 1000,
  ]
  return [...new Set(values)].filter(v => v >= gt).slice(0, 6)
})

function getMethodIcon(mode: string) {
  const lower = mode.toLowerCase()
  if (lower === 'cash') return Banknote
  if (lower.includes('card') || lower.includes('credit') || lower.includes('debit')) return CreditCard
  if (lower.includes('coin') || lower.includes('token')) return Coins
  return Wallet
}

function selectMethod(mode: string) {
  paymentStore.setActivePaymentMethod(mode)
}

function pressKey(key: string) {
  if (key === 'C') {
    displayValue.value = ''
    paymentStore.setPaymentAmount(paymentStore.activePaymentMethod, 0)
    return
  }
  if (key === 'DEL') {
    displayValue.value = displayValue.value.slice(0, -1)
  } else if (key === '.') {
    if (!displayValue.value.includes('.')) {
      displayValue.value = (displayValue.value || '0') + '.'
    }
  } else {
    displayValue.value += key
  }
  paymentStore.setPaymentAmount(
    paymentStore.activePaymentMethod,
    parseFloat(displayValue.value) || 0
  )
}

function onPaymentInput(e: Event) {
  const val = (e.target as HTMLInputElement).value
  displayValue.value = val
  paymentStore.setPaymentAmount(
    paymentStore.activePaymentMethod,
    parseFloat(val) || 0
  )
}

function setCashAmount(amount: number) {
  displayValue.value = String(amount)
  paymentStore.setPaymentAmount(paymentStore.activePaymentMethod, amount)
}

function handleSubmit() {
  error.value = ''
  errorMessages.value = []
  if (!customerStore.customer) {
    error.value = __('Please select a customer')
    return
  }

  // Partial / pay-later (credit) payments are allowed everywhere; confirm them
  // so the cashier sees the outstanding amount. A credit-limit excess is shown
  // as a warning in the dialog but no longer blocks the sale.
  if (isPartialPayment.value) {
    showPartialConfirm.value = true
    return
  }

  doSubmit()
}

async function doSubmit() {
  showPartialConfirm.value = false
  error.value = ''
  errorMessages.value = []
  try {
    const activePayments = paymentStore.payments.filter((p) => p.amount > 0)

    const writeOff = applyWriteOff.value ? possibleWriteOff.value : 0

    // Exclude free items — ERPNext adds them automatically via pricing rules
    const itemsPayload = cartStore.items.filter((i) => !i.is_free_item).map((item) => ({
      item_code: item.item_code,
      qty: item.qty,
      rate: item.rate,
      discount_percentage: item.discount_percentage,
      discount_amount: item.discount_amount || undefined,
      serial_no: item.serial_no || undefined,
      batch_no: item.batch_no || undefined,
      serial_and_batch_bundle: item.serial_and_batch_bundle || undefined,
      uom: item.uom || undefined,
      conversion_factor: item.conversion_factor || 1,
      item_tax_template: item.item_tax_template || undefined,
      margin_type: item.margin_type || undefined,
      margin_rate_or_amount: item.margin_rate_or_amount || undefined,
      description: item.description || undefined,
      project: item.project || undefined,
      weight_per_unit: item.weight_per_unit || undefined,
      weight_uom: item.weight_uom || undefined,
    }))

    const opts = cartStore.invoiceOptions || {}

    const invoice = await paymentStore.submitInvoice({
      customer: customerStore.customer.name,
      pos_profile: sessionStore.posProfile,
      items: itemsPayload,
      payments: activePayments,
      taxes: settingsStore.posProfile?.taxes_and_charges || undefined,
      additional_discount_percentage: cartStore.pricingRuleDiscount?.type === 'percentage'
        ? cartStore.pricingRuleDiscount.value
        : cartStore.additionalDiscountPercentage || undefined,
      discount_amount: cartStore.pricingRuleDiscount?.type === 'amount'
        ? cartStore.pricingRuleDiscount.value
        : cartStore.additionalDiscountAmount || undefined,
      apply_discount_on: cartStore.applyDiscountOn,
      coupon_code: cartStore.couponCode || undefined,
      ...(redeemLoyalty.value && loyaltyPointsToRedeem.value > 0 && customerStore.loyaltyData
        ? {
            redeem_loyalty_points: true,
            loyalty_points: loyaltyPointsToRedeem.value,
            loyalty_program: customerStore.loyaltyData.loyalty_program,
            loyalty_redemption_account: customerStore.loyaltyData.expense_account || undefined,
            loyalty_redemption_cost_center: customerStore.loyaltyData.cost_center || undefined,
          }
        : {}),
      ...(writeOff > 0 ? { write_off_amount: writeOff } : {}),
      ...(storeCreditAppliedAmount.value > 0 ? { store_credit_amount: storeCreditAppliedAmount.value } : {}),
      ...Object.fromEntries(
        Object.entries(opts).filter(([_, v]) => v != null && v !== '' && v !== false)
      ),
    })
    if (invoice) {
      paymentStore.closePaymentDialog()
    }
  } catch (e: any) {
    // ERPNext sends HTML-formatted error messages — extract all messages
    const rawMessages: string[] = e.messages || (e.message ? [e.message] : ['Failed to submit invoice'])
    errorMessages.value = rawMessages.map((msg: string) =>
      msg.replace(/<[^>]*>/g, '').trim()
    )
    error.value = errorMessages.value.join('; ')
  }
}

const numpadKeys = ['1','2','3','4','5','6','7','8','9','.','0','DEL']
</script>

<template>
  <Teleport to="body">
    <Transition name="payment-overlay">
      <div v-if="paymentStore.showPaymentDialog" class="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" :aria-label="__('Payment')">
        <!-- Backdrop -->
        <div class="absolute inset-0 bg-black/20 backdrop-blur-[2px]" @click="paymentStore.closePaymentDialog()" />

        <!-- Dialog -->
        <div class="relative bg-white w-full max-w-md rounded-[24px] shadow-2xl flex flex-col overflow-hidden max-h-[90vh] animate-scale-in">
          
          <div class="p-6 overflow-y-auto no-scrollbar flex-1 flex flex-col">
            <!-- Header -->
            <div class="flex items-center justify-between mb-6">
              <div class="flex items-center gap-3">
                <div class="w-9 h-9 bg-gray-100 rounded-xl flex items-center justify-center text-gray-700">
                  <WalletCards :size="17" />
                </div>
                <span class="text-lg font-bold text-gray-900">{{ __('Payment') }}</span>
              </div>
              <button
                @click="paymentStore.closePaymentDialog()"
                class="w-8 h-8 rounded-full bg-gray-50 hover:bg-gray-100 flex items-center justify-center text-gray-500 transition-colors"
              >
                <X :size="16" />
              </button>
            </div>

            <!-- Grand Total -->
            <div class="text-center mb-6">
              <div class="text-sm text-gray-500 mb-1">{{ __('Grand Total') }}</div>
              <div class="text-[40px] leading-tight font-bold text-gray-900 tracking-tight">
                {{ formatCurrency(effectiveGrandTotal) }}
              </div>
              <div v-if="storeCreditAppliedAmount > 0 || loyaltyRedemptionAmount > 0" class="text-xs mt-1">
                <span class="line-through text-gray-400 mr-1">{{ formatCurrency(cartStore.roundedTotal) }}</span>
                <span v-if="storeCreditAppliedAmount > 0" class="text-emerald-600 mr-1">-{{ formatCurrency(storeCreditAppliedAmount) }} {{ __('credit') }}</span>
                <span v-if="loyaltyRedemptionAmount > 0" class="text-violet-600">-{{ formatCurrency(loyaltyRedemptionAmount) }} {{ __('loyalty') }}</span>
              </div>
            </div>

            <!-- Customer Credit Info -->
            <div
              v-if="customerStore.customer && (customerStore.outstanding > 0 || customerStore.creditLimit > 0)"
              class="text-xs mb-6 bg-red-50 rounded-xl px-4 py-3 space-y-1"
            >
              <div class="flex items-center gap-3">
                <div v-if="customerStore.outstanding > 0" class="flex items-center gap-1 text-red-600 font-medium">
                  <AlertTriangle :size="12" />
                  <span>{{ __('Outstanding') }}: {{ formatCurrency(customerStore.outstanding) }}</span>
                </div>
                <div v-if="customerStore.creditLimit > 0" class="text-red-500/80">
                  {{ __('Limit') }}: {{ formatCurrency(customerStore.creditLimit) }}
                </div>
                <div
                  v-if="customerStore.creditLimit > 0 && customerStore.outstanding > customerStore.creditLimit"
                  class="text-red-700 font-bold"
                >
                  {{ __('Exceeded!') }}
                </div>
              </div>
              <div v-if="remainingCreditLimit > 0" class="flex items-center gap-1 text-green-600 font-medium">
                <span>{{ __('Available Credit') }}: {{ formatCurrency(remainingCreditLimit) }}</span>
              </div>
            </div>

            <!-- Progress Bar -->
            <div class="mb-8">
              <div class="relative h-1.5 mb-3">
                <div class="absolute inset-0 top-1/2 -translate-y-1/2 h-1 bg-gray-200 rounded-full"></div>
                <div class="absolute left-0 top-1/2 -translate-y-1/2 h-1 bg-green-500 rounded-full transition-all duration-300" :style="{ width: `${paidPercentage}%` }"></div>

                <!-- Start knob (solid black, fixed left) -->
                <div class="absolute left-0 top-1/2 -translate-y-1/2 w-3 h-3 bg-black rounded-full ring-2 ring-white z-10"></div>
                <!-- Goal knob (green ring, fixed right — fills green once fully paid) -->
                <div
                  class="absolute right-0 top-1/2 -translate-y-1/2 w-3.5 h-3.5 border-2 border-solid border-green-500 rounded-full ring-2 ring-white z-10 transition-colors duration-300"
                  :class="paidPercentage >= 100 ? 'bg-green-500' : 'bg-white'"
                ></div>
              </div>
              <div class="flex justify-between text-xs font-semibold">
                <span class="text-gray-900">{{ __('Unpaid') }}</span>
                <span class="text-green-500">{{ __('Fully paid') }}</span>
              </div>
            </div>

            <!-- Payment Methods Tabs -->
            <div class="flex flex-wrap gap-2 mb-6" role="tablist">
              <button
                v-for="pm in settingsStore.paymentMethods"
                :key="pm.mode_of_payment"
                @click="selectMethod(pm.mode_of_payment)"
                class="flex items-center gap-2 px-4 py-2 rounded-full text-[13px] font-medium transition-all border shrink-0"
                :class="
                  paymentStore.activePaymentMethod === pm.mode_of_payment
                    ? 'border-gray-200 bg-gray-100 text-gray-900 font-semibold'
                    : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50'
                "
              >
                <component :is="getMethodIcon(pm.mode_of_payment)" :size="14" />
                {{ pm.mode_of_payment }}
                <!-- Amount badge -->
                <span
                  v-if="paymentStore.payments.find(p => p.mode_of_payment === pm.mode_of_payment)?.amount > 0 && paymentStore.activePaymentMethod !== pm.mode_of_payment"
                  class="ml-1 text-[11px] font-bold text-gray-400"
                >
                  {{ formatCurrency(paymentStore.payments.find(p => p.mode_of_payment === pm.mode_of_payment)?.amount ?? 0) }}
                </span>
              </button>
            </div>

            <!-- Amount Received Input -->
            <div class="mb-6">
              <div class="text-sm text-gray-500 mb-2 font-medium">{{ __('Amount received') }}</div>
              <input
                v-if="!isTouchDevice"
                :value="displayValue"
                @input="onPaymentInput"
                type="number"
                step="any"
                min="0"
                placeholder="₹0.00"
                class="w-full text-2xl font-bold text-gray-400 bg-gray-50 rounded-2xl px-4 py-3 focus:outline-none focus:ring-1 focus:ring-gray-300 transition-colors"
                :class="{ 'text-gray-900': activeAmount > 0 }"
              />
              <div
                v-else
                class="w-full text-2xl font-bold text-gray-400 bg-gray-50 rounded-2xl px-4 py-3"
                :class="{ 'text-gray-900': activeAmount > 0 }"
              >
                {{ displayValue || '₹0.00' }}
              </div>
            </div>

            <!-- Cash Quick Amounts -->
            <div v-if="isCashMethod && cashShortcuts.length > 0" class="grid grid-cols-3 gap-2 mb-6">
              <button
                v-for="amount in cashShortcuts"
                :key="amount"
                @click="setCashAmount(amount)"
                class="py-2.5 bg-white border border-gray-200 text-gray-700 rounded-xl text-sm font-semibold hover:bg-gray-50 active:scale-95 transition-all duration-150"
              >
                {{ formatCurrency(amount) }}
              </button>
            </div>

            <!-- NumPad (touch devices only) -->
            <div v-if="isTouchDevice" class="grid grid-cols-4 gap-2 mb-6">
              <button
                v-for="key in numpadKeys"
                :key="key"
                @click="pressKey(key)"
                :aria-label="key === 'DEL' ? 'Delete' : `Press ${key}`"
                class="h-14 rounded-xl font-semibold transition-all duration-150 active:scale-95 flex items-center justify-center bg-gray-50 text-gray-900 hover:bg-gray-100 text-lg"
                :class="{ 'text-red-500 bg-red-50 hover:bg-red-100': key === 'DEL' }"
              >
                <Delete v-if="key === 'DEL'" :size="20" />
                <span v-else>{{ key }}</span>
              </button>
              <!-- Clear button in 4th column -->
              <button
                @click="pressKey('C')"
                aria-label="Clear"
                class="h-14 rounded-xl font-semibold bg-gray-100 text-gray-700 hover:bg-gray-200 active:scale-95 transition-all duration-150 text-sm"
              >
                {{ __('Clear') }}
              </button>
            </div>

            <!-- Apply Store Credit Card -->
            <div v-if="customerStore.storeCredit > 0" class="border border-gray-100 rounded-2xl p-4 flex items-center justify-between mb-4 shadow-sm">
              <div class="flex items-center gap-3">
                <div class="w-9 h-9 bg-black rounded-2xl flex items-center justify-center text-white">
                  <Star :size="15" class="fill-current" />
                </div>
                <div>
                  <div class="text-sm font-semibold text-gray-900">{{ __('Apply Store Credit') }}</div>
                  <div class="text-xs text-gray-500 mt-0.5">{{ formatCurrency(customerStore.storeCredit) }} {{ __('available') }}</div>
                </div>
              </div>
              
              <!-- Custom Toggle -->
              <button 
                @click="applyStoreCredit = !applyStoreCredit"
                class="relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none flex-shrink-0"
                :class="applyStoreCredit ? 'bg-black' : 'bg-gray-200'"
              >
                <span class="inline-block h-4 w-4 transform rounded-full bg-white transition-transform" :class="applyStoreCredit ? 'translate-x-6' : 'translate-x-1'"></span>
              </button>
            </div>
            
            <div v-if="applyStoreCredit" class="mb-6 px-2 space-y-2">
              <div class="flex items-center gap-2">
                <label class="text-xs text-gray-500 font-medium shrink-0">{{ __('Amount') }}:</label>
                <input
                  v-model.number="storeCreditAmount"
                  type="number"
                  step="any"
                  :min="0"
                  :max="Math.min(customerStore.storeCredit, cartStore.roundedTotal)"
                  class="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm text-right focus:outline-none focus:ring-1 focus:ring-gray-300"
                />
              </div>
              <div class="flex items-center justify-between text-xs">
                <span class="text-gray-500">
                  {{ __('Applied to this invoice') }}
                </span>
                <span class="font-bold text-gray-900">
                  -{{ formatCurrency(storeCreditAppliedAmount) }}
                </span>
              </div>
            </div>

            <!-- Loyalty Points -->
            <div v-if="customerStore.loyaltyProgram && customerStore.loyaltyPoints > 0" class="border border-gray-100 rounded-2xl p-4 flex items-center justify-between mb-4 shadow-sm">
               <div class="flex items-center gap-3">
                <div class="w-9 h-9 bg-violet-600 rounded-2xl flex items-center justify-center text-white">
                  <Award :size="15" />
                </div>
                <div>
                  <div class="text-sm font-semibold text-gray-900">{{ __('Redeem Loyalty') }}</div>
                  <div class="text-xs text-gray-500 mt-0.5">{{ customerStore.loyaltyPoints }} {{ __('pts') }} ({{ formatCurrency(customerStore.maxRedeemableAmount) }})</div>
                </div>
              </div>
              <button 
                @click="redeemLoyalty = !redeemLoyalty"
                class="relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none flex-shrink-0"
                :class="redeemLoyalty ? 'bg-violet-600' : 'bg-gray-200'"
              >
                <span class="inline-block h-4 w-4 transform rounded-full bg-white transition-transform" :class="redeemLoyalty ? 'translate-x-6' : 'translate-x-1'"></span>
              </button>
            </div>

            <div v-if="redeemLoyalty" class="mb-6 px-2 space-y-2">
                <div class="flex items-center gap-2">
                  <label class="text-xs text-gray-500 font-medium shrink-0">{{ __('Points') }}:</label>
                  <input
                    v-model.number="loyaltyPointsToRedeem"
                    type="number"
                    :min="0"
                    :max="customerStore.loyaltyPoints"
                    class="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm text-right focus:outline-none focus:ring-1 focus:ring-gray-300"
                  />
                  <button
                    @click="applyLoyaltyPoints"
                    :disabled="loyaltyPointsToRedeem <= 0"
                    class="px-4 py-2 rounded-lg text-xs font-bold transition-all"
                    :class="loyaltyApplied
                      ? 'bg-gray-900 text-white'
                      : loyaltyPointsToRedeem > 0
                        ? 'bg-gray-100 text-gray-900 hover:bg-gray-200'
                        : 'bg-gray-50 text-gray-400 cursor-not-allowed'"
                  >
                    <Check v-if="loyaltyApplied" :size="12" class="inline -mt-0.5 mr-1" />
                    {{ loyaltyApplied ? __('Applied') : __('Apply') }}
                  </button>
                </div>
                <div v-if="loyaltyApplied" class="flex items-center justify-between text-xs">
                  <span class="text-gray-500">
                    {{ loyaltyPointsToRedeem }} {{ __('pts') }} × {{ customerStore.loyaltyData?.conversion_factor }}
                  </span>
                  <span class="font-bold text-gray-900">
                    -{{ formatCurrency(loyaltyRedemptionAmount) }}
                  </span>
                </div>
            </div>

            <!-- Write-off -->
            <div v-if="possibleWriteOff > 0 && remaining > 0" class="border border-gray-100 rounded-2xl p-4 flex items-center justify-between mb-4 shadow-sm">
               <div class="flex items-center gap-3">
                <div class="w-9 h-9 bg-amber-500 rounded-2xl flex items-center justify-center text-white">
                  <Eraser :size="15" />
                </div>
                <div>
                  <div class="text-sm font-semibold text-gray-900">{{ __('Write off') }}</div>
                  <div class="text-xs text-gray-500 mt-0.5">{{ formatCurrency(possibleWriteOff) }}</div>
                </div>
              </div>
              <button 
                @click="applyWriteOff = !applyWriteOff"
                class="relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none flex-shrink-0"
                :class="applyWriteOff ? 'bg-amber-500' : 'bg-gray-200'"
              >
                <span class="inline-block h-4 w-4 transform rounded-full bg-white transition-transform" :class="applyWriteOff ? 'translate-x-6' : 'translate-x-1'"></span>
              </button>
            </div>

            <!-- Payment Summary -->
            <div class="bg-gray-50 rounded-2xl p-4 mb-4">
              <div class="space-y-2.5 mb-3.5">
                <div class="flex justify-between text-sm">
                  <span class="text-gray-900 font-semibold">{{ __('Total') }}</span>
                  <span class="text-gray-900">{{ formatCurrency(effectiveGrandTotal) }}</span>
                </div>
                <div class="flex justify-between text-sm">
                  <span class="text-gray-900 font-semibold">{{ __('Paid') }}</span>
                  <span class="text-gray-900">{{ formatCurrency(paymentStore.totalPaid + storeCreditAppliedAmount) }}</span>
                </div>
                <div v-if="change > 0" class="flex justify-between text-sm text-green-600">
                  <span class="font-semibold">{{ __('Change') }}</span>
                  <span class="font-bold">{{ formatCurrency(change) }}</span>
                </div>
              </div>
              <div class="pt-3.5 flex justify-between text-sm font-bold border-t border-gray-200">
                <span class="text-gray-900">{{ __('Balance / Pending') }}</span>
                <span class="text-gray-900">{{ formatCurrency(newOutstanding) }}</span>
              </div>
            </div>

            <!-- Error -->
            <div v-if="errorMessages.length > 0" class="mb-4 px-4 py-3 bg-red-50 rounded-xl text-xs font-medium space-y-1 text-red-600">
              <div v-for="(msg, i) in errorMessages" :key="i">{{ msg }}</div>
            </div>
            <div v-else-if="error" class="mb-4 px-4 py-3 bg-red-50 rounded-xl text-xs font-medium text-red-600">
              {{ error }}
            </div>

            <!-- Credit limit warning -->
            <div
              v-if="wouldExceedCreditLimit && isPartialPayment"
              class="mb-4 bg-red-50 rounded-xl p-3 flex items-start gap-2"
            >
              <AlertTriangle :size="16" class="text-red-500 shrink-0 mt-0.5" />
              <div class="text-xs text-red-700">
                <div class="font-semibold">{{ __('Credit limit would be exceeded') }}</div>
                <div class="mt-0.5 text-red-600">
                  {{ __('Outstanding') }}: {{ formatCurrency(customerStore.outstanding) }} + {{ formatCurrency(newOutstanding) }}
                  = {{ formatCurrency(customerStore.outstanding + newOutstanding) }}
                  / {{ formatCurrency(customerStore.creditLimit) }}
                </div>
              </div>
            </div>

            <!-- Info text -->
            <div class="flex items-center gap-1.5 text-[11px] text-gray-500 mb-6 px-1">
              <Info :size="12" />
              <span>{{ __('Payment status is calculated automatically.') }}</span>
            </div>

            <!-- Complete Payment Button -->
            <button
              @click="handleSubmit"
              :disabled="!canSubmit"
              class="w-full py-4 rounded-xl text-sm font-bold transition-all flex items-center justify-center gap-2"
              :class="canSubmit
                ? 'bg-black text-white hover:bg-gray-900 active:scale-[0.98]'
                : 'bg-gray-100 text-gray-400 cursor-not-allowed'
              "
            >
              <Loader2 v-if="paymentStore.submitting" :size="16" class="animate-spin" />
              <Lock v-else :size="16" />
              {{ paymentStore.submitting ? __('Processing...') : __('Complete Payment') }}
            </button>
            
          </div>
        </div>
      </div>
    </Transition>

    <!-- Partial Payment Confirmation -->
    <div v-if="showPartialConfirm" class="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div class="absolute inset-0 bg-black/40" @click="showPartialConfirm = false" />
      <div class="relative bg-white rounded-2xl shadow-xl w-full max-w-xs p-6 text-center animate-scale-in">
        <div class="w-12 h-12 bg-amber-50 rounded-full flex items-center justify-center mx-auto mb-4">
          <AlertTriangle :size="24" class="text-amber-500" />
        </div>
        <h4 class="text-base font-bold text-gray-900 mb-2">{{ __('Partial Payment') }}</h4>
        <p class="text-sm text-gray-500 mb-2">
          {{ __('Paid') }}: {{ formatCurrency(paymentStore.totalPaid) }} / {{ formatCurrency(cartStore.roundedTotal) }}
        </p>
        <p class="text-sm font-bold text-amber-600 mb-6">
          {{ __('Outstanding') }}: {{ formatCurrency(newOutstanding) }}
        </p>
        <div class="flex gap-3">
          <button
            @click="showPartialConfirm = false"
            class="flex-1 py-3 bg-gray-50 text-gray-700 rounded-xl text-sm font-bold hover:bg-gray-100 transition-colors"
          >
            {{ __('Cancel') }}
          </button>
          <button
            @click="doSubmit"
            class="flex-1 py-3 bg-amber-500 text-white rounded-xl text-sm font-bold hover:bg-amber-600 active:scale-[0.98] transition-all"
          >
            {{ __('Confirm') }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.no-scrollbar::-webkit-scrollbar { display: none; }
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }

@keyframes scale-in {
  from { transform: scale(0.95); opacity: 0; }
  to { transform: scale(1); opacity: 1; }
}
.animate-scale-in { animation: scale-in 0.2s ease-out; }

.payment-overlay-enter-active { transition: opacity 0.2s ease; }
.payment-overlay-leave-active { transition: opacity 0.15s ease; }
.payment-overlay-enter-from,
.payment-overlay-leave-to { opacity: 0; }
</style>
