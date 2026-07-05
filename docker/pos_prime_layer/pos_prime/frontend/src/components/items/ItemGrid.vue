<!-- Copyright (c) 2026, Ravindu Gajanayaka -->
<!-- Licensed under GPLv3. See license.txt -->

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useVirtualizer } from '@tanstack/vue-virtual'
import { useItemsStore } from '@/stores/items'
import { useCartStore } from '@/stores/cart'
import { useSettingsStore } from '@/stores/settings'
import { useBarcodeScanner } from '@/composables/useBarcodeScanner'
import ItemCard from './ItemCard.vue'
import ItemTableRow from './ItemTableRow.vue'
import ItemSearch from './ItemSearch.vue'
import BatchSerialSelector from './BatchSerialSelector.vue'
import CameraScanner from '@/components/scanner/CameraScanner.vue'
import { Grid2X2, List, Package } from 'lucide-vue-next'
import { useDeskMode } from '@/composables/useDeskMode'
import type { Item } from '@/types'

const { isDeskMode } = useDeskMode()

const itemsStore = useItemsStore()
const cartStore = useCartStore()
const settingsStore = useSettingsStore()
const scrollContainer = ref<HTMLElement | null>(null)
const showCameraScanner = ref(false)
const columnCount = ref(4)
const showCategories = ref(localStorage.getItem('pos_show_categories') !== 'false')
type ViewMode = 'card' | 'table'
const storedViewMode = localStorage.getItem('pos_item_view_mode')
const viewMode = ref<ViewMode>(storedViewMode === 'card' ? 'card' : 'table')

function setViewMode(mode: ViewMode) {
  if (viewMode.value === mode) return
  viewMode.value = mode
  localStorage.setItem('pos_item_view_mode', mode)
  scrollContainer.value?.scrollTo({ top: 0, behavior: 'smooth' })
  nextTick(() => virtualizer.value.measure())
}

function delayedUpdateColumnCount() {
  // Delay to let sidebar CSS transition finish before measuring
  setTimeout(updateColumnCount, 300)
}

// jQuery is only present in Frappe desk; in the standalone SPA `$` is undefined.
// Guard so we don't throw `$ is not defined` during mount (which can disrupt the
// render flush and break other components' post-mount hooks, e.g. dialogs).
const jq = (window as any).$ as undefined | ((el: unknown) => any)

onMounted(() => {
  itemsStore.fetchItemGroups()
  itemsStore.fetchAllItems()
  updateColumnCount()
  window.addEventListener('resize', updateColumnCount)
  // Adapt when Frappe desk sidebar is toggled (desk mode only)
  if (jq) jq(document.body).on('toggleSidebar', delayedUpdateColumnCount)
})

onUnmounted(() => {
  window.removeEventListener('resize', updateColumnCount)
  if (jq) jq(document.body).off('toggleSidebar', delayedUpdateColumnCount)
})

function updateColumnCount() {
  const width = scrollContainer.value?.clientWidth || window.innerWidth
  if (width < 640) columnCount.value = 2
  else if (width < 768) columnCount.value = 3
  else columnCount.value = 4
}

// Group filtered items into rows for virtual scrolling
const rows = computed(() => {
  const items = [...itemsStore.filteredItems].sort((a, b) => (b.actual_qty || 0) - (a.actual_qty || 0))
  if (viewMode.value === 'table') return items.map(item => [item])
  const cols = columnCount.value
  const result: Item[][] = []
  for (let i = 0; i < items.length; i += cols) {
    result.push(items.slice(i, i + cols))
  }
  return result
})

const virtualizer = useVirtualizer(
  computed(() => ({
    count: rows.value.length,
    getScrollElement: () => scrollContainer.value,
    estimateSize: () => viewMode.value === 'table'
      ? 68
      : settingsStore.hideImages ? 70 : (isDeskMode.value ? 185 : 200),
    overscan: 5,
  }))
)

