<!-- Copyright (c) 2026, Ravindu Gajanayaka -->
<!-- Licensed under GPLv3. See license.txt -->

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { BadgeIndianRupee, Wallet } from "lucide-vue-next";
import { usePayrollStore } from "@/stores/payroll";
import type { PayrollPreviewRow } from "@/types";
import Button from "@/components/ui/button/Button.vue";
import DeleteConfirmDialog from "@/components/ui/DeleteConfirmDialog.vue";

const store = usePayrollStore();

const money = (v: number) =>
	new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(
		v || 0,
	);

// ----- period selection (month) -----
const now = new Date();
const month = ref(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`);

const startDate = computed(() => `${month.value}-01`);
const endDate = computed(() => {
	const [y, m] = month.value.split("-").map(Number);
	return new Date(y, m, 0).toISOString().slice(0, 10); // day 0 of next month = last day
});
const periodLabel = computed(() => {
	const [y, m] = month.value.split("-").map(Number);
	return new Date(y, m - 1, 1).toLocaleString("en-IN", { month: "short", year: "numeric" });
});

async function reload() {
	await Promise.all([store.loadPreview(startDate.value, endDate.value), store.loadPayslips()]);
}

// ----- deduction editing (single total, distributed oldest-first) -----
function maxDeduction(emp: string): number {
	return (store.edits[emp]?.deductions || []).reduce((s, d) => s + (Number(d.max) || 0), 0);
}
function totalDeduction(emp: string): number {
	return (store.edits[emp]?.deductions || []).reduce((s, d) => s + (Number(d.amount) || 0), 0);
}
function setDeduction(emp: string, value: number) {
	const e = store.edits[emp];
	if (!e) return;
	let remaining = Math.max(0, Math.min(Number(value) || 0, maxDeduction(emp)));
	for (const d of e.deductions) {
		const take = Math.min(Number(d.max) || 0, remaining);
		d.amount = take;
		remaining -= take;
	}
}

async function payRow(row: PayrollPreviewRow, pay: boolean) {
	try {
		await store.generateAndPay(row, startDate.value, endDate.value, periodLabel.value, pay);
	} catch (e: any) {
		alert(e?.messages?.[0] || e?.message || __("Could not process payroll"));
	}
}

async function onMarkPaid(name: string) {
	try {
		await store.markPaid(name);
	} catch (e: any) {
		alert(e?.messages?.[0] || e?.message || __("Could not mark paid"));
	}
}
const cancellingPayslip = ref<string | null>(null);

function requestCancelPayslip(name: string) {
	cancellingPayslip.value = name;
}

async function confirmCancelPayslip() {
	if (!cancellingPayslip.value) return;
	try {
		await store.cancelPayslip(cancellingPayslip.value);
		cancellingPayslip.value = null;
		await reload();
	} catch (e: any) {
		alert(e?.messages?.[0] || e?.message || __("Could not cancel"));
	}
}

const totalNet = computed(() =>
	store.preview.reduce((s, r) => (r.existing_payslip?.status === "Paid" ? s : s + store.netFor(r)), 0),
);

const payslipBadge: Record<string, string> = {
	Draft: "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300",
	Paid: "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
	Cancelled: "bg-gray-100 text-gray-400 dark:bg-gray-700 dark:text-gray-500",
};

onMounted(reload);
</script>

<template>
	<div class="h-full overflow-y-auto bg-gray-50 dark:bg-gray-900">
		<div class="max-w-5xl mx-auto px-4 py-5">
			<!-- Header -->
			<div class="flex items-center justify-between gap-3 mb-4 flex-wrap">
				<div>
					<h1 class="flex items-center gap-2 text-xl font-bold text-gray-900 dark:text-gray-100">
						<BadgeIndianRupee :size="22" /> {{ __("Payroll") }}
					</h1>
					<p class="text-sm text-gray-500 dark:text-gray-400">{{ __("Run monthly salaries") }}</p>
				</div>
				<input
					type="month"
					v-model="month"
					@change="reload"
					class="px-3 py-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-sm"
				/>
			</div>

			<div v-if="store.loading" class="text-center py-16 text-gray-400 text-sm">{{ __("Loading…") }}</div>
			<div v-else-if="!store.preview.length" class="text-center py-16 text-gray-400 text-sm">
				{{ __("No active employees with a salary set") }}
			</div>

			<template v-else>
				<!-- Payroll table -->
				<div class="bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 overflow-hidden">
					<table class="w-full text-sm">
						<thead class="bg-gray-50 dark:bg-gray-900/50 text-gray-500 text-xs uppercase">
							<tr>
								<th class="text-left font-semibold px-4 py-2.5">{{ __("Employee") }}</th>
								<th class="text-right font-semibold px-3 py-2.5">{{ __("Salary") }}</th>
								<th class="text-right font-semibold px-3 py-2.5">{{ __("Deduct Advance") }}</th>
								<th class="text-right font-semibold px-3 py-2.5">{{ __("Adjust") }}</th>
								<th class="text-right font-semibold px-3 py-2.5">{{ __("Net") }}</th>
								<th class="px-3 py-2.5"></th>
							</tr>
						</thead>
						<tbody class="divide-y divide-gray-100 dark:divide-gray-700">
							<tr v-for="r in store.preview" :key="r.employee">
								<td class="px-4 py-3">
									<div class="font-semibold text-gray-900 dark:text-gray-100">{{ r.employee_name }}</div>
									<div v-if="maxDeduction(r.employee) > 0" class="text-[11px] text-amber-600 dark:text-amber-400 flex items-center gap-1">
										<Wallet :size="11" /> {{ money(maxDeduction(r.employee)) }} {{ __("outstanding") }}
									</div>
								</td>
								<td class="px-3 py-3 text-right text-gray-700 dark:text-gray-300">{{ money(r.base_salary) }}</td>
								<td class="px-3 py-3 text-right">
									<input
										v-if="maxDeduction(r.employee) > 0"
										type="number"
										min="0"
										:max="maxDeduction(r.employee)"
										:value="totalDeduction(r.employee)"
										@input="setDeduction(r.employee, Number(($event.target as HTMLInputElement).value))"
										:disabled="r.existing_payslip?.status === 'Paid'"
										class="w-24 px-2 py-1.5 text-right rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-sm disabled:opacity-50"
									/>
									<span v-else class="text-gray-300">—</span>
								</td>
								<td class="px-3 py-3 text-right">
									<input
										v-if="store.edits[r.employee]"
										type="number"
										v-model.number="store.edits[r.employee].adjustment"
										:disabled="r.existing_payslip?.status === 'Paid'"
										class="w-20 px-2 py-1.5 text-right rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-sm disabled:opacity-50"
										placeholder="0"
									/>
								</td>
								<td class="px-3 py-3 text-right font-bold text-gray-900 dark:text-gray-100">
									{{ money(r.existing_payslip?.status === "Paid" ? r.existing_payslip.net_pay : store.netFor(r)) }}
								</td>
								<td class="px-3 py-3 text-right whitespace-nowrap">
									<span
										v-if="r.existing_payslip?.status === 'Paid'"
										class="text-[10px] font-semibold px-2 py-1 rounded-full bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
										>{{ __("Paid") }}</span
									>
									<Button
										v-else
										@click="payRow(r, true)"
										:disabled="store.running"
									>
										{{ __("Pay") }}
									</Button>
								</td>
							</tr>
						</tbody>
						<tfoot class="bg-gray-50 dark:bg-gray-900/50">
							<tr>
								<td colspan="4" class="px-4 py-3 text-right text-sm font-semibold text-gray-500">
									{{ __("Total unpaid net") }}
								</td>
								<td class="px-3 py-3 text-right font-extrabold text-gray-900 dark:text-gray-100">{{ money(totalNet) }}</td>
								<td></td>
							</tr>
						</tfoot>
					</table>
				</div>

				<!-- Payslips this period -->
				<div v-if="store.payslips.length" class="mt-5">
					<h2 class="text-sm font-bold text-gray-700 dark:text-gray-300 mb-2">{{ __("Recent Payslips") }}</h2>
					<div class="bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 divide-y divide-gray-100 dark:divide-gray-700">
						<div v-for="p in store.payslips" :key="p.name" class="flex items-center justify-between px-4 py-2.5">
							<div>
								<div class="text-sm font-semibold text-gray-900 dark:text-gray-100">
									{{ p.employee_name }} <span class="text-gray-400 font-normal">· {{ p.period_label || p.start_date }}</span>
								</div>
								<div class="text-xs text-gray-500">
									{{ __("Net") }} {{ money(p.net_pay) }}<span v-if="p.paid_on"> · {{ __("paid") }} {{ p.paid_on }}</span>
								</div>
							</div>
							<div class="flex items-center gap-2">
								<span class="text-[10px] font-semibold px-2 py-0.5 rounded-full" :class="payslipBadge[p.status]">{{ p.status }}</span>
								<button v-if="p.status === 'Draft'" @click="onMarkPaid(p.name)" class="text-xs font-semibold text-emerald-700 dark:text-emerald-400">{{ __("Mark paid") }}</button>
								<button v-if="p.status !== 'Cancelled'" @click="requestCancelPayslip(p.name)" class="text-xs font-semibold text-gray-400 hover:text-red-500">{{ __("Cancel") }}</button>
							</div>
						</div>
					</div>
				</div>
			</template>
		</div>

		<DeleteConfirmDialog
			:show="!!cancellingPayslip"
			@update:show="cancellingPayslip = null"
			:title="__('Cancel Payslip?')"
			:message="__('This action cannot be undone. Any recovered advances will be restored.')"
			:confirm-text="__('Cancel Payslip')"
			@confirm="confirmCancelPayslip"
			@cancel="cancellingPayslip = null"
		/>
	</div>
</template>
