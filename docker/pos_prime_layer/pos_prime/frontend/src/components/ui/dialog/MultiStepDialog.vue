<script setup lang="ts">
import { Check } from "lucide-vue-next";
import {
	Dialog,
	DialogPortal,
	DialogOverlay,
} from "@/components/ui/dialog";

interface Step {
	id: string;
	title: string;
	subtitle?: string;
}

const props = defineProps<{
	show: boolean;
	title?: string;
	steps: Step[];
	currentStepIndex: number;
	loading?: boolean;
	error?: string;
}>();

const emit = defineEmits<{
	close: [];
	"update:currentStepIndex": [index: number];
	next: [];
	back: [];
	submit: [];
}>();

function nextOrSubmit() {
	if (props.currentStepIndex === props.steps.length - 1) {
		emit("submit");
	} else {
		emit("next");
	}
}
</script>

<template>
	<Dialog :open="show" @update:open="(val) => { if (!val) emit('close') }">
		<DialogPortal>
			<DialogOverlay />

			<!-- Centered full-screen container -->
			<div
				class="dialog-container fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6"
				@keydown.escape="emit('close')"
			>
				<!-- Dialog Container -->
				<div
					class="relative w-full max-w-4xl max-h-[90vh] rounded-2xl shadow-[0px_48px_100px_0px_rgba(17,12,46,0.15)] border border-zinc-200 overflow-hidden flex flex-col md:flex-row"
				>
					<!-- Left Sidebar (Steps Progress) -->
					<div
						class="bg-gray-50/80 backdrop-blur-xl dark:bg-gray-800/50 w-full md:w-72 p-6 md:p-8 shrink-0 border-b md:border-b-0 md:border-r border-gray-100 dark:border-gray-800 flex flex-col"
					>
						<div class="flex items-center gap-3 mb-8">
							<div
								v-if="$slots.icon"
								class="w-10 h-10 rounded-full flex items-center justify-center shrink-0"
								:class="
									$attrs.iconClass ||
									'bg-gray-200 dark:bg-gray-700 text-gray-950 dark:text-gray-100'
								"
							>
								<slot name="icon" />
							</div>
							<h2
								v-if="title"
								class="text-lg font-bold text-gray-900 dark:text-white"
							>
								{{ title }}
							</h2>
						</div>

						<div class="space-y-6 flex-1 hidden md:block">
							<div
								v-for="(step, index) in steps"
								:key="step.id"
								class="relative flex items-start gap-4"
							>
								<!-- Connector line -->
								<div
									v-if="index !== steps.length - 1"
									class="absolute left-[11px] top-8 bottom-[-24px] w-0.5"
									:class="
										index < currentStepIndex
											? 'bg-gray-950 dark:bg-gray-100'
											: 'bg-gray-200 dark:bg-gray-700'
									"
								></div>

								<!-- Circle indicator -->
								<div
									class="relative z-10 w-6 h-6 rounded-full flex items-center justify-center shrink-0 border-2 transition-colors duration-200"
									:class="[
										index < currentStepIndex
											? 'bg-gray-950 border-gray-950 text-white dark:bg-gray-100 dark:border-gray-100 dark:text-gray-950'
											: index === currentStepIndex
												? 'border-gray-950 bg-white dark:bg-gray-900 text-gray-950 dark:border-gray-300 dark:text-gray-100'
												: 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-gray-400',
									]"
								>
									<Check
										v-if="index < currentStepIndex"
										:size="12"
										stroke-width="3"
									/>
									<span v-else class="text-[10px] font-bold">{{
										index + 1
									}}</span>
								</div>

								<div class="flex-1 pb-2">
									<div
										class="text-sm font-semibold transition-colors duration-200"
										:class="
											index <= currentStepIndex
												? 'text-gray-900 dark:text-white'
												: 'text-gray-500'
										"
									>
										{{ step.title }}
									</div>
									<div v-if="step.subtitle" class="text-xs text-gray-500 mt-0.5">
										{{ step.subtitle }}
									</div>
								</div>
							</div>
						</div>

						<!-- Mobile Step Indicator -->
						<div
							class="md:hidden text-sm font-medium text-gray-600 dark:text-gray-400"
						>
							Step {{ currentStepIndex + 1 }} of {{ steps.length }}
						</div>
					</div>

					<!-- Right Content Area -->
					<div
						class="flex-1 bg-white flex flex-col dark:bg-gray-900 overflow-hidden relative"
					>
						<button
							@click="emit('close')"
							class="absolute top-4 right-4 z-10 w-8 h-8 rounded-full flex items-center justify-center text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:text-gray-300 dark:hover:bg-gray-800 transition-colors focus:outline-none focus:ring-0 border-none outline-none"
						>
							<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
						</button>

						<!-- Main Content Scroll Area -->
						<div class="flex-1 overflow-y-auto p-6 md:p-10 pb-24 md:pb-32">
							<div class="max-w-md mx-auto h-full flex flex-col">
								<div
									v-if="error"
									class="mb-6 p-4 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 rounded-xl text-sm border border-red-100 dark:border-red-900/30 flex items-center gap-3"
								>
									<div
										class="w-8 h-8 rounded-full bg-red-100 dark:bg-red-900/50 flex items-center justify-center shrink-0"
									>
										<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-red-600 dark:text-red-400"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
									</div>
									{{ error }}
								</div>

								<div class="flex-1 flex flex-col justify-center relative">
									<Transition name="step" mode="out-in">
										<div :key="currentStepIndex" class="h-full w-full">
											<slot :name="steps[currentStepIndex].id" />
										</div>
									</Transition>
								</div>
							</div>
						</div>

						<!-- Sticky Bottom Navigation -->
						<div
							class="absolute bottom-0 left-0 right-0 p-6 md:px-10 md:py-6 bg-white/90 dark:bg-gray-900/90 backdrop-blur-md border-t border-gray-100 dark:border-gray-800"
						>
							<div class="max-w-md mx-auto flex items-center justify-between gap-4">
								<button
									v-if="currentStepIndex > 0"
									@click="emit('back')"
									class="px-4 py-3 rounded-xl text-sm font-semibold text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors focus:outline-none focus:ring-0 border-none outline-none"
								>
									&larr; Go back
								</button>
								<div v-else class="flex-1"></div>

								<button
									@click="nextOrSubmit"
									:disabled="loading"
									class="px-4 py-3 shadow-xl rounded-xl text-sm font-semibold bg-gray-900 dark:bg-white text-white dark:text-gray-900 hover:bg-gray-800 dark:hover:bg-gray-100 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 ml-auto focus:outline-none focus:ring-0 border-none outline-none"
								>
									<svg
										v-if="loading"
										class="animate-spin -ml-1 mr-2 h-4 w-4"
										xmlns="http://www.w3.org/2000/svg"
										fill="none"
										viewBox="0 0 24 24"
									>
										<circle
											class="opacity-25"
											cx="12"
											cy="12"
											r="10"
											stroke="currentColor"
											stroke-width="4"
										></circle>
										<path
											class="opacity-75"
											fill="currentColor"
											d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
										></path>
									</svg>
									{{
										currentStepIndex === steps.length - 1
											? loading
												? "Creating..."
												: "Create"
											: "Next step"
									}}
								</button>
							</div>
						</div>
					</div>
				</div>
			</div>
		</DialogPortal>
	</Dialog>
</template>

<style scoped>
.step-enter-active,
.step-leave-active {
	transition: all 0.25s ease-out;
}

.step-enter-from {
	opacity: 0;
	transform: translateX(10px);
}

.step-leave-to {
	opacity: 0;
	transform: translateX(-10px);
}
</style>
