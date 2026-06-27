//! Rust licensing core for Dokkomplekt.
//!
//! This crate contains no HTTP, payment provider, UI or patient-document code.
//! It is the deterministic local verifier: signed license in, machine/usage
//! facts in, access decision out.

pub mod canonical;
pub mod clock;
pub mod crypto;
pub mod error;
pub mod machine;
pub mod models;
pub mod policy;
pub mod usage;

pub use clock::{ClockGuard, ClockState};
pub use crypto::{verify_license_signature, PublicKeyBytes};
pub use error::{LicenseCoreError, LicenseCoreResult};
pub use machine::{MachineFingerprint, MachineFacts};
pub use models::{Feature, LicenseDocument, LicensePayload, PlanId, SignedLicense};
pub use policy::{AccessDecision, AccessRequest, AccessStatus, evaluate_access};
pub use usage::{UsageCounter, UsageLedger};
