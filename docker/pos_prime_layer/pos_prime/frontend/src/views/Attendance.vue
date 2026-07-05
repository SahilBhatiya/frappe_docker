<!-- Copyright (c) 2026, Ravindu Gajanayaka -->
<!-- Licensed under GPLv3. See license.txt -->

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { CalendarCheck, CheckCheck, Calendar, ArrowLeft } from "lucide-vue-next";
import { useAttendanceStore } from "@/stores/attendance";
import type { AttendanceStatus } from "@/types";

const router = useRouter();
const store = useAttendanceStore();

const STATUSES: { key: AttendanceStatus; label: string; on: string }[] = [
	{ key: "Present", label: "P", on: "bg-emerald-500 text-white border-emerald-500" },
	{ key: "Absent", label: "A", on: "bg-red-500 text-white border-red-500" },
	{ key: "Half Day", label: "½", on: "bg-amber-500 text-white border-amber-500" },
	{ key: "Leave", label: "L", on: "bg-blue-500 text-white border-blue-500" },
];

const counts = computed(() => {
	const c: Record<string, number> = { Present: 0, Absent: 0, "Half Day": 0, Leave: 0, Unmarked: 0 };
	for (const r of store.rows) {
		if (!r.status) c.Unmarked++;
		else c[r.status] = (c[r.status] || 0) + 1;
	}
	return c;
});

const mobileShowDetail = ref(false);

const dateOptions = [
	{ label: "Today", value: "today" },
	{ label: "Yesterday", value: "yesterday" },
	{ label: "This Week", value: "this_week" },
	{ label: "This Month", value: "this_month" },
	{ label: "Custom Date", value: "custom" },
];

const selectedOption = ref("today");
const customDate = ref(formatDate(new Date()));

function formatDate(d: Date) {
	return d.toISOString().slice(0, 10);
}

function selectDateOption(opt: string) {
	selectedOption.value = opt;
	const now = new Date();
	
	if (opt === "today") {
		store.loadDay(formatDate(now));
	} else if (opt === "yesterday") {
		store.loadDay(formatDate(new Date(now.getTime() - 86400000)));
	} else if (opt === "this_week") {
		const day = now.getDay();
		const diff = now.getDate() - day + (day === 0 ? -6 : 1);
		const start = new Date(now.setDate(diff));
		store.loadRange(formatDate(start), formatDate(new Date()));
	} else if (opt === "this_month") {
		const start = new Date(now.getFullYear(), now.getMonth(), 1);
		store.loadRange(formatDate(start), formatDate(new Date()));
	} else if (opt === "custom") {
		store.loadDay(customDate.value);
	}
	mobileShowDetail.value = true;
}

function updateCustomDate(e: Event) {
	customDate.value = (e.target as HTMLInputElement).value;
	if (selectedOption.value === "custom") {
		store.loadDay(customDate.value);
	}
}

async function setStatus(employee: string, status: AttendanceStatus) {
	try {
		await store.mark(employee, status);
	} catch (e: any) {
		alert(e?.messages?.[0] || e?.message || __("Could not save attendance"));
	}
}

onMounted(() => {
	selectDateOption("today");
});
</script>

