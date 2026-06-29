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

## Implemented in this branch

- Rust workspace with separate core/server/Python-binding crates.
- Core license payload, signed license models, canonical JSON and Ed25519 verification.
- Core access policy, usage ledger model, clock guard and watermark decision.
- Server order/status/activation/provider-callback routes and license issuer.
- PostgreSQL schema boundary for orders, payment events, licenses, machines and audit events.
- Payment provider contracts and manual provider adapter.
- Native Python binding module `dokkomplekt_license_native`.
- Python product-access bridge with fail-closed paid access.
- Windows CI step that prebuilds and installs the native verifier into `.venv_build` before PyInstaller.
- Rust CI for `cargo test --workspace` and `cargo clippy --workspace --all-targets -D warnings`.

## Next implementation steps

1. Add real provider adapters: YooKassa/SBP/bank invoice.
2. Add concrete PostgreSQL runtime implementation behind the storage boundary.
3. Add activation-slot management and revocation cache.
4. Add signed local usage ledger.
5. Restore strict rustfmt check after connector-side formatting constraints are resolved.

## Signature model

The license server signs a license payload. The desktop program stores only the public verification key and verifies the signed license locally.

If a user edits `document_limit_month`, `valid_until`, `allowed_machines`, `features`, `watermark_mode` or `plan`, signature verification must fail.
