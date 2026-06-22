<!-- Copyright (c) 2026, Ravindu Gajanayaka -->
<!-- Licensed under GPLv3. See license.txt -->

<script setup lang="ts">
import { Minus, Plus, Trash2, Gift, Zap, Package } from 'lucide-vue-next'
import { useCurrency } from '@/composables/useCurrency'
import type { CartItem } from '@/types'

const props = defineProps<{
  item: CartItem
  index: number
  selected: boolean
}>()

const emit = defineEmits<{
  select: [index: number]
  updateQty: [index: number, qty: number]
  remove: [index: number]
}>()

const { formatCurrency } = useCurrency()
</script>

<template>
  <div class="px-1">
    <div
      role="listitem"
      @click="!item.is_free_item && emit('select', index)"
      class="group flex items-center gap-2 px-3.5 py-2.5 rounded-xl border transition-all duration-150 mb-2 shadow-[0_2px_8px_rgba(0,0,0,0.015)]"
      :class="[
        item.is_free_item
          ? 'bg-green-50/60 dark:bg-green-900/10 border-green-100/60 dark:border-green-950/30 text-green-800 dark:text-green-300 cursor-default'
          : [
              'cursor-pointer border-zinc-100 dark:border-gray-800',
              'hover:-translate-y-0.5 hover:border-orange-500 hover:bg-orange-500 hover:text-white hover:shadow-lg hover:shadow-orange-500/15 active:translate-y-0 active:scale-[0.99] dark:hover:border-orange-500 dark:hover:bg-orange-500 dark:hover:text-white dark:hover:shadow-orange-500/5',
              selected
                ? 'bg-orange-500 border-orange-500 text-white shadow-lg shadow-orange-500/15'
                : index % 2 === 1
                  ? 'bg-gray-50/70 dark:bg-zinc-900/40 text-gray-800 dark:text-gray-200'
                  : 'bg-white dark:bg-gray-900 text-gray-800 dark:text-gray-200'
            ]
      ]"
    >
      <!-- Item image thumbnail (ERPNext-style) -->
      <div
        class="w-8 h-8 rounded-md flex items-center justify-center shrink-0 overflow-hidden transition-colors"
        :class="[selected ? 'bg-white/20 text-white' : 'bg-gray-100 dark:bg-gray-800 text-gray-400 group-hover:bg-white/20 group-hover:text-white']"
      >
        <img
          v-if="item.image"
          :src="item.image"
          :alt="item.item_name"
          class="w-full h-full object-cover"
        />
        <Package v-else class="transition-colors text-current opacity-80" :size="14" />
      </div>

      <!-- Item name & description -->
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-1.5">
          <span
            class="text-sm font-bold truncate leading-tight transition-colors"
            :class="[selected ? 'text-white' : 'text-gray-800 dark:text-gray-200 group-hover:text-white']"
          >
            {{ item.item_name }}
          </span>
          <span
            v-if="item.is_free_item"
            class="inline-flex items-center gap-0.5 px-1.5 py-0 bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-400 rounded text-[9px] font-bold shrink-0"
          >
            <Gift :size="8" />
            {{ __('Free') }}
          </span>
          <span
            v-else-if="item.pricing_rules"
            class="inline-flex items-center gap-0.5 px-1.5 py-0 rounded text-[9px] font-bold shrink-0 transition-colors"
            :class="[selected ? 'bg-white/25 text-white' : 'bg-gray-200 dark:bg-gray-700 text-gray-950 dark:text-gray-100 group-hover:bg-white/25 group-hover:text-white']"
          >
            <Zap :size="8" />
            {{ __('Promo') }}
          </span>
        </div>
        <div
          class="flex items-center gap-1.5 mt-0.5 text-xs transition-colors"
          :class="[selected ? 'text-white/80' : 'text-gray-500 dark:text-gray-400 group-hover:text-white/80']"
        >
          <span v-if="item.is_free_item" class="text-green-600 dark:text-green-400 font-medium">{{ formatCurrency(0) }}</span>
          <template v-else>
            <span
              v-if="item.price_list_rate && item.price_list_rate !== item.rate"
              class="line-through text-[10px] transition-colors"
              :class="[selected ? 'text-white/60' : 'text-gray-400 dark:text-gray-500 group-hover:text-white/60']"
            >{{ formatCurrency(item.price_list_rate) }}</span>
            <span class="font-medium">{{ formatCurrency(item.rate) }}</span>
          </template>
          <span
            v-if="!item.is_free_item && item.discount_percentage > 0"
            class="inline-flex items-center px-1 py-0 rounded text-[10px] font-semibold transition-colors"
            :class="[selected ? 'bg-white/25 text-white' : 'bg-orange-100 dark:bg-orange-900/30 text-orange-600 dark:text-orange-400 group-hover:bg-white/25 group-hover:text-white']"
          >
            -{{ item.discount_percentage }}%
          </span>
          <span
            v-else-if="!item.is_free_item && item.discount_amount > 0"
            class="inline-flex items-center px-1 py-0 rounded text-[10px] font-semibold transition-colors"
            :class="[selected ? 'bg-white/25 text-white' : 'bg-orange-100 dark:bg-orange-900/30 text-orange-600 dark:text-orange-400 group-hover:bg-white/25 group-hover:text-white']"
          >
            -{{ formatCurrency(item.discount_amount) }}
          </span>
        </div>
        <div v-if="item.batch_no || item.serial_no" class="flex items-center gap-1 mt-0.5">
          <span
            v-if="item.batch_no"
            class="inline-flex items-center px-1.5 py-0 rounded text-[9px] font-medium transition-colors"
            :class="[selected ? 'bg-white/20 text-white' : 'bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 group-hover:bg-white/20 group-hover:text-white']"
          >
            B: {{ item.batch_no }}
          </span>
          <span
            v-if="item.serial_no"
            class="inline-flex items-center px-1.5 py-0 rounded text-[9px] font-medium transition-colors"
            :class="[selected ? 'bg-white/20 text-white' : 'bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 group-hover:bg-white/20 group-hover:text-white']"
          >
            SN: {{ item.serial_no }}
          </span>
        </div>
        <div
          v-if="item.uom !== item.stock_uom"
          class="text-[9px] mt-0.5 transition-colors"
          :class="[selected ? 'text-white/70' : 'text-gray-400 dark:text-gray-500 group-hover:text-white/70']"
        >
          {{ item.uom }} ({{ item.conversion_factor }}x)
        </div>
        <div
          v-if="item.item_tax_template"
          class="text-[9px] mt-0.5 transition-colors"
          :class="[selected ? 'text-white/75' : 'text-purple-500 dark:text-purple-400 group-hover:text-white/75']"
        >
          {{ item.item_tax_template }}
        </div>
      </div>

      <!-- Qty Controls (hidden for free items) -->
      <div v-if="!item.is_free_item" class="flex items-center gap-0.5 shrink-0">
        <button
          @click.stop="emit('updateQty', index, item.qty - 1)"
          aria-label="Decrease quantity"
          class="w-7 h-7 rounded-md flex items-center justify-center transition-all duration-150 active:scale-90"
          :class="[selected ? 'text-white hover:bg-white/20' : 'text-gray-400 dark:text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-700 hover:text-gray-600 dark:hover:text-gray-300 group-hover:text-white group-hover:hover:bg-white/20']"
        >
          <Minus :size="14" />
        </button>
        <span
          class="w-7 text-center text-xs font-bold transition-colors"
          :class="[selected ? 'text-white' : 'text-gray-800 dark:text-gray-200 group-hover:text-white']"
        >
          {{ item.qty }}
        </span>
        <button
          @click.stop="emit('updateQty', index, item.qty + 1)"
          aria-label="Increase quantity"
          class="w-7 h-7 rounded-md flex items-center justify-center transition-all duration-150 active:scale-90"
          :class="[selected ? 'text-white hover:bg-white/20' : 'text-gray-400 dark:text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-700 hover:text-gray-600 dark:hover:text-gray-300 group-hover:text-white group-hover:hover:bg-white/20']"
        >
          <Plus :size="14" />
        </button>
      </div>
      <div v-else class="shrink-0">
        <span class="text-xs font-bold text-green-600 dark:text-green-400">&times;{{ item.qty }}</span>
      </div>

      <!-- Amount -->
      <div class="w-[72px] text-right shrink-0">
        <span
          class="text-sm font-bold transition-colors"
          :class="[item.is_free_item ? 'text-green-600 dark:text-green-400' : selected ? 'text-white' : 'text-gray-900 dark:text-gray-100 group-hover:text-white']"
        >
          {{ formatCurrency(item.is_free_item ? 0 : item.amount) }}
        </span>
      </div>

      <!-- Delete (hidden for free items — they're managed by pricing rules) -->
      <button
        v-if="!item.is_free_item"
        @click.stop="emit('remove', index)"
        aria-label="Remove item"
        class="w-7 h-7 rounded-md flex items-center justify-center active:scale-90 transition-all duration-150 opacity-0 group-hover:opacity-100"
        :class="[selected ? 'text-white/80 hover:text-white hover:bg-white/20' : 'text-gray-300 dark:text-gray-600 hover:text-red-500 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20', { 'opacity-100': selected }]"
      >
        <Trash2 :size="13" />
      </button>
      <div v-else class="w-7" />
    </div>
  </div>
</template>
