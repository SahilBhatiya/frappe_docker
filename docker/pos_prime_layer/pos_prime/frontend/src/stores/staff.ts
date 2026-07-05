// Copyright (c) 2026, Ravindu Gajanayaka
// Licensed under GPLv3. See license.txt

import { defineStore } from "pinia";
import { ref } from "vue";
import { call } from "frappe-ui";
import type { StaffMember, StaffAdvance, StaffPayslip, StaffAttendance } from "@/types";

export const useStaffStore = defineStore("staff", () => {
	const staff = ref<StaffMember[]>([]);
	const loading = ref(false);
	const saving = ref(false);
	const searchTerm = ref("");
	const includeInactive = ref(false);

	// Currently-open member detail
	const current = ref<StaffMember | null>(null);
	const advances = ref<StaffAdvance[]>([]);
	const payslips = ref<StaffPayslip[]>([]);
	const attendance = ref<StaffAttendance[]>([]);
	const detailLoading = ref(false);

	async function loadStaff() {
		loading.value = true;
		try {
			staff.value = await call("pos_prime.api.staff.list_staff", {
				search: searchTerm.value,
				include_inactive: includeInactive.value ? 1 : 0,
			});
		} catch {
			staff.value = [];
		} finally {
			loading.value = false;
		}
	}

	async function createStaff(payload: {
		employee_name: string;
		monthly_salary?: number;
		mobile?: string;
		designation?: string;
		date_of_joining?: string;
	}) {
		saving.value = true;
		try {
			const created: StaffMember = await call("pos_prime.api.staff.create_staff", payload);
			await loadStaff();
			return created;
		} finally {
			saving.value = false;
		}
	}

	async function updateStaff(
		employee: string,
		patch: Partial<{
			employee_name: string;
			monthly_salary: number;
			mobile: string;
			designation: string;
			status: string;
		}>,
	) {
		saving.value = true;
		try {
			const updated: StaffMember = await call("pos_prime.api.staff.update_staff", {
				employee,
				...patch,
			});
			current.value = updated;
			await loadStaff();
			return updated;
		} finally {
			saving.value = false;
		}
	}

	async function loadMember(employee: string) {
		detailLoading.value = true;
		try {
			const [member, advs, slips] = await Promise.all([
				call("pos_prime.api.staff.get_staff", { employee }),
				call("pos_prime.api.payroll.list_advances", { employee }),
				call("pos_prime.api.payroll.list_payslips", { employee }),
			]);
			current.value = member;
			advances.value = advs || [];
			payslips.value = slips || [];
		} finally {
			detailLoading.value = false;
		}
	}

	async function loadMemberAttendance(employee: string, fromDate: string, toDate: string) {
		try {
			attendance.value = await call("pos_prime.api.attendance.list_attendance", {
				employee,
				from_date: fromDate,
				to_date: toDate,
			});
		} catch {
			attendance.value = [];
		}
	}

	async function addAdvance(employee: string, amount: number, date?: string, notes?: string) {
		await call("pos_prime.api.payroll.create_advance", { employee, amount, date, notes });
		await loadMember(employee);
	}

	async function cancelAdvance(name: string, employee: string) {
		await call("pos_prime.api.payroll.cancel_advance", { name });
		await loadMember(employee);
	}

	return {
		staff,
		loading,
		saving,
		searchTerm,
		includeInactive,
		current,
		advances,
		payslips,
		attendance,
		detailLoading,
		loadStaff,
		createStaff,
		updateStaff,
		loadMember,
		loadMemberAttendance,
		addAdvance,
		cancelAdvance,
	};
});
