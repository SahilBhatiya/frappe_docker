<!-- Copyright (c) 2026, Ravindu Gajanayaka -->
<!-- Licensed under GPLv3. See license.txt -->

<script setup lang="ts">
import Input from "@/components/ui/input/Input.vue";
import TemplateDialog from "@/components/reminders/TemplateDialog.vue";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import DeleteConfirmDialog from "@/components/ui/DeleteConfirmDialog.vue";
import { useRemindersStore, type Recipient } from "@/stores/reminders";
import { usePosSessionStore } from "@/stores/posSession";
import {
	CAR_PLACEHOLDERS,
	colorForTemplate,
	normalizePhone,
	TEMPLATE_COLORS,
	TEMPLATE_PLACEHOLDERS,
} from "@/utils/whatsapp";
import {
	ArrowLeft,
	Check,
	CheckCircle2,
	Edit,
	Loader2,
	MessageCircle,
	Plus,
	Save,
	Search,
	Send,
	Trash2,
	Users,
	X,
	XCircle,
} from "lucide-vue-next";
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRouter } from "vue-router";

const router = useRouter();
const store = useRemindersStore();
const sessionStore = usePosSessionStore();

const searchInput = ref("");
const saveMsg = ref("");
const mobileShowCompose = ref(false);
const deletingTemplateId = ref<string | null>(null);
const showTemplateDialog = ref(false);

function confirmDeleteTemplate() {
	if (deletingTemplateId.value) {
		store.deleteTemplate(deletingTemplateId.value);
		deletingTemplateId.value = null;
	}
}

let debounceTimer: ReturnType<typeof setTimeout>;
let saveMsgTimer: ReturnType<typeof setTimeout>;

const shopName = computed(() => store.shopName || sessionStore.company || "");

const messageFor = (r: Recipient) =>
	store.fillTemplate(store.selectedTemplate?.body || "", {
		customer_name: r.customer_name,
		mobile: store.numberFor(r),
		shop_name: shopName.value,
		...(store.carContext.get(r.name) || {}),
	});

const previewRecipient = computed<Recipient | null>(() => store.recipientList[0] || null);
const previewText = computed(() => {
	if (previewRecipient.value) return messageFor(previewRecipient.value);
	// Illustrative sample so data-driven templates read sensibly before a pick.
	return store.fillTemplate(store.selectedTemplate?.body || "", {
		customer_name: "Rahul Sharma",
		mobile: "",
		shop_name: shopName.value,
		vehicle: "Maruti Swift",
		registration: "MH12AB1234",
		odometer: "42,000",
		next_alignment_date: "15 Dec 2026",
		next_alignment_km: "47,000",
		next_balancing_date: "10 Mar 2027",
		next_balancing_km: "52,000",
	});
});

// Color of the currently selected template (for editor + preview accents).
const selectedColor = computed(() => {
	const idx = store.templates.findIndex((t) => t.id === store.selectedTemplateId);
	return colorForTemplate(store.selectedTemplate?.color, idx < 0 ? 0 : idx);
});

const sendableCount = computed(
	() => store.recipientList.filter((r) => normalizePhone(store.numberFor(r)).length >= 11).length,
);
const missingNumberCount = computed(() => store.recipientCount - sendableCount.value);

const canSend = computed(
	() => !store.sending && !!store.selectedTemplate?.body?.trim() && sendableCount.value > 0,
);

// Left-panel helper tabs (shown only when not searching)
const leftTab = ref<"added" | "searches" | "sent">("added");
const leftTabs = [
	{ k: "added" as const, l: __("Recently Added") },
	{ k: "searches" as const, l: __("Searches") },
	{ k: "sent" as const, l: __("Recently Sent") },
];
const isSearching = computed(() => searchInput.value.trim().length > 0);
const pickerList = computed(() => {
	if (isSearching.value) return store.customers;
	if (leftTab.value === "added") return store.recentlyAdded;
	return [];
});

function formatSentAt(s: string): string {
	if (!s) return "";
	const d = new Date(s.replace(" ", "T"));
	if (isNaN(d.getTime())) return s;
	const diff = (Date.now() - d.getTime()) / 1000;
	if (diff < 60) return __("just now");
	if (diff < 3600) return `${Math.floor(diff / 60)}m`;
	if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
	return d.toLocaleDateString(undefined, { day: "2-digit", month: "short" });
}

