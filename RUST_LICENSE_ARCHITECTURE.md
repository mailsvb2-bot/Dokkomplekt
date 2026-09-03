# Dokkomplekt Rust licensing architecture

## Goal

Move the commercial licensing and payment-access foundation out of Python into Rust without rewriting the medical document UI/generation workflow.

```text
Python app = UI, DOCX/DOCM workflow, doctor-owned templates, popups, generation.
Rust license core = signed license verification, machine binding, usage policy, clock guard.
Rust license server = orders, provider payments/callbacks, machine activation, license issuing boundary.
```

## Rules

- The desktop app must not contain payment-provider secrets.
- The desktop app must not contain the issuer seed used to produce license proofs.
- Patient documents, diagnoses, names and template contents must not be sent to the license server.
- Paid licenses must never get trial watermarks.
- Trial/demo access may watermark generated DOCX files.
- License checks must fail closed for paid access if the native core is missing or cannot verify a license.
- The medical workflow must remain doctor-owned and local-first.
- A provider callback is not payment proof by itself: external-provider payments must be verified server-to-server before an order becomes paid.

## Implemented

- Rust workspace with separate core/server/Python-binding crates.
- Core license payload, signed license models, canonical JSON and Ed25519 verification.
- Core access policy, usage ledger model, clock guard and watermark decision.
- Server order/status/activation/provider-callback routes and license issuer.
- Concrete PostgreSQL runtime storage with migrations for orders, payment events, licenses, machines and audit events.
- Atomic/idempotent payment-event persistence and activation-slot enforcement.
- Payment provider contracts and manual development adapter.
- Real YooKassa payment creation over the Payments API with Basic Auth and idempotence keys.
- SBP payments through YooKassa with `payment_method_data.type=sbp`.
- YooKassa notification handling that re-fetches the payment from YooKassa and verifies amount, order metadata, status and payment method before persistence.
- Server-side tariff authority: the desktop/client cannot choose a different paid amount.
- Native Python binding module `dokkomplekt_license_native`.
- Python product-access bridge with fail-closed paid access.
- Windows CI step that prebuilds and installs the native verifier into `.venv_build` before PyInstaller.
- Rust CI with strict `cargo fmt --all -- --check`, PostgreSQL migration validation, storage-boundary locks, `cargo test --workspace` and `cargo clippy --workspace --all-targets -- -D warnings`.
- Concrete bank-invoice provider with order-scoped invoice details and secret-protected, idempotent bank-transfer confirmation.
- Persistent license status/revocation in Memory and PostgreSQL plus a public minimal status endpoint and fail-closed administrative revoke endpoint.
- Desktop revocation cache with TTL/offline-grace semantics; cached revocation is always fail-closed.
- Product-access state v3 with a random integrity key, Windows DPAPI protection, redundant key copies, monotonic usage sequence, and lossless v2 migration.
- Manual YooKassa sandbox workflow that uses dedicated TEST secrets only and never production credentials.

## Production configuration

For a production license server, configure at least:

- `DOKKOMPLEKT_ENV=production`;
- `DATABASE_URL`;
- `DOKKOMPLEKT_LICENSE_ISSUER_KEY_B64`;
- `DOKKOMPLEKT_LICENSE_ISSUE_SECRET`;
- `DOKKOMPLEKT_PAYMENT_PROVIDER=yookassa`, `sbp` or `bank_invoice`;
- for YooKassa/SBP: `DOKKOMPLEKT_YOOKASSA_SHOP_ID` and `DOKKOMPLEKT_YOOKASSA_SECRET_KEY`;
- for bank invoice: the validated bank-requisite environment variables documented in `rust/README.md`;
- `DOKKOMPLEKT_LICENSE_PUBLIC_URL` pointing to the externally reachable HTTPS service.

The YooKassa webhook endpoint is `/api/provider/yookassa/callback` for both normal YooKassa and SBP mode. The generic `/api/provider/callback` is the manual/development path and cannot mark external-provider production orders as paid.

## Remaining operational work

No known repository-side commercial-license runtime item remains intentionally enabled-but-unimplemented. Production rollout still requires deployment-specific secrets/requisites, an externally reachable HTTPS license service, and a real YooKassa sandbox execution when dedicated test credentials are supplied. Those are environment/operations prerequisites rather than missing runtime code.

## Signature model

The license server signs a license payload. The desktop program stores only the public verification key and verifies the signed license locally.

If a user edits `document_limit_month`, `valid_until`, `allowed_machines`, `features`, `watermark_mode` or `plan`, signature verification must fail.
