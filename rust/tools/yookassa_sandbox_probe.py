from __future__ import annotations

"""TEST-only YooKassa smoke probe for the licensing server.

The probe intentionally reads only *_TEST_* credentials. It creates a 1 RUB
payment in a YooKassa test shop with capture disabled; it never completes or
captures a payment and never reads production credentials.
"""

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
import uuid

API_URL = "https://api.yookassa.ru/v3/payments"


def required_test_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing TEST credential: {name}")
    return value


def build_probe_payload(probe_id: str) -> dict:
    return {
        "amount": {"value": "1.00", "currency": "RUB"},
        "capture": False,
        "confirmation": {
            "type": "redirect",
            "return_url": "https://example.invalid/dokkomplekt-yookassa-sandbox",
        },
        "description": "Dokkomplekt TEST-only YooKassa integration probe",
        "metadata": {
            "dokkomplekt_probe": probe_id,
            "environment": "test-only",
        },
    }


def validate_probe_response(response: dict, probe_id: str) -> None:
    if not str(response.get("id") or "").strip():
        raise RuntimeError("YooKassa response has no payment id")
    amount = response.get("amount") if isinstance(response.get("amount"), dict) else {}
    if amount.get("value") != "1.00" or amount.get("currency") != "RUB":
        raise RuntimeError(f"Unexpected TEST payment amount: {amount!r}")
    metadata = response.get("metadata") if isinstance(response.get("metadata"), dict) else {}
    if metadata.get("dokkomplekt_probe") != probe_id or metadata.get("environment") != "test-only":
        raise RuntimeError(f"TEST payment metadata mismatch: {metadata!r}")
    if response.get("paid") is True:
        raise RuntimeError("Sandbox probe unexpectedly returned an already-paid payment")
    status = str(response.get("status") or "")
    if status not in {"pending", "waiting_for_capture"}:
        raise RuntimeError(f"Unexpected TEST payment status: {status!r}")


def run_probe() -> dict:
    shop_id = required_test_env("DOKKOMPLEKT_YOOKASSA_TEST_SHOP_ID")
    secret_key = required_test_env("DOKKOMPLEKT_YOOKASSA_TEST_SECRET_KEY")
    probe_id = uuid.uuid4().hex
    payload = build_probe_payload(probe_id)
    auth = base64.b64encode(f"{shop_id}:{secret_key}".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
            "Idempotence-Key": f"dokkomplekt-test-{probe_id}",
            "User-Agent": "Dokkomplekt-YooKassa-Test-Probe/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1200]
        raise RuntimeError(f"YooKassa TEST API HTTP {exc.code}: {detail}") from exc
    validate_probe_response(body, probe_id)
    return {
        "payment_id": body["id"],
        "status": body.get("status"),
        "amount": body.get("amount"),
        "probe_id": probe_id,
    }


def self_test() -> None:
    probe_id = "probe-test"
    payload = build_probe_payload(probe_id)
    assert payload["capture"] is False
    assert payload["amount"] == {"value": "1.00", "currency": "RUB"}
    validate_probe_response(
        {
            "id": "test-payment",
            "status": "pending",
            "paid": False,
            "amount": {"value": "1.00", "currency": "RUB"},
            "metadata": {"dokkomplekt_probe": probe_id, "environment": "test-only"},
        },
        probe_id,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("YooKassa TEST probe self-test: OK")
        return 0
    result = run_probe()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"YooKassa TEST probe failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