onMounted(() => {
	store.loadTemplates();
	store.loadStatus();
	store.loadRecentlyAdded(sessionStore.posProfile);
	store.loadRecentSent();
});

onUnmounted(() => {
	clearTimeout(debounceTimer);
	clearTimeout(saveMsgTimer);
});

watch(searchInput, (term) => {
	clearTimeout(debounceTimer);
	debounceTimer = setTimeout(() => {
		store.searchCustomers(term, sessionStore.posProfile);
		if (term.trim().length >= 2) store.addRecentSearch(term);
	}, 300);
});

// Fetch per-customer car/service-due context for the selected recipients so the
// preview and sends resolve {next_alignment_date}, {odometer}, etc.
watch(
	() => store.recipientList.map((r) => r.name),
	(names) => {
		if (names.length) store.ensureCarContext(names);
	},
);

// Infinite scroll: fetch the next page when the list nears the bottom.
function onListScroll(e: Event) {
	const el = e.target as HTMLElement;
	if (store.loadingMore) return;
	if (el.scrollHeight - el.scrollTop - el.clientHeight > 80) return;
	if (isSearching.value) {
		if (store.searchHasMore) store.searchCustomers(searchInput.value, sessionStore.posProfile, true);
	} else if (leftTab.value === "added" && store.addedHasMore) {
		store.loadRecentlyAdded(sessionStore.posProfile, true);
	}
}

function clearSearch() {
	searchInput.value = "";
	store.searchCustomers("", sessionStore.posProfile);
}

async function onSaveTemplates() {
	try {
		await store.saveTemplates();
		saveMsg.value = __("Saved");
	} catch {
		saveMsg.value = __("Save failed");
	}
	clearTimeout(saveMsgTimer);
	saveMsgTimer = setTimeout(() => (saveMsg.value = ""), 2500);
}

function onAddTemplate() {
	store.addTemplate();
	showTemplateDialog.value = true;
}

function onEditTemplate() {
	if (store.selectedTemplate) {
		showTemplateDialog.value = true;
	}
}

async function onSend() {
	await store.sendAll(messageFor);
}

