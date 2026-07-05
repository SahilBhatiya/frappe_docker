<!-- Copyright (c) 2026, Ravindu Gajanayaka -->
<!-- Licensed under GPLv3. See license.txt -->

<script setup lang="ts">
import Button from "@/components/ui/button/Button.vue";
import Input from "@/components/ui/input/Input.vue";
import {
	Dialog,
	DialogContent,
	DialogHeader,
	DialogTitle,
	DialogFooter,
} from "@/components/ui/dialog";
import { useStaffStore } from "@/stores/staff";
import { ArrowLeft, Plus, Search, UserPlus, Users, Wallet, X } from "lucide-vue-next";
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import StaffMember from "./StaffMember.vue";

const router = useRouter();
const route = useRoute();
const store = useStaffStore();

const mobileShowDetail = ref(false);

const money = (v: number) =>
	new Intl.NumberFormat("en-IN", {
		style: "currency",
		currency: "INR",
		maximumFractionDigits: 0,
	}).format(v || 0);

const showAdd = ref(false);
const form = ref({ employee_name: "", mobile: "", designation: "", monthly_salary: 0 });
const addError = ref("");

const filtered = computed(() => store.staff);

function initials(name: string) {
	const parts = (name || "?").trim().split(/\s+/);
	return (
		(parts[0]?.[0] || "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")
	).toUpperCase();
}

let debounceTimer: ReturnType<typeof setTimeout>;

async function onSearch() {
	clearTimeout(debounceTimer);
	debounceTimer = setTimeout(() => {
		store.loadStaff();
	}, 300);
}

function clearSearch() {
	store.searchTerm = "";
	store.loadStaff();
}

function openAdd() {
	form.value = { employee_name: "", mobile: "", designation: "", monthly_salary: 0 };
	addError.value = "";
	showAdd.value = true;
}

async function submitAdd() {
	if (!form.value.employee_name.trim()) {
		addError.value = __("Name is required");
		return;
	}
	try {
		await store.createStaff({
			employee_name: form.value.employee_name.trim(),
			monthly_salary: Number(form.value.monthly_salary) || 0,
			mobile: form.value.mobile.trim() || undefined,
			designation: form.value.designation.trim() || undefined,
		});
		showAdd.value = false;
	} catch (e: any) {
		addError.value = e?.messages?.[0] || e?.message || __("Could not add employee");
	}
}

async function selectMember(employee: string) {
	// Either we push route or just update state. Using state to match Customer display on desktop.
	if (route.params.id) {
		router.push({ name: "StaffMember", params: { id: employee } });
	} else {
		await store.loadMember(employee);
		mobileShowDetail.value = true;
	}
}

onMounted(() => {
	store.loadStaff();
	if (route.params.id) {
		store.loadMember(route.params.id as string);
		mobileShowDetail.value = true;
	}
});

watch(
	() => route.params.id,
	(newId) => {
		if (newId) {
			store.loadMember(newId as string);
			mobileShowDetail.value = true;
		} else {
			mobileShowDetail.value = false;
		}
	},
);
</script>

