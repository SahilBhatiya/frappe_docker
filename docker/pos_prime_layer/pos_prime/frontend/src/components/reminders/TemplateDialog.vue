<!-- Copyright (c) 2026, Ravindu Gajanayaka -->
<!-- Licensed under GPLv3. See license.txt -->

<script setup lang="ts">
import {
	Dialog,
	DialogContent,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import Input from "@/components/ui/input/Input.vue";
import { useRemindersStore } from "@/stores/reminders";
import {
	CAR_PLACEHOLDERS,
	TEMPLATE_COLORS,
	TEMPLATE_PLACEHOLDERS,
	colorForTemplate,
} from "@/utils/whatsapp";
import { Trash2 } from "lucide-vue-next";
import { computed } from "vue";

const props = defineProps<{
	show: boolean;
}>();

const emit = defineEmits<{
	(e: "update:show", val: boolean): void;
	(e: "delete"): void;
}>();

const store = useRemindersStore();

const selectedColor = computed(() => {
	const idx = store.templates.findIndex((t) => t.id === store.selectedTemplateId);
	return colorForTemplate(store.selectedTemplate?.color, idx < 0 ? 0 : idx);
});
</script>

<template>
	<Dialog :open="show" @update:open="emit('update:show', $event)">
		<DialogContent class="sm:max-w-[500px]">
			<DialogHeader>
				<DialogTitle>{{ __("Edit Template") }}</DialogTitle>
			</DialogHeader>

			<div v-if="store.selectedTemplate" class="mt-4 space-y-4">
				<Input
					:model-value="store.selectedTemplate.title"
					@update:model-value="store.updateTemplate(store.selectedTemplate!.id, { title: String($event) })"
					:placeholder="__('Template title')"
					class="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm font-medium"
				/>
				<textarea
					:value="store.selectedTemplate.body"
					@input="store.updateTemplate(store.selectedTemplate!.id, { body: ($event.target as HTMLTextAreaElement).value })"
					rows="6"
					:placeholder="__('Message text. Use placeholders below.')"
					class="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 px-3 py-2 text-sm resize-y focus:outline-none focus:ring-2 focus:ring-gray-950 dark:focus:ring-gray-300"
				/>

				<!-- Color swatches -->
				<div class="flex items-center gap-2">
					<span class="text-sm font-medium text-gray-700 dark:text-gray-300 mr-2">{{ __("Color") }}</span>
					<button
						v-for="col in TEMPLATE_COLORS"
						:key="col.name"
						:title="col.name"
						@click="store.updateTemplate(store.selectedTemplate!.id, { color: col.name })"
						class="w-6 h-6 rounded-full ring-offset-2 ring-offset-white dark:ring-offset-gray-900 transition"
						:class="[col.swatch, selectedColor.name === col.name ? 'ring-2 ring-gray-950 dark:ring-gray-100 scale-110' : 'ring-0']"
					/>
				</div>

				<div class="pt-2 border-t border-gray-100 dark:border-gray-800">
					<div class="mb-1 text-xs text-gray-500 dark:text-gray-400">{{ __("Standard placeholders:") }}</div>
					<div class="flex flex-wrap items-center gap-1.5 mb-3">
						<code v-for="p in TEMPLATE_PLACEHOLDERS" :key="p" class="text-xs bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 px-2 py-1 rounded">{{ p }}</code>
					</div>
					<div class="mb-1 text-xs text-gray-500 dark:text-gray-400">{{ __("Car data placeholders:") }}</div>
					<div class="flex flex-wrap items-center gap-1.5">
						<code v-for="p in CAR_PLACEHOLDERS" :key="p" class="text-xs bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-300 px-2 py-1 rounded">{{ p }}</code>
					</div>
				</div>

				<div class="flex justify-between items-center pt-4 mt-2">
					<button class="flex items-center gap-1.5 text-sm font-medium text-red-600 dark:text-red-400 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-900/20 px-3 py-1.5 rounded-lg transition-colors" @click="emit('delete')">
						<Trash2 :size="16" /> {{ __("Delete") }}
					</button>
					<button class="px-4 py-2 rounded-lg bg-gray-950 text-white dark:bg-gray-100 dark:text-gray-900 text-sm font-semibold" @click="emit('update:show', false)">
						{{ __("Done") }}
					</button>
				</div>
			</div>
		</DialogContent>
	</Dialog>
</template>
