<script setup lang="ts">
import type { TabsTriggerProps } from "reka-ui"
import type { HTMLAttributes } from "vue"
import { reactiveOmit } from "@vueuse/core"
import { TabsTrigger, useForwardProps } from "reka-ui"
import { cn } from "@/lib/utils"

const props = defineProps<TabsTriggerProps & { class?: HTMLAttributes["class"] }>()

const delegatedProps = reactiveOmit(props, "class")

const forwardedProps = useForwardProps(delegatedProps)
</script>

<template>
  <TabsTrigger
    data-slot="tabs-trigger"
    :class="cn(
      'gap-1.5 rounded-lg border-0 px-3 text-sm font-medium [&_svg:not([class*=size-])]:size-4 has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2 relative inline-flex h-8 flex-1 items-center justify-center whitespace-nowrap text-gray-500 transition-all duration-200 group-data-vertical/tabs:w-full group-data-vertical/tabs:justify-start hover:text-gray-900 focus-visible:ring-2 focus-visible:ring-gray-900/15 focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50 dark:text-gray-400 dark:hover:text-gray-100 dark:focus-visible:ring-white/20 [&_svg]:pointer-events-none [&_svg]:shrink-0',
      'group-data-[variant=default]/tabs-list:data-active:bg-white group-data-[variant=default]/tabs-list:data-active:text-gray-900 group-data-[variant=default]/tabs-list:data-active:shadow-sm group-data-[variant=default]/tabs-list:data-[state=active]:bg-white group-data-[variant=default]/tabs-list:data-[state=active]:text-gray-900 group-data-[variant=default]/tabs-list:data-[state=active]:shadow-sm dark:group-data-[variant=default]/tabs-list:data-active:bg-gray-100 dark:group-data-[variant=default]/tabs-list:data-active:text-gray-900 dark:group-data-[variant=default]/tabs-list:data-[state=active]:bg-gray-100 dark:group-data-[variant=default]/tabs-list:data-[state=active]:text-gray-900',
      'group-data-[variant=line]/tabs-list:bg-transparent group-data-[variant=line]/tabs-list:data-active:bg-transparent group-data-[variant=line]/tabs-list:data-[state=active]:bg-transparent',
      'after:absolute after:bg-foreground after:opacity-0 after:transition-opacity group-data-horizontal/tabs:after:inset-x-0 group-data-horizontal/tabs:after:bottom-[-5px] group-data-horizontal/tabs:after:h-0.5 group-data-vertical/tabs:after:inset-y-0 group-data-vertical/tabs:after:-right-1 group-data-vertical/tabs:after:w-0.5 group-data-[variant=line]/tabs-list:data-active:after:opacity-100',
      props.class,
    )"
    v-bind="forwardedProps"
  >
    <slot />
  </TabsTrigger>
</template>
