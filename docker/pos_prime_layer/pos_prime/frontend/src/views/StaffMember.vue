<!-- Copyright (c) 2026, Ravindu Gajanayaka -->
<!-- Licensed under GPLv3. See license.txt -->

<script setup lang="ts">
import { useRoute, useRouter } from "vue-router";
import { ArrowLeft, Plus, Pencil, X, Wallet, CalendarCheck, Receipt } from "lucide-vue-next";
import { useStaffStore } from "@/stores/staff";
import Button from "@/components/ui/button/Button.vue";
import DeleteConfirmDialog from "@/components/ui/DeleteConfirmDialog.vue";

const props = defineProps<{ employeeId?: string }>();
const route = useRoute();
const router = useRouter();
const store = useStaffStore();

const employee = computed(() => String(props.employeeId || route.params.id || store.current?.name || ""));

const money = (v: number) =>
	new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(
		v || 0,
	);

// ----- edit salary/profile -----
const showEdit = ref(false);
const editForm = ref({ employee_name: "", mobile: "", designation: "", monthly_salary: 0, status: "Active" });

function openEdit() {
	const m = store.current;
	if (!m) return;
	editForm.value = {
		employee_name: m.employee_name,
		mobile: m.cell_number || "",
		designation: m.designation || "",
		monthly_salary: m.monthly_salary,
		status: m.status,
	};
	showEdit.value = true;
}
async function saveEdit() {
	await store.updateStaff(employee.value, {
		employee_name: editForm.value.employee_name,
		mobile: editForm.value.mobile,
		designation: editForm.value.designation,
		monthly_salary: Number(editForm.value.monthly_salary) || 0,
		status: editForm.value.status,
	});
	showEdit.value = false;
}

// ----- add advance -----
const showAdv = ref(false);
const advForm = ref({ amount: 0, date: new Date().toISOString().slice(0, 10), notes: "" });
const advError = ref("");
function openAdv() {
	advForm.value = { amount: 0, date: new Date().toISOString().slice(0, 10), notes: "" };
	advError.value = "";
	showAdv.value = true;
}
async function submitAdv() {
	if (Number(advForm.value.amount) <= 0) {
		advError.value = __("Enter an amount");
		return;
	}
	try {
		await store.addAdvance(employee.value, Number(advForm.value.amount), advForm.value.date, advForm.value.notes);
		showAdv.value = false;
	} catch (e: any) {
		advError.value = e?.messages?.[0] || e?.message || __("Could not add advance");
	}
}
const cancellingAdvance = ref<string | null>(null);

function requestCancelAdvance(name: string) {
	cancellingAdvance.value = name;
}

async function confirmCancelAdvance() {
	if (!cancellingAdvance.value) return;
	try {
		await store.cancelAdvance(cancellingAdvance.value, employee.value);
		cancellingAdvance.value = null;
	} catch (e: any) {
		alert(e?.messages?.[0] || e?.message || __("Could not cancel"));
	}
}

const advanceBadge: Record<string, string> = {
	Outstanding: "bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
	"Partially Adjusted": "bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
	Adjusted: "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
	Cancelled: "bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400",
};
const payslipBadge: Record<string, string> = {
	Draft: "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300",
	Paid: "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
	Cancelled: "bg-gray-100 text-gray-400 dark:bg-gray-700 dark:text-gray-500",
};
const attBadge: Record<string, string> = {
	Present: "bg-emerald-500",
	Absent: "bg-red-500",
	"Half Day": "bg-amber-500",
	Leave: "bg-blue-500",
	Holiday: "bg-gray-400",
};

import { watch, onMounted, computed, ref } from "vue";

async function loadData(emp: string) {
	if (!emp) return;
	await store.loadMember(emp);
	const to = new Date();
	const from = new Date();
	from.setDate(from.getDate() - 45);
	await store.loadMemberAttendance(
		emp,
		from.toISOString().slice(0, 10),
		to.toISOString().slice(0, 10),
	);
}

watch(employee, (newEmp) => {
	if (newEmp) loadData(newEmp);
}, { immediate: true });
</script>