// Auto-add to cart if setting enabled and exactly 1 item matches
watch(
  () => [itemsStore.searchTerm, itemsStore.filteredItems.length],
  () => {
    if (
      settingsStore.autoAddItemToCart &&
      itemsStore.filteredItems.length === 1 &&
      itemsStore.searchTerm
    ) {
      const err = cartStore.addItem(itemsStore.filteredItems[0], settingsStore.validateStockOnSave)
      if (err) showStockError(err)
      itemsStore.setSearchTerm('')
    }
  }
)

function onSearchChange(term: string) {
  itemsStore.setSearchTerm(term)
  virtualizer.value.scrollToOffset(0)
}

function onGroupSelect(group: string) {
  itemsStore.setSelectedGroup(group)
  virtualizer.value.scrollToOffset(0)
}

// Batch/Serial selector state
const batchSerialItem = ref<Item | null>(null)

function showStockError(msg: string) {
  const frappe = (window as any).frappe
  if (frappe?.show_alert) {
    frappe.show_alert({ message: msg, indicator: 'orange' }, 3)
  }
}

function onItemSelect(item: Item) {
  if (item.has_batch_no || item.has_serial_no) {
    // Show batch/serial selector dialog
    batchSerialItem.value = item
    return
  }
  const err = cartStore.addItem(item, settingsStore.validateStockOnSave)
  if (err) showStockError(err)
}

function onBatchSerialConfirm(batchNo: string | null, serialNo: string | null) {
  const item = batchSerialItem.value
  if (!item) return

  // For serial items, serials may span multiple batches — auto-split
  if (serialNo && item.has_batch_no && item.has_serial_no && !batchNo) {
    // This case shouldn't happen with current UI (batch is required first),
    // but handle it for safety
    cartStore.addItem(item, settingsStore.validateStockOnSave)
    const lastIndex = cartStore.items.length - 1
    cartStore.updateItemBatchSerial(lastIndex, null, serialNo)
  } else {
    // Normal case: add item and set batch/serial
    cartStore.addItem(item, settingsStore.validateStockOnSave)
    const lastIndex = cartStore.items.length - 1
    cartStore.updateItemBatchSerial(lastIndex, batchNo, serialNo)
    // Set qty from serial count if serials were selected
    if (serialNo) {
      const serialCount = serialNo.split('\n').filter(s => s.trim()).length
      if (serialCount > 1) {
        cartStore.updateQty(lastIndex, serialCount)
      }
    }
  }
  batchSerialItem.value = null
}

// Hardware barcode scanner integration
async function handleBarcodeScan(barcode: string) {
  const result = await itemsStore.searchByBarcode(barcode)
  if (result && result.item_code) {
    // Find item in full list or create minimal item for cart
    const existingItem = itemsStore.allItems.find((i) => i.item_code === result.item_code)
    if (existingItem) {
      const err = cartStore.addItem(existingItem, settingsStore.validateStockOnSave)
      if (err) { showStockError(err); return }
    } else {
      // Add as minimal item — the backend will resolve full details
      const err = cartStore.addItem({
        item_code: result.item_code,
        item_name: result.item_name || result.item_code,
        rate: result.rate || 0,
        actual_qty: result.actual_qty || 0,
        is_stock_item: result.is_stock_item ?? true,
        stock_uom: result.stock_uom || 'Nos',
        description: '',
        item_group: '',
        image: null,
        currency: settingsStore.currency,
        has_batch_no: !!result.batch_no || !!result.has_batch_no,
        has_serial_no: !!result.serial_no || !!result.has_serial_no,
        brand: null,
        weight_per_unit: null,
        weight_uom: null,
        barcode: result.barcode || null,
        item_tax_template: null,
        is_product_bundle: false,
      }, settingsStore.validateStockOnSave)
      if (err) { showStockError(err); return }

      // If scanned item has batch/serial info, update the cart item
      if (result.batch_no || result.serial_no) {
        const lastIndex = cartStore.items.length - 1
        cartStore.updateItemBatchSerial(
          lastIndex,
          result.batch_no || null,
          result.serial_no || null
        )
      }
    }

    // Apply barcode-specific UOM if returned by backend
    if (result.barcode_uom) {
      const lastIndex = cartStore.items.length - 1
      cartStore.updateItemUom(lastIndex, result.barcode_uom, result.barcode_conversion_factor || 1)
    }
  }
}

