use crate::canonical::canonical_json;
use crate::core_error::{CoreError, CoreResult};
use crate::models::LicensePayload;
use base64::{engine::general_purpose::STANDARD, Engine as _};
use ed25519_dalek::{Signature, Verifier, VerifyingKey};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PublicKeyBytes(pub [u8; 32]);

impl PublicKeyBytes {
    pub fn from_base64(input: &str) -> CoreResult<Self> {
        let decoded = STANDARD.decode(input).map_err(|_| CoreError::BadPublicKey)?;
        let bytes: [u8; 32] = decoded.try_into().map_err(|_| CoreError::BadPublicKey)?;
        Ok(Self(bytes))
    }
}

pub fn verify_license_signature(payload: &LicensePayload, signature_b64: &str, public_key: &PublicKeyBytes) -> CoreResult<()> {
    if signature_b64.trim().is_empty() {
        return Err(CoreError::MissingProof);
    }
    let message = canonical_json(payload)?;
    let signature_bytes = STANDARD.decode(signature_b64).map_err(|_| CoreError::BadProof)?;
    let signature = Signature::from_slice(&signature_bytes).map_err(|_| CoreError::BadProof)?;
    let verifying_key = VerifyingKey::from_bytes(&public_key.0).map_err(|_| CoreError::BadPublicKey)?;
    verifying_key.verify(&message, &signature).map_err(|_| CoreError::BadProof)
}
