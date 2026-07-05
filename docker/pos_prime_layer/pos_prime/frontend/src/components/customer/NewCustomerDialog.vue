<script setup lang="ts">
import MultiStepDialog from "@/components/ui/dialog/MultiStepDialog.vue";
import { useCustomerStore } from "@/stores/customer";
import { usePosSessionStore } from "@/stores/posSession";
import { call } from "frappe-ui";
import { User } from "lucide-vue-next";
import { computed, onMounted, ref, watch } from "vue";
import Input from "../ui/input/Input.vue";

interface QuickField {
	fieldname: string;
	label: string;
	fieldtype: string;
	options?: string;
	reqd: boolean;
	default?: string;
}

const props = defineProps<{
	show?: boolean;
	initialName?: string;
}>();

watch(
	() => props.show,
	(newVal) => {
		if (newVal) {
			customerName.value = props.initialName || "";
			mobileNo.value = "";
			emailId.value = "";
			gstin.value = "";
			gstCategory.value = "";
			currentStepIndex.value = 0;
			error.value = "";
		}
	},
);

const emit = defineEmits<{
	close: [];
	created: [];
}>();

const customerStore = useCustomerStore();
const sessionStore = usePosSessionStore();

// Form state
const customerName = ref(props.initialName || "");
const mobileNo = ref("");
const emailId = ref("");
const customerType = ref("Individual");
const customerGroup = ref("");
const extraFields = ref<Record<string, string>>({});

// Referral capture
const referredBy = ref("");
const referredByName = ref("");
const referrerSearch = ref("");
const gstin = ref("");
const gstCategory = ref("");
const referrerResults = ref<{ name: string; customer_name: string }[]>([]);
let referrerTimer: ReturnType<typeof setTimeout>;

function onReferrerSearch() {
	clearTimeout(referrerTimer);
	referredBy.value = "";
	referredByName.value = "";
	const term = referrerSearch.value.trim();
	if (term.length < 2) { referrerResults.value = []; return; }
	referrerTimer = setTimeout(async () => {
		try {
			referrerResults.value = await call("pos_prime.api.customers.search_customers", { search_term: term }) || [];
		} catch { referrerResults.value = []; }
	}, 300);
}

function pickReferrer(r: { name: string; customer_name: string }) {
	referredBy.value = r.name;
	referredByName.value = r.customer_name;
	referrerSearch.value = r.customer_name;
	referrerResults.value = [];
}

const loading = ref(false);
const loadingOptions = ref(true);
const error = ref("");

// Step management
const currentStepIndex = ref(0);
const steps = computed(() => {
	const baseSteps = [
		{ id: "basic", title: "Basic Info", subtitle: "Name, Type & Group" },
		{ id: "contact", title: "Contact", subtitle: "Mobile & Email" },
	];
	if (quickFields.value.length > 0) {
		baseSteps.push({
			id: "extra",
			title: "Additional Details",
			subtitle: "Extra Information",
		});
	}
	return baseSteps;
});

// Options from backend
const customerTypes = ref<string[]>(["Individual", "Company"]);
const customerGroups = ref<string[]>([]);
const quickFields = ref<QuickField[]>([]);

onMounted(async () => {
	try {
		const data = await call("pos_prime.api.customers.get_quick_entry_options", {
			pos_profile: sessionStore.posProfile || "",
		});
		customerTypes.value = data.customer_types || ["Individual"];
		customerGroups.value = data.customer_groups || [];
		customerType.value = data.default_customer_type || "Individual";
		customerGroup.value = data.default_customer_group || "";

		// Filter out fields we handle explicitly
		const handled = new Set(["customer_name", "customer_type", "customer_group", "territory"]);
		quickFields.value = (data.quick_fields || []).filter(
			(f: QuickField) => !handled.has(f.fieldname),
		);
		// Set defaults for extra fields
		for (const f of quickFields.value) {
			if (f.default) extraFields.value[f.fieldname] = f.default;
		}
	} catch {
		// Use sensible defaults if API fails
	} finally {
		loadingOptions.value = false;
	}
});

function validateStep() {
	error.value = "";
	const stepId = steps.value[currentStepIndex.value].id;

	if (stepId === "basic") {
		if (!customerName.value.trim()) {
			error.value = __("Customer name is required");
			return false;
		}
		if (customerName.value.trim().length > 140) {
			error.value = __("Customer name must be 140 characters or less");
			return false;
		}
	} else if (stepId === "contact") {
		if (emailId.value.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(emailId.value.trim())) {
			error.value = __("Please enter a valid email address");
			return false;
		}
		if (mobileNo.value.trim() && !/^[0-9+\-() ]+$/.test(mobileNo.value.trim())) {
			error.value = __("Please enter a valid phone number");
			return false;
		}
	} else if (stepId === "extra") {
		for (const f of quickFields.value) {
			if (f.reqd && !extraFields.value[f.fieldname]?.trim()) {
				error.value = __("{0} is required", [__(f.label)]);
				return false;
			}
		}
	}

	return true;
}