useBarcodeScanner(handleBarcodeScan)

function onCameraScan(value: string) {
  showCameraScanner.value = false
  handleBarcodeScan(value)
}

// Display label: show selected group or "All Items"
const headerLabel = computed(() => {
  return itemsStore.selectedGroup === 'All Item Groups'
    ? __('All Items')
    : itemsStore.selectedGroup || __('All Items')
})
</script>

<template>
  <div class="flex flex-col h-full">
    <!-- Filter section — ERPNext-style: label + search + category toggle -->
    <div class="flex items-center gap-2 px-3 py-2">
      <!-- Section label (like ERPNext's "All Items") -->
      <div class="hidden sm:flex items-center gap-2 shrink-0">
        <span class="text-base font-bold text-gray-900 dark:text-gray-100 whitespace-nowrap">{{ headerLabel }}</span>
      </div>

      <!-- Search -->
      <ItemSearch
        class="flex-1"
        :model-value="itemsStore.searchTerm"
        @update:model-value="onSearchChange"
        @open-scanner="showCameraScanner = true"
      />

      <div
        class="flex shrink-0 items-center rounded-xl bg-gray-100 p-1 dark:bg-gray-800"
        role="group"
        :aria-label="__('Item view')"
      >
        <button
          type="button"
          class="flex size-8 items-center justify-center rounded-lg transition-all duration-200"
          :class="viewMode === 'card'
            ? 'bg-primary text-primary-foreground shadow-sm'
            : 'text-gray-400 hover:bg-white hover:text-gray-700 dark:text-gray-500 dark:hover:bg-gray-700 dark:hover:text-gray-200'"
          :title="__('Card view')"
          :aria-label="__('Card view')"
          :aria-pressed="viewMode === 'card'"
          @click="setViewMode('card')"
        >
          <Grid2X2 :size="16" />
        </button>
        <button
          type="button"
          class="flex size-8 items-center justify-center rounded-lg transition-all duration-200"
          :class="viewMode === 'table'
            ? 'bg-primary text-primary-foreground shadow-sm'
            : 'text-gray-400 hover:bg-white hover:text-gray-700 dark:text-gray-500 dark:hover:bg-gray-700 dark:hover:text-gray-200'"
          :title="__('Table view')"
          :aria-label="__('Table view')"
          :aria-pressed="viewMode === 'table'"
          @click="setViewMode('table')"
        >
          <List :size="17" />
        </button>
      </div>
    </div>

    <div class="flex flex-1 overflow-hidden">
      <div class="flex-1 flex flex-col relative overflow-hidden">
        <div
          ref="scrollContainer"
          class="flex-1 overflow-y-auto"
          style="container-type: inline-size; container-name: item-results;"
        >
          <div
            v-if="itemsStore.loading && itemsStore.allItems.length === 0"
            class="flex items-center justify-center py-12"
          >
            <div class="text-gray-400 dark:text-gray-500 text-sm">{{ __('Loading items...') }}</div>
          </div>

          <div
            v-else-if="itemsStore.filteredItems.length === 0"
            class="flex flex-col items-center justify-center py-12"
          >
            <Package class="text-gray-300 dark:text-gray-600 mb-3" :size="48" />
            <p class="text-gray-500 dark:text-gray-400 text-sm">{{ __('No items found') }}</p>
          </div>

          <div
            v-if="viewMode === 'table' && itemsStore.filteredItems.length > 0"
            role="row"
            class="item-table-header sticky top-0 z-10 mx-2 grid gap-3 bg-white/95 px-3.5 py-3 text-xs font-medium text-gray-500 backdrop-blur-md dark:bg-gray-950/95 dark:text-gray-400"
          >
            <span role="columnheader">{{ __('Item') }}</span>
            <span role="columnheader" class="item-table-header-group">{{ __('Group') }}</span>
            <span role="columnheader" class="item-table-header-stock">{{ __('Stock') }}</span>
            <span role="columnheader" class="text-right">{{ __('Price') }}</span>
            <span role="columnheader" class="text-right text-gray-400/60 dark:text-gray-500/60 font-normal">..</span>
          </div>

          <!-- Both layouts stay virtualized so large catalogs and live search remain fluid. -->
          <div
            v-if="itemsStore.filteredItems.length > 0"
            :role="viewMode === 'table' ? 'rowgroup' : undefined"
            :style="{ height: `${virtualizer.getTotalSize()}px`, width: '100%', position: 'relative' }"
          >
            <div
              v-for="virtualRow in virtualizer.getVirtualItems()"
              :key="virtualRow.index"
              :ref="(el) => { if (el) virtualizer.measureElement(el as Element) }"
              :data-index="virtualRow.index"
              :style="{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                transform: `translateY(${virtualRow.start}px)`,
                paddingLeft: 'var(--padding-sm, 8px)',
                paddingRight: 'var(--padding-sm, 8px)',
              }"
            >
              <div
                class="grid animate-in fade-in-0 slide-in-from-bottom-1 duration-200"
                :class="viewMode === 'table' ? 'pb-2' : 'pb-2'"
                style="gap: var(--margin-sm, 8px);"
                :style="viewMode === 'card'
                  ? { gridTemplateColumns: `repeat(${columnCount}, minmax(0, 1fr))` }
                  : undefined"
              >
                <ItemCard
                  v-if="viewMode === 'card'"
                  v-for="item in rows[virtualRow.index]"
                  :key="item.item_code"
                  :item="item"
                  @select="onItemSelect"
                />
                <ItemTableRow
                  v-else
                  :item="rows[virtualRow.index][0]"
                  :is-alternate="virtualRow.index % 2 === 1"
                  @select="onItemSelect"
                />
              </div>
            </div>
          </div>
        </div>
        <!-- Gradient white transparent overlay at the bottom -->
        <div class="pointer-events-none absolute bottom-0 left-0 right-0 h-10 bg-gradient-to-t from-white to-transparent dark:from-gray-950 dark:to-transparent z-10" />
      </div>
    </div>

    <!-- Camera scanner overlay -->
    <CameraScanner
      v-if="showCameraScanner"
      @scan="onCameraScan"
      @close="showCameraScanner = false"
    />

    <!-- Batch/Serial selector dialog -->
    <BatchSerialSelector
      v-if="batchSerialItem"
      :item-code="batchSerialItem.item_code"
      :item-name="batchSerialItem.item_name"
      :has-batch-no="batchSerialItem.has_batch_no"
      :has-serial-no="batchSerialItem.has_serial_no"
      @confirm="onBatchSerialConfirm"
      @close="batchSerialItem = null"
    />
  </div>
</template>

<style scoped>
.item-table-header {
  grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr) 4.5rem 6.5rem 2rem;
}

@container item-results (max-width: 620px) {
  .item-table-header {
    grid-template-columns: minmax(0, 1fr) 4.5rem 6.5rem 2rem;
  }

  .item-table-header-group {
    display: none;
  }
}

@container item-results (max-width: 410px) {
  .item-table-header {
    grid-template-columns: minmax(0, 1fr) 6rem;
  }

  .item-table-header-stock,
  .item-table-header > span:last-child {
    display: none;
  }
}
</style>
