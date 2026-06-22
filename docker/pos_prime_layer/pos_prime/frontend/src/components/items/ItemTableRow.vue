<!-- Copyright (c) 2026, Ravindu Gajanayaka -->
<!-- Licensed under GPLv3. See license.txt -->

<script setup lang="ts">
import { useCurrency } from '@/composables/useCurrency'
import type { Item } from '@/types'
import { Package, Plus } from 'lucide-vue-next'

const props = defineProps<{
  item: Item
}>()

const emit = defineEmits<{
  select: [item: Item]
}>()

const { formatCurrency } = useCurrency()
</script>

<template>
  <button
    role="row"
    type="button"
    class="item-table-row group grid min-h-14 w-full items-center gap-3 rounded-xl border border-gray-100 bg-white px-3 py-2 text-left shadow-sm transition-[background-color,color,box-shadow,transform] duration-150 hover:-translate-y-px hover:border-primary hover:bg-primary hover:text-primary-foreground hover:shadow-md active:translate-y-0 dark:border-gray-800 dark:bg-gray-900 dark:hover:border-primary dark:hover:bg-primary dark:hover:text-primary-foreground"
    :aria-label="`Add ${props.item.item_name} to cart`"
    @click="emit('select', props.item)"
  >
    <span role="cell" class="flex min-w-0 items-center gap-2.5">
      <span class="flex size-9 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-gray-50 text-gray-300 transition-colors group-hover:bg-primary-foreground/15 group-hover:text-primary-foreground dark:bg-gray-800 dark:text-gray-600">
        <img
          v-if="item.image"
          :src="item.image"
          :alt="item.item_name"
          loading="lazy"
          class="h-full w-full object-cover"
        />
        <Package v-else :size="18" />
      </span>
      <span class="min-w-0">
        <span class="block truncate text-sm font-semibold text-gray-900 transition-colors group-hover:text-primary-foreground dark:text-gray-100">
          {{ item.item_name }}
        </span>
        <span class="mt-0.5 block truncate text-[11px] text-gray-400 transition-colors group-hover:text-primary-foreground/75">
          {{ item.item_code }}
        </span>
      </span>
    </span>

    <span role="cell" class="item-table-group truncate text-xs text-gray-500 transition-colors group-hover:text-primary-foreground/75 dark:text-gray-400">
      {{ item.item_group || '-' }}
    </span>

    <span role="cell" class="item-table-stock">
      <span
        v-if="item.is_stock_item || item.is_product_bundle"
        class="inline-flex min-w-8 items-center justify-center rounded-md px-1.5 py-0.5 text-[10px] font-bold transition-colors group-hover:bg-primary-foreground/15 group-hover:text-primary-foreground"
        :class="item.actual_qty > 10
          ? 'bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-400'
          : item.actual_qty > 0
            ? 'bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
            : 'bg-red-50 text-red-600 dark:bg-red-900/30 dark:text-red-400'"
      >
        {{ item.actual_qty > 0 ? item.actual_qty : __('Out') }}
      </span>
      <span v-else class="text-xs text-gray-400 group-hover:text-primary-foreground/70">-</span>
    </span>

    <span role="cell" class="text-right">
      <span class="block text-sm font-bold text-gray-900 transition-colors group-hover:text-primary-foreground dark:text-gray-100">
        {{ formatCurrency(item.rate) }}
      </span>
      <span v-if="item.stock_uom" class="block text-[10px] text-gray-400 transition-colors group-hover:text-primary-foreground/70">
        / {{ item.stock_uom }}
      </span>
    </span>

    <span role="cell" class="item-table-action flex size-8 items-center justify-center rounded-lg bg-gray-50 text-gray-400 transition-colors group-hover:bg-primary-foreground group-hover:text-primary dark:bg-gray-800">
      <Plus :size="15" />
    </span>
  </button>
</template>

<style scoped>
.item-table-row {
  grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr) 4.5rem 6.5rem 2rem;
}

@container item-results (max-width: 620px) {
  .item-table-row {
    grid-template-columns: minmax(0, 1fr) 4.5rem 6.5rem 2rem;
  }

  .item-table-group {
    display: none;
  }
}

@container item-results (max-width: 410px) {
  .item-table-row {
    grid-template-columns: minmax(0, 1fr) 6rem;
  }

  .item-table-stock,
  .item-table-action {
    display: none;
  }
}
</style>
