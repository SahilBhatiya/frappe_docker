// Copyright (c) 2026, Ravindu Gajanayaka
// Licensed under GPLv3. See license.txt

import { defineStore } from "pinia";
import { ref } from "vue";
import { call } from "frappe-ui";
import type { AttendanceDayRow, AttendanceStatus, StaffAttendance } from "@/types";

export const useAttendanceStore = defineStore("attendance", () => {
	const date = ref<string>(new Date().toISOString().slice(0, 10));
	const rows = ref<AttendanceDayRow[]>([]);
	
	// For date range
	const rangeMode = ref(false);
	const rangeRecords = ref<StaffAttendance[]>([]);
	const rangeFrom = ref<string>("");
	const rangeTo = ref<string>("");

	const loading = ref(false);
	const saving = ref(false);

	async function loadDay(forDate?: string) {
		rangeMode.value = false;
		if (forDate) date.value = forDate;
		loading.value = true;
		try {
			rows.value = await call("pos_prime.api.attendance.day_sheet", {
				attendance_date: date.value,
			});
		} catch {
			rows.value = [];
		} finally {
			loading.value = false;
		}
	}

	async function loadRange(from_date: string, to_date: string) {
		rangeMode.value = true;
		rangeFrom.value = from_date;
		rangeTo.value = to_date;
		loading.value = true;
		try {
			rangeRecords.value = await call("pos_prime.api.attendance.list_attendance", {
				from_date,
				to_date,
			});
		} catch {
			rangeRecords.value = [];
		} finally {
			loading.value = false;
		}
	}

	// Optimistic single-employee mark (used by the day grid buttons).
	async function mark(employee: string, status: AttendanceStatus) {
		const row = rows.value.find((r) => r.name === employee);
		const prev = row?.status ?? null;
		if (row) row.status = status;
		try {
			await call("pos_prime.api.attendance.mark_attendance", {
				employee,
				attendance_date: date.value,
				status,
			});
		} catch (e) {
			if (row) row.status = prev; // revert on failure
			throw e;
		}
	}

	// Mark every still-unmarked employee Present in one call.
	async function markAllPresent() {
		saving.value = true;
		try {
			const payload = rows.value
				.filter((r) => !r.status)
				.map((r) => ({ employee: r.name, status: "Present" as AttendanceStatus }));
			if (!payload.length) return;
			await call("pos_prime.api.attendance.bulk_mark", {
				attendance_date: date.value,
				rows: payload,
			});
			await loadDay();
		} finally {
			saving.value = false;
		}
	}

	return { date, rows, rangeMode, rangeRecords, rangeFrom, rangeTo, loading, saving, loadDay, loadRange, mark, markAllPresent };
});
