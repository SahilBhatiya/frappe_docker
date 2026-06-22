"""
Install and run daily UPI payment tracking for ERPNext.

Creates:
  1. A Script Report named "UPI Payments Today"
  2. A CSV importer that creates submitted Bank Transaction deposits
  3. A Google Pay Omnichannel transaction-status importer

Usage:
  $env:ERPNEXT_API_KEY="..."
  $env:ERPNEXT_API_SECRET="..."
  $env:UPI_BANK_ACCOUNT="HDFC Bank - HDFC Bank"

  python upi_payment_tracker.py install-report
  python upi_payment_tracker.py import-csv payments.csv --dry-run
  python upi_payment_tracker.py import-csv payments.csv
  python upi_payment_tracker.py import-google-transactions google_transactions.csv

CSV columns:
  date, amount, utr, payer_vpa, payer_name, description, status

Google transaction CSV columns:
  merchant_transaction_id, description
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Protocol
from zoneinfo import ZoneInfo

import requests


ERPNEXT_URL = os.getenv("ERPNEXT_URL", "http://localhost:8080").rstrip("/")
API_TIMEOUT = int(os.getenv("ERPNEXT_API_TIMEOUT", "120"))
COMPANY = "ADARSH MOTOR STORES"
CURRENCY = "INR"
TIMEZONE = "Asia/Kolkata"
REPORT_NAME = "UPI Payments Today"
GOOGLE_OMNICHANNEL_SCOPE = "https://www.googleapis.com/auth/nbupaymentsmerchants"
GOOGLE_TRANSACTION_DETAILS_URL = (
    "https://nbupayments.googleapis.com/v1/merchantTransactions:get"
)

SUCCESS_STATUSES = {
    "success",
    "successful",
    "succeeded",
    "settled",
    "completed",
    "complete",
    "paid",
    "credited",
    "credit",
}


class UPIImportError(ValueError):
    """Raised for invalid input rows that should stop an import."""


@dataclass(frozen=True)
class NormalizedUPIPayment:
    date: str
    amount: Decimal
    utr: str
    payer_vpa: str = ""
    payer_name: str = ""
    description: str = ""
    status: str = "success"
    provider: str = "csv"

    @property
    def transaction_id(self) -> str:
        return f"UPI:{self.utr}"

    @property
    def bank_transaction_description(self) -> str:
        parts = ["UPI Payment"]
        if self.payer_name:
            parts.append(f"Payer: {self.payer_name}")
        if self.payer_vpa:
            parts.append(f"VPA: {self.payer_vpa}")
        if self.description:
            parts.append(self.description)
        return " | ".join(parts)


class PaymentProvider(Protocol):
    def fetch_payments(self) -> Iterable[NormalizedUPIPayment]:
        """Return normalized UPI payments from a provider-specific source."""


class CSVPaymentProvider:
    def __init__(self, path: Path):
        self.path = path

    def fetch_payments(self) -> Iterable[NormalizedUPIPayment]:
        with self.path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            missing = required_csv_columns() - set(reader.fieldnames or [])
            if missing:
                raise UPIImportError(
                    "Missing required CSV column(s): " + ", ".join(sorted(missing))
                )

            for row_number, row in enumerate(reader, start=2):
                payment = payment_from_csv_row(row, row_number=row_number)
                if payment:
                    yield payment


class GoogleOmnichannelProvider:
    """Fetch Google Pay Omnichannel transaction status by merchant transaction id."""

    def __init__(
        self,
        path: Path,
        *,
        google_merchant_id: str,
        service_account_file: str | None = None,
        session: object | None = None,
    ):
        self.path = path
        self.google_merchant_id = google_merchant_id
        self.service_account_file = service_account_file
        self.session = session or make_google_authorized_session(service_account_file)

    def fetch_payments(self) -> Iterable[NormalizedUPIPayment]:
        with self.path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            missing = required_google_transaction_columns() - set(reader.fieldnames or [])
            if missing:
                raise UPIImportError(
                    "Missing required Google transaction CSV column(s): "
                    + ", ".join(sorted(missing))
                )

            for row_number, row in enumerate(reader, start=2):
                merchant_transaction_id = clean(row.get("merchant_transaction_id"))
                if not merchant_transaction_id:
                    raise UPIImportError(
                        f"Row {row_number}: merchant_transaction_id is required."
                    )

                details = self.get_transaction_details(merchant_transaction_id)
                payment = payment_from_google_transaction(
                    details,
                    row_number=row_number,
                    fallback_description=clean(row.get("description")),
                )
                if payment:
                    yield payment

    def get_transaction_details(self, merchant_transaction_id: str) -> dict:
        response = self.session.post(
            GOOGLE_TRANSACTION_DETAILS_URL,
            json={
                "merchantInfo": {"googleMerchantId": self.google_merchant_id},
                "transactionIdentifier": {
                    "merchantTransactionId": merchant_transaction_id
                },
            },
            timeout=API_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()


class ERPNextClient:
    def __init__(self, url: str, api_key: str, api_secret: str):
        self.url = url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"token {api_key}:{api_secret}",
                "Content-Type": "application/json",
            }
        )

    def get_resource(self, doctype: str, name: str) -> dict | None:
        response = self.session.get(
            f"{self.url}/api/resource/{doctype}/{requests.utils.quote(str(name), safe='')}",
            timeout=API_TIMEOUT,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json().get("data", {})

    def list_resources(
        self,
        doctype: str,
        *,
        fields: list[str] | None = None,
        filters: list[list[object]] | None = None,
        limit: int = 20,
    ) -> list[dict]:
        params = {"limit_page_length": limit}
        if fields:
            params["fields"] = json.dumps(fields)
        if filters:
            params["filters"] = json.dumps(filters)

        response = self.session.get(
            f"{self.url}/api/resource/{doctype}", params=params, timeout=API_TIMEOUT
        )
        response.raise_for_status()
        return response.json().get("data", [])

    def upsert_resource(self, doctype: str, name: str, data: dict) -> dict:
        if self.get_resource(doctype, name):
            response = self.session.put(
                f"{self.url}/api/resource/{doctype}/{requests.utils.quote(name, safe='')}",
                json={"data": data},
                timeout=API_TIMEOUT,
            )
        else:
            response = self.session.post(
                f"{self.url}/api/resource/{doctype}",
                json={"data": data},
                timeout=API_TIMEOUT,
            )
        response.raise_for_status()
        return response.json().get("data", {})

    def insert_resource(self, doctype: str, data: dict) -> dict:
        response = self.session.post(
            f"{self.url}/api/resource/{doctype}",
            json={"data": data},
            timeout=API_TIMEOUT,
        )
        response.raise_for_status()
        return response.json().get("data", {})

    def submit_doc(self, doc: dict) -> dict:
        response = self.session.post(
            f"{self.url}/api/method/frappe.client.submit",
            json={"doc": json.dumps(doc)},
            timeout=API_TIMEOUT,
        )
        response.raise_for_status()
        return response.json().get("message", {})


REPORT_SCRIPT = r'''
def get_columns():
    return [
        {"fieldname": "date", "label": "Date", "fieldtype": "Date", "width": 105},
        {"fieldname": "deposit", "label": "Amount", "fieldtype": "Currency", "options": "currency", "width": 115},
        {"fieldname": "reference_number", "label": "UTR", "fieldtype": "Data", "width": 160},
        {"fieldname": "payer_name", "label": "Payer", "fieldtype": "Data", "width": 180},
        {"fieldname": "payer_vpa", "label": "Payer VPA", "fieldtype": "Data", "width": 180},
        {"fieldname": "bank_account", "label": "Bank Account", "fieldtype": "Link", "options": "Bank Account", "width": 230},
        {"fieldname": "status", "label": "Reconciliation", "fieldtype": "Data", "width": 120},
        {"fieldname": "description", "label": "Description", "fieldtype": "Small Text", "width": 260},
        {"fieldname": "name", "label": "Bank Transaction", "fieldtype": "Link", "options": "Bank Transaction", "width": 170},
    ]


def get_data(filters):
    conditions = [
        "bt.docstatus = 1",
        "bt.deposit > 0",
        "bt.transaction_type = 'UPI'",
        "bt.date BETWEEN %(from_date)s AND %(to_date)s",
    ]
    if filters.get("bank_account"):
        conditions.append("bt.bank_account = %(bank_account)s")

    return frappe.db.sql(
        f"""
        SELECT
            bt.name,
            bt.date,
            bt.deposit,
            bt.currency,
            bt.reference_number,
            bt.bank_party_name AS payer_name,
            bt.bank_party_account_number AS payer_vpa,
            bt.bank_account,
            bt.status,
            bt.description
        FROM `tabBank Transaction` bt
        WHERE {" AND ".join(conditions)}
        ORDER BY bt.date DESC, bt.creation DESC
        """,
        filters,
        as_dict=True,
    )


def get_summary(data):
    total = sum(row.deposit for row in data)
    unreconciled = sum(1 for row in data if row.status != "Reconciled")
    return [
        {"value": len(data), "label": "UPI Payments", "datatype": "Int", "indicator": "Blue"},
        {"value": total, "label": "Total UPI Received", "datatype": "Currency", "indicator": "Green"},
        {"value": unreconciled, "label": "Unreconciled", "datatype": "Int", "indicator": "Orange"},
    ]


def get_chart(data):
    by_date = {}
    for row in data:
        key = str(row.date)
        by_date[key] = by_date.get(key, 0) + row.deposit

    labels = sorted(by_date)
    if not labels:
        return None

    return {
        "data": {
            "labels": labels,
            "datasets": [{"name": "UPI Received", "values": [by_date[label] for label in labels]}],
        },
        "type": "bar",
        "fieldtype": "Currency",
        "title": "UPI Received by Date",
    }


if not filters.get("from_date"):
    filters["from_date"] = frappe.utils.nowdate()
if not filters.get("to_date"):
    filters["to_date"] = frappe.utils.nowdate()

columns = get_columns()
rows = get_data(filters)
summary = get_summary(rows)
chart = get_chart(rows)
data = [columns, rows, None, chart, summary]
'''

REPORT_JS = r'''
frappe.query_reports["UPI Payments Today"] = {
    filters: [
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
            reqd: 1,
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
            reqd: 1,
        },
        {
            fieldname: "bank_account",
            label: __("Bank Account"),
            fieldtype: "Link",
            options: "Bank Account",
        },
    ],

    formatter: function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (!data) return value;

        if (column.fieldname === "status") {
            const color = data.status === "Reconciled" ? "green" : "orange";
            return `<span class="indicator-pill ${color}">${data.status || ""}</span>`;
        }
        return value;
    },
};
'''


def required_csv_columns() -> set[str]:
    return {"date", "amount", "utr", "payer_vpa", "payer_name", "description", "status"}


def required_google_transaction_columns() -> set[str]:
    return {"merchant_transaction_id"}


def payment_from_csv_row(
    row: dict[str, str], *, row_number: int
) -> NormalizedUPIPayment | None:
    status = clean(row.get("status"))
    if status.lower() not in SUCCESS_STATUSES:
        return None

    utr = clean(row.get("utr"))
    if not utr:
        raise UPIImportError(f"Row {row_number}: utr is required for successful payments.")

    amount_text = clean(row.get("amount")).replace(",", "")
    try:
        amount = Decimal(amount_text)
    except InvalidOperation as exc:
        raise UPIImportError(f"Row {row_number}: invalid amount {amount_text!r}.") from exc

    if amount <= 0:
        raise UPIImportError(f"Row {row_number}: amount must be greater than zero.")

    return NormalizedUPIPayment(
        date=parse_date(clean(row.get("date")), row_number=row_number),
        amount=amount.quantize(Decimal("0.01")),
        utr=utr,
        payer_vpa=clean(row.get("payer_vpa")),
        payer_name=clean(row.get("payer_name")),
        description=clean(row.get("description")),
        status=status,
    )


def payment_from_google_transaction(
    data: dict, *, row_number: int, fallback_description: str = ""
) -> NormalizedUPIPayment | None:
    status = clean((data.get("transactionStatus") or {}).get("status"))
    if status.lower() not in SUCCESS_STATUSES:
        return None

    upi_details = data.get("upiTransactionDetails") or {}
    utr = clean(upi_details.get("upiRrn")) or clean(data.get("googleTransactionId"))
    if not utr:
        raise UPIImportError(
            f"Row {row_number}: Google transaction response did not include "
            "upiTransactionDetails.upiRrn or googleTransactionId."
        )

    amount = google_money_to_decimal(data.get("amountPaid") or {}, row_number=row_number)
    merchant_transaction_id = clean(data.get("transactionId"))
    google_transaction_id = clean(data.get("googleTransactionId"))
    payee_vpa = clean(data.get("payeeVpa"))
    payer_account_type = clean(data.get("payerAccountType"))

    description_parts = ["Google Pay Omnichannel"]
    if merchant_transaction_id:
        description_parts.append(f"Merchant Txn: {merchant_transaction_id}")
    if google_transaction_id:
        description_parts.append(f"Google Txn: {google_transaction_id}")
    if payee_vpa:
        description_parts.append(f"Payee VPA: {payee_vpa}")
    if payer_account_type:
        description_parts.append(f"Payer Account: {payer_account_type}")
    if fallback_description:
        description_parts.append(fallback_description)

    return NormalizedUPIPayment(
        date=parse_google_updated_date(clean(data.get("lastUpdatedTime")), row_number),
        amount=amount,
        utr=utr,
        payer_vpa="",
        payer_name="",
        description=" | ".join(description_parts),
        status=status,
        provider="google_omnichannel",
    )


def google_money_to_decimal(value: dict, *, row_number: int) -> Decimal:
    if clean(value.get("currencyCode")) != CURRENCY:
        raise UPIImportError(
            f"Row {row_number}: expected Google amount currency {CURRENCY}, "
            f"got {clean(value.get('currencyCode')) or 'missing'}."
        )

    units = clean(value.get("units")) or "0"
    nanos = clean(value.get("nanos")) or "0"
    try:
        amount = Decimal(units) + (Decimal(nanos) / Decimal("1000000000"))
    except InvalidOperation as exc:
        raise UPIImportError(f"Row {row_number}: invalid Google amount.") from exc

    if amount <= 0:
        raise UPIImportError(f"Row {row_number}: Google amount must be greater than zero.")
    return amount.quantize(Decimal("0.01"))


def parse_google_updated_date(value: str, row_number: int) -> str:
    if not value:
        return datetime.now(ZoneInfo(TIMEZONE)).date().isoformat()

    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise UPIImportError(
            f"Row {row_number}: invalid Google lastUpdatedTime {value!r}."
        ) from exc

    return parsed.astimezone(ZoneInfo(TIMEZONE)).date().isoformat()


def parse_date(value: str, *, row_number: int) -> str:
    if not value:
        raise UPIImportError(f"Row {row_number}: date is required.")

    for date_format in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, date_format).date().isoformat()
        except ValueError:
            pass

    raise UPIImportError(
        f"Row {row_number}: invalid date {value!r}; use YYYY-MM-DD or DD-MM-YYYY."
    )


def clean(value: object) -> str:
    return str(value or "").strip()


def decimal_for_erpnext(value: Decimal) -> float:
    return float(value)


def build_bank_transaction_doc(
    payment: NormalizedUPIPayment, *, bank_account: str
) -> dict:
    return {
        "doctype": "Bank Transaction",
        "naming_series": "ACC-BTN-.YYYY.-",
        "date": payment.date,
        "status": "Unreconciled",
        "bank_account": bank_account,
        "company": COMPANY,
        "deposit": decimal_for_erpnext(payment.amount),
        "withdrawal": 0,
        "currency": CURRENCY,
        "description": payment.bank_transaction_description,
        "reference_number": payment.utr,
        "transaction_id": payment.transaction_id,
        "transaction_type": "UPI",
        "bank_party_name": payment.payer_name,
        "bank_party_account_number": payment.payer_vpa,
    }


def existing_bank_transaction(
    client: ERPNextClient, payment: NormalizedUPIPayment, *, bank_account: str
) -> dict | None:
    by_transaction_id = client.list_resources(
        "Bank Transaction",
        fields=["name", "date", "deposit", "reference_number", "transaction_id"],
        filters=[
            ["Bank Transaction", "transaction_id", "=", payment.transaction_id],
            ["Bank Transaction", "bank_account", "=", bank_account],
        ],
        limit=1,
    )
    if by_transaction_id:
        return by_transaction_id[0]

    by_composite = client.list_resources(
        "Bank Transaction",
        fields=["name", "date", "deposit", "reference_number", "transaction_id"],
        filters=[
            ["Bank Transaction", "reference_number", "=", payment.utr],
            ["Bank Transaction", "date", "=", payment.date],
            ["Bank Transaction", "deposit", "=", decimal_for_erpnext(payment.amount)],
            ["Bank Transaction", "bank_account", "=", bank_account],
        ],
        limit=1,
    )
    return by_composite[0] if by_composite else None


def import_payments(
    client: ERPNextClient,
    provider: PaymentProvider,
    *,
    bank_account: str,
    dry_run: bool,
) -> dict[str, int]:
    stats = {"seen": 0, "inserted": 0, "skipped_duplicate": 0, "dry_run": 0}
    for payment in provider.fetch_payments():
        stats["seen"] += 1
        existing = existing_bank_transaction(client, payment, bank_account=bank_account)
        if existing:
            stats["skipped_duplicate"] += 1
            print(f"SKIP duplicate {payment.utr}: {existing.get('name')}")
            continue

        doc = build_bank_transaction_doc(payment, bank_account=bank_account)
        if dry_run:
            stats["dry_run"] += 1
            print(
                f"DRY RUN insert UTR {payment.utr}: "
                f"{payment.date} INR {payment.amount} into {bank_account}"
            )
            continue

        inserted = client.insert_resource("Bank Transaction", doc)
        submitted = client.submit_doc(inserted)
        stats["inserted"] += 1
        print(f"INSERTED {submitted.get('name', inserted.get('name'))}: UTR {payment.utr}")

    return stats


def install_report(client: ERPNextClient) -> None:
    data = {
        "report_name": REPORT_NAME,
        "report_type": "Script Report",
        "ref_doctype": "Bank Transaction",
        "is_standard": "No",
        "disabled": 0,
        "report_script": REPORT_SCRIPT,
        "javascript": REPORT_JS,
    }
    client.upsert_resource("Report", REPORT_NAME, data)
    print(f"Installed report: {REPORT_NAME}")
    print(f"Open: {ERPNEXT_URL}/app/query-report/UPI%20Payments%20Today")


def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise UPIImportError(f"{name} environment variable is required.")
    return value


def make_client() -> ERPNextClient:
    return ERPNextClient(
        ERPNEXT_URL,
        get_required_env("ERPNEXT_API_KEY"),
        get_required_env("ERPNEXT_API_SECRET"),
    )


def make_google_authorized_session(service_account_file: str | None = None):
    credential_path = service_account_file or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not credential_path:
        raise UPIImportError(
            "GOOGLE_APPLICATION_CREDENTIALS is required for Google Pay API import."
        )

    try:
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2 import service_account
    except ImportError as exc:
        raise UPIImportError(
            "google-auth is required for Google Pay API import. Install it with "
            "`pip install google-auth`."
        ) from exc

    credentials = service_account.Credentials.from_service_account_file(
        credential_path,
        scopes=[GOOGLE_OMNICHANNEL_SCOPE],
    )
    return AuthorizedSession(credentials)


def resolve_bank_account(args: argparse.Namespace) -> str:
    bank_account = args.bank_account or os.getenv("UPI_BANK_ACCOUNT")
    if not bank_account:
        raise UPIImportError(
            "UPI_BANK_ACCOUNT is required. Set it in the environment or pass "
            "--bank-account because this ERPNext site has multiple bank accounts."
        )
    return bank_account


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Track daily UPI payments in ERPNext Bank Transaction records."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    install_parser = subparsers.add_parser("install-report")
    install_parser.set_defaults(func=command_install_report)

    import_parser = subparsers.add_parser("import-csv")
    import_parser.add_argument("csv_path", type=Path)
    import_parser.add_argument("--bank-account")
    import_parser.add_argument("--dry-run", action="store_true")
    import_parser.set_defaults(func=command_import_csv)

    google_parser = subparsers.add_parser("import-google-transactions")
    google_parser.add_argument("csv_path", type=Path)
    google_parser.add_argument("--bank-account")
    google_parser.add_argument("--dry-run", action="store_true")
    google_parser.add_argument(
        "--google-merchant-id",
        default=os.getenv("GOOGLE_PAY_MERCHANT_ID"),
        help="Google Pay merchant id; defaults to GOOGLE_PAY_MERCHANT_ID.",
    )
    google_parser.add_argument(
        "--google-service-account",
        default=os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
        help="Path to Google service-account JSON; defaults to GOOGLE_APPLICATION_CREDENTIALS.",
    )
    google_parser.set_defaults(func=command_import_google_transactions)

    list_parser = subparsers.add_parser("list-bank-accounts")
    list_parser.set_defaults(func=command_list_bank_accounts)
    return parser


def command_install_report(args: argparse.Namespace) -> int:
    install_report(make_client())
    return 0


def command_import_csv(args: argparse.Namespace) -> int:
    if not args.csv_path.exists():
        raise UPIImportError(f"CSV file not found: {args.csv_path}")

    client = make_client()
    bank_account = resolve_bank_account(args)
    if not client.get_resource("Bank Account", bank_account):
        raise UPIImportError(f"Bank Account not found in ERPNext: {bank_account}")

    stats = import_payments(
        client,
        CSVPaymentProvider(args.csv_path),
        bank_account=bank_account,
        dry_run=args.dry_run,
    )
    print(
        "Done. "
        f"Seen: {stats['seen']}, Inserted: {stats['inserted']}, "
        f"Duplicates: {stats['skipped_duplicate']}, Dry-run: {stats['dry_run']}"
    )
    return 0


def command_import_google_transactions(args: argparse.Namespace) -> int:
    if not args.csv_path.exists():
        raise UPIImportError(f"CSV file not found: {args.csv_path}")
    if not args.google_merchant_id:
        raise UPIImportError(
            "GOOGLE_PAY_MERCHANT_ID is required. Set it in the environment or pass "
            "--google-merchant-id."
        )

    client = make_client()
    bank_account = resolve_bank_account(args)
    if not client.get_resource("Bank Account", bank_account):
        raise UPIImportError(f"Bank Account not found in ERPNext: {bank_account}")

    stats = import_payments(
        client,
        GoogleOmnichannelProvider(
            args.csv_path,
            google_merchant_id=args.google_merchant_id,
            service_account_file=args.google_service_account,
        ),
        bank_account=bank_account,
        dry_run=args.dry_run,
    )
    print(
        "Done. "
        f"Seen: {stats['seen']}, Inserted: {stats['inserted']}, "
        f"Duplicates: {stats['skipped_duplicate']}, Dry-run: {stats['dry_run']}"
    )
    return 0


def command_list_bank_accounts(args: argparse.Namespace) -> int:
    rows = make_client().list_resources(
        "Bank Account",
        fields=["name", "account_name", "bank", "account", "is_company_account"],
        filters=[["Bank Account", "is_company_account", "=", 1]],
        limit=200,
    )
    for row in rows:
        print(f"{row['name']}  ->  {row.get('account', '')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except requests.HTTPError as exc:
        response_text = exc.response.text[:500] if exc.response is not None else ""
        print(f"ERPNext API error: {exc}\n{response_text}", file=sys.stderr)
        return 1
    except requests.RequestException as exc:
        print(f"ERPNext connection error: {exc}", file=sys.stderr)
        return 1
    except UPIImportError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