function onGstinInput() {
	// A GSTIN means the customer is GST-registered; default the category so the
	// backend applies B2B / inter-state (IGST) logic. Cleared GSTIN resets it.
	gstin.value = gstin.value.toUpperCase();
	if (gstin.value.trim() && !gstCategory.value) {
		gstCategory.value = "Registered Regular";
	} else if (!gstin.value.trim()) {
		gstCategory.value = "";
	}
}

function handleNext() {
	if (validateStep()) {
		currentStepIndex.value++;
	}
}

function handleBack() {
	error.value = "";
	currentStepIndex.value--;
}

async function handleCreate() {
	if (!validateStep()) return;

	loading.value = true;
	error.value = "";
	try {
		await customerStore.quickCreateCustomer({
			customer_name: customerName.value.trim(),
			mobile_no: mobileNo.value.trim() || undefined,
			email_id: emailId.value.trim() || undefined,
			customer_type: customerType.value || undefined,
			customer_group: customerGroup.value || undefined,
			pos_profile: sessionStore.posProfile || undefined,
			...extraFields.value,
			custom_referred_by: referredBy.value || undefined,
				gstin: gstin.value.trim().toUpperCase() || undefined,
				gst_category: gstCategory.value || undefined,
		});
		emit("created");
	} catch (e: any) {
		error.value = e.messages?.[0] || e.message || __("Failed to create customer");
	} finally {
		loading.value = false;
	}
}
</script>

