<!-- Copyright (c) 2026, Ravindu Gajanayaka -->
<!-- Licensed under GPLv3. See license.txt -->

<script setup lang="ts">
import DisplayControls from "@/components/display/DisplayControls.vue";
import { useDeskMode } from "@/composables/useDeskMode";
import { useDraftsStore } from "@/stores/drafts";
import { usePosSessionStore } from "@/stores/posSession";
import { session as userSession } from "@/stores/session";
import { call, Tooltip } from "frappe-ui";
import {
	BadgeIndianRupee,
	Briefcase,
	CalendarCheck,
	ClipboardList,
	Contact,
	Grid3x3,
	History,
	LogOut,
	Maximize,
	Menu,
	Minimize,
	Monitor,
	PauseCircle,
	Receipt,
	RotateCcw,
	Send,
	Settings,
	Store,
	Users,
	X,
} from "lucide-vue-next";
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

const { isDeskMode } = useDeskMode();
const router = useRouter();
const route = useRoute();
const draftsStore = useDraftsStore();
const sessionStore = usePosSessionStore();
const sidebarOpen = ref(false);
const showDisplayPopover = ref(false);

const companyLogo = ref<string | null>(null);
const companyAbbr = ref("P");
const userFullName = ref("");
const userImage = ref<string | null>(null);

// ---------------------------------------------------------------------------
// Two-level navigation
//   Bottom dock  -> major categories (POS / CRM / HR / Settings)
//   Left sidebar -> the pages of the currently-active category
// ---------------------------------------------------------------------------
interface NavPage {
	name: string;
	routeName: string;
	icon: any;
}
interface NavCategory {
	key: string;
	name: string;
	icon: any;
	defaultRoute: string;
	children: NavPage[];
}

const categories: NavCategory[] = [
	{
		key: "pos",
		name: __("POS"),
		icon: Store,
		defaultRoute: "POS",
		children: [
			{ name: __("POS"), routeName: "POS", icon: Grid3x3 },
			{ name: __("Orders"), routeName: "Orders", icon: ClipboardList },
			{ name: __("Customers"), routeName: "Customers", icon: Users },
			{ name: __("Alignment"), routeName: "AlignmentHistory", icon: History },
		],
	},
	{
		key: "crm",
		name: __("CRM"),
		icon: Users,
		defaultRoute: "Customers",
		children: [
			{ name: __("Customers"), routeName: "Customers", icon: Users },
			{ name: __("Reminders"), routeName: "Reminders", icon: Send },
		],
	},
	{
		key: "hr",
		name: __("HR"),
		icon: Briefcase,
		defaultRoute: "Staff",
		children: [
			{ name: __("Staff"), routeName: "Staff", icon: Contact },
			{ name: __("Attendance"), routeName: "Attendance", icon: CalendarCheck },
			{ name: __("Payroll"), routeName: "Payroll", icon: BadgeIndianRupee },
		],
	},
	{
		key: "settings",
		name: __("Settings"),
		icon: Settings,
		defaultRoute: "GstReport",
		children: [{ name: __("GST"), routeName: "GstReport", icon: Receipt }],
	},
];

// Canonical route name (detail routes fold into their list route).
const currentRouteName = computed(() => {
	if (route.name === "CustomerDetail") return "Customers";
	if (route.name === "StaffMember") return "Staff";
	return route.name as string;
});

function categoryKeyForRoute(routeName: string): string {
	const c = categories.find((cat) => cat.children.some((ch) => ch.routeName === routeName));
	return c ? c.key : "pos";
}

// Active category is an explicit ref (a dock click wins) that also follows the route
// when you navigate to a page outside the current category.
const activeCategoryKey = ref(categoryKeyForRoute(currentRouteName.value));
const activeCategory = computed(
	() => categories.find((c) => c.key === activeCategoryKey.value) || categories[0],
);
const isPosCategory = computed(() => activeCategoryKey.value === "pos");

