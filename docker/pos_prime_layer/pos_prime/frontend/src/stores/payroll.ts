// Copyright (c) 2026, Ravindu Gajanayaka
// Licensed under GPLv3. See license.txt

import { defineStore } from "pinia";
import { ref } from "vue";
import { call } from "frappe-ui";
import type { PayrollPreviewRow, StaffPayslip } from "@/types";

// A per-employee deduction the owner is editing in the payroll run
export interface DeductionEdit {
	advance: string;
	amount: number;
	max: number;
}

export const usePayrollStore = defineStore("payroll", () => {
	const preview = ref<PayrollPreviewRow[]>([]);
	const payslips = ref<StaffPayslip[]>([]);
	const loading = ref(false);
	const running = ref(false);

	// Owner edits, keyed by employee → { deductions, adjustment, adjustmentNote }
	const edits = ref<
		Record<
			string,
			{ deductions: DeductionEdit[]; adjustment: number; adjustmentNote: string }
		>
	>({});

	async function loadPreview(startDate: string, endDate: string) {
		loading.value = true;
		try {
			preview.value = await call("pos_prime.api.payroll.preview_payroll", {
				start_date: startDate,
				end_date: endDate,
			});
			// Seed editable deductions with the suggested full recovery.
			const next: typeof edits.value = {};
			for (const row of preview.value) {
				next[row.employee] = {
					deductions: row.advances.map((a) => ({
						advance: a.name,
						amount: a.balance,
						max: a.balance,
					})),
					adjustment: 0,
					adjustmentNote: "",
				};
			}
			edits.value = next;
		} catch {
			preview.value = [];
			edits.value = {};
		} finally {
			loading.value = false;
		}
	}

	async function loadPayslips(startDate?: string) {
		try {
			payslips.value = await call("pos_prime.api.payroll.list_payslips", {});
		} catch {
			payslips.value = [];
		}
	}

	function netFor(row: PayrollPreviewRow): number {
		const e = edits.value[row.employee];
		if (!e) return row.net_preview;
		const deducted = e.deductions.reduce((s, d) => s + (Number(d.amount) || 0), 0);
		return (Number(row.base_salary) || 0) - deducted + (Number(e.adjustment) || 0);
	}

	async function generateAndPay(
		row: PayrollPreviewRow,
		startDate: string,
		endDate: string,
		periodLabel: string,
		pay = true,
		paymentMode = "Cash",
	) {
		running.value = true;
		try {
			const e = edits.value[row.employee];
			const deductions = (e?.deductions || [])
				.filter((d) => (Number(d.amount) || 0) > 0)
				.map((d) => ({ advance: d.advance, amount: Number(d.amount) }));

			const slip: StaffPayslip = await call("pos_prime.api.payroll.create_payslip", {
				employee: row.employee,
				start_date: startDate,
				end_date: endDate,
				base_salary: row.base_salary,
				period_label: periodLabel,
				advance_deductions: deductions,
				adjustment: e?.adjustment || 0,
				adjustment_note: e?.adjustmentNote || "",
			});

			if (pay) {
				await call("pos_prime.api.payroll.mark_payslip_paid", {
					name: slip.name,
					payment_mode: paymentMode,
				});
			}
			await Promise.all([loadPreview(startDate, endDate), loadPayslips()]);
			return slip;
		} finally {
			running.value = false;
		}
	}

	async function markPaid(name: string, paymentMode = "Cash") {
		await call("pos_prime.api.payroll.mark_payslip_paid", { name, payment_mode: paymentMode });
		await loadPayslips();
	}

	async function cancelPayslip(name: string) {
		await call("pos_prime.api.payroll.cancel_payslip", { name });
		await loadPayslips();
	}

	return {
		preview,
		payslips,
		loading,
		running,
		edits,
		loadPreview,
		loadPayslips,
		netFor,
		generateAndPay,
		markPaid,
		cancelPayslip,
	};
});