<template>
	<MultiStepDialog
		:show="show"
		title="New Customer"
		:steps="steps"
		:current-step-index="currentStepIndex"
		:loading="loading || loadingOptions"
		:error="error"
		@close="emit('close')"
		@next="handleNext"
		@back="handleBack"
		@submit="handleCreate"
	>
		<template #icon>
			<User :size="20" />
		</template>

		<!-- Step 1: Basic Info -->
		<template #basic>
			<div class="space-y-6">
				<div>
					<h3 class="text-2xl font-bold text-gray-900 dark:text-white mb-2">
						Basic Information
					</h3>
					<p class="text-sm text-gray-500 dark:text-gray-400">
						Let's start with the essential details of the new customer.
					</p>
				</div>

				<div class="space-y-5">
					<!-- Customer Name -->
					<div>
						<label
							class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2"
							>{{ __("Customer Name") }} <span class="text-red-500">*</span></label
						>
						<Input
							v-model="customerName"
							type="text"
							autofocus
							class="w-full rounded-xl border border-solid border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800/50 text-gray-900 dark:text-gray-100 px-4 py-3 text-base focus:outline-none focus:ring-0 focus:border-gray-300 dark:focus:border-gray-600 transition-all placeholder-gray-400 dark:placeholder-gray-500 outline-none"
							:placeholder="__('Enter full name')"
							@keydown.enter="handleNext"
						/>
					</div>

					<!-- Customer Type -->
					<div>
						<label
							class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2"
							>{{ __("Customer Type") }} <span class="text-red-500">*</span></label
						>
						<select
							v-model="customerType"
							data-slot="select"
							class="w-full text-gray-900 dark:text-gray-100 text-base transition-all appearance-none"
						>
							<option v-for="t in customerTypes" :key="t" :value="t">
								{{ __(t) }}
							</option>
						</select>
					</div>

					<!-- Customer Group -->
					<div>
						<label
							class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2"
							>{{ __("Customer Group") }} <span class="text-red-500">*</span></label
						>
						<select
							v-model="customerGroup"
							data-slot="select"
							class="w-full text-gray-900 dark:text-gray-100 text-base transition-all appearance-none"
						>
							<option v-for="g in customerGroups" :key="g" :value="g">
								{{ g }}
							</option>
						</select>
					</div>
				</div>
			</div>
		</template>

		<!-- Step 2: Contact -->
		<template #contact>
			<div class="space-y-6">
				<div>
					<h3 class="text-2xl font-bold text-gray-900 dark:text-white mb-2">
						Contact Details
					</h3>
					<p class="text-sm text-gray-500 dark:text-gray-400">
						How can we reach this customer?
					</p>
				</div>

				<div class="space-y-5">
					<!-- Mobile -->
					<div>
						<label
							class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2"
							>{{ __("Mobile Number") }}</label
						>
						<Input
							v-model="mobileNo"
							type="tel"
							autofocus
							class="w-full rounded-xl border border-solid border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800/50 text-gray-900 dark:text-gray-100 px-4 py-3 text-base focus:outline-none focus:ring-0 focus:border-gray-300 dark:focus:border-gray-600 transition-all placeholder-gray-400 dark:placeholder-gray-500 outline-none"
							:placeholder="__('+1 (555) 000-0000')"
							@keydown.enter="handleNext"
						/>
					</div>

					<!-- Email -->
					<div>
						<label
							class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2"
							>{{ __("Email Address") }}</label
						>
						<Input
							v-model="emailId"
							type="email"
							class="w-full rounded-xl border border-solid border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800/50 text-gray-900 dark:text-gray-100 px-4 py-3 text-base focus:outline-none focus:ring-0 focus:border-gray-300 dark:focus:border-gray-600 transition-all placeholder-gray-400 dark:placeholder-gray-500 outline-none"
							:placeholder="__('customer@example.com')"
							@keydown.enter="handleNext"
						/>
					</div>

					<!-- GSTIN (optional) -->
					<div>
							<label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">{{ __("GSTIN") }} <span class="text-gray-400 font-normal">({{ __("optional") }})</span></label>
							<Input
								v-model="gstin"
								type="text"
								maxlength="15"
								class="w-full rounded-xl border border-solid border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800/50 text-gray-900 dark:text-gray-100 px-4 py-3 text-base uppercase focus:outline-none focus:ring-0 focus:border-gray-300 dark:focus:border-gray-600 transition-all placeholder-gray-400 dark:placeholder-gray-500 outline-none"
								:placeholder="__('e.g. 24AADFA2635A1ZA')"
								@input="onGstinInput"
							/>
							<p v-if="gstin" class="mt-1.5 text-xs text-gray-500 dark:text-gray-400">{{ __("Registered customer — used for B2B GST and inter-state IGST.") }}</p>
						</div>

					<!-- Referred by (optional) -->
					<div class="relative">
						<label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">{{ __("Referred By") }} <span class="text-gray-400 font-normal">({{ __("optional") }})</span></label>
						<Input
							v-model="referrerSearch"
							type="text"
							@input="onReferrerSearch"
							class="w-full rounded-xl border border-solid border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800/50 text-gray-900 dark:text-gray-100 px-4 py-3 text-base focus:outline-none focus:ring-0 focus:border-gray-300 dark:focus:border-gray-600 transition-all placeholder-gray-400 dark:placeholder-gray-500 outline-none"
							:placeholder="__('Search the customer who referred them…')"
						/>
						<div v-if="referrerResults.length" class="absolute z-20 mt-1 w-full max-h-44 overflow-y-auto rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-lg">
							<button v-for="r in referrerResults" :key="r.name" type="button" @click="pickReferrer(r)" class="block w-full text-left px-4 py-2.5 text-sm hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-900 dark:text-gray-100">
								{{ r.customer_name }}
							</button>
						</div>
						<p v-if="referredBy" class="mt-1.5 text-xs text-emerald-600 dark:text-emerald-400">{{ __("They'll earn ₹50 credit after this customer's first service.") }}</p>
					</div>
				</div>
			</div>
		</template>

		<!-- Step 3: Extra Info -->
		<template #extra>
			<div class="space-y-6">
				<div>
					<h3 class="text-2xl font-bold text-gray-900 dark:text-white mb-2">
						Additional Information
					</h3>
					<p class="text-sm text-gray-500 dark:text-gray-400">
						Please provide any extra details required.
					</p>
				</div>

				<div class="space-y-5">
					<div v-for="field in quickFields" :key="field.fieldname">
						<label
							class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2"
						>
							{{ __(field.label)
							}}<span v-if="field.reqd" class="text-red-500 ml-1">*</span>
						</label>

						<select
							v-if="field.fieldtype === 'Select' && field.options"
							v-model="extraFields[field.fieldname]"
							data-slot="select"
							class="w-full text-gray-900 dark:text-gray-100 text-base transition-all appearance-none"
						>
							<option value="">{{ __("Select...") }}</option>
							<option
								v-for="opt in field.options.split('\n')"
								:key="opt"
								:value="opt"
							>
								{{ __(opt) }}
							</option>
						</select>

						<Input
							v-else
							v-model="extraFields[field.fieldname]"
							:type="field.fieldtype === 'Int' ? 'number' : 'text'"
							class="w-full rounded-xl border border-solid border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800/50 text-gray-900 dark:text-gray-100 px-4 py-3 text-base focus:outline-none focus:ring-0 focus:border-gray-300 dark:focus:border-gray-600 transition-all placeholder-gray-400 dark:placeholder-gray-500 outline-none"
							:placeholder="__(field.label)"
							@keydown.enter="handleCreate"
						/>
					</div>
				</div>
			</div>
		</template>
	</MultiStepDialog>
</template>
