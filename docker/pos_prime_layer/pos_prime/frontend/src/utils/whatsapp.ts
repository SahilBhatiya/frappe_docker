// Copyright (c) 2026, Ravindu Gajanayaka
// Licensed under GPLv3. See license.txt

// Shared WhatsApp helpers for POS Prime.

// Strip non-digits and assume India (+91) for bare 10-digit numbers entered
// without a country code (also handles a leading 0). Returns digits only.
export function normalizePhone(num: string | null | undefined): string {
	const digits = (num || "").replace(/\D/g, "");
	if (digits.length === 10) return `91${digits}`;
	if (digits.length === 11 && digits.startsWith("0")) return `91${digits.slice(1)}`;
	return digits;
}

// Build a wa.me click-to-chat link (kept for the customer detail panel).
export function waLink(num: string | null | undefined): string {
	return `https://wa.me/${normalizePhone(num)}`;
}

export interface TemplateContext {
	customer_name?: string | null;
	mobile?: string | null;
	shop_name?: string | null;
	// Car / service-due data (from get_reminder_car_context)
	vehicle?: string | null;
	registration?: string | null;
	odometer?: string | null;
	monthly_driven?: string | null;
	next_alignment_date?: string | null;
	next_balancing_date?: string | null;
	next_alignment_km?: string | null;
	next_balancing_km?: string | null;
}

// Substitute {placeholder} tokens in a template body. Unknown tokens are left
// blank rather than printed literally.
export function fillTemplate(body: string, ctx: TemplateContext): string {
	const fullName = (ctx.customer_name || "").trim();
	const firstName = fullName.split(/\s+/)[0] || fullName;
	const values: Record<string, string> = {
		customer_name: fullName,
		first_name: firstName,
		mobile: ctx.mobile || "",
		shop_name: (ctx.shop_name || "").trim(),
		vehicle: ctx.vehicle || "",
		registration: ctx.registration || "",
		odometer: ctx.odometer || "",
		monthly_driven: ctx.monthly_driven || "",
		next_alignment_date: ctx.next_alignment_date || "",
		next_balancing_date: ctx.next_balancing_date || "",
		next_alignment_km: ctx.next_alignment_km || "",
		next_balancing_km: ctx.next_balancing_km || "",
	};
	return (body || "").replace(/\{(\w+)\}/g, (_match, key: string) =>
		key in values ? values[key] : "",
	);
}

// Placeholders shown in the editor legend (basic).
export const TEMPLATE_PLACEHOLDERS = [
	"{customer_name}",
	"{first_name}",
	"{mobile}",
	"{shop_name}",
] as const;

// Car / service-due placeholders, resolved per customer from Customer Car data.
export const CAR_PLACEHOLDERS = [
	"{vehicle}",
	"{odometer}",
	"{next_alignment_date}",
	"{next_alignment_km}",
	"{next_balancing_date}",
	"{next_balancing_km}",
] as const;

// Per-template color palette. Class strings are written out in FULL (literal) so
// Tailwind's content scanner keeps them — never build these names dynamically.
export interface TemplateColor {
	name: string;
	swatch: string; // solid dot for the picker
	chipIdle: string; // unselected chip
	chipActive: string; // selected chip
	accent: string; // editor card left border + header tint
	previewRing: string; // preview card border tint
}

export const TEMPLATE_COLORS: TemplateColor[] = [
	{
		name: "blue",
		swatch: "bg-blue-500",
		chipIdle: "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-900/20 dark:text-blue-300 dark:border-blue-900/40",
		chipActive: "bg-blue-600 text-white border-blue-600",
		accent: "border-l-blue-500 bg-blue-50/40 dark:bg-blue-900/10",
		previewRing: "border-blue-200 dark:border-blue-900/40 bg-blue-50/40 dark:bg-blue-900/10",
	},
	{
		name: "amber",
		swatch: "bg-amber-500",
		chipIdle: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900/20 dark:text-amber-300 dark:border-amber-900/40",
		chipActive: "bg-amber-500 text-white border-amber-500",
		accent: "border-l-amber-500 bg-amber-50/40 dark:bg-amber-900/10",
		previewRing: "border-amber-200 dark:border-amber-900/40 bg-amber-50/40 dark:bg-amber-900/10",
	},
	{
		name: "rose",
		swatch: "bg-rose-500",
		chipIdle: "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-900/20 dark:text-rose-300 dark:border-rose-900/40",
		chipActive: "bg-rose-600 text-white border-rose-600",
		accent: "border-l-rose-500 bg-rose-50/40 dark:bg-rose-900/10",
		previewRing: "border-rose-200 dark:border-rose-900/40 bg-rose-50/40 dark:bg-rose-900/10",
	},
	{
		name: "violet",
		swatch: "bg-violet-500",
		chipIdle: "bg-violet-50 text-violet-700 border-violet-200 dark:bg-violet-900/20 dark:text-violet-300 dark:border-violet-900/40",
		chipActive: "bg-violet-600 text-white border-violet-600",
		accent: "border-l-violet-500 bg-violet-50/40 dark:bg-violet-900/10",
		previewRing: "border-violet-200 dark:border-violet-900/40 bg-violet-50/40 dark:bg-violet-900/10",
	},
	{
		name: "emerald",
		swatch: "bg-emerald-500",
		chipIdle: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/20 dark:text-emerald-300 dark:border-emerald-900/40",
		chipActive: "bg-emerald-600 text-white border-emerald-600",
		accent: "border-l-emerald-500 bg-emerald-50/40 dark:bg-emerald-900/10",
		previewRing: "border-emerald-200 dark:border-emerald-900/40 bg-emerald-50/40 dark:bg-emerald-900/10",
	},
	{
		name: "cyan",
		swatch: "bg-cyan-500",
		chipIdle: "bg-cyan-50 text-cyan-700 border-cyan-200 dark:bg-cyan-900/20 dark:text-cyan-300 dark:border-cyan-900/40",
		chipActive: "bg-cyan-600 text-white border-cyan-600",
		accent: "border-l-cyan-500 bg-cyan-50/40 dark:bg-cyan-900/10",
		previewRing: "border-cyan-200 dark:border-cyan-900/40 bg-cyan-50/40 dark:bg-cyan-900/10",
	},
	{
		name: "orange",
		swatch: "bg-orange-500",
		chipIdle: "bg-orange-50 text-orange-700 border-orange-200 dark:bg-orange-900/20 dark:text-orange-300 dark:border-orange-900/40",
		chipActive: "bg-orange-500 text-white border-orange-500",
		accent: "border-l-orange-500 bg-orange-50/40 dark:bg-orange-900/10",
		previewRing: "border-orange-200 dark:border-orange-900/40 bg-orange-50/40 dark:bg-orange-900/10",
	},
	{
		name: "teal",
		swatch: "bg-teal-500",
		chipIdle: "bg-teal-50 text-teal-700 border-teal-200 dark:bg-teal-900/20 dark:text-teal-300 dark:border-teal-900/40",
		chipActive: "bg-teal-600 text-white border-teal-600",
		accent: "border-l-teal-500 bg-teal-50/40 dark:bg-teal-900/10",
		previewRing: "border-teal-200 dark:border-teal-900/40 bg-teal-50/40 dark:bg-teal-900/10",
	},
];

// Resolve a template's color entry: explicit `color` name, else cycle by index.
export function colorForTemplate(
	color: string | null | undefined,
	index = 0,
): TemplateColor {
	if (color) {
		const found = TEMPLATE_COLORS.find((c) => c.name === color);
		if (found) return found;
	}
	return TEMPLATE_COLORS[index % TEMPLATE_COLORS.length];
}
