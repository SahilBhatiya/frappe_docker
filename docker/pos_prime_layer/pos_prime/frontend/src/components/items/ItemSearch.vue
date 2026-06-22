<!-- Copyright (c) 2026, Ravindu Gajanayaka -->
<!-- Licensed under GPLv3. See license.txt -->

<script setup lang="ts">
import Input from '@/components/ui/input/Input.vue'
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { Search, X, ScanBarcode } from 'lucide-vue-next'
import { useTouchDevice } from '@/composables/useTouchDevice'

const { isTouchDevice } = useTouchDevice()

const props = defineProps<{
  modelValue: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  openScanner: []
}>()

const localValue = ref(props.modelValue)
const isFocused = ref(false)
const inputRef = ref<InstanceType<typeof Input> | null>(null)
let searchTimeout: ReturnType<typeof setTimeout> | null = null

onMounted(() => {
  inputRef.value?.focus()
})

onUnmounted(() => {
  if (searchTimeout !== null) clearTimeout(searchTimeout)
})

watch(
  () => props.modelValue,
  (v) => {
    localValue.value = v
  }
)

function onInput(val: string | number) {
  const value = String(val)
  localValue.value = value
  if (searchTimeout !== null) clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    emit('update:modelValue', value)
  }, 300)
}

function clear() {
  localValue.value = ''
  emit('update:modelValue', '')
}
</script>

<template>
  <div
    class="relative flex h-10 items-center rounded-xl transition-all duration-200"
    :class="isFocused
      ? 'ring-2 ring-gray-900/10 dark:ring-white/15 bg-gray-100 dark:bg-gray-800'
      : 'bg-gray-100 dark:bg-gray-800'"
  >
    <Search
      class="ml-3 shrink-0 transition-colors duration-200"
      :class="isFocused ? 'text-gray-950 dark:text-gray-100' : 'text-gray-400 dark:text-gray-500'"
      :size="16"
    />
    <Input
      ref="inputRef"
      :model-value="localValue"
      @update:model-value="onInput"
      @focus="isFocused = true"
      @blur="isFocused = false"
      type="text"
      :placeholder="__('Search items... (F1 or /)')"
      aria-label="Search items"
      class="item-search-input h-full min-w-0 flex-1 bg-transparent pl-2 pr-2 text-sm text-gray-900 dark:text-gray-100 focus:outline-none placeholder-gray-400 dark:placeholder-gray-500"
    />
    <div class="flex items-center gap-0.5 mr-1.5">
      <button
        v-if="localValue"
        @click="clear"
        aria-label="Clear search"
        class="w-7 h-7 rounded-lg flex items-center justify-center text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
      >
        <X :size="14" />
      </button>
      <button
        v-if="isTouchDevice"
        @click="emit('openScanner')"
        class="w-7 h-7 rounded-lg flex items-center justify-center text-gray-400 dark:text-gray-500 hover:text-gray-950 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
        title="Scan barcode"
        aria-label="Scan barcode"
      >
        <ScanBarcode :size="16" />
      </button>
    </div>
  </div>
</template>

<style scoped>
.item-search-input:focus-visible {
  outline: none !important;
}
</style>
