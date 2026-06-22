from decimal import Decimal

import pytest

from upi_payment_tracker import (
    CSVPaymentProvider,
    GOOGLE_TRANSACTION_DETAILS_URL,
    GoogleOmnichannelProvider,
    NormalizedUPIPayment,
    REPORT_NAME,
    UPIImportError,
    build_bank_transaction_doc,
    existing_bank_transaction,
    install_report,
    payment_from_csv_row,
    payment_from_google_transaction,
)


def test_successful_csv_row_is_normalized():
    payment = payment_from_csv_row(
        {
            "date": "07-06-2026",
            "amount": "1,250.50",
            "utr": "612345678901",
            "payer_vpa": "customer@upi",
            "payer_name": "Customer Name",
            "description": "QR payment",
            "status": "SUCCESS",
        },
        row_number=2,
    )

    assert payment == NormalizedUPIPayment(
        date="2026-06-07",
        amount=Decimal("1250.50"),
        utr="612345678901",
        payer_vpa="customer@upi",
        payer_name="Customer Name",
        description="QR payment",
        status="SUCCESS",
    )
    assert payment.transaction_id == "UPI:612345678901"


@pytest.mark.parametrize("status", ["PENDING", "FAILED", ""])
def test_non_success_csv_rows_are_ignored(status):
    assert (
        payment_from_csv_row(
            {
                "date": "2026-06-07",
                "amount": "100",
                "utr": "UTR1",
                "payer_vpa": "",
                "payer_name": "",
                "description": "",
                "status": status,
            },
            row_number=2,
        )
        is None
    )


def test_successful_row_requires_utr():
    with pytest.raises(UPIImportError, match="utr is required"):
        payment_from_csv_row(
            {
                "date": "2026-06-07",
                "amount": "100",
                "utr": "",
                "payer_vpa": "",
                "payer_name": "",
                "description": "",
                "status": "SUCCESS",
            },
            row_number=2,
        )


def test_successful_row_requires_valid_amount():
    with pytest.raises(UPIImportError, match="invalid amount"):
        payment_from_csv_row(
            {
                "date": "2026-06-07",
                "amount": "abc",
                "utr": "UTR1",
                "payer_vpa": "",
                "payer_name": "",
                "description": "",
                "status": "SUCCESS",
            },
            row_number=2,
        )


def test_csv_provider_requires_expected_columns(tmp_path):
    csv_path = tmp_path / "payments.csv"
    csv_path.write_text("date,amount,utr\n2026-06-07,100,UTR1\n", encoding="utf-8")

    with pytest.raises(UPIImportError, match="Missing required CSV column"):
        list(CSVPaymentProvider(csv_path).fetch_payments())


def test_google_success_response_is_normalized():
    payment = payment_from_google_transaction(
        {
            "transactionId": "MERCHANT-1",
            "googleTransactionId": "GOOGLE-1",
            "paymentMode": "UPI",
            "transactionStatus": {"status": "SUCCESS"},
            "upiTransactionDetails": {"upiRrn": "RRN123"},
            "amountPaid": {
                "currencyCode": "INR",
                "units": "100",
                "nanos": 750000000,
            },
            "lastUpdatedTime": "2026-06-07T20:00:00Z",
            "payerAccountType": "UPI_DEBIT",
            "payeeVpa": "merchant@upi",
        },
        row_number=2,
        fallback_description="Order payment",
    )

    assert payment == NormalizedUPIPayment(
        date="2026-06-08",
        amount=Decimal("100.75"),
        utr="RRN123",
        payer_vpa="",
        payer_name="",
        description=(
            "Google Pay Omnichannel | Merchant Txn: MERCHANT-1 | "
            "Google Txn: GOOGLE-1 | Payee VPA: merchant@upi | "
            "Payer Account: UPI_DEBIT | Order payment"
        ),
        status="SUCCESS",
        provider="google_omnichannel",
    )


def test_google_non_success_response_is_ignored():
    assert (
        payment_from_google_transaction(
            {
                "transactionStatus": {"status": "IN_PROGRESS"},
                "amountPaid": {"currencyCode": "INR", "units": "1"},
            },
            row_number=2,
        )
        is None
    )


def test_google_success_response_requires_inr_amount():
    with pytest.raises(UPIImportError, match="expected Google amount currency INR"):
        payment_from_google_transaction(
            {
                "transactionStatus": {"status": "SUCCESS"},
                "upiTransactionDetails": {"upiRrn": "RRN123"},
                "amountPaid": {"currencyCode": "USD", "units": "1"},
                "lastUpdatedTime": "2026-06-08T00:00:00Z",
            },
            row_number=2,
        )