watch(currentRouteName, (rn) => {
	const active = categories.find((c) => c.key === activeCategoryKey.value);
	if (!active || !active.children.some((ch) => ch.routeName === rn)) {
		activeCategoryKey.value = categoryKeyForRoute(rn);
	}
});

function selectCategory(cat: NavCategory) {
	activeCategoryKey.value = cat.key;
	// Stay on the current page if it already belongs to this category; else jump to default.
	if (!cat.children.some((ch) => ch.routeName === currentRouteName.value)) {
		router.push({ name: cat.defaultRoute });
	}
	sidebarOpen.value = false;
}

// ----- Bottom dock auto-hide -----
// Revealed by moving the pointer to the bottom edge (desktop) or tapping the peek
// handle (touch). Never blocks content clicks — reveal is driven by a window
// mousemove listener, not an overlay strip.
const dockVisible = ref(true); // always visible (auto-hide disabled)
const dockHovered = ref(false);
const REVEAL_PX = 24; // how close to the bottom edge triggers a reveal
let hideTimer: ReturnType<typeof setTimeout> | undefined;

function showDock() {
	if (hideTimer) clearTimeout(hideTimer);
	dockVisible.value = true;
}
function hideDock() {
	// Dock is always visible — auto-hide disabled.
}
function toggleDock() {
	if (dockVisible.value) {
		if (hideTimer) clearTimeout(hideTimer);
		dockVisible.value = false;
	} else {
		showDock();
	}
}
function onDockEnter() {
	dockHovered.value = true;
	showDock();
}
function onDockLeave() {
	dockHovered.value = false;
	hideDock();
}
function onMouseMove(e: MouseEvent) {
	if (e.clientY >= window.innerHeight - REVEAL_PX) showDock();
	else if (!dockHovered.value && dockVisible.value) hideDock();
}

const draftCount = computed(() => draftsStore.drafts.length);

const userInitials = computed(() => {
	if (!userFullName.value) return "?";
	const parts = userFullName.value.trim().split(/\s+/);
	if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
	return parts[0][0].toUpperCase();
});

function setFavicon(url: string) {
	let link = document.querySelector<HTMLLinkElement>("link[rel~='icon']");
	if (!link) {
		link = document.createElement("link");
		link.rel = "icon";
		document.head.appendChild(link);
	}
	link.href = url;
}

function goToDesk() {
	window.location.href = "/app";
}

onMounted(async () => {
	if (sessionStore.posProfile) {
		await draftsStore.fetchDrafts(sessionStore.posProfile);
	}

	// Fetch app logo & favicon via backend endpoint (no Website Settings permission needed)
	try {
		const branding = await call("pos_prime.api.pos_session.get_branding", {
			company: sessionStore.company || "",
		});
		if (branding?.app_logo) {
			companyLogo.value = branding.app_logo;
		} else if (branding?.company_logo) {
			companyLogo.value = branding.company_logo;
		}
		if (branding?.favicon) {
			setFavicon(branding.favicon);
		} else if (branding?.company_logo) {
			setFavicon(branding.company_logo);
		}
		if (branding?.company_abbr) {
			companyAbbr.value = branding.company_abbr;
		}
		if (!companyLogo.value && sessionStore.company) {
			companyAbbr.value = sessionStore.company[0];
		}
	} catch {
		/* ignore */
	}

	// Fetch user info via backend endpoint (skip in desk mode — navbar shows user)
	if (!isDeskMode.value && userSession.user?.data) {
		try {
			const userInfo = await call("pos_prime.api.pos_session.get_user_info");
			if (userInfo) {
				userFullName.value = userInfo.full_name || userSession.user.data;
				userImage.value = userInfo.user_image || null;
			}
		} catch {
			userFullName.value = userSession.user.data;
		}
	}
});

function navigate(routeName: string) {
	router.push({ name: routeName });
	sidebarOpen.value = false;
}

