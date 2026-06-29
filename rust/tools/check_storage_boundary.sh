#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

old_schema="crates/dokkomplekt-license-server/migrations/0001_license_server_schema.sql"
old_module="crates/dokkomplekt-license-server/src/storage_postgres.rs"
contract="crates/dokkomplekt-license-server/src/storage.rs"
pg_store="crates/dokkomplekt-license-server/src/storage/postgres.rs"

grep -qi "CREATE TABLE" "$old_schema" && { echo "old schema must stay empty" >&2; exit 1; }
grep -q "pub struct PostgresStore" "$old_module" && { echo "old storage module must stay empty" >&2; exit 1; }
grep -q "mod postgres" "$contract" || { echo "storage.rs must load storage/postgres.rs" >&2; exit 1; }
grep -q "0001_license_schema.sql" "$pg_store" || { echo "postgres storage must load canonical schema" >&2; exit 1; }

echo "storage boundary ok"