def test_bank_transaction_payload_uses_reconciliation_fields():
    payment = NormalizedUPIPayment(
        date="2026-06-07",
        amount=Decimal("250.00"),
        utr="UTR250",
        payer_vpa="payer@upi",
        payer_name="Payer",
        description="Counter QR",
    )

    doc = build_bank_transaction_doc(payment, bank_account="HDFC Bank - HDFC Bank")

    assert doc["doctype"] == "Bank Transaction"
    assert doc["deposit"] == 250.0
    assert doc["withdrawal"] == 0
    assert doc["transaction_type"] == "UPI"
    assert doc["reference_number"] == "UTR250"
    assert doc["transaction_id"] == "UPI:UTR250"
    assert doc["status"] == "Unreconciled"
    assert doc["bank_party_name"] == "Payer"
    assert doc["bank_party_account_number"] == "payer@upi"
    assert "Counter QR" in doc["description"]


class FakeGoogleResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeGoogleSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def post(self, url, json, timeout):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        return FakeGoogleResponse(self.payload)


def test_google_provider_calls_transaction_details_api(tmp_path):
    csv_path = tmp_path / "google_transactions.csv"
    csv_path.write_text(
        "merchant_transaction_id,description\nMERCHANT-1,Counter QR\n",
        encoding="utf-8",
    )
    session = FakeGoogleSession(
        {
            "transactionId": "MERCHANT-1",
            "googleTransactionId": "GOOGLE-1",
            "transactionStatus": {"status": "SUCCESS"},
            "upiTransactionDetails": {"upiRrn": "RRN123"},
            "amountPaid": {"currencyCode": "INR", "units": "11", "nanos": 0},
            "lastUpdatedTime": "2026-06-08T00:00:00Z",
        }
    )

    provider = GoogleOmnichannelProvider(
        csv_path,
        google_merchant_id="GOOGLE-MERCHANT",
        session=session,
    )
    payments = list(provider.fetch_payments())

    assert len(payments) == 1
    assert payments[0].utr == "RRN123"
    assert session.calls == [
        {
            "url": GOOGLE_TRANSACTION_DETAILS_URL,
            "json": {
                "merchantInfo": {"googleMerchantId": "GOOGLE-MERCHANT"},
                "transactionIdentifier": {
                    "merchantTransactionId": "MERCHANT-1"
                },
            },
            "timeout": 120,
        }
    ]


class FakeERPNextClient:
    def __init__(self, first_result=None, second_result=None):
        self.results = [first_result or [], second_result or []]
        self.calls = []

    def list_resources(self, doctype, **kwargs):
        self.calls.append((doctype, kwargs))
        return self.results.pop(0)


def test_existing_transaction_checks_transaction_id_first():
    payment = NormalizedUPIPayment(
        date="2026-06-07",
        amount=Decimal("100.00"),
        utr="UTR100",
    )
    client = FakeERPNextClient(first_result=[{"name": "ACC-BTN-1"}])

    existing = existing_bank_transaction(client, payment, bank_account="Bank A")

    assert existing == {"name": "ACC-BTN-1"}
    assert len(client.calls) == 1
    filters = client.calls[0][1]["filters"]
    assert ["Bank Transaction", "transaction_id", "=", "UPI:UTR100"] in filters


def test_existing_transaction_falls_back_to_composite_key():
    payment = NormalizedUPIPayment(
        date="2026-06-07",
        amount=Decimal("100.00"),
        utr="UTR100",
    )
    client = FakeERPNextClient(
        first_result=[],
        second_result=[{"name": "ACC-BTN-2"}],
    )

    existing = existing_bank_transaction(client, payment, bank_account="Bank A")

    assert existing == {"name": "ACC-BTN-2"}
    assert len(client.calls) == 2
    filters = client.calls[1][1]["filters"]
    assert ["Bank Transaction", "reference_number", "=", "UTR100"] in filters
    assert ["Bank Transaction", "date", "=", "2026-06-07"] in filters
    assert ["Bank Transaction", "deposit", "=", 100.0] in filters
    assert ["Bank Transaction", "bank_account", "=", "Bank A"] in filters


class FakeReportClient:
    def __init__(self):
        self.upserts = []

    def upsert_resource(self, doctype, name, data):
        self.upserts.append((doctype, name, data))


def test_install_report_uses_erpnext_v16_report_script_field(capsys):
    client = FakeReportClient()

    install_report(client)

    doctype, name, data = client.upserts[0]
    assert doctype == "Report"
    assert name == REPORT_NAME
    assert "report_script" in data
    assert "script" not in data
    assert data["report_script"].strip()