const badge = computed(() => {
	const s = store.waStatus;
	if (!s)
		return { text: __("Checking WhatsApp…"), cls: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300" };
	if (s.connected)
		return { text: __("WhatsApp connected"), cls: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400" };
	if (s.status === "SCAN_QR_CODE" || s.status === "STARTING")
		return { text: __("Scan QR in WAHA"), cls: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400" };
	return { text: __("WhatsApp not connected"), cls: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400" };
});
</script>

<template>
	<div class="h-full flex flex-col">
		<!-- Header -->
		<div class="px-4 py-3 flex items-center gap-3">
			<button
				@click="mobileShowCompose ? (mobileShowCompose = false) : router.push({ name: 'POS' })"
				class="lg:hidden text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200"
			>
				<ArrowLeft :size="20" />
			</button>
			<h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100">{{ __("Reminders") }}</h2>
			<span class="ml-auto inline-flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1 rounded-full" :class="badge.cls">
				<span class="w-1.5 h-1.5 rounded-full bg-current opacity-70" />
				{{ badge.text }}
			</span>
		</div>

		<div class="flex-1 flex overflow-hidden">
			<!-- Left: customer picker -->
			<div
				class="w-full lg:w-[360px] shrink-0 flex flex-col rounded-2xl bg-white dark:bg-gray-900"
				:class="{ 'hidden lg:flex': mobileShowCompose }"
			>
				<div class="p-3">
					<div class="relative">
						<Search class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500 pointer-events-none" :size="14" />
						<Input
							v-model="searchInput"
							type="text"
							:placeholder="__('Search customers…')"
							class="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 pl-8 pr-8 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-950 dark:focus:ring-gray-300 placeholder-gray-400 dark:placeholder-gray-500"
						/>
						<button v-if="searchInput" @click="clearSearch" class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300">
							<X :size="14" />
						</button>
					</div>
				</div>

				<div class="px-3 pb-2 flex items-center justify-between text-xs">
					<span class="text-gray-500 dark:text-gray-400">
						{{ __("Selected") }}:
						<span class="font-semibold text-gray-800 dark:text-gray-200">{{ store.recipientCount }}</span>
					</span>
					<div class="flex items-center gap-3">
						<button class="text-gray-600 dark:text-gray-300 hover:underline" @click="store.selectAll(store.customers)">
							{{ __("Select shown") }}
						</button>
						<button v-if="store.recipientCount" class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300" @click="store.clearRecipients()">
							{{ __("Clear") }}
						</button>
					</div>
				</div>

				<!-- Helper tabs (when not searching) -->
				<div v-if="!isSearching" class="px-3 pb-2">
					<Tabs
						:model-value="leftTab"
						@update:model-value="(val) => leftTab = String(val) as any"
						class="w-full"
					>
						<TabsList class="grid w-full grid-cols-3">
							<TabsTrigger
								v-for="t in leftTabs"
								:key="t.k"
								:value="t.k"
							>
								{{ t.l }}
							</TabsTrigger>
						</TabsList>
					</Tabs>
				</div>

				<div class="flex-1 overflow-y-auto px-3 pb-3" @scroll="onListScroll">
					<div v-if="store.listLoading" class="flex items-center justify-center py-12">
						<Loader2 :size="24" class="animate-spin text-gray-400" />
					</div>

					<!-- Recent searches -->
					<div v-else-if="!isSearching && leftTab === 'searches'">
						<div v-if="store.recentSearches.length" class="flex flex-wrap gap-2">
							<button
								v-for="term in store.recentSearches"
								:key="term"
								@click="searchInput = term"
								class="px-3 py-1.5 bg-gray-100 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 text-xs rounded-full hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors flex items-center gap-1.5"
							>
								{{ term }}
								<X :size="10" class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300" @click.stop="store.removeRecentSearch(term)" />
							</button>
						</div>
						<div v-else class="flex flex-col items-center justify-center py-12 text-gray-400 dark:text-gray-500">
							<Search :size="28" class="mb-2" />
							<p class="text-sm">{{ __("No recent searches") }}</p>
						</div>
						<button v-if="store.recentSearches.length" @click="store.clearRecentSearches()" class="mt-3 text-[10px] text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 uppercase tracking-wider font-semibold">{{ __("Clear all") }}</button>
					</div>

					<!-- Recently sent (shows the message that was sent) -->
					<div v-else-if="!isSearching && leftTab === 'sent'">
						<div v-if="store.recentSent.length" class="space-y-2">
							<button
								v-for="c in store.recentSent"
								:key="c.name"
								@click="store.toggleRecipient(c)"
								class="w-full text-left p-3 rounded-xl border transition-all duration-150"
								:class="
									store.isSelected(c.name)
										? 'border-gray-950 bg-gray-100 dark:bg-gray-800 dark:border-gray-300'
										: 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800'
								"
							>
								<div class="flex items-center gap-2">
									<span
										class="w-4 h-4 rounded border flex items-center justify-center shrink-0"
										:class="store.isSelected(c.name) ? 'bg-gray-950 border-gray-950 dark:bg-gray-100 dark:border-gray-100' : 'border-gray-300 dark:border-gray-600'"
									>
										<Check v-if="store.isSelected(c.name)" :size="11" class="text-white dark:text-gray-900" />
									</span>
									<span class="font-medium text-sm text-gray-900 dark:text-gray-100 truncate flex-1 min-w-0">{{ c.customer_name }}</span>
									<span class="text-[10px] text-gray-400 shrink-0">{{ formatSentAt(c.sent_at) }}</span>
								</div>
								<p v-if="c.text" class="mt-1.5 ml-6 text-xs text-gray-500 dark:text-gray-400 line-clamp-2 whitespace-pre-wrap">{{ c.text }}</p>
								<span class="block ml-6 text-[11px] text-gray-400 dark:text-gray-500 mt-0.5">{{ store.numberFor(c) || __("No number") }}</span>
							</button>
						</div>
						<div v-else class="flex flex-col items-center justify-center py-12 text-gray-400 dark:text-gray-500">
							<MessageCircle :size="28" class="mb-2" />
							<p class="text-sm">{{ __("No reminders sent yet") }}</p>
						</div>
					</div>

					<!-- Empty state for customer lists -->
					<div v-else-if="pickerList.length === 0" class="flex flex-col items-center justify-center py-12 text-gray-400 dark:text-gray-500">
						<Users :size="32" class="mb-3" />
						<p class="text-sm">{{ isSearching ? __("No customers found") : (leftTab === 'sent' ? __("No reminders sent yet") : __("No customers yet")) }}</p>
					</div>

					<!-- Customer rows (search results / recently added / recently sent) -->
					<div v-else class="space-y-2">
						<button
							v-for="c in pickerList"
							:key="c.name"
							@click="store.toggleRecipient(c)"
							class="w-full text-left p-3 rounded-xl border transition-all duration-150 flex items-start gap-3"
							:class="
								store.isSelected(c.name)
									? 'border-gray-950 bg-gray-100 dark:bg-gray-800 dark:border-gray-300'
									: 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800'
							"
						>
							<span
								class="mt-0.5 w-4 h-4 rounded border flex items-center justify-center shrink-0"
								:class="store.isSelected(c.name) ? 'bg-gray-950 border-gray-950 dark:bg-gray-100 dark:border-gray-100' : 'border-gray-300 dark:border-gray-600'"
							>
								<Check v-if="store.isSelected(c.name)" :size="11" class="text-white dark:text-gray-900" />
							</span>
							<span class="min-w-0">
								<span class="block font-medium text-sm text-gray-900 dark:text-gray-100 truncate">{{ c.customer_name }}</span>
								<span class="block text-xs mt-0.5 truncate" :class="store.numberFor(c) ? 'text-gray-500 dark:text-gray-400' : 'text-amber-600 dark:text-amber-400'">
									{{ store.numberFor(c) || __("No number") }}
								</span>
							</span>
						</button>
					</div>

					<!-- Infinite-scroll loader -->
					<div v-if="store.loadingMore" class="flex items-center justify-center py-3">
						<Loader2 :size="18" class="animate-spin text-gray-400" />
					</div>
				</div>

				<div class="lg:hidden p-3 border-t border-gray-200 dark:border-gray-700">
					<button @click="mobileShowCompose = true" class="w-full py-2.5 rounded-xl bg-gray-950 text-white dark:bg-gray-100 dark:text-gray-900 text-sm font-semibold">
						{{ __("Next: compose message") }}
					</button>
				</div>
			</div>

			<!-- Right: compose & send -->
			<div class="flex-1 overflow-y-auto" :class="{ 'hidden lg:block': !mobileShowCompose }">
				<div class="max-w-3xl mx-auto w-full p-4 lg:p-6 space-y-5">
					<!-- Not connected warning -->
					<div v-if="store.waStatus && !store.waStatus.connected" class="rounded-2xl border border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-900/20 p-4 text-xs text-amber-800 dark:text-amber-300">
						{{ __("WhatsApp is not connected.") }}
						<a v-if="store.waStatus.dashboard_url" :href="store.waStatus.dashboard_url" target="_blank" class="underline font-medium">{{ __("Open WAHA dashboard to scan QR") }}</a>
						<span v-if="store.waStatus.error" class="block opacity-70 mt-1">{{ store.waStatus.error }}</span>
					</div>

					<!-- Templates -->
					<div class="rounded-2xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-5">
						<div class="flex items-center justify-between mb-4">
							<h4 class="text-sm font-semibold text-gray-900 dark:text-gray-100">{{ __("Templates") }}</h4>
							<div class="flex items-center gap-2">
								<span v-if="saveMsg" class="text-[11px] text-green-600 dark:text-green-400">{{ saveMsg }}</span>
								<button class="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800" @click="onEditTemplate" :disabled="!store.selectedTemplate">
									<Edit :size="13" /> {{ __("Edit") }}
								</button>
								<button class="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800" @click="onAddTemplate">
									<Plus :size="13" /> {{ __("New") }}
								</button>
								<button class="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-gray-950 text-white dark:bg-gray-100 dark:text-gray-900 disabled:opacity-50" :disabled="store.savingTemplates" @click="onSaveTemplates">
									<Save :size="13" /> {{ store.savingTemplates ? __("Saving…") : __("Save") }}
								</button>
							</div>
						</div>

						<!-- Color-coded template chips -->
						<div class="flex flex-wrap gap-2 mb-4">
							<button
								v-for="(t, i) in store.templates"
								:key="t.id"
								@click="store.selectedTemplateId = t.id"
								class="px-3 py-1.5 text-xs font-medium rounded-full border transition-colors"
								:class="store.selectedTemplateId === t.id ? colorForTemplate(t.color, i).chipActive : colorForTemplate(t.color, i).chipIdle"
							>
								{{ t.title || __("Untitled") }}
							</button>
						</div>


					</div>

					<!-- Preview -->
					<div class="rounded-2xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-5">
						<h4 class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">
							{{ __("Preview") }}
							<span v-if="previewRecipient" class="font-normal text-gray-400">— {{ previewRecipient.customer_name }}</span>
						</h4>
						<div class="rounded-xl border p-3.5 text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap min-h-[3.5rem]" :class="selectedColor.previewRing">
							{{ previewText || __("Select a template to preview the message.") }}
						</div>
					</div>

					<!-- Send -->
					<div class="rounded-2xl bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 p-5">
						<div class="flex items-center justify-between gap-3 mb-3">
							<div class="text-sm text-gray-600 dark:text-gray-400">
								<span class="font-semibold text-gray-900 dark:text-gray-100">{{ store.recipientCount }}</span>
								{{ __("selected") }}
								<span v-if="missingNumberCount" class="text-amber-600 dark:text-amber-400">· {{ missingNumberCount }} {{ __("no number") }}</span>
								<span v-if="store.sentCount" class="text-green-600 dark:text-green-400">· {{ store.sentCount }} {{ __("sent") }}</span>
								<span v-if="store.failedCount" class="text-red-600 dark:text-red-400">· {{ store.failedCount }} {{ __("failed") }}</span>
							</div>
							<button
								class="flex items-center gap-2 h-10 px-4 rounded-xl bg-green-600 hover:bg-green-700 text-white text-sm font-semibold disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
								:disabled="!canSend"
								@click="onSend"
							>
								<Loader2 v-if="store.sending" :size="16" class="animate-spin" />
								<Send v-else :size="16" />
								{{ store.sending ? __("Sending…") : __("Send to {n}", { n: String(sendableCount) }) }}
							</button>
						</div>

						<div v-if="store.recipientCount" class="space-y-1.5 max-h-64 overflow-y-auto">
							<div v-for="r in store.recipientList" :key="r.name" class="flex items-center justify-between gap-2 text-xs px-2.5 py-1.5 rounded-lg bg-gray-50 dark:bg-gray-800">
								<span class="min-w-0 truncate">
									<span class="font-medium text-gray-800 dark:text-gray-200">{{ r.customer_name }}</span>
									<span class="text-gray-400 ml-2">{{ store.numberFor(r) || __("No number") }}</span>
								</span>
								<span class="shrink-0 flex items-center gap-1">
									<Loader2 v-if="r.status === 'sending'" :size="13" class="animate-spin text-gray-400" />
									<CheckCircle2 v-else-if="r.status === 'sent'" :size="13" class="text-green-600 dark:text-green-400" />
									<XCircle v-else-if="r.status === 'failed'" :size="13" class="text-red-500" :title="r.error || ''" />
									<span v-else-if="!store.numberFor(r)" class="text-amber-600 dark:text-amber-400">{{ __("no number") }}</span>
									<button class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300" @click="store.toggleRecipient(r)">
										<X :size="13" />
									</button>
								</span>
							</div>
						</div>
						<div v-else class="flex flex-col items-center justify-center py-8 text-gray-400 dark:text-gray-500">
							<MessageCircle :size="28" class="mb-2" />
							<p class="text-sm">{{ __("Select customers on the left to send a reminder") }}</p>
						</div>
					</div>
				</div>
			</div>
		</div>


		<DeleteConfirmDialog
			:show="!!deletingTemplateId"
			@update:show="deletingTemplateId = null"
			:title="__('Delete Template?')"
			:message="__('This action cannot be undone. The template will be permanently removed.')"
			:confirm-text="__('Delete')"
			@confirm="confirmDeleteTemplate"
			@cancel="deletingTemplateId = null"
		/>

		<TemplateDialog
			:show="showTemplateDialog"
			@update:show="showTemplateDialog = $event"
			@delete="deletingTemplateId = store.selectedTemplate?.id || null"
		/>
	</div>
</template>
