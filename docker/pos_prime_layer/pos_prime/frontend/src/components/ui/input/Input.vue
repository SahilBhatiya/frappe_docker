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


