<!-- Copyright (c) 2026, Ravindu Gajanayaka -->
<!-- Licensed under GPLv3. See license.txt -->

<script setup lang="ts">
import { ref } from "vue";
import AppShell from "./AppShell.vue";

type ActiveView = {
	toggleHeldOrders?: () => void;
	openReturnDialog?: () => void;
};

const activeView = ref<ActiveView | null>(null);
</script>

<template>
	<AppShell
		@toggle-held-orders="activeView?.toggleHeldOrders?.()"
		@toggle-return="activeView?.openReturnDialog?.()"
	>
		<router-view v-slot="{ Component, route }">
			<transition name="page-blur" mode="out-in">
				<component :is="Component" :key="route.fullPath" ref="activeView" />
			</transition>
		</router-view>
	</AppShell>
</template>
