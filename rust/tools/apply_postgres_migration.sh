#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required" >&2
  exit 2
fi

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f crates/dokkomplekt-license-server/migrations/0001_license_schema.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name IN ('license_orders','billing_events','license_documents','license_machines','license_audit_events');"