<template>
	<div class="h-full">
		<div class="h-full flex flex-col">
			<!-- Header -->
			<div class="px-4 py-3 flex items-center gap-3">
				<button
					@click="
						mobileShowDetail
							? route.params.id
								? router.push({ name: 'Staff' })
								: (mobileShowDetail = false)
							: router.push({ name: 'POS' })
					"
					class="lg:hidden text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200"
				>
					<ArrowLeft :size="20" />
				</button>
				<h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100 flex-1">
					{{ __("Staff") }}
				</h2>
				<Button
					@click="openAdd"
					class="flex items-center gap-2 shrink-0"
				>
					<Plus :size="16" />
					<span class="hidden sm:inline">{{ __("Add Employee") }}</span>
				</Button>
			</div>

			<div class="flex-1 flex overflow-hidden">
				<!-- Left Pane -->
				<div
					class="w-full lg:w-[360px] shrink-0 flex flex-col rounded-2xl bg-white dark:bg-gray-900"
					:class="{ 'hidden lg:flex': mobileShowDetail }"
				>
					<!-- Search -->
					<div class="p-3">
						<div class="relative">
							<Search
								class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500 pointer-events-none"
								:size="14"
							/>
							<Input
								v-model="store.searchTerm"
								@input="onSearch"
								type="text"
								:placeholder="__('Search by name or mobile')"
								class="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 pl-8 pr-8 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-gray-950 dark:focus:ring-gray-300 placeholder-gray-400 dark:placeholder-gray-500"
							/>
							<button
								v-if="store.searchTerm"
								@click="clearSearch"
								class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300"
							>
								<X :size="14" />
							</button>
						</div>
					</div>

					<!-- List -->
					<div class="flex-1 overflow-y-auto p-3 pt-0">
						<!-- Loading -->
						<div v-if="store.loading" class="text-center py-12 text-gray-400 text-sm">
							{{ __("Loading…") }}
						</div>
						<!-- Empty -->
						<div
							v-else-if="!filtered.length && !store.searchTerm"
							class="text-center py-12 bg-white dark:bg-gray-800 rounded-2xl border border-dashed border-gray-200 dark:border-gray-700"
						>
							<UserPlus
								:size="32"
								class="mx-auto text-gray-300 dark:text-gray-600"
							/>
							<p class="mt-3 text-sm text-gray-500 dark:text-gray-400">
								{{ __("No employees yet") }}
							</p>
							<button
								@click="openAdd"
								class="mt-3 text-sm font-semibold text-gray-900 dark:text-gray-100 underline"
							>
								{{ __("Add your first employee") }}
							</button>
						</div>
						<div
							v-else-if="!filtered.length && store.searchTerm"
							class="flex flex-col items-center justify-center py-12 text-gray-400 dark:text-gray-500"
						>
							<Users :size="32" class="mb-3" />
							<p class="text-sm">{{ __("No employees found") }}</p>
						</div>
						<!-- List -->
						<div v-else class="space-y-2">
							<button
								v-for="s in filtered"
								:key="s.name"
								@click="selectMember(s.name)"
								class="w-full flex items-center gap-3 rounded-lg border px-3 py-3 text-left transition-all duration-150"
								:class="
									store.current?.name === s.name || route.params.id === s.name
										? 'border-primary bg-primary text-primary-foreground'
										: 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800 bg-white dark:bg-gray-800'
								"
							>
								<div
									class="w-9 h-9 rounded-full flex items-center justify-center shrink-0"
									:class="
										store.current?.name === s.name ||
										route.params.id === s.name
											? 'bg-primary-foreground/20'
											: 'bg-gray-200 dark:bg-gray-700'
									"
								>
									<span
										class="text-xs font-bold"
										:class="
											store.current?.name === s.name ||
											route.params.id === s.name
												? 'text-primary-foreground'
												: 'text-gray-700 dark:text-gray-200'
										"
										>{{ initials(s.employee_name) }}</span
									>
								</div>
								<div class="min-w-0 flex-1">
									<div class="flex items-center gap-2">
										<span
											class="font-medium text-sm truncate"
											:class="
												store.current?.name === s.name ||
												route.params.id === s.name
													? 'text-primary-foreground'
													: 'text-gray-900 dark:text-gray-100'
											"
											>{{ s.employee_name }}</span
										>
										<span
											v-if="s.status !== 'Active'"
											class="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-500"
											>{{ s.status }}</span
										>
									</div>
									<div
										class="text-xs truncate mt-0.5"
										:class="
											store.current?.name === s.name ||
											route.params.id === s.name
												? 'text-primary-foreground/70'
												: 'text-gray-500 dark:text-gray-400'
										"
									>
										{{ s.designation || __("—")
										}}<span v-if="s.cell_number"> · {{ s.cell_number }}</span>
									</div>
								</div>
								<div class="text-right shrink-0">
									<div
										class="text-sm font-medium"
										:class="
											store.current?.name === s.name ||
											route.params.id === s.name
												? 'text-primary-foreground'
												: 'text-gray-900 dark:text-gray-100'
										"
									>
										{{ money(s.monthly_salary) }}
									</div>
									<div
										v-if="s.outstanding_advance > 0"
										class="text-[10px] font-medium text-amber-600 dark:text-amber-500 flex items-center gap-1 justify-end mt-0.5"
									>
										<Wallet :size="10" /> {{ money(s.outstanding_advance) }}
										{{ __("adv") }}
									</div>
								</div>
							</button>
						</div>
					</div>
				</div>

				<!-- Right Pane -->
				<div
					class="flex-1 overflow-y-auto"
					:class="{ 'hidden lg:block': !mobileShowDetail }"
				>
					<div
						v-if="!store.current && !route.params.id"
						class="flex flex-col items-center justify-center h-full"
					>
						<div
							class="w-20 h-20 rounded-full bg-gray-200 dark:bg-gray-800 flex items-center justify-center mb-5"
						>
							<Users :size="36" class="text-gray-400 dark:text-gray-500" />
						</div>
						<p class="text-lg font-semibold text-gray-600 dark:text-gray-300">
							{{ __("Select an employee") }}
						</p>
						<p class="text-sm mt-1.5 text-gray-400 dark:text-gray-500">
							{{ __("Search and select an employee to view details") }}
						</p>
					</div>
					<StaffMember
						v-else
						:employee-id="(route.params.id as string) || store.current?.name"
					/>
				</div>
			</div>
		</div>

		<!-- Add Employee dialog -->
		<Dialog :open="showAdd" @update:open="(v) => { if (!v) showAdd = false }">
			<DialogContent class="sm:max-w-md">
				<DialogHeader>
					<DialogTitle>{{ __("Add Employee") }}</DialogTitle>
				</DialogHeader>

				<div class="space-y-3">
					<div>
						<label class="block text-xs font-semibold text-gray-500 mb-1"
							>{{ __("Full Name") }} *</label
						>
						<input
							v-model="form.employee_name"
							type="text"
							data-slot="input"
							class="w-full text-sm transition-all"
							:placeholder="__('e.g. Ramesh Patel')"
						/>
					</div>
					<div class="grid grid-cols-2 gap-3">
						<div>
							<label class="block text-xs font-semibold text-gray-500 mb-1">{{
								__("Mobile")
							}}</label>
							<input
								v-model="form.mobile"
								type="tel"
								data-slot="input"
								class="w-full text-sm transition-all"
							/>
						</div>
						<div>
							<label class="block text-xs font-semibold text-gray-500 mb-1">{{
								__("Designation")
							}}</label>
							<input
								v-model="form.designation"
								type="text"
								data-slot="input"
								class="w-full text-sm transition-all"
								:placeholder="__('e.g. Mechanic')"
							/>
						</div>
					</div>
					<div>
						<label class="block text-xs font-semibold text-gray-500 mb-1">{{
							__("Monthly Salary (₹)")
						}}</label>
						<input
							v-model.number="form.monthly_salary"
							type="number"
							min="0"
							data-slot="input"
							class="w-full text-sm transition-all"
						/>
					</div>
					<p v-if="addError" class="text-sm text-red-600 dark:text-red-400">
						{{ addError }}
					</p>
				</div>

				<DialogFooter class="flex-row gap-2">
					<Button variant="outline" @click="showAdd = false" class="flex-1">
						{{ __("Cancel") }}
					</Button>
					<Button @click="submitAdd" :disabled="store.saving" class="flex-1">
						{{ store.saving ? __("Saving...") : __("Add") }}
					</Button>
				</DialogFooter>
			</DialogContent>
		</Dialog>
	</div>
</template>