<template>
	<div class="h-full overflow-y-auto bg-gray-50 dark:bg-gray-900">
		<div class="max-w-3xl mx-auto p-4 lg:p-6 space-y-5">

			<div v-if="store.detailLoading && !store.current" class="text-center py-16 text-gray-400 text-sm">
				{{ __("Loading…") }}
			</div>

			<template v-else-if="store.current">
				<!-- Profile / salary card -->
				<div class="bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 p-5 mb-4">
					<div class="flex items-start justify-between">
						<div>
							<h1 class="text-xl font-bold text-gray-900 dark:text-gray-100">{{ store.current.employee_name }}</h1>
							<p class="text-sm text-gray-500 dark:text-gray-400">
								{{ store.current.designation || __("—") }}
								<span v-if="store.current.cell_number"> · {{ store.current.cell_number }}</span>
							</p>
						</div>
						<button
							@click="openEdit"
							class="flex items-center gap-1.5 text-sm font-semibold text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-1.5 hover:bg-gray-50 dark:hover:bg-gray-700"
						>
							<Pencil :size="14" /> {{ __("Edit") }}
						</button>
					</div>
					<div class="grid grid-cols-2 gap-3 mt-4">
						<div class="rounded-xl bg-gray-50 dark:bg-gray-900 p-3">
							<div class="text-xs font-semibold text-gray-500">{{ __("Monthly Salary") }}</div>
							<div class="text-lg font-bold text-gray-900 dark:text-gray-100">{{ money(store.current.monthly_salary) }}</div>
						</div>
						<div class="rounded-xl bg-gray-50 dark:bg-gray-900 p-3">
							<div class="text-xs font-semibold text-gray-500">{{ __("Outstanding Advance") }}</div>
							<div class="text-lg font-bold text-amber-600 dark:text-amber-400">{{ money(store.current.outstanding_advance) }}</div>
						</div>
					</div>
				</div>

				<!-- Advances -->
				<div class="bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 p-5 mb-4">
					<div class="flex items-center justify-between mb-3">
						<h2 class="flex items-center gap-2 font-bold text-gray-900 dark:text-gray-100">
							<Wallet :size="18" /> {{ __("Advances") }}
						</h2>
						<button
							@click="openAdv"
							class="flex items-center gap-1.5 text-sm font-semibold text-gray-900 dark:text-gray-100 border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-1.5 hover:bg-gray-50 dark:hover:bg-gray-700"
						>
							<Plus :size="14" /> {{ __("Add") }}
						</button>
					</div>
					<div v-if="!store.advances.length" class="text-sm text-gray-400 py-4 text-center">
						{{ __("No advances recorded") }}
					</div>
					<div v-else class="divide-y divide-gray-100 dark:divide-gray-700">
						<div v-for="a in store.advances" :key="a.name" class="flex items-center justify-between py-2.5">
							<div>
								<div class="text-sm font-semibold text-gray-900 dark:text-gray-100">{{ money(a.amount) }}</div>
								<div class="text-xs text-gray-500">
									{{ a.date }}<span v-if="a.notes"> · {{ a.notes }}</span>
								</div>
							</div>
							<div class="flex items-center gap-2">
								<span v-if="a.balance > 0 && a.status !== 'Cancelled'" class="text-xs text-gray-500">
									{{ money(a.balance) }} {{ __("left") }}
								</span>
								<span class="text-[10px] font-semibold px-2 py-0.5 rounded-full" :class="advanceBadge[a.status]">{{ a.status }}</span>
								<button
									v-if="a.balance >= a.amount && a.status === 'Outstanding'"
									@click="requestCancelAdvance(a.name)"
									class="text-gray-300 hover:text-red-500"
									:title="__('Cancel advance')"
								>
									<X :size="16" />
								</button>
							</div>
						</div>
					</div>
				</div>

				<!-- Payslips -->
				<div class="bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 p-5 mb-4">
					<h2 class="flex items-center gap-2 font-bold text-gray-900 dark:text-gray-100 mb-3">
						<Receipt :size="18" /> {{ __("Payslips") }}
					</h2>
					<div v-if="!store.payslips.length" class="text-sm text-gray-400 py-4 text-center">
						{{ __("No payslips yet — run payroll from the Payroll page") }}
					</div>
					<div v-else class="divide-y divide-gray-100 dark:divide-gray-700">
						<div v-for="p in store.payslips" :key="p.name" class="flex items-center justify-between py-2.5">
							<div>
								<div class="text-sm font-semibold text-gray-900 dark:text-gray-100">{{ p.period_label || p.start_date }}</div>
								<div class="text-xs text-gray-500">
									{{ __("Base") }} {{ money(p.base_salary) }} · −{{ money(p.total_advance_deducted) }}
									<span v-if="p.adjustment"> · {{ p.adjustment > 0 ? "+" : "" }}{{ money(p.adjustment) }}</span>
								</div>
							</div>
							<div class="text-right">
								<div class="text-sm font-bold text-gray-900 dark:text-gray-100">{{ money(p.net_pay) }}</div>
								<span class="text-[10px] font-semibold px-2 py-0.5 rounded-full" :class="payslipBadge[p.status]">{{ p.status }}</span>
							</div>
						</div>
					</div>
				</div>

				<!-- Attendance -->
				<div class="bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 p-5">
					<h2 class="flex items-center gap-2 font-bold text-gray-900 dark:text-gray-100 mb-3">
						<CalendarCheck :size="18" /> {{ __("Recent Attendance") }}
					</h2>
					<div v-if="!store.attendance.length" class="text-sm text-gray-400 py-4 text-center">
						{{ __("No attendance recorded") }}
					</div>
					<div v-else class="flex flex-wrap gap-1.5">
						<div
							v-for="d in store.attendance"
							:key="d.name"
							class="flex items-center gap-1.5 text-xs bg-gray-50 dark:bg-gray-900 rounded-lg px-2 py-1"
							:title="d.status"
						>
							<span class="w-2 h-2 rounded-full" :class="attBadge[d.status]" />
							{{ d.attendance_date?.slice(5) }}
						</div>
					</div>
				</div>
			</template>
		</div>

		<!-- Edit dialog -->
		<Teleport to="body">
			<div v-if="showEdit" class="fixed inset-0 z-50 flex items-center justify-center p-4">
				<div class="absolute inset-0 bg-black/40 backdrop-blur-sm" @click="showEdit = false" />
				<div class="relative w-full max-w-md bg-white dark:bg-gray-800 rounded-2xl shadow-xl border border-solid border-gray-100 dark:border-gray-700 p-5">
					<div class="flex items-center justify-between mb-4">
						<h2 class="text-lg font-bold text-gray-900 dark:text-gray-100">{{ __("Edit Employee") }}</h2>
						<button @click="showEdit = false" class="text-gray-400 hover:text-gray-600"><X :size="20" /></button>
					</div>
					<div class="space-y-3">
						<div>
							<label class="block text-xs font-semibold text-gray-500 mb-1">{{ __("Full Name") }}</label>
							<input v-model="editForm.employee_name" type="text" data-slot="input" class="w-full text-sm transition-all" />
						</div>
						<div class="grid grid-cols-2 gap-3">
							<div>
								<label class="block text-xs font-semibold text-gray-500 mb-1">{{ __("Mobile") }}</label>
								<input v-model="editForm.mobile" type="tel" data-slot="input" class="w-full text-sm transition-all" />
							</div>
							<div>
								<label class="block text-xs font-semibold text-gray-500 mb-1">{{ __("Designation") }}</label>
								<input v-model="editForm.designation" type="text" data-slot="input" class="w-full text-sm transition-all" />
							</div>
						</div>
						<div class="grid grid-cols-2 gap-3">
							<div>
								<label class="block text-xs font-semibold text-gray-500 mb-1">{{ __("Monthly Salary (₹)") }}</label>
								<input v-model.number="editForm.monthly_salary" type="number" min="0" data-slot="input" class="w-full text-sm transition-all" />
							</div>
							<div>
								<label class="block text-xs font-semibold text-gray-500 mb-1">{{ __("Status") }}</label>
								<select v-model="editForm.status" data-slot="select" class="w-full text-sm transition-all appearance-none">
									<option>Active</option>
									<option>Inactive</option>
									<option>Left</option>
									<option>Suspended</option>
								</select>
							</div>
						</div>
					</div>
					<div class="flex gap-2 mt-5">
						<Button variant="outline" @click="showEdit = false" class="flex-1">{{ __("Cancel") }}</Button>
						<Button @click="saveEdit" :disabled="store.saving" class="flex-1">{{ store.saving ? __("Saving...") : __("Save") }}</Button>
					</div>
				</div>
			</div>
		</Teleport>

		<!-- Add advance dialog -->
		<Teleport to="body">
			<div v-if="showAdv" class="fixed inset-0 z-50 flex items-center justify-center p-4">
				<div class="absolute inset-0 bg-black/40 backdrop-blur-sm" @click="showAdv = false" />
				<div class="relative w-full max-w-sm bg-white dark:bg-gray-800 rounded-2xl shadow-xl border border-solid border-gray-100 dark:border-gray-700 p-5">
					<div class="flex items-center justify-between mb-4">
						<h2 class="text-lg font-bold text-gray-900 dark:text-gray-100">{{ __("Add Advance") }}</h2>
						<button @click="showAdv = false" class="text-gray-400 hover:text-gray-600"><X :size="20" /></button>
					</div>
					<div class="space-y-3">
						<div>
							<label class="block text-xs font-semibold text-gray-500 mb-1">{{ __("Amount (₹)") }} *</label>
							<input v-model.number="advForm.amount" type="number" min="0" data-slot="input" class="w-full text-sm transition-all" />
						</div>
						<div>
							<label class="block text-xs font-semibold text-gray-500 mb-1">{{ __("Date") }}</label>
							<input v-model="advForm.date" type="date" data-slot="input" class="w-full text-sm transition-all" />
						</div>
						<div>
							<label class="block text-xs font-semibold text-gray-500 mb-1">{{ __("Notes") }}</label>
							<input v-model="advForm.notes" type="text" data-slot="input" class="w-full text-sm transition-all" />
						</div>
						<p v-if="advError" class="text-sm text-red-600 dark:text-red-400">{{ advError }}</p>
					</div>
					<div class="flex gap-2 mt-5">
						<Button variant="outline" @click="showAdv = false" class="flex-1">{{ __("Cancel") }}</Button>
						<Button @click="submitAdv" class="flex-1">{{ __("Add Advance") }}</Button>
					</div>
				</div>
			</div>
		</Teleport>

		<DeleteConfirmDialog
			:show="!!cancellingAdvance"
			@update:show="cancellingAdvance = null"
			:title="__('Cancel Advance?')"
			:message="__('This action cannot be undone.')"
			:confirm-text="__('Cancel Advance')"
			@confirm="confirmCancelAdvance"
			@cancel="cancellingAdvance = null"
		/>
	</div>
</template>
