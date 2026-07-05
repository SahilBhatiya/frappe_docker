# Copyright (c) 2026, Ravindu Gajanayaka
# Licensed under GPLv3. See license.txt

"""Staff Payslip — a monthly pay record for one employee.

net_pay = base_salary - total_advance_deducted + adjustment

The advance deductions are held in the child table and only *applied* to the linked
Staff Advance balances when the payslip is marked Paid (done in the Payroll API), so a
Draft payslip can be freely re-edited without touching advance balances.
"""

import frappe
from frappe.model.document import Document
from frappe.utils import flt


class StaffPayslip(Document):
    def validate(self):
        self.total_advance_deducted = sum(flt(r.amount_deducted) for r in (self.advances or []))
        self.net_pay = flt(self.base_salary) - flt(self.total_advance_deducted) + flt(self.adjustment)
