const defaultSupabaseUrl = "https://api.adarshtyre.in";
// Supabase anon keys are public client credentials; RLS remains the security boundary.
const defaultSupabaseKey = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9.CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0";
const supabaseUrl = (import.meta.env.VITE_ALIGNMENT_SUPABASE_URL || defaultSupabaseUrl).replace(/\/$/, "");
const supabaseKey = import.meta.env.VITE_ALIGNMENT_SUPABASE_ANON_KEY || defaultSupabaseKey;

export interface AlignmentMeasurement {
	param_id: string;
	param_name: string;
	param_type?: string;
	before_value?: string | number | null;
	after_value?: string | number | null;
	min_value?: string | number | null;
	max_value?: string | number | null;
	best_value?: string | number | null;
}

export interface AlignmentReport {
	report_id: string;
	report_date_raw?: string | null;
	start_time_raw?: string | null;
	end_time_raw?: string | null;
	vehicle_registration?: string | null;
	mileage_raw?: string | number | null;
	customer_name?: string | null;
	customer_address?: string | null;
	customer_phone?: string | null;
	manufacturer_name?: string | null;
	model_name?: string | null;
	model_year_raw?: string | number | null;
	vin?: string | null;
	measurement_count?: number | null;
	measurements?: AlignmentMeasurement[];
}

const summaryFields = [
	"report_id",
	"report_date_raw",
	"start_time_raw",
	"end_time_raw",
	"vehicle_registration",
	"mileage_raw",
	"customer_name",
	"customer_address",
	"customer_phone",
	"manufacturer_name",
	"model_name",
	"model_year_raw",
	"vin",
	"measurement_count",
].join(",");

function headers(includeCount = false) {
	if (!supabaseUrl || !supabaseKey) {
		throw new Error("Alignment Supabase connection is not configured");
	}
	return {
		apikey: supabaseKey,
		Authorization: `Bearer ${supabaseKey}`,
		...(includeCount ? { Prefer: "count=exact" } : {}),
	};
}

export async function fetchAlignmentReports(page: number, pageSize: number, search = "") {
	const params = new URLSearchParams({
		select: summaryFields,
		order: "report_date_raw.desc,start_time_raw.desc",
	});
	const term = search.trim().replace(/[,*()]/g, " ");
	if (term) {
		params.set(
			"or",
			`(vehicle_registration.ilike.*${term}*,customer_name.ilike.*${term}*,customer_phone.ilike.*${term}*,manufacturer_name.ilike.*${term}*,model_name.ilike.*${term}*)`,
		);
	}
	const from = (page - 1) * pageSize;
	const response = await fetch(
		`${supabaseUrl}/rest/v1/alignment_machine_reports_v1?${params}`,
		{
			headers: {
				...headers(true),
				Range: `${from}-${from + pageSize - 1}`,
			},
		},
	);
	if (!response.ok) throw new Error(`Machine history request failed (${response.status})`);
	const range = response.headers.get("content-range") || "";
	const total = Number(range.split("/")[1]) || 0;
	return { reports: (await response.json()) as AlignmentReport[], total };
}

export async function fetchAlignmentReport(reportId: string) {
	const params = new URLSearchParams({
		select: `${summaryFields},measurements`,
		report_id: `eq.${reportId}`,
		limit: "1",
	});
	const response = await fetch(
		`${supabaseUrl}/rest/v1/alignment_machine_reports_v1?${params}`,
		{ headers: headers() },
	);
	if (!response.ok) throw new Error(`Alignment detail request failed (${response.status})`);
	const rows = (await response.json()) as AlignmentReport[];
	return rows[0] || null;
}
