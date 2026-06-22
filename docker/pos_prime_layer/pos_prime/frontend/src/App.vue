<!-- Copyright (c) 2026, Ravindu Gajanayaka -->
<!-- Licensed under GPLv3. See license.txt -->

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { session } from './stores/session'
import { useRTL } from './composables/useRTL'
import { useDeskMode } from './composables/useDeskMode'
import ToastContainer from './components/layout/ToastContainer.vue'

const { isRTL } = useRTL()
const { isDeskMode } = useDeskMode()
const initialized = ref(false)

onMounted(async () => {
  if (isDeskMode.value) {
    // In desk mode, user is already authenticated
    try { await session.user.reload() } catch { /* ignore */ }
    initialized.value = true
    return
  }

  // Standalone mode — verify authentication
  try {
    await session.user.reload()
  } catch (err) {
    console.error('Session user reload error:', err)
  }
  initialized.value = true
})
</script>

<template>
  <div :dir="isRTL ? 'rtl' : 'ltr'" :class="isDeskMode ? 'h-full' : ''">
    <router-view v-if="initialized" v-slot="{ Component, route }">
      <transition name="page-blur" mode="out-in">
        <component :is="Component" :key="route.matched[0]?.path || route.path" />
      </transition>
    </router-view>
    <div v-else class="flex items-center justify-center bg-white dark:bg-gray-900" :class="isDeskMode ? 'h-full' : 'h-screen'">
      <div class="text-gray-500 dark:text-gray-400">{{ __('Loading...') }}</div>
    </div>
    <ToastContainer />
  </div>
</template>

<style>
.page-blur-enter-active,
.page-blur-leave-active {
  will-change: opacity, filter, transform;
}

.page-blur-enter-active {
  transition:
    opacity 240ms ease-out,
    filter 240ms ease-out,
    transform 240ms ease-out;
}

.page-blur-leave-active {
  transition:
    opacity 160ms ease-in,
    filter 160ms ease-in,
    transform 160ms ease-in;
}

.page-blur-enter-from {
  opacity: 0;
  filter: blur(10px);
  transform: scale(0.992);
}

.page-blur-leave-to {
  opacity: 0;
  filter: blur(8px);
  transform: scale(1.006);
}

@media (prefers-reduced-motion: reduce) {
  .page-blur-enter-active,
  .page-blur-leave-active {
    transition: opacity 1ms linear;
  }

  .page-blur-enter-from,
  .page-blur-leave-to {
    filter: none;
    transform: none;
  }
}
</style>
