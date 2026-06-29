# Dokkomplekt Rust workspace

This workspace is the new foundation for commercial licensing and the license server.

## Crates

- `dokkomplekt-license-core` — pure deterministic license verification and access policy.
- `dokkomplekt-license-server` — HTTP service boundary for orders, provider callbacks and machine activation.
- `dokkomplekt-license-python` — PyO3 native verifier module packaged as `dokkomplekt_license_native`.

## Local commands

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

## Runtime server command

```bash
cd rust
DOKKOMPLEKT_LICENSE_BIND=127.0.0.1:8787 cargo run -p dokkomplekt-license-server
```

## Integration principle

Python remains responsible for the existing doctor workflow. Rust owns license proof verification and commercial access decisions.
