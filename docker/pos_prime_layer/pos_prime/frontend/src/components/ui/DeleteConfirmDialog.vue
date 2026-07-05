<script setup lang="ts">
import { AlertTriangle } from "lucide-vue-next";
import {
	Dialog,
	DialogContent,
	DialogHeader,
	DialogTitle,
	DialogFooter,
} from "@/components/ui/dialog";

const props = defineProps<{
	show: boolean;
	title: string;
	message: string;
	confirmText?: string;
}>();

const emit = defineEmits<{
	(e: "update:show", value: boolean): void;
	(e: "confirm"): void;
	(e: "cancel"): void;
}>();

function onCancel() {
	emit("cancel");
	emit("update:show", false);
}

function onConfirm() {
	emit("confirm");
}
</script>

<template>
	<Dialog :open="show" @update:open="(val) => { if (!val) onCancel() }">
		<DialogContent class="sm:max-w-[340px] text-center" :show-close-button="false">
			<DialogHeader class="items-center">
				<div class="w-16 h-16 rounded-full bg-orange-50 dark:bg-orange-900/20 text-orange-500 mx-auto flex items-center justify-center mb-2">
					<AlertTriangle :size="28" stroke-width="2" />
				</div>
				<DialogTitle class="text-lg font-bold text-gray-900 dark:text-gray-100">
					{{ title }}
				</DialogTitle>
			</DialogHeader>

			<p class="text-sm text-gray-500 dark:text-gray-400 leading-relaxed whitespace-pre-wrap">
				{{ message }}
			</p>

			<DialogFooter class="flex-row gap-3">
				<button
					@click="onCancel"
					class="flex-1 py-2.5 rounded-xl bg-gray-50 dark:bg-gray-800 text-gray-700 dark:text-gray-300 font-semibold text-sm hover:bg-gray-100 dark:hover:bg-gray-700 transition"
				>
					{{ __("Cancel") }}
				</button>
				<button
					@click="onConfirm"
					class="flex-1 py-2.5 rounded-xl bg-red-500 text-white font-semibold text-sm hover:bg-red-600 transition"
				>
					{{ confirmText || __("Delete") }}
				</button>
			</DialogFooter>
		</DialogContent>
	</Dialog>
</template>
