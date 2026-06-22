frappe.ui.form.on("Customer", {
    refresh(frm) {
        setTimeout(() => _setup_ledger_tab(frm), 0);
    }
});

function _setup_ledger_tab(frm) {
    const layout = frm.layout;
    if (!layout?.tab_link_container || !layout?.tabs_content) return;

    if (layout.tab_link_container.find('[data-fieldname="ledger_tab"]').length) return;

    const tab_id = "customer-ledger_tab";

    const $tab_link_li = $(`
        <li class="nav-item show">
            <button class="nav-link"
                id="${tab_id}-tab"
                data-fieldname="ledger_tab"
                type="button"
                role="tab"
                aria-controls="${tab_id}">
                    ${__("Ledger")}
            </button>
        </li>
    `).appendTo(layout.tab_link_container);

    const today = frappe.datetime.get_today();
    const fy_year = today >= today.substring(0, 4) + "-04-01"
        ? today.substring(0, 4)
        : String(parseInt(today.substring(0, 4)) - 1);
    const year_start = frappe.defaults.get_default("year_start_date") || (fy_year + "-04-01");

    const $tab_pane = $(`
        <div class="tab-pane fade show" id="${tab_id}"
            role="tabpanel" aria-labelledby="${tab_id}-tab">
            <div style="padding:16px;">
                <div style="display:flex; gap:12px; align-items:flex-end; flex-wrap:wrap; margin-bottom:16px;">
                    <div>
                        <label style="font-size:11px;color:#6c757d;display:block;">${__("From Date")}</label>
                        <input type="date" class="ledger-from-date form-control form-control-sm" style="width:150px;" value="${year_start}">
                    </div>
                    <div>
                        <label style="font-size:11px;color:#6c757d;display:block;">${__("To Date")}</label>
                        <input type="date" class="ledger-to-date form-control form-control-sm" style="width:150px;" value="${today}">
                    </div>
                    <button class="btn btn-sm btn-primary ledger-fetch-btn">${__("Show")}</button>
                    <div style="margin-left:auto;">
                        <button class="btn btn-sm btn-default ledger-fullreport-btn">${__("View Full Report ↗")}</button>
                    </div>
                </div>
                <div class="ledger-table-wrapper"></div>
            </div>
        </div>
    `).appendTo(layout.tabs_content);

    $tab_link_li.find("button").on("click", function (e) {
        e.preventDefault();
        layout.tab_link_container.find(".nav-link").removeClass("active");
        layout.tabs_content.find(".tab-pane").removeClass("show active");
        $(this).addClass("active");
        $tab_pane.addClass("show active");
        if (!$tab_pane.data("loaded")) {
            $tab_pane.data("loaded", true);
            _load_ledger(frm, $tab_pane);
        }
    });

    $tab_pane.find(".ledger-fetch-btn").on("click", () => _load_ledger(frm, $tab_pane));

    $tab_pane.find(".ledger-fullreport-btn").on("click", () => {
        const from_date = $tab_pane.find(".ledger-from-date").val();
        const to_date   = $tab_pane.find(".ledger-to-date").val();
        const company   = frappe.defaults.get_default("company");
        const params = new URLSearchParams({
            company:   company,
            from_date: from_date,
            to_date:   to_date,
            party_type: "Customer",
            party:      JSON.stringify([frm.doc.name]),
            categorize_by: "Categorize by Voucher (Consolidated)",
            include_default_book_entries: 1
        });
        frappe.set_route("query-report/General Ledger?" + params.toString());
    });
}

function _load_ledger(frm, $tab_pane) {
    const from_date = $tab_pane.find(".ledger-from-date").val();
    const to_date   = $tab_pane.find(".ledger-to-date").val();
    const company   = frappe.defaults.get_default("company");
    const $wrapper  = $tab_pane.find(".ledger-table-wrapper");

    $wrapper.html(`<div style="text-align:center;padding:20px;color:#6c757d;">${__("Loading…")}</div>`);

    frappe.call({
        method: "frappe.desk.query_report.run",
        args: {
            report_name: "General Ledger",
            filters: {
                company:   company,
                from_date: from_date,
                to_date:   to_date,
                party_type: "Customer",
                party:      [frm.doc.name],
                categorize_by: "Categorize by Voucher (Consolidated)",
                include_default_book_entries: 1
            },
            ignore_prepared_report: 1
        },
        callback(r) {
            if (r.exc || !r.message) return;
            _render_gl($wrapper, r.message);
        }
    });
}

function _render_gl($wrapper, report) {
    const rows = report.result || [];
    if (!rows.length) {
        $wrapper.html(`<div style="padding:20px;color:#6c757d;">${__("No entries found.")}</div>`);
        return;
    }

    const fc = (v) => (v !== undefined && v !== null && v !== 0 && v !== "")
        ? format_number(Math.abs(flt(v)), null, 2) : "";

    let tbody = "";
    for (const row of rows) {
        // Opening / Total / Closing summary rows have no posting_date
        const is_summary = !row.posting_date;
        const style = is_summary
            ? 'style="font-weight:700;background:#f8f9fa;"'
            : "";
        const colspan_label = is_summary
            ? `<td colspan="4" style="text-align:right;">${frappe.utils.escape_html(row.account || "")}</td>`
            : `<td>${row.posting_date ? frappe.datetime.str_to_user(row.posting_date) : ""}</td>
               <td>${frappe.utils.escape_html(row.account || "")}</td>
               <td>${frappe.utils.escape_html(row.voucher_type || "")}</td>
               <td>${row.voucher_no
                   ? `<a href="#" onclick="frappe.set_route('Form','${row.voucher_type}','${row.voucher_no}');return false;">${frappe.utils.escape_html(row.voucher_no)}</a>`
                   : ""}</td>`;

        // Balance sign: positive = Dr, negative = Cr
        const bal = flt(row.balance);
        const bal_display = bal !== 0
            ? fc(bal) + " " + (bal >= 0 ? "Dr" : "Cr")
            : (is_summary ? fc(bal) : "");

        tbody += `<tr ${style}>
            ${colspan_label}
            <td style="text-align:right;color:#c0392b;">${fc(row.debit)}</td>
            <td style="text-align:right;color:#1a7a4a;">${fc(row.credit)}</td>
            <td style="text-align:right;">${bal_display}</td>
        </tr>`;
    }

    $wrapper.html(`
        <div class="ledger-scroll-wrapper" style="overflow:auto;max-width:100%;-webkit-overflow-scrolling:touch;touch-action:pan-x pan-y;">
            <table class="table table-bordered table-hover" style="font-size:12px;margin-bottom:0;">
                <thead style="background:#eef2f5;position:sticky;top:0;z-index:1;">
                    <tr>
                        <th style="min-width:90px;">${__("Date")}</th>
                        <th style="min-width:180px;">${__("Account")}</th>
                        <th style="min-width:110px;">${__("Vch Type")}</th>
                        <th style="min-width:150px;">${__("Vch No.")}</th>
                        <th style="min-width:110px;text-align:right;">${__("Debit (INR)")}</th>
                        <th style="min-width:110px;text-align:right;">${__("Credit (INR)")}</th>
                        <th style="min-width:130px;text-align:right;">${__("Balance (INR)")}</th>
                    </tr>
                </thead>
                <tbody>${tbody}</tbody>
            </table>
        </div>
    `);
}
