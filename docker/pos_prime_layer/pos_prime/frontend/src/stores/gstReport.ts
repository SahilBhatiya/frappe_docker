// Copyright (c) 2026, Ravindu Gajanayaka
// Licensed under GPLv3. See license.txt

import { defineStore } from "pinia";
import { ref } from "vue";
import { call } from "frappe-ui";

export interface GstRateRow {
	gst_rate: number;
	taxable_amount: number;
	cgst: number;
	sgst: number;
	igst: number;
	total_gst: number;
}

export interface GstSummary {
	company: string;
	from_date: string;
	to_date: string;
	taxable_amount: number;
	cgst: number;
	sgst: number;
	igst: number;
	total_gst: number;
	invoice_count: number;
	by_rate: GstRateRow[];
}

export interface GstInvoiceRow {
	name: string;
	doctype: string;
	posting_date: string;
	customer: string;
	customer_name: string;
	is_return: number;
	place_of_supply: string | null;
	gstin: string | null;
	taxable: number;
	cgst: number;
	sgst: number;
	igst: number;
	total_gst: number;
}

const PAGE = 50;

export const useGstReportStore = defineStore("gstReport", () => {
	const summary = ref<GstSummary | null>(null);
	const invoices = ref<GstInvoiceRow[]>([]);
	const loading = ref(false);
	const loadingMore = ref(false);
	const hasMore = ref(false);
	const error = ref("");

	async function loadSummary(company: string, fromDate: string, toDate: string) {
		loading.value = true;
		error.value = "";
		invoices.value = [];
		try {
			summary.value = await call("pos_prime.api.gst_report.get_gst_summary", {
				company,
				from_date: fromDate,
				to_date: toDate,
			});
			await loadInvoices(company, fromDate, toDate, false);
		} catch (e: any) {
			error.value = e?.messages?.[0] || e?.message || "Failed to load GST summary";
			summary.value = null;
		} finally {
			loading.value = false;
		}
	}

	async function loadInvoices(
		company: string,
		fromDate: string,
		toDate: string,
		append = true,
	) {
		if (append) loadingMore.value = true;
		try {
			const data = await call("pos_prime.api.gst_report.get_gst_invoices", {
				company,
				from_date: fromDate,
				to_date: toDate,
				limit: PAGE,
				offset: append ? invoices.value.length : 0,
			});
			invoices.value = append ? [...invoices.value, ...data.invoices] : data.invoices;
			hasMore.value = data.has_more;
		} catch {
			hasMore.value = false;
		} finally {
			loadingMore.value = false;
		}
	}

	function toCsv(): string {
		const head = ["Invoice", "Date", "Customer", "GSTIN", "Place of Supply", "Taxable", "CGST", "SGST", "IGST", "Total GST"];
		const rows = invoices.value.map((r) => [
			r.name,
			r.posting_date,
			`"${(r.customer_name || r.customer || "").replace(/"/g, '""')}"`,
			r.gstin || "",
			r.place_of_supply || "",
			r.taxable,
			r.cgst,
			r.sgst,
			r.igst,
			r.total_gst,
		]);
		return [head, ...rows].map((r) => r.join(",")).join("\n");
	}

	return {
		summary,
		invoices,
		loading,
		loadingMore,
		hasMore,
		error,
		loadSummary,
		loadInvoices,
		toCsv,
	};
});
