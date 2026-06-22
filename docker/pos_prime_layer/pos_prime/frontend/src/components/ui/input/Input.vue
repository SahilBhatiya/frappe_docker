<script setup lang="ts">
import { ref, type HTMLAttributes } from "vue"
import { useVModel } from "@vueuse/core"
import { cn } from "@/lib/utils"

const props = defineProps<{
  defaultValue?: string | number
  modelValue?: string | number
  class?: HTMLAttributes["class"]
}>()

const emits = defineEmits<{
  (e: "update:modelValue", payload: string | number): void
}>()

const modelValue = useVModel(props, "modelValue", emits, {
  passive: true,
  defaultValue: props.defaultValue,
})

const inputElement = ref<HTMLInputElement | null>(null)

defineExpose({
  focus: () => inputElement.value?.focus(),
  select: () => inputElement.value?.select(),
  inputElement,
})
</script>

<template>
  <input
    ref="inputElement"
    v-model="modelValue"
    data-slot="input"
    :class="cn(
      '!h-10 !rounded-xl border border-transparent bg-gray-100 dark:bg-gray-800 px-3 !py-2 text-base transition-colors file:h-6 file:text-sm file:font-medium md:text-sm w-full min-w-0 outline-none file:inline-flex file:border-0 file:bg-transparent file:text-foreground placeholder:text-muted-foreground disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50',
      props.class,
    )"
  >
</template>

<style scoped>
[data-slot="input"] {
  height: 40px !important;
  border-radius: 0.75rem !important;
  border-color: transparent !important;
  background-color: #f3f4f6 !important;
  padding-top: 0.5rem !important;
  padding-bottom: 0.5rem !important;
}

[data-slot="input"]:focus,
[data-slot="input"]:focus-visible {
  border-color: transparent !important;
  background-color: #f3f4f6 !important;
  box-shadow: 0 0 0 2px rgb(17 24 39 / 0.1) !important;
}

[data-slot="input"][aria-invalid="true"] {
  box-shadow: 0 0 0 2px rgb(239 68 68 / 0.25) !important;
}

:global([data-theme="dark"]) [data-slot="input"] {
  background-color: #1f2937 !important;
}

:global([data-theme="dark"]) [data-slot="input"]:focus,
:global([data-theme="dark"]) [data-slot="input"]:focus-visible {
  background-color: #1f2937 !important;
  box-shadow: 0 0 0 2px rgb(255 255 255 / 0.14) !important;
}
</style>
