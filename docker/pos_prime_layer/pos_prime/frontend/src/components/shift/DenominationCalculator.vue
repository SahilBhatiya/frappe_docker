<!-- Copyright (c) 2026, Ravindu Gajanayaka -->
<!-- Licensed under GPLv3. See license.txt -->

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { getDenominations, getSmallestNote } from '@/utils/denominations'
import { useCurrency } from '@/composables/useCurrency'
import Input from '@/components/ui/input/Input.vue'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'

const props = defineProps<{
  modelValue: number
  currency: string
  show: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: number]
  'update:show': [value: boolean]
}>()

const { formatCurrency } = useCurrency()

interface DenomRow {
  value: number
  count: number
}

const rows = ref<DenomRow[]>([])

const smallestNote = computed(() => getSmallestNote(props.currency))

const notes = computed(() => rows.value.filter((r) => r.value >= smallestNote.value))
const coins = computed(() => rows.value.filter((r) => r.value < smallestNote.value))

const grandTotal = computed(() =>
  rows.value.reduce((sum, r) => sum + r.value * r.count, 0)
)

watch(
  () => props.show,
  (visible) => {
    if (visible) {
      const denoms = getDenominations(props.currency)
      rows.value = denoms.map((v) => ({ value: v, count: 0 }))
    }
  }
)

function formatDenom(value: number): string {
  if (value >= 1) return value.toLocaleString()
  return value.toFixed(2)
}

function subtotal(row: DenomRow): number {
  return row.value * row.count
}

function clearAll() {
  rows.value.forEach((r) => (r.count = 0))
}

function apply() {
  emit('update:modelValue', Math.round(grandTotal.value * 100) / 100)
  emit('update:show', false)
}

function close() {
  emit('update:show', false)
}
</script>

<template>
  <Dialog :open="show" @update:open="(val) => { if (!val) close() }">
    <DialogContent class="sm:max-w-md max-h-[90vh] p-0 gap-0 overflow-hidden flex flex-col">
      <!-- Header -->
      <DialogHeader class="flex-row items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-gray-700 shrink-0 space-y-0">
        <DialogTitle class="text-base font-semibold text-gray-900 dark:text-gray-100">
          {{ __('Cash Denomination Count') }}
        </DialogTitle>
      </DialogHeader>

      <!-- Body (scrollable) -->
      <div class="flex-1 overflow-y-auto px-5 py-4 space-y-4">
        <!-- Notes section -->
        <div v-if="notes.length > 0">
          <h3 class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">
            {{ __('Notes') }}
          </h3>
          <div class="space-y-1.5">
            <div
              v-for="row in notes"
              :key="row.value"
              class="flex items-center gap-3"
            >
              <span class="w-16 text-sm font-medium text-gray-700 dark:text-gray-300 text-right tabular-nums">
                {{ formatDenom(row.value) }}
              </span>
              <span class="text-gray-400 dark:text-gray-500 text-sm">&times;</span>
              <Input
                v-model.number="row.count"
                type="number"
                min="0"
                step="1"
                class="w-20 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 px-2 py-1.5 text-sm text-center focus:outline-none focus:ring-2 focus:ring-gray-950 focus:border-gray-950 dark:focus:ring-gray-300 dark:focus:border-gray-300 tabular-nums"
                @focus="($event.target as HTMLInputElement).select()"
              />
              <span class="text-gray-400 dark:text-gray-500 text-sm">=</span>
              <span class="flex-1 text-sm text-right font-medium tabular-nums"
                :class="subtotal(row) > 0 ? 'text-gray-900 dark:text-gray-100' : 'text-gray-400 dark:text-gray-600'"
              >
                {{ formatCurrency(subtotal(row)) }}
              </span>
            </div>
          </div>
        </div>

        <!-- Coins section -->
        <div v-if="coins.length > 0">
          <h3 class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">
            {{ __('Coins') }}
          </h3>
          <div class="space-y-1.5">
            <div
              v-for="row in coins"
              :key="row.value"
              class="flex items-center gap-3"
            >
              <span class="w-16 text-sm font-medium text-gray-700 dark:text-gray-300 text-right tabular-nums">
                {{ formatDenom(row.value) }}
              </span>
              <span class="text-gray-400 dark:text-gray-500 text-sm">&times;</span>
              <Input
                v-model.number="row.count"
                type="number"
                min="0"
                step="1"
                class="w-20 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 px-2 py-1.5 text-sm text-center focus:outline-none focus:ring-2 focus:ring-gray-950 focus:border-gray-950 dark:focus:ring-gray-300 dark:focus:border-gray-300 tabular-nums"
                @focus="($event.target as HTMLInputElement).select()"
              />
              <span class="text-gray-400 dark:text-gray-500 text-sm">=</span>
              <span class="flex-1 text-sm text-right font-medium tabular-nums"
                :class="subtotal(row) > 0 ? 'text-gray-900 dark:text-gray-100' : 'text-gray-400 dark:text-gray-600'"
              >
                {{ formatCurrency(subtotal(row)) }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <DialogFooter class="border-t border-gray-200 dark:border-gray-700 px-5 py-4 space-y-3 flex-col sm:flex-col">
        <!-- Total bar -->
        <div class="flex items-center justify-between bg-gray-100 dark:bg-gray-800 rounded-lg px-4 py-3">
          <span class="text-sm font-semibold text-gray-950 dark:text-gray-100">{{ __('TOTAL') }}</span>
          <span class="text-lg font-bold text-gray-950 dark:text-gray-100 tabular-nums">
            {{ formatCurrency(grandTotal) }}
          </span>
        </div>

        <!-- Actions -->
        <div class="flex gap-3">
          <button
            @click="clearAll"
            class="flex-1 py-2 bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-lg text-sm font-medium hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
          >
            {{ __('Clear All') }}
          </button>
          <button
            @click="apply"
            class="flex-1 py-2 bg-gray-950 text-white rounded-lg text-sm font-medium hover:bg-black dark:bg-gray-100 dark:text-gray-950 dark:hover:bg-white transition-colors"
          >
            {{ __('Apply') }}
          </button>
        </div>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
