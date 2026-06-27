-- Dokkomplekt license server schema.
-- This schema stores only commercial and activation data.
-- Patient documents, diagnoses, names and template contents must never be stored here.

CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY,
    plan TEXT NOT NULL,
    amount_rub BIGINT NOT NULL CHECK (amount_rub > 0),
    status TEXT NOT NULL,
    machine_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS payment_events (
    id UUID PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES orders(id),
    provider TEXT NOT NULL,
    provider_event_id TEXT NOT NULL,
    provider_payment_id TEXT,
    status TEXT NOT NULL,
    amount_rub BIGINT NOT NULL CHECK (amount_rub > 0),
    received_at TIMESTAMPTZ NOT NULL,
    UNIQUE(provider, provider_event_id)
);

CREATE TABLE IF NOT EXISTS licenses (
    id UUID PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES orders(id),
    license_id TEXT NOT NULL UNIQUE,
    document_json TEXT NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS license_machines (
    id UUID PRIMARY KEY,
    license_id TEXT NOT NULL REFERENCES licenses(license_id),
    machine_hash TEXT NOT NULL,
    activated_at TIMESTAMPTZ NOT NULL,
    deactivated_at TIMESTAMPTZ,
    UNIQUE(license_id, machine_hash)
);

CREATE TABLE IF NOT EXISTS audit_events (
    id UUID PRIMARY KEY,
    entity_id UUID NOT NULL,
    event_type TEXT NOT NULL,
    happened_at TIMESTAMPTZ NOT NULL,
    details_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_payment_events_order_id ON payment_events(order_id);
CREATE INDEX IF NOT EXISTS idx_license_machines_machine_hash ON license_machines(machine_hash);
CREATE INDEX IF NOT EXISTS idx_audit_events_entity_id ON audit_events(entity_id);