function closeShift() {
	router.push({ name: "CloseShift" });
	sidebarOpen.value = false;
}

const isFullscreen = ref(false);

function toggleFullscreen() {
	if (!document.fullscreenElement) {
		document.documentElement.requestFullscreen();
	} else {
		document.exitFullscreen();
	}
}

function onFullscreenChange() {
	isFullscreen.value = !!document.fullscreenElement;
}

if (typeof document !== "undefined") {
	document.addEventListener("fullscreenchange", onFullscreenChange);
}
if (typeof window !== "undefined") {
	window.addEventListener("mousemove", onMouseMove);
}

onUnmounted(() => {
	if (typeof document !== "undefined") {
		document.removeEventListener("fullscreenchange", onFullscreenChange);
	}
	if (typeof window !== "undefined") {
		window.removeEventListener("mousemove", onMouseMove);
	}
	if (hideTimer) clearTimeout(hideTimer);
});

const emit = defineEmits<{
	toggleHeldOrders: [];
	toggleReturn: [];
}>();
</script>

<template>
	<div
		:class="[
			'relative flex overflow-hidden bg-gray-50 dark:bg-gray-900 p-2',
			isDeskMode ? 'h-full' : 'h-screen',
		]"
	>
		<!-- Desktop Sidebar (pages of the active category) -->
		<aside
			class="hidden lg:flex flex-col items-center bg-gray-50 dark:bg-gray-900 dark:border-gray-800 mr-3"
			:class="isDeskMode ? 'lg:w-[60px] py-1.5 gap-1' : 'lg:w-[68px] py-3 gap-1.5'"
		>
			<div
				class="bg-white rounded-full p-1 flex flex-col gap-1 shadow-[0_0_50px_-10px_rgba(0,0,0,.1)]"
			>
				<!-- Pages of the active category -->
				<Tooltip
					v-for="item in activeCategory.children"
					:key="item.routeName"
					:text="item.name"
					placement="right"
				>
					<button
						@click="navigate(item.routeName)"
						:aria-label="item.name"
						class="relative flex flex-col items-center justify-center rounded-full transition-all duration-150"
						:class="[
							isDeskMode ? 'w-11 h-11' : 'w-12 h-12',
							currentRouteName === item.routeName
								? 'bg-gray-100 dark:bg-gray-800 text-gray-950 dark:text-gray-100 shadow-sm shadow-gray-200 dark:shadow-black/20'
								: 'text-gray-400 dark:text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800 hover:text-gray-600 dark:hover:text-gray-300',
						]"
					>
						<component
							:is="item.icon"
							:size="isDeskMode ? 18 : 20"
							:stroke-width="currentRouteName === item.routeName ? 2.5 : 2"
						/>
					</button>
				</Tooltip>
			</div>

			<!-- POS-only actions (act on the live cart) -->
			<div
				v-if="isPosCategory"
				class="bg-white rounded-full p-1 flex flex-col gap-1 shadow-[0_0_50px_-10px_rgba(0,0,0,.1)] mt-3"
			>
				<!-- Held orders -->
				<Tooltip :text="__('Held')" placement="right">
					<button
						@click="emit('toggleHeldOrders')"
						aria-label="Held Orders"
						class="relative flex flex-col items-center justify-center rounded-xl text-gray-400 dark:text-gray-500 hover:bg-amber-50 dark:hover:bg-amber-900/20 hover:text-amber-600 dark:hover:text-amber-400 transition-all duration-150"
						:class="isDeskMode ? 'w-11 h-11' : 'w-12 h-12'"
					>
						<PauseCircle :size="isDeskMode ? 18 : 20" />
						<span
							v-if="draftCount > 0"
							class="absolute -top-0.5 -end-0.5 bg-amber-500 text-white text-[8px] font-bold rounded-full min-w-[16px] h-4 flex items-center justify-center px-0.5 shadow-sm"
						>
							{{ draftCount > 9 ? "9+" : draftCount }}
						</span>
					</button>
				</Tooltip>

				<!-- Return -->
				<Tooltip :text="__('Return')" placement="right">
					<button
						@click="emit('toggleReturn')"
						aria-label="Return"
						class="flex flex-col items-center justify-center rounded-xl text-gray-400 dark:text-gray-500 hover:bg-red-50 dark:hover:bg-red-900/20 hover:text-red-500 dark:hover:text-red-400 transition-all duration-150"
						:class="isDeskMode ? 'w-11 h-11' : 'w-12 h-12'"
					>
						<RotateCcw :size="isDeskMode ? 18 : 20" />
					</button>
				</Tooltip>

				<!-- Display -->
				<div class="relative">
					<Tooltip
						:text="__('Display')"
						placement="right"
						:disabled="showDisplayPopover"
					>
						<button
							@click="showDisplayPopover = !showDisplayPopover"
							aria-label="Customer Display"
							class="flex flex-col items-center justify-center rounded-xl text-gray-400 dark:text-gray-500 hover:bg-purple-50 dark:hover:bg-purple-900/20 hover:text-purple-500 dark:hover:text-purple-400 transition-all duration-150"
							:class="[
								isDeskMode ? 'w-11 h-11' : 'w-12 h-12',
								showDisplayPopover
									? 'bg-purple-50 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400'
									: '',
							]"
						>
							<Monitor :size="isDeskMode ? 18 : 20" />
						</button>
					</Tooltip>
					<Transition name="fade">
						<div
							v-if="showDisplayPopover"
							class="fixed inset-0 z-40"
							@click="showDisplayPopover = false"
						/>
					</Transition>
					<Transition name="fade">
						<div v-if="showDisplayPopover" class="absolute left-full top-0 ml-2 z-50">
							<DisplayControls />
						</div>
					</Transition>
				</div>
			</div>

			<div class="flex-1" />
			<div
				class="bg-white rounded-full p-1 flex flex-col gap-1 shadow-[0_0_50px_-10px_rgba(0,0,0,.1)] mt-3"
			>
				<!-- Fullscreen toggle -->
				<Tooltip
					:text="isFullscreen ? __('Exit fullscreen') : __('Fullscreen')"
					placement="right"
				>
					<button
						@click="toggleFullscreen"
						:aria-label="isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'"
						class="flex flex-col items-center justify-center rounded-xl text-gray-400 dark:text-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800 hover:text-gray-600 dark:hover:text-gray-300 transition-all duration-150 mb-0.5"
						:class="isDeskMode ? 'w-11 h-11' : 'w-12 h-12'"
					>
						<Minimize v-if="isFullscreen" :size="isDeskMode ? 18 : 20" />
						<Maximize v-else :size="isDeskMode ? 18 : 20" />
					</button>
				</Tooltip>

				<!-- User profile (hidden in desk mode — ERPNext navbar has it) -->
				<Tooltip
					v-slot="{ active }"
					v-if="!isDeskMode"
					:text="userFullName || userSession.user?.data || ''"
					placement="right"
				>
					<div
						class="flex flex-col items-center justify-center rounded-full mb-1 w-12 h-12 hover:bg-gray-50 dark:hover:bg-gray-800 transition-all duration-150"
					>
						<img
							v-if="userImage"
							:src="userImage"
							:alt="userFullName"
							class="w-8 h-8 rounded-full object-cover border border-gray-200 dark:border-gray-700"
						/>
						<div
							v-else
							class="w-8 h-8 bg-gray-200 dark:bg-gray-700 rounded-full flex items-center justify-center"
						>
							<span class="text-[10px] font-bold text-gray-950 dark:text-gray-100">{{
								userInitials
							}}</span>
						</div>
					</div>
				</Tooltip>

				<!-- Close shift -->
				<Tooltip :text="__('Close Shift')" placement="right">
					<button
						@click="closeShift"
						aria-label="Close Shift"
						class="flex flex-col items-center justify-center rounded-xl text-gray-400 dark:text-gray-500 hover:bg-red-50 dark:hover:bg-red-900/20 hover:text-red-500 dark:hover:text-red-400 transition-all duration-150"
						:class="isDeskMode ? 'w-11 h-11' : 'w-12 h-12'"
					>
						<LogOut :size="isDeskMode ? 18 : 20" />
					</button>
				</Tooltip>
			</div>
		</aside>

		<!-- Main content area -->
		<div class="flex-1 flex flex-col overflow-hidden">
			<!-- Mobile header -->
			<header
				class="lg:hidden flex items-center justify-between bg-white dark:bg-gray-900 border-b border-gray-100 dark:border-gray-800 px-4 h-12"
			>
				<button
					@click="goToDesk"
					class="flex items-center gap-2 cursor-pointer"
					:title="`Back to ${sessionStore.company || 'Desk'}`"
				>
					<img
						v-if="companyLogo"
						:src="companyLogo"
						:alt="sessionStore.company"
						class="w-6 h-6 rounded-lg object-contain"
					/>
					<div
						v-else
						class="w-6 h-6 bg-gradient-to-br from-gray-900 to-black rounded-lg flex items-center justify-center"
					>
						<span class="text-white font-bold text-[10px]">{{ companyAbbr }}</span>
					</div>
					<span class="font-bold text-gray-800 dark:text-gray-200 text-sm">{{
						sessionStore.company || "POS Prime"
					}}</span>
				</button>
				<div class="flex items-center gap-1">
					<button
						@click="emit('toggleHeldOrders')"
						aria-label="Held Orders"
						class="relative w-9 h-9 rounded-lg flex items-center justify-center text-gray-500 dark:text-gray-400 hover:text-amber-600 dark:hover:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-900/20 transition-colors"
					>
						<PauseCircle :size="18" />
						<span
							v-if="draftCount > 0"
							class="absolute top-0.5 end-0.5 bg-amber-500 text-white text-[7px] font-bold rounded-full w-3.5 h-3.5 flex items-center justify-center"
						>
							{{ draftCount }}
						</span>
					</button>
					<button
						@click="sidebarOpen = !sidebarOpen"
						class="w-9 h-9 rounded-lg flex items-center justify-center text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
						aria-label="Toggle menu"
					>
						<Menu v-if="!sidebarOpen" :size="18" />
						<X v-else :size="18" />
					</button>
				</div>
			</header>

			<!-- Mobile menu overlay (categories -> pages) -->
			<Transition name="fade">
				<div
					v-if="sidebarOpen"
					class="lg:hidden fixed inset-0 z-40 bg-black/30 backdrop-blur-sm"
					@click="sidebarOpen = false"
				/>
			</Transition>
			<Transition name="slide-right">
				<nav
					v-if="sidebarOpen"
					class="lg:hidden fixed end-0 top-12 z-50 bg-white dark:bg-gray-900 shadow-xl rounded-bl-2xl w-56 border-s border-gray-100 dark:border-gray-800"
				>
					<div class="py-1 max-h-[75vh] overflow-y-auto">
						<template v-for="cat in categories" :key="cat.key">
							<div
								class="px-4 pt-3 pb-1 text-[10px] font-bold uppercase tracking-wide text-gray-400"
							>
								{{ cat.name }}
							</div>
							<button
								v-for="item in cat.children"
								:key="cat.key + '-' + item.routeName"
								@click="navigate(item.routeName)"
								class="flex items-center gap-3 w-full px-4 py-2.5 text-sm font-medium transition-colors"
								:class="
									currentRouteName === item.routeName
										? 'bg-gray-100 dark:bg-gray-800 text-gray-950 dark:text-gray-100'
										: 'text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800'
								"
							>
								<component :is="item.icon" :size="16" />
								{{ item.name }}
							</button>
						</template>
						<div class="mx-4 my-1 border-t border-gray-100 dark:border-gray-800" />
						<button
							@click="
								emit('toggleReturn');
								sidebarOpen = false;
							"
							class="flex items-center gap-3 w-full px-4 py-2.5 text-sm font-medium text-gray-600 dark:text-gray-400 hover:bg-red-50 dark:hover:bg-red-900/20 hover:text-red-600 dark:hover:text-red-400"
						>
							<RotateCcw :size="16" />
							{{ __("Return") }}
						</button>
						<button
							@click="closeShift"
							class="flex items-center gap-3 w-full px-4 py-2.5 text-sm font-medium text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20"
						>
							<LogOut :size="16" />
							{{ __("Close Shift") }}
						</button>
					</div>
				</nav>
			</Transition>

			<main class="flex-1 overflow-hidden">
				<slot />
			</main>

			<!-- Mobile bottom nav (categories) -->
			<nav
				class="lg:hidden flex items-center justify-around bg-white dark:bg-gray-900 border-t border-gray-100 dark:border-gray-800 h-14"
			>
				<button
					v-for="cat in categories"
					:key="cat.key"
					@click="selectCategory(cat)"
					class="flex flex-col items-center justify-center flex-1 h-full transition-colors"
					:class="
						activeCategoryKey === cat.key
							? 'text-gray-950 dark:text-gray-100'
							: 'text-gray-400 dark:text-gray-500'
					"
				>
					<component
						:is="cat.icon"
						:size="18"
						:stroke-width="activeCategoryKey === cat.key ? 2.5 : 2"
					/>
					<span class="text-[9px] mt-0.5 font-semibold">{{ cat.name }}</span>
				</button>
			</nav>
		</div>

		<!-- the dock itself -->
		<div
			class="hidden lg:flex absolute bottom-4 left-1/2 -translate-x-1/2 z-40 items-center gap-1 rounded-full border border-solid border-gray-100 dark:border-gray-700 bg-white/70 dark:bg-gray-800/90 backdrop-blur-md p-1.5 shadow-[0_26px_100px_-12px_rgba(0,0,0,.35)] ring-2 ring-gray-50 transition-all duration-300 ease-out"
			:class="
				dockVisible
					? 'translate-y-0 opacity-100'
					: 'translate-y-[180%] opacity-0 pointer-events-none'
			"
			@mouseenter="onDockEnter"
			@mouseleave="onDockLeave"
		>
			<button
				v-for="cat in categories"
				:key="cat.key"
				@click="selectCategory(cat)"
				:aria-label="cat.name"
				class="flex flex-col items-center justify-center gap-0.5 p-4 rounded-full transition-all duration-350 origin-bottom hover:ring-1 ring-gray-100 hover:shadow-[0_0px_300px_-2px_rgba(0,0,0,.15)]"
				:class="
					activeCategoryKey === cat.key
						? 'bg-gray-50 dark:bg-gray-700 text-gray-950 dark:text-gray-100'
						: 'text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700/60 hover:text-gray-800 dark:hover:text-gray-200'
				"
			>
				<component
					:is="cat.icon"
					:size="22"
					:stroke-width="activeCategoryKey === cat.key ? 2.5 : 2"
				/>
			</button>
		</div>
	</div>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
	transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
	opacity: 0;
}

.slide-right-enter-active {
	transition:
		transform 0.2s ease-out,
		opacity 0.2s ease-out;
}
.slide-right-leave-active {
	transition:
		transform 0.15s ease-in,
		opacity 0.15s ease-in;
}
.slide-right-enter-from {
	transform: translateX(100%);
	opacity: 0;
}
.slide-right-leave-to {
	transform: translateX(100%);
	opacity: 0;
}
</style>
