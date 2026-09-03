# Dokkomplekt Rust workspace

This workspace contains the commercial licensing core, the license server and the native verifier packaged into the desktop application.

## Crates

- `dokkomplekt-license-core` — deterministic signed-license verification and access policy.
- `dokkomplekt-license-server` — HTTP service for orders, YooKassa/SBP payments, provider callbacks, PostgreSQL persistence, machine activation and license issuing.
- `dokkomplekt-license-python` — PyO3 native verifier module packaged as `dokkomplekt_license_native`.

## Local checks

```bash
cd rust
cargo fmt --all
cargo test --workspace
cargo clippy --workspace --all-targets -- -D warnings
```

## Native verifier wheel

```bash
python -m pip install ./rust/crates/dokkomplekt-license-python
python -c "import dokkomplekt_license_native as n; print(n.native_core_version())"
```

The Windows EXE workflow installs this wheel into `.venv_build` before PyInstaller runs.

## License server

Development/manual mode can still be started locally for tests. A real production deployment must use PostgreSQL and a real payment provider.

Example YooKassa configuration:

```bash
cd rust
export DOKKOMPLEKT_ENV=production
export DOKKOMPLEKT_LICENSE_BIND=127.0.0.1:8787
export DOKKOMPLEKT_LICENSE_PUBLIC_URL=https://license.example.ru
export DATABASE_URL=postgres://user:password@127.0.0.1/dokkomplekt_license
export DOKKOMPLEKT_LICENSE_ISSUER_KEY_B64='...'
export DOKKOMPLEKT_LICENSE_ISSUE_SECRET='...'
export DOKKOMPLEKT_PAYMENT_PROVIDER=yookassa
export DOKKOMPLEKT_YOOKASSA_SHOP_ID='...'
export DOKKOMPLEKT_YOOKASSA_SECRET_KEY='...'
cargo run -p dokkomplekt-license-server
```

For SBP through YooKassa, set `DOKKOMPLEKT_PAYMENT_PROVIDER=sbp`. The server creates a YooKassa payment with the SBP payment method and returns the provider confirmation URL.

Configure YooKassa notifications to:

```text
https://license.example.ru/api/provider/yookassa/callback
```

The server does not trust the incoming notification as payment proof. It reads the payment back from YooKassa over authenticated server-to-server API and checks the internal `order_id`, amount, status and payment method before persisting the event.

For a bank-transfer invoice deployment, set `DOKKOMPLEKT_PAYMENT_PROVIDER=bank_invoice` and configure the validated invoice requisites required by `ServerConfig` (recipient, bank name, BIC, settlement account and tax identifiers). The order response points to `/api/orders/{order_id}/invoice`; payment confirmation is accepted only through the secret-protected bank-invoice confirmation endpoint and is persisted through the same atomic payment-event owner as other providers.

The desktop may set `DOKKOMPLEKT_LICENSE_SERVER_URL=https://license.example.ru` to refresh `/api/licenses/{license_id}/status`. A cached `revoked` result always blocks the license. A previously confirmed active license may continue through its configured offline grace if the status service is temporarily unavailable; after TTL+grace it fails closed until status can be refreshed.

Local product-access counters use state format v3. The integrity key is random instead of being derivable from the machine fingerprint, is protected with Windows DPAPI in production, and is stored redundantly so a single damaged key copy can be recovered without resetting usage. Existing v2 counters migrate without resetting limits.

The manual `YooKassa Sandbox` workflow reads only dedicated TEST secrets (`DOKKOMPLEKT_YOOKASSA_TEST_SHOP_ID` and `DOKKOMPLEKT_YOOKASSA_TEST_SECRET_KEY`) and is intentionally not part of ordinary CI.

## Integration principle

Python remains responsible for the existing local doctor workflow. Rust owns license proof verification, commercial access decisions, payment/order state and machine activation. Patient documents and template contents do not belong in the license-server boundary.
