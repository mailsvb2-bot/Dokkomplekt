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
- The desktop app must not contain the private signing key.
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
- future license issuing with the private signing key.

## Next implementation steps

1. Add Ed25519 signing to the server-side issuer module.
2. Add persistent storage: PostgreSQL tables for orders, provider events, licenses, machines and audit log.
3. Add provider adapters: YooKassa/SBP/bank invoice.
4. Add PyO3 binding crate for desktop Python integration.
5. Replace Python HMAC verification with Rust Ed25519 verification.
6. Add CI job: `cargo fmt`, `cargo clippy`, `cargo test` for `rust/`.
7. Add desktop fallback rule: if Rust core is missing, paid access is denied but profile export remains available.

## Signature model

The license server signs a license payload with a private key. The desktop program stores only the public key and verifies the signed license locally.

If a user edits `document_limit_month`, `valid_until`, `allowed_machines`, `features`, `watermark_mode` or `plan`, signature verification must fail.
