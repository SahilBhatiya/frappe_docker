# Copyright (c) 2026, Ravindu Gajanayaka
# Licensed under GPLv3. See license.txt

"""Staff Advance — a cash advance paid to an employee, later deducted from a payslip.

Deliberately lightweight (no GL posting): it is a running record of how much an
employee has taken and how much is still to be recovered. `balance` is the amount
not yet deducted; the Payroll API reduces it when a payslip is marked paid.
"""

import frappe
from frappe.model.document import Document
from frappe.utils import flt


class StaffAdvance(Document):
    def validate(self):
        # New advance: balance starts equal to the full amount.
        if self.balance is None:
            self.balance = self.amount

        # Never let the balance drift outside [0, amount].
        self.balance = max(0, min(flt(self.balance), flt(self.amount)))

        self._sync_status()

    def _sync_status(self):
        if self.status == "Cancelled":
            return
        if flt(self.balance) <= 0:
            self.status = "Adjusted"
        elif flt(self.balance) < flt(self.amount):
            self.status = "Partially Adjusted"
        else:
            self.status = "Outstanding"
