// Copyright (c) 2026, Ravindu Gajanayaka
// Licensed under GPLv3. See license.txt

import { defineStore } from "pinia";
import { computed, ref } from "vue";
import { useStorage } from "@vueuse/core";
import { call } from "frappe-ui";
import { fillTemplate, normalizePhone, TEMPLATE_COLORS } from "@/utils/whatsapp";

export interface ReminderTemplate {
	id: string;
	title: string;
	body: string;
	color?: string;
}

export interface ReminderCustomer {
	name: string;
	customer_name: string;
	mobile_no: string | null;
	email_id?: string | null;
	custom_whatsapp?: string | null;
}

export type SendStatus = "pending" | "sending" | "sent" | "failed";

export interface Recipient extends ReminderCustomer {
	status: SendStatus;
	error?: string | null;
}

export interface RecentSentItem extends ReminderCustomer {
	text: string;
	sent_at: string;
}

export interface WhatsappStatus {
	connected: boolean;
	status: string;
	session?: string;
	dashboard_url?: string;
	error?: string;
	shop_name?: string;
}

// Preferred WhatsApp number: custom_whatsapp if set, else mobile_no.
function preferredNumber(c: ReminderCustomer): string {
	return (c.custom_whatsapp || c.mobile_no || "").trim();
}

