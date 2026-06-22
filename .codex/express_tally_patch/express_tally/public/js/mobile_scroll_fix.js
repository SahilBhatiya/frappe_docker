(function () {
	"use strict";

	if (window.__expressTallyMobileScrollFix) return;
	window.__expressTallyMobileScrollFix = true;

	function isMobileWidth() {
		return window.matchMedia && window.matchMedia("(max-width: 768px)").matches;
	}

	function hasOpenModal() {
		return !!document.querySelector(".modal.show, .modal.in, .modal-backdrop.show, .modal-backdrop.in");
	}

	function hasOpenSidebar() {
		return !!document.querySelector(".body-sidebar-container.expanded");
	}

	function clearStaleScrollLock() {
		if (!isMobileWidth() || hasOpenModal() || hasOpenSidebar()) return;

		document.body.classList.remove("modal-open");
		document.body.style.removeProperty("overflow");
		document.body.style.removeProperty("padding-right");
		document.documentElement.style.removeProperty("overflow");

		document.querySelectorAll(".main-section").forEach(function (section) {
			if (section.style.overflow === "hidden") {
				section.style.removeProperty("overflow");
			}
		});
	}

	function scheduleUnlock() {
		window.requestAnimationFrame(clearStaleScrollLock);
		window.setTimeout(clearStaleScrollLock, 250);
	}

	document.addEventListener("hidden.bs.modal", scheduleUnlock, true);
	document.addEventListener("click", function () {
		window.setTimeout(clearStaleScrollLock, 400);
	}, true);

	$(document).on("sidebar-expand page-change form-refresh", scheduleUnlock);

	if (window.frappe && frappe.router && frappe.router.on) {
		frappe.router.on("change", scheduleUnlock);
	}

	window.addEventListener("orientationchange", scheduleUnlock);
	window.addEventListener("resize", scheduleUnlock);
	window.setInterval(clearStaleScrollLock, 2000);
	scheduleUnlock();
})();
