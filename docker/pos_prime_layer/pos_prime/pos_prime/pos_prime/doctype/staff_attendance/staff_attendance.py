# Copyright (c) 2026, Ravindu Gajanayaka
# Licensed under GPLv3. See license.txt

"""Staff Attendance — one record per employee per day.

Uniqueness is enforced by the autoname format ``{employee}-{attendance_date}`` so a
duplicate insert collides on the primary key. ``working_hours`` is derived from the
optional check-in / check-out timestamps (which the deferred QR/kiosk flow will fill).
"""

import frappe
from frappe.model.document import Document
from frappe.utils import time_diff_in_hours


class StaffAttendance(Document):
    def validate(self):
        self._compute_hours()

    def _compute_hours(self):
        if self.check_in and self.check_out:
            hours = time_diff_in_hours(self.check_out, self.check_in)
            self.working_hours = round(hours, 2) if hours and hours > 0 else 0
        elif not self.check_in and not self.check_out:
            # Leave manually-entered hours untouched only when timings are absent.
            self.working_hours = self.working_hours or 0
