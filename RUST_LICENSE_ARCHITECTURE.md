# Dokkomplekt Rust licensing architecture

## Goal

Move the commercial licensing and payment-access foundation out of Python into Rust without rewriting the medical document UI/generation workflow.

```text
Python app = UI, DOCX/DOCM workflow, doctor-owned templates, popups, generation.
Rust license core = signed license verification, machine binding, usage policy, clock guard.
Rust license server = orders, provider callbacks, machine activation, license issuing boundary.
```

## Rules

- The desktop app must not contain payment-provider secrets.
- The desktop app must not contain the issuer seed used to produce license proofs.
- Patient documents, diagnoses, names and template contents must not be sent to the license server.
- Paid licenses must never get trial watermarks.
- Trial/demo access may watermark generated DOCX files.
- License checks must fail closed for paid access if the native core is missing or cannot verify a license.
- The medical workflow must remain doctor-owned and local-first.

## Rust workspace

```text
rust/
  Cargo.toml
  crates/
    dokkomplekt-license-core/
    dokkomplekt-license-server/
```

## Core crate responsibilities

`dokkomplekt-license-core` has no HTTP, payment, Tkinter, DOCX or filesystem UI code.

It owns:

- canonical JSON for signed payloads;
- Ed25519 public-key verification;
- machine fingerprint comparison;
- plan and limit policy;
- trial/demo watermark decision;
- clock rollback guard;
- usage ledger model.

## Server crate responsibilities

`dokkomplekt-license-server` owns online commercial operations:

- order creation;
- QR/payment URL handoff;
- provider callback boundary;
- order status;
- machine activation;
- license issuing from paid orders.

## Implemented in this branch

- Rust workspace with separate core/server crates.
- Core license payload and signed license models.
- Core canonical JSON and Ed25519 proof verification.
- Core access policy and watermark decision.
- Server health/order/status/activation/provider-callback routes.
- Server issuer that produces a signed `license.json` document when an order is paid.
- Rust CI for `cargo test --workspace` and `cargo clippy --workspace --all-targets -D warnings`.

## Next implementation steps

1. Add PostgreSQL tables for orders, provider events, licenses, machines and audit log.
2. Add provider adapters: YooKassa/SBP/bank invoice.
3. Add PyO3 binding crate for desktop Python integration.
4. Replace Python HMAC verification with Rust Ed25519 verification.
5. Add desktop fallback rule: if Rust core is missing, paid access is denied but profile export remains available.
6. Restore strict rustfmt check after connector-side formatting constraints are resolved.

## Signature model

The license server signs a license payload. The desktop program stores only the public verification key and verifies the signed license locally.

If a user edits `document_limit_month`, `valid_until`, `allowed_machines`, `features`, `watermark_mode` or `plan`, signature verification must fail.
