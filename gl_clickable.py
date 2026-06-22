"""
Install a Client Script on the General Ledger report.
Makes Voucher No, Party, and Account columns clickable — opens a detail dialog.
Run: python gl_clickable.py
"""

import requests

ERPNEXT_URL = "http://localhost:8080"
API_KEY     = "12d80506c40944c"
API_SECRET  = "903ef51e33f8869"
HEADERS     = {
    "Authorization": f"token {API_KEY}:{API_SECRET}",
    "Content-Type":  "application/json",
}

SCRIPT_NAME = "GL Clickable Details"

CLIENT_SCRIPT = r"""
(function () {
    'use strict';

    /* ── helpers ─────────────────────────────────────────────────── */
    function esc(v) { return frappe.utils.escape_html(String(v || '')); }

    function fmtCurrency(v) {
        return v != null ? frappe.format(v, { fieldtype: 'Currency' }) : '—';
    }

    function badge(label, color) {
        const c = { 'Paid': 'green', 'Unpaid': 'red', 'Partly Paid': 'orange',
                    'Submitted': 'blue', 'Cancelled': 'red', 'Draft': 'grey',
                    'Active': 'green' }[label] || color || 'grey';
        return `<span class="badge badge-${c}" style="font-size:0.82em">${esc(label)}</span>`;
    }

    function row(label, value) {
        if (value === null || value === undefined || value === '') return '';
        return `<tr>
            <th style="width:38%;font-weight:600;color:var(--text-muted);
                       padding:6px 10px;white-space:nowrap">${esc(label)}</th>
            <td style="padding:6px 10px">${value}</td>
        </tr>`;
    }

    function table(rows) {
        return `<table class="table table-bordered table-condensed" style="margin:0">
            <tbody>${rows.join('')}</tbody>
        </table>`;
    }

    function itemsTable(items, cols) {
        if (!items || !items.length) return '';
        const head = cols.map(c => `<th>${esc(c.label)}</th>`).join('');
        const body = items.map(it =>
            `<tr>${cols.map(c => `<td>${it[c.field] != null ? esc(it[c.field]) : ''}</td>`).join('')}</tr>`
        ).join('');
        return `<div style="margin-top:12px;font-weight:600;margin-bottom:4px">Items</div>
            <table class="table table-bordered table-condensed" style="font-size:0.85em">
            <thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
    }

    /* ── per-doctype summary builders ────────────────────────────── */
    function buildHtml(doctype, doc) {
        const openBtn = `<a href="/app/${frappe.router.slug(doctype)}/${encodeURIComponent(doc.name)}"
            target="_blank" class="btn btn-xs btn-default" style="float:right;margin-top:-4px">
            Open ↗</a>`;

        let mainRows = [], extra = '';

        if (doctype === 'Sales Invoice') {
            mainRows = [
                row('Customer',     esc(doc.customer)),
                row('Date',         esc(doc.posting_date)),
                row('Status',       badge(doc.status)),
                row('Taxable Value',fmtCurrency(doc.net_total)),
                row('Grand Total',  fmtCurrency(doc.grand_total)),
                row('Tax Amount',   fmtCurrency(doc.total_taxes_and_charges)),
                row('Outstanding',  fmtCurrency(doc.outstanding_amount)),
                row('Voucher No',   esc(doc.name)),
            ];
            extra = itemsTable(doc.items, [
                {label:'Item', field:'item_code'},
                {label:'Qty',  field:'qty'},
                {label:'Rate', field:'rate'},
                {label:'Amount', field:'amount'},
            ]);

        } else if (doctype === 'Purchase Invoice') {
            mainRows = [
                row('Supplier',     esc(doc.supplier)),
                row('Bill No',      esc(doc.bill_no)),
                row('Date',         esc(doc.posting_date)),
                row('Status',       badge(doc.status)),
                row('Grand Total',  fmtCurrency(doc.grand_total)),
                row('Outstanding',  fmtCurrency(doc.outstanding_amount)),
            ];
            extra = itemsTable(doc.items, [
                {label:'Item', field:'item_code'},
                {label:'Qty',  field:'qty'},
                {label:'Rate', field:'rate'},
                {label:'Amount', field:'amount'},
            ]);

        } else if (doctype === 'Payment Entry') {
            mainRows = [
                row('Type',         esc(doc.payment_type)),
                row('Party',        esc(doc.party)),
                row('Date',         esc(doc.posting_date)),
                row('Mode',         esc(doc.mode_of_payment)),
                row('Paid Amount',  fmtCurrency(doc.paid_amount)),
                row('Reference No', esc(doc.reference_no)),
                row('Reference Date', esc(doc.reference_date)),
            ];
            if (doc.references && doc.references.length) {
                extra = `<div style="margin-top:12px;font-weight:600;margin-bottom:4px">Applied Against</div>
                    <table class="table table-bordered table-condensed" style="font-size:0.85em">
                    <thead><tr><th>Invoice</th><th>Type</th><th>Allocated</th></tr></thead>
                    <tbody>${doc.references.map(r =>
                        `<tr><td>${esc(r.reference_name)}</td><td>${esc(r.reference_doctype)}</td>
                         <td>${fmtCurrency(r.allocated_amount)}</td></tr>`
                    ).join('')}</tbody></table>`;
            }

        } else if (doctype === 'Journal Entry') {
            mainRows = [
                row('Date',     esc(doc.posting_date)),
                row('Type',     esc(doc.voucher_type)),
                row('Remark',   esc(doc.user_remark || doc.remark)),
            ];
            extra = `<div style="margin-top:12px;font-weight:600;margin-bottom:4px">Accounts</div>
                <table class="table table-bordered table-condensed" style="font-size:0.85em">
                <thead><tr><th>Account</th><th>Debit</th><th>Credit</th></tr></thead>
                <tbody>${(doc.accounts || []).map(a =>
                    `<tr><td>${esc(a.account)}</td>
                     <td>${fmtCurrency(a.debit_in_account_currency)}</td>
                     <td>${fmtCurrency(a.credit_in_account_currency)}</td></tr>`
                ).join('')}</tbody></table>`;

        } else if (doctype === 'Customer') {
            mainRows = [
                row('Name',   esc(doc.customer_name)),
                row('GSTIN',  esc(doc.gstin || doc.tax_id)),
                row('Type',   esc(doc.customer_type)),
                row('Mobile', esc(doc.mobile_no)),
            ];

        } else if (doctype === 'Supplier') {
            mainRows = [
                row('Name',   esc(doc.supplier_name)),
                row('GSTIN',  esc(doc.tax_id)),
                row('Type',   esc(doc.supplier_type)),
            ];

        } else if (doctype === 'Account') {
            mainRows = [
                row('Type',    esc(doc.account_type)),
                row('Parent',  esc(doc.parent_account)),
                row('Currency',esc(doc.account_currency)),
                row('Group?',  doc.is_group ? 'Yes' : 'No'),
            ];

        } else {
            // generic fallback
            mainRows = Object.entries(doc)
                .filter(([k,v]) => v && typeof v === 'string' && !k.startsWith('_'))
                .slice(0, 12)
                .map(([k,v]) => row(frappe.meta.get_label(doctype, k) || k, esc(v)));
        }

        return `<div>${openBtn}<h5 style="margin:0 0 10px">${esc(doctype)}: ${esc(doc.name)}</h5>
            ${table(mainRows)}${extra}</div>`;
    }

    /* ── open dialog ─────────────────────────────────────────────── */
    function showDialog(doctype, docname) {
        frappe.call({
            method: 'frappe.client.get',
            args: { doctype, name: docname },
            freeze: true,
            freeze_message: __('Loading…'),
            callback: function (r) {
                if (!r.message) { frappe.msgprint(__('Document not found.')); return; }
                let d = new frappe.ui.Dialog({
                    title: `${doctype} — ${docname}`,
                    size: 'extra-large',
                });
                $(d.body).css({ padding: '16px', overflowY: 'auto', maxHeight: '72vh' })
                         .html(buildHtml(doctype, r.message));
                d.show();
            },
        });
    }

    /* ── formatter: make cells clickable ─────────────────────────── */
    function makeLink(dt, dn, display) {
        return `<a href="#" class="gl-detail-link"
            data-dt="${esc(dt)}" data-dn="${esc(dn)}"
            style="color:var(--blue-500);text-decoration:underline dotted;cursor:pointer"
            title="Click for details">${display}</a>`;
    }

    /* ── hook into report ────────────────────────────────────────── */
    frappe.provide('frappe.query_reports');

    let _orig = (frappe.query_reports['General Ledger'] || {}).formatter;

    Object.assign(frappe.query_reports['General Ledger'] = frappe.query_reports['General Ledger'] || {}, {

        formatter: function (value, row, column, data, default_formatter) {
            let out = _orig
                ? _orig(value, row, column, data, default_formatter)
                : default_formatter(value, row, column, data);

            if (!value || !data) return out;

            if (column.fieldname === 'voucher_no' && data.voucher_type)
                out = makeLink(data.voucher_type, value, out);

            else if (column.fieldname === 'party' && data.party_type)
                out = makeLink(data.party_type, value, out);

            else if (column.fieldname === 'account')
                out = makeLink('Account', value, out);

            return out;
        },

        onload: function (report) {
            /* delegate click on the entire report wrapper — works after every re-render */
            $(report.page.main).off('click.gl_detail').on('click.gl_detail', 'a.gl-detail-link', function (e) {
                e.preventDefault();
                e.stopPropagation();
                showDialog($(this).data('dt'), $(this).data('dn'));
            });
        },
    });
})();
"""

def install():
    print("Installing JavaScript on Report: General Ledger...")
    r = requests.put(
        f"{ERPNEXT_URL}/api/resource/Report/{requests.utils.quote('General Ledger')}",
        headers=HEADERS,
        json={"data": {"javascript": CLIENT_SCRIPT}},
        timeout=30,
    )
    if r.status_code in (200, 201):
        print("  Success.")
    else:
        print(f"  WARN [{r.status_code}]: {r.text[:400]}")
        # Fallback: Client Script on GL Entry with Report view
        print("  Trying Client Script on GL Entry (Report view)...")
        cs_data = {
            "dt":      "GL Entry",
            "script":  CLIENT_SCRIPT,
            "enabled": 1,
            "view":    "Report",
        }
        r2 = requests.post(
            f"{ERPNEXT_URL}/api/resource/Client Script",
            headers=HEADERS,
            json={"data": cs_data},
            timeout=30,
        )
        if r2.status_code in (200, 201):
            print(f"  Client Script created: {r2.json().get('data', {}).get('name', '')}")
        else:
            print(f"  Also failed: {r2.text[:300]}")

if __name__ == "__main__":
    install()
    print("\nDone. Hard-refresh the General Ledger report (Ctrl+Shift+R) to activate.")
