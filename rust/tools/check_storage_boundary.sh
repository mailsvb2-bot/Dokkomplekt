#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

old_schema="crates/dokkomplekt-license-server/migrations/0001_license_server_schema.sql"
old_module="crates/dokkomplekt-license-server/src/storage_postgres.rs"
main_storage="crates/dokkomplekt-license-server/src/storage.rs"

if grep -qi "CREATE TABLE" "$old_schema"; then
  echo "old schema must stay table-free" >&2
  exit 1
fi

if grep -q "pub struct PostgresStore" "$old_module"; then
  echo "old storage module must stay code-free" >&2
  exit 1
fi

if ! grep -q "0001_license_schema.sql" "$main_storage"; then
  echo "canonical storage must embed canonical schema" >&2
  exit 1
fi

echo "storage boundary ok"