<template>
	<div class="h-full">
		<div class="h-full flex flex-col">
			<!-- Header -->
			<div class="px-4 py-3 flex items-center gap-3">
				<button
					@click="mobileShowDetail ? (mobileShowDetail = false) : router.push({ name: 'POS' })"
					class="lg:hidden text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200"
				>
					<ArrowLeft :size="20" />
				</button>
				<h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100 flex-1">{{ __("Attendance") }}</h2>
			</div>

			<div class="flex-1 flex overflow-hidden">
				<!-- Left Pane -->
				<div
					class="w-full lg:w-[360px] shrink-0 flex flex-col rounded-2xl bg-white dark:bg-gray-900"
					:class="{ 'hidden lg:flex': mobileShowDetail }"
				>
					<div class="flex-1 overflow-y-auto p-3">
						<div class="space-y-2">
							<div v-for="opt in dateOptions" :key="opt.value">
								<button
									@click="selectDateOption(opt.value)"
									class="w-full flex items-center gap-3 rounded-lg border px-3 py-3 text-left transition-all duration-150"
									:class="
										selectedOption === opt.value
											? 'border-primary bg-primary text-primary-foreground'
											: 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800 bg-white dark:bg-gray-800'
									"
								>
									<div
										class="w-9 h-9 rounded-full flex items-center justify-center shrink-0"
										:class="selectedOption === opt.value ? 'bg-primary-foreground/20' : 'bg-gray-200 dark:bg-gray-700'"
									>
										<Calendar :size="16" :class="selectedOption === opt.value ? 'text-primary-foreground' : 'text-gray-700 dark:text-gray-200'" />
									</div>
									<div class="min-w-0 flex-1">
										<span class="font-medium text-sm" :class="selectedOption === opt.value ? 'text-primary-foreground' : 'text-gray-900 dark:text-gray-100'">{{ __(opt.label) }}</span>
									</div>
								</button>
								<div v-if="opt.value === 'custom' && selectedOption === 'custom'" class="mt-2 px-1">
									<input
										type="date"
										:value="customDate"
										@change="updateCustomDate"
										class="w-full px-3 py-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-sm focus:outline-none focus:ring-2 focus:ring-gray-950 dark:focus:ring-gray-300"
									/>
								</div>
							</div>
						</div>
					</div>
				</div>

				<!-- Right Pane -->
				<div class="flex-1 overflow-y-auto bg-gray-50 dark:bg-gray-900" :class="{ 'hidden lg:block': !mobileShowDetail }">
					<div class="p-5 max-w-3xl mx-auto">
						<div v-if="!store.rangeMode">
							<!-- Day View -->
							<div class="flex items-center justify-between gap-3 mb-4">
								<div>
									<h1 class="flex items-center gap-2 text-xl font-bold text-gray-900 dark:text-gray-100">
										<CalendarCheck :size="22" /> {{ store.date }}
									</h1>
									<p class="text-sm text-gray-500 dark:text-gray-400">{{ __("Mark who's in") }}</p>
								</div>
							</div>

							<!-- Summary + bulk -->
							<div class="flex items-center justify-between gap-2 mb-4 flex-wrap">
								<div class="flex items-center gap-2 text-xs">
									<span class="px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400 font-semibold">{{ __("Present") }} {{ counts.Present }}</span>
									<span class="px-2.5 py-1 rounded-full bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-400 font-semibold">{{ __("Absent") }} {{ counts.Absent }}</span>
									<span class="px-2.5 py-1 rounded-full bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400 font-semibold">{{ __("Unmarked") }} {{ counts.Unmarked }}</span>
								</div>
								<button
									@click="store.markAllPresent"
									:disabled="store.saving || counts.Unmarked === 0"
									class="flex items-center gap-1.5 text-sm font-semibold text-gray-900 dark:text-gray-100 border border-gray-200 dark:border-gray-700 rounded-xl px-3 py-2 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-40"
								>
									<CheckCheck :size="16" /> {{ __("Mark all present") }}
								</button>
							</div>

							<div v-if="store.loading" class="text-center py-16 text-gray-400 text-sm">{{ __("Loading…") }}</div>
							<div v-else-if="!store.rows.length" class="text-center py-16 text-gray-400 text-sm">{{ __("No active employees") }}</div>

							<!-- Grid -->
							<div v-else class="space-y-2">
								<div
									v-for="r in store.rows"
									:key="r.name"
									class="flex items-center justify-between gap-3 bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 px-4 py-3"
								>
									<span class="font-semibold text-gray-900 dark:text-gray-100 truncate">{{ r.employee_name }}</span>
									<div class="flex items-center gap-1.5 shrink-0">
										<button
											v-for="s in STATUSES"
											:key="s.key"
											@click="setStatus(r.name, s.key)"
											class="w-9 h-9 rounded-lg border text-sm font-bold transition"
											:class="
												r.status === s.key
													? s.on
													: 'border-gray-200 dark:border-gray-600 text-gray-400 hover:border-gray-400'
											"
											:title="s.key"
										>
											{{ s.label }}
										</button>
									</div>
								</div>
							</div>
						</div>

						<div v-else>
							<!-- Range View -->
							<div class="flex items-center justify-between gap-3 mb-4">
								<div>
									<h1 class="flex items-center gap-2 text-xl font-bold text-gray-900 dark:text-gray-100">
										<CalendarCheck :size="22" /> {{ store.rangeFrom }} {{ __("to") }} {{ store.rangeTo }}
									</h1>
									<p class="text-sm text-gray-500 dark:text-gray-400">{{ __("Attendance records") }}</p>
								</div>
							</div>

							<div v-if="store.loading" class="text-center py-16 text-gray-400 text-sm">{{ __("Loading…") }}</div>
							<div v-else-if="!store.rangeRecords.length" class="text-center py-16 text-gray-400 text-sm">{{ __("No records found") }}</div>
							
							<div v-else class="space-y-2">
								<div
									v-for="r in store.rangeRecords"
									:key="r.name"
									class="flex items-center justify-between gap-3 bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 px-4 py-3"
								>
									<div class="flex flex-col">
										<span class="font-semibold text-gray-900 dark:text-gray-100 truncate">{{ r.employee_name }}</span>
										<span class="text-xs text-gray-500">{{ r.attendance_date }}</span>
									</div>
									<div class="shrink-0 text-sm font-medium">
										<span
											class="px-2 py-1 rounded-md"
											:class="{
												'bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-300': r.status === 'Present',
												'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300': r.status === 'Absent',
												'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-300': r.status === 'Half Day',
												'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300': r.status === 'Leave'
											}"
										>
											{{ r.status }}
										</span>
									</div>
								</div>
							</div>
						</div>
					</div>
				</div>
			</div>
		</div>
	</div>
</template>
