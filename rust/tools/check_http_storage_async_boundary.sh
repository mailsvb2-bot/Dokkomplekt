#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

http_dir="crates/dokkomplekt-license-server/src/http"

if grep -R "LicenseStore" "$http_dir" --include='*.rs'; then
  echo "HTTP handlers must not import LicenseStore directly; use StoreBackend async facade" >&2
  exit 1
fi

for method in \
  create_order \
  get_order \
  update_order_status \
  create_activation \
  create_activation_for_order \
  record_payment_event \
  record_payment_event_for_order \
  store_license \
  audit
  do
  if grep -R "state\.store\.${method}(" "$http_dir" --include='*.rs'; then
    echo "HTTP handlers must not call blocking state.store.${method}; use ${method}_async where applicable" >&2
    exit 1
  fi
  if grep -R "\.store\.${method}(" "$http_dir" --include='*.rs'; then
    echo "HTTP handlers must not call blocking .store.${method}; use async facade" >&2
    exit 1
  fi
done

required_async_calls=(
  "create_order_async"
  "get_order_async"
  "record_payment_event_for_order_async"
  "create_activation_for_order_async"
  "store_license_async"
  "update_order_status_async"
)

for method in "${required_async_calls[@]}"; do
  if ! grep -R "${method}(" "$http_dir" --include='*.rs' >/dev/null; then
    echo "expected HTTP async facade method missing: ${method}" >&2
    exit 1
  fi
done

echo "http storage async boundary ok"
