pub mod canonical;
pub mod clock;
pub mod core_error;
pub mod crypto;
pub mod machine;
pub mod models;
pub mod policy;
pub mod usage;

pub use clock::{ClockGuard, ClockState};
pub use core_error::{CoreError, CoreResult};
pub use crypto::{verify_license_signature, PublicKeyBytes};
pub use machine::{MachineFacts, MachineFingerprint};
pub use models::{Feature, LicenseDocument, LicensePayload, PlanId, SignedLicense};
pub use policy::{evaluate_access, AccessDecision, AccessRequest, AccessStatus};
pub use usage::{UsageCounter, UsageLedger};