export const useRemindersStore = defineStore("reminders", () => {
	// Templates
	const templates = ref<ReminderTemplate[]>([]);
	const selectedTemplateId = ref<string | null>(null);
	const templatesLoading = ref(false);
	const savingTemplates = ref(false);

	// WhatsApp connection
	const waStatus = ref<WhatsappStatus | null>(null);
	const statusLoading = ref(false);
	const shopName = ref("");

	// Customer picker
	const customers = ref<ReminderCustomer[]>([]);
	const listLoading = ref(false);
	const searchTerm = ref("");

	// Helper tabs (shown when not searching)
	const recentSearches = useStorage<string[]>("pos_prime_reminder_recent_searches", []);
	const recentlyAdded = ref<ReminderCustomer[]>([]);
	const recentSent = ref<RecentSentItem[]>([]);

	// Pagination (infinite scroll)
	const PAGE = 30;
	const searchHasMore = ref(false);
	const addedHasMore = ref(false);
	const loadingMore = ref(false);

	// Selected recipients, keyed by customer name
	const recipients = ref<Map<string, Recipient>>(new Map());
	const sending = ref(false);

	// Per-customer car/service-due context for the data-driven template
	const carContext = ref<Map<string, Record<string, string>>>(new Map());

	const selectedTemplate = computed(
		() => templates.value.find((t) => t.id === selectedTemplateId.value) || null,
	);
	const recipientList = computed(() => Array.from(recipients.value.values()));
	const recipientCount = computed(() => recipients.value.size);
	const sentCount = computed(
		() => recipientList.value.filter((r) => r.status === "sent").length,
	);
	const failedCount = computed(
		() => recipientList.value.filter((r) => r.status === "failed").length,
	);

	function numberFor(c: ReminderCustomer): string {
		return preferredNumber(c);
	}

	// ----- Templates -----
	async function loadTemplates() {
		templatesLoading.value = true;
		try {
			const data = await call("pos_prime.api.reminders.get_reminder_templates");
			templates.value = data || [];
			if (!selectedTemplateId.value && templates.value.length) {
				selectedTemplateId.value = templates.value[0].id;
			}
		} catch {
			templates.value = [];
		} finally {
			templatesLoading.value = false;
		}
	}

	async function saveTemplates() {
		savingTemplates.value = true;
		try {
			const data = await call("pos_prime.api.reminders.save_reminder_templates", {
				templates: templates.value,
			});
			templates.value = data || [];
			return true;
		} finally {
			savingTemplates.value = false;
		}
	}

	function addTemplate() {
		const id = `tmp-${Date.now()}`;
		const color = TEMPLATE_COLORS[templates.value.length % TEMPLATE_COLORS.length].name;
		templates.value = [
			...templates.value,
			{ id, title: __("New template"), body: "", color },
		];
		selectedTemplateId.value = id;
	}

	function updateTemplate(id: string, patch: Partial<ReminderTemplate>) {
		templates.value = templates.value.map((t) =>
			t.id === id ? { ...t, ...patch } : t,
		);
	}

	function deleteTemplate(id: string) {
		templates.value = templates.value.filter((t) => t.id !== id);
		if (selectedTemplateId.value === id) {
			selectedTemplateId.value = templates.value[0]?.id ?? null;
		}
	}

	// ----- WhatsApp status -----
	async function loadStatus() {
		statusLoading.value = true;
		try {
			waStatus.value = await call("pos_prime.api.reminders.get_whatsapp_status");
			if (waStatus.value?.shop_name) shopName.value = waStatus.value.shop_name;
		} catch (e: any) {
			waStatus.value = { connected: false, status: "UNREACHABLE", error: String(e) };
		} finally {
			statusLoading.value = false;
		}
	}

	// ----- Customers -----
	async function searchCustomers(term: string, posProfile = "", append = false) {
		searchTerm.value = term;
		if (append) loadingMore.value = true;
		else listLoading.value = true;
		try {
			const offset = append ? customers.value.length : 0;
			const rows: ReminderCustomer[] = await call("pos_prime.api.reminders.list_customers", {
				search: term,
				pos_profile: posProfile,
				limit: PAGE,
				offset,
			});
			customers.value = append ? [...customers.value, ...(rows || [])] : rows || [];
			searchHasMore.value = (rows?.length || 0) === PAGE;
		} catch {
			if (!append) customers.value = [];
			searchHasMore.value = false;
		} finally {
			listLoading.value = false;
			loadingMore.value = false;
		}
	}

	// ----- Car / service-due context -----
	async function ensureCarContext(names: string[]) {
		const missing = names.filter((n) => !carContext.value.has(n));
		if (!missing.length) return;
		try {
			const data: Record<string, Record<string, string>> = await call(
				"pos_prime.api.reminders.get_reminder_car_context",
				{ customers: missing },
			);
			const next = new Map(carContext.value);
			for (const [name, ctx] of Object.entries(data || {})) next.set(name, ctx);
			carContext.value = next;
		} catch {
			// leave uncached; template placeholders fall back to blank
		}
	}

	// ----- Helper tabs -----
	async function loadRecentlyAdded(posProfile = "", append = false) {
		if (append) loadingMore.value = true;
		try {
			const offset = append ? recentlyAdded.value.length : 0;
			const rows: ReminderCustomer[] = await call("pos_prime.api.reminders.recently_added_customers", {
				pos_profile: posProfile,
				limit: PAGE,
				offset,
			});
			recentlyAdded.value = append ? [...recentlyAdded.value, ...(rows || [])] : rows || [];
			addedHasMore.value = (rows?.length || 0) === PAGE;
		} catch {
			if (!append) recentlyAdded.value = [];
			addedHasMore.value = false;
		} finally {
			loadingMore.value = false;
		}
	}

	async function loadRecentSent() {
		try {
			const rows: { customer: string; customer_name: string; mobile_no: string; text?: string; sent_at?: string }[] =
				await call("pos_prime.api.reminders.get_recent_reminders", { limit: 20 });
			recentSent.value = (rows || []).map((r) => ({
				name: r.customer,
				customer_name: r.customer_name,
				mobile_no: r.mobile_no || null,
				custom_whatsapp: null,
				text: r.text || "",
				sent_at: r.sent_at || "",
			}));
		} catch {
			recentSent.value = [];
		}
	}

	function addRecentSearch(term: string) {
		const t = (term || "").trim();
		if (t.length < 2) return;
		recentSearches.value = [t, ...recentSearches.value.filter((x) => x !== t)].slice(0, 8);
	}

	function removeRecentSearch(term: string) {
		recentSearches.value = recentSearches.value.filter((x) => x !== term);
	}

	function clearRecentSearches() {
		recentSearches.value = [];
	}

	// ----- Recipients -----
	function isSelected(name: string) {
		return recipients.value.has(name);
	}

	function toggleRecipient(c: ReminderCustomer) {
		const next = new Map(recipients.value);
		if (next.has(c.name)) {
			next.delete(c.name);
		} else {
			next.set(c.name, { ...c, status: "pending", error: null });
		}
		recipients.value = next;
	}

	function selectAll(list: ReminderCustomer[]) {
		const next = new Map(recipients.value);
		for (const c of list) {
			if (!next.has(c.name)) next.set(c.name, { ...c, status: "pending", error: null });
		}
		recipients.value = next;
	}

	function clearRecipients() {
		recipients.value = new Map();
	}

	// ----- Send -----
	async function sendAll(messageFor: (r: Recipient) => string) {
		if (sending.value) return;
		const targets = recipientList.value.filter(
			(r) => r.status !== "sent" && normalizePhone(numberFor(r)).length >= 11,
		);
		if (!targets.length) return;

		sending.value = true;
		const next = new Map(recipients.value);
		for (const r of targets) next.set(r.name, { ...r, status: "sending", error: null });
		recipients.value = next;

		try {
			const payload = targets.map((r) => ({
				customer: r.name,
				phone: numberFor(r),
				text: messageFor(r),
			}));
			const res = await call("pos_prime.api.reminders.send_whatsapp_reminders", {
				messages: payload,
			});
			const results: { customer: string; ok: boolean; error?: string }[] =
				res?.results || [];
			const byCustomer = new Map(results.map((x) => [x.customer, x]));
			const updated = new Map(recipients.value);
			for (const r of targets) {
				const out = byCustomer.get(r.name);
				updated.set(r.name, {
					...r,
					status: out?.ok ? "sent" : "failed",
					error: out?.ok ? null : out?.error || __("Send failed"),
				});
			}
			recipients.value = updated;
		} catch (e: any) {
			const updated = new Map(recipients.value);
			for (const r of targets) {
				updated.set(r.name, { ...r, status: "failed", error: String(e) });
			}
			recipients.value = updated;
		} finally {
			sending.value = false;
			loadRecentSent();
		}
	}

	function $reset() {
		templates.value = [];
		selectedTemplateId.value = null;
		waStatus.value = null;
		customers.value = [];
		searchTerm.value = "";
		recipients.value = new Map();
	}

	return {
		templates,
		selectedTemplateId,
		templatesLoading,
		savingTemplates,
		waStatus,
		statusLoading,
		shopName,
		customers,
		listLoading,
		searchTerm,
		recentSearches,
		recentlyAdded,
		recentSent,
		searchHasMore,
		addedHasMore,
		loadingMore,
		loadRecentlyAdded,
		loadRecentSent,
		addRecentSearch,
		removeRecentSearch,
		clearRecentSearches,
		recipients,
		sending,
		carContext,
		ensureCarContext,
		selectedTemplate,
		recipientList,
		recipientCount,
		sentCount,
		failedCount,
		numberFor,
		loadTemplates,
		saveTemplates,
		addTemplate,
		updateTemplate,
		deleteTemplate,
		loadStatus,
		searchCustomers,
		isSelected,
		toggleRecipient,
		selectAll,
		clearRecipients,
		sendAll,
		$reset,
		// re-exported helper for the view's preview
		fillTemplate,
	};
});
